# gui/views/lobby_view.py
"""
Vista de lobby/sala de espera.
"""
import tkinter as tk
from tkinter import ttk, messagebox
import logging

from core.roles import ROLES, get_recommended_config

logger = logging.getLogger(__name__)


class LobbyView(ttk.Frame):
    """Vista de lobby donde se configuran jugadores y roles antes de empezar."""

    def __init__(self, parent, controller, colors):
        super().__init__(parent)
        self.controller = controller
        # Asegurar que controller tiene player_types
        if not hasattr(self.controller, "player_types"):
            self.controller.player_types = {}
        # Mantener referencia compartida (source of truth en controller)
        self.player_types = self.controller.player_types

        # Mapeo índice -> player_id para la listbox (reconstruido en refresh)
        self._player_index_map = []
        self.colors = colors or {}

        self.configure(style="TFrame")

        # Crear interfaz
        self._create_widgets()

        # Registrar callback para actualizaciones (guardar prev por si hace falta)
        self._prev_on_game_update = getattr(self.controller, "on_game_update", None)
        self.controller.on_game_update = self.refresh

        logger.info("LobbyView initialized")

    def _create_widgets(self):
        """Crea todos los widgets de la vista."""

        # HEADER
        header = ttk.Frame(self)
        header.pack(fill=tk.X, padx=20, pady=20)

        title = ttk.Label(header, text="🎭 Mafia - Lobby", font=("Arial", 24, "bold"))
        title.pack()

        subtitle = ttk.Label(header, text="Configura la partida y agrega jugadores", font=("Arial", 12))
        subtitle.pack()

        # MAIN CONTAINER (2 columnas)
        main = ttk.Frame(self)
        main.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)

        left_frame = ttk.LabelFrame(main, text="Jugadores", padding=10)
        left_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 10))

        right_frame = ttk.LabelFrame(main, text="Configuración", padding=10)
        right_frame.grid(row=0, column=1, sticky="nsew", padx=(10, 0))

        main.columnconfigure(0, weight=1)
        main.columnconfigure(1, weight=1)
        main.rowconfigure(0, weight=1)

        self._create_players_panel(left_frame)
        self._create_config_panel(right_frame)

        # FOOTER (botones)
        footer = ttk.Frame(self)
        footer.pack(fill=tk.X, padx=20, pady=20)

        self.start_button = ttk.Button(
            footer,
            text="▶️ Iniciar Partida",
            command=self._on_start_game,
            style="Accent.TButton"
        )
        self.start_button.pack(side=tk.RIGHT, padx=5)

        reset_button = ttk.Button(footer, text="🔄 Reiniciar", command=self._on_reset)
        reset_button.pack(side=tk.RIGHT, padx=5)

    def _create_players_panel(self, parent):
        """Panel de lista de jugadores."""

        list_frame = ttk.Frame(parent)
        list_frame.pack(fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Listbox con colores respetando tema (evita texto blanco sobre blanco)
        bg = self.colors.get("bg", None)
        fg = self.colors.get("fg", None)
        selectbg = self.colors.get("accent", None)

        self.players_listbox = tk.Listbox(
            list_frame,
            yscrollcommand=scrollbar.set,
            font=("Arial", 11),
            height=15,
            bg=bg if bg else None,
            fg=fg if fg else None,
            selectbackground=selectbg if selectbg else None
        )
        self.players_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.players_listbox.yview)

        # Treeview (opcional, informativo). Usamos `iid` con player_id para operaciones futuras.
        self.players_tree = ttk.Treeview(
            list_frame,
            columns=("tipo",),
            height=12,
            selectmode="browse"
        )
        self.players_tree.heading("#0", text="Jugador")
        self.players_tree.heading("tipo", text="Tipo")
        self.players_tree.column("tipo", width=100)
        self.players_tree.pack(fill=tk.BOTH, expand=True)

        # Controles agregar/quitar
        controls = ttk.Frame(parent)
        controls.pack(fill=tk.X, pady=(10, 0))

        self.player_name_var = tk.StringVar()
        name_entry = ttk.Entry(controls, textvariable=self.player_name_var, font=("Arial", 10))
        name_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        name_entry.bind("<Return>", lambda e: self._on_add_player())

        add_button = ttk.Button(controls, text="➕ Agregar", command=self._on_add_player, width=10)
        add_button.pack(side=tk.LEFT, padx=2)

        remove_button = ttk.Button(controls, text="➖ Quitar", command=self._on_remove_player, width=10)
        remove_button.pack(side=tk.LEFT, padx=2)

        test_button = ttk.Button(controls, text="🎲 Test (8)", command=self._add_test_players, width=10)
        test_button.pack(side=tk.LEFT, padx=2)

        type_combo = ttk.Combobox(
            controls,
            values=["Humano", "Bot Fácil", "Bot Normal", "Bot Difícil"],
            state="readonly",
            width=15
        )
        type_combo.pack(side=tk.LEFT, padx=2)

        change_type_btn = ttk.Button(
            controls,
            text="📋 Cambiar Tipo",
            command=lambda: self._on_change_player_type(type_combo),
            width=12
        )
        change_type_btn.pack(side=tk.LEFT, padx=2)

    def _create_config_panel(self, parent):
        """Panel de configuración de roles."""

        info_frame = ttk.Frame(parent)
        info_frame.pack(fill=tk.X, pady=(0, 10))

        info_label = ttk.Label(
            info_frame,
            text="Configura cuántos jugadores de cada rol habrá:",
            font=("Arial", 10),
            wraplength=300,
            justify=tk.LEFT
        )
        info_label.pack(anchor=tk.W)

        canvas_frame = ttk.Frame(parent)
        canvas_frame.pack(fill=tk.BOTH, expand=True)

        canvas = tk.Canvas(canvas_frame, height=300)
        scrollbar = ttk.Scrollbar(canvas_frame, orient="vertical", command=canvas.yview)
        self.roles_config_frame = ttk.Frame(canvas)

        self.roles_config_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=self.roles_config_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.role_vars = {}

        from core.roles import Faction, get_roles_by_faction

        for faction in [Faction.TOWN, Faction.MAFIA, Faction.NEUTRAL]:
            faction_label = ttk.Label(self.roles_config_frame, text=faction.value.upper(), font=("Arial", 11, "bold"))
            faction_label.pack(anchor=tk.W, pady=(10, 5))

            roles = get_roles_by_faction(faction)
            for role_key, role in sorted(roles.items(), key=lambda x: x[1].name):
                self._create_role_control(role_key, role.name)

        quick_config = ttk.Frame(parent)
        quick_config.pack(fill=tk.X, pady=(10, 0))

        ttk.Label(quick_config, text="Config rápida:").pack(side=tk.LEFT, padx=(0, 5))

        for num in [4, 6, 8, 10]:
            btn = ttk.Button(quick_config, text=f"{num}J", command=lambda n=num: self._apply_recommended_config(n), width=5)
            btn.pack(side=tk.LEFT, padx=2)

    def _create_role_control(self, role_key: str, role_name: str):
        frame = ttk.Frame(self.roles_config_frame)
        frame.pack(fill=tk.X, pady=2)

        label = ttk.Label(frame, text=role_name, width=20)
        label.pack(side=tk.LEFT)

        var = tk.IntVar(value=0)
        self.role_vars[role_key] = var

        spinbox = ttk.Spinbox(frame, from_=0, to=10, textvariable=var, width=5)
        spinbox.pack(side=tk.RIGHT)

    # EVENT HANDLERS
    def _on_add_player(self):
        name = self.player_name_var.get().strip()
        if not name:
            messagebox.showwarning("Nombre vacío", "Escribe un nombre para el jugador")
            return

        if not self.controller.game:
            self.controller.create_game(host_name=name)
            self.player_name_var.set("")
            self.refresh()
            return

        success = self.controller.add_player(name)
        if success:
            self.player_name_var.set("")
            self.refresh()
        else:
            messagebox.showerror("Error", "No se pudo agregar el jugador")

    def _on_remove_player(self):
        selection = self.players_listbox.curselection()
        if not selection:
            messagebox.showinfo("Sin selección", "Selecciona un jugador para quitar")
            return

        index = selection[0]
        if not self.controller.game:
            return

        # Mapear índice a player_id
        if index < len(self._player_index_map):
            player_id = self._player_index_map[index]
            player = self.controller.game.players.get(player_id)
            if not player:
                return

            if player.user_id == self.controller.game.host_id:
                messagebox.showwarning("No permitido", "No puedes eliminar al host")
                return

            success = self.controller.remove_player(player.user_id)
            if success:
                self.refresh()

    def _on_change_player_type(self, combo_widget):
        """Cambia el tipo del jugador seleccionado."""
        try:
            selection = combo_widget.get() if hasattr(combo_widget, "get") else str(combo_widget)
            map_display_to_key = {
                "Humano": "human",
                "Bot Fácil": "bot_easy",
                "Bot Normal": "bot_normal",
                "Bot Difícil": "bot_hard",
                "human": "human",
                "bot_easy": "bot_easy",
                "bot_normal": "bot_normal",
                "bot_hard": "bot_hard",
            }
            key = map_display_to_key.get(selection, "human")

            sel = self.players_listbox.curselection()
            if not sel:
                messagebox.showinfo("Sin selección", "Selecciona un jugador primero")
                return
            index = sel[0]
            if index >= len(self._player_index_map):
                logger.warning("Índice seleccionado fuera de rango del mapa de jugadores")
                return
            player_id = self._player_index_map[index]

            # actualizar dict en controller (source of truth)
            self.controller.player_types[player_id] = key
            self.player_types = self.controller.player_types

            # si es bot, (re)crear en controller; pasamos la key ("bot_*") que espera GUIGameController
            if key.startswith("bot") and hasattr(self.controller, "create_bot_player"):
                player = self.controller.game.players.get(player_id)
                if player:
                    try:
                        self.controller.create_bot_player(player_id, player.name, key)
                    except Exception:
                        logger.exception("Error creando bot en controller")

            # refrescar UI
            self.refresh()
            logger.info("Changed player %s type to %s", player_id, key)
        except Exception:
            logger.exception("Error in _on_change_player_type")

    def _on_reset(self):
        if not self.controller.game:
            return
        if messagebox.askyesno("Confirmar", "¿Reiniciar la partida y perder toda la configuración?"):
            self.controller.reset_game()
            self.refresh()

    def _on_start_game(self):
        """Inicia la partida con mejor flujo - MEJORADO."""
        if not self.controller.game:
            messagebox.showwarning("Sin partida", "Primero agrega jugadores")
            return

        # Aplicar configuración de roles
        self._apply_roles_config()

        # Recolectar tipos de jugadores
        player_types = {}
        for player_id, player in self.controller.game.players.items():
            player_types[player_id] = self.controller.player_types.get(player_id, "human")
        self.controller.player_types = player_types

        # Validar configuración
        errors = self.controller.start_game()
        if errors:
            messagebox.showerror("No se puede iniciar", "\n".join(errors))
            return

        # Mostrar vista de juego
        if hasattr(self.controller, "app") and getattr(self.controller.app, "show_game", None):
            self.controller.app.show_game(self.controller.game)

        # NUEVO: Preguntar si abrir ventanas de perspectiva
        human_count = sum(1 for t in player_types.values() if t == "human")

        if human_count > 0:
            response = messagebox.askyesno(
                "Ventanas de Perspectiva",
                f"¿Abrir ventanas de perspectiva para los {human_count} jugador(es) humano(s)?\n\n"
                "Esto te permitirá controlar cada jugador desde su propia ventana.",
                icon='question'
            )

            if response and hasattr(self.controller.app, 'open_all_perspective_windows'):
                # Usar after para dar tiempo a que la vista de juego se renderice
                self.controller.app.root.after(500, self.controller.app.open_all_perspective_windows)

        # Log informativo
        logger.info(f"Game started: {human_count} humans, {len(player_types) - human_count} bots")

    def _add_test_players(self):
        """Agrega jugadores de prueba con configuración automática - MEJORADO."""
        test_names = ["Alice", "Bob", "Charlie", "Diana", "Eve", "Frank", "Grace", "Henry"]

        if not self.controller.game:
            self.controller.create_game(host_name=test_names[0])
            test_names = test_names[1:]

        # Agregar jugadores
        for name in test_names:
            if len(self.controller.game.players) >= 8:
                break
            self.controller.add_player(name)

        # Configurar tipos: primer jugador humano, resto bots
        player_ids = list(self.controller.game.players.keys())

        # Host humano
        if player_ids:
            self.controller.player_types[player_ids[0]] = "human"

        # Resto bots con dificultades variadas
        bot_difficulties = ["bot_easy", "bot_normal", "bot_hard"]
        for i, player_id in enumerate(player_ids[1:], start=1):
            difficulty = bot_difficulties[i % len(bot_difficulties)]
            self.controller.player_types[player_id] = difficulty
            # Crear el bot
            player = self.controller.game.players[player_id]
            self.controller.create_bot_player(player_id, player.name, difficulty)

        # Aplicar config recomendada
        self._apply_recommended_config(len(self.controller.game.players))

        # Refrescar vista
        self.refresh()

        messagebox.showinfo(
            "Listo",
            f"Se agregaron {len(player_ids)} jugadores de prueba:\n"
            f"- 1 humano (host)\n"
            f"- {len(player_ids)-1} bots (variados)"
        )

    def _apply_recommended_config(self, num_players: int):
        config = get_recommended_config(num_players)
        for var in self.role_vars.values():
            var.set(0)
        for role_key, count in config.items():
            if role_key in self.role_vars:
                self.role_vars[role_key].set(count)
        logger.info(f"Applied recommended config for {num_players} players")

    def _apply_roles_config(self):
        if not self.controller.game:
            return
        config = {}
        for role_key, var in self.role_vars.items():
            count = var.get()
            if count > 0:
                config[role_key] = count
        if not config:
            config = {"mafia": 1, "ciudadano": len(self.controller.game.players) - 1}
        self.controller.game.roles_config = config
        logger.info(f"Roles config applied: {config}")

    # REFRESH
    def refresh(self):
        """Actualiza la vista con el estado actual - PROTEGIDO."""
        # CRÍTICO: Verificar que el widget todavía existe antes de actualizar
        try:
            if not self.winfo_exists():
                return
        except Exception:
            # El widget fue destruido
            return

        if not self.controller.game:
            try:
                self.players_listbox.delete(0, tk.END)
                self.start_button.config(state=tk.DISABLED)
            except Exception:
                # Widgets ya destruidos, ignorar
                pass
            return

        # Actualizar listbox
        try:
            self.players_listbox.delete(0, tk.END)
            self._player_index_map = []
            for player in self.controller.game.players.values():
                icon = "👑" if player.user_id == self.controller.game.host_id else "👤"
                self.players_listbox.insert(tk.END, f"{icon} {player.name}")
                self._player_index_map.append(player.user_id)
        except Exception:
            # Listbox ya destruido, ignorar
            pass

        # Sincronizar treeview
        try:
            for item in self.players_tree.get_children():
                self.players_tree.delete(item)
            for player in self.controller.game.players.values():
                tipo = self.controller.player_types.get(player.user_id, "human")
                display_tipo = {
                    "human": "Humano",
                    "bot_easy": "Bot Fácil",
                    "bot_normal": "Bot Normal",
                    "bot_hard": "Bot Difícil"
                }.get(tipo, "Humano")
                self.players_tree.insert("", tk.END, iid=str(player.user_id), text=player.name, values=(display_tipo,))
        except Exception:
            # Treeview ya destruido, ignorar
            pass

        # Actualizar botón
        try:
            can_start = len(self.controller.game.players) >= 4
            self.start_button.config(state=tk.NORMAL if can_start else tk.DISABLED)
        except Exception:
            # Botón ya destruido, ignorar
            pass

    def destroy(self):
        """Override destroy para limpiar callbacks."""
        # Restaurar callback original del controller
        try:
            if self._prev_on_game_update is not None:
                self.controller.on_game_update = self._prev_on_game_update
            else:
                # Si no había callback previo, poner None
                self.controller.on_game_update = None
        except Exception:
            logger.exception("Error restoring on_game_update callback")

        # Llamar al destroy del padre
        super().destroy()
