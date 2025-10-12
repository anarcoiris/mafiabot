"""
gui/views/lobby_view.py
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
        self.colors = colors
        
        self.configure(style='TFrame')
        
        # Crear interfaz
        self._create_widgets()
        
        # Registrar callback para actualizaciones
        self.controller.on_game_update = self.refresh
        
        logger.info("LobbyView initialized")
    
    def _create_widgets(self):
        """Crea todos los widgets de la vista."""
        
        # ====================================================================
        # HEADER
        # ====================================================================
        header = ttk.Frame(self)
        header.pack(fill=tk.X, padx=20, pady=20)
        
        title = ttk.Label(
            header,
            text="🎭 Mafia - Lobby",
            font=('Arial', 24, 'bold')
        )
        title.pack()
        
        subtitle = ttk.Label(
            header,
            text="Configura la partida y agrega jugadores",
            font=('Arial', 12)
        )
        subtitle.pack()
        
        # ====================================================================
        # MAIN CONTAINER (2 columnas)
        # ====================================================================
        main = ttk.Frame(self)
        main.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        # Columna izquierda: Jugadores
        left_frame = ttk.LabelFrame(main, text="Jugadores", padding=10)
        left_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        
        # Columna derecha: Configuración
        right_frame = ttk.LabelFrame(main, text="Configuración", padding=10)
        right_frame.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        
        main.columnconfigure(0, weight=1)
        main.columnconfigure(1, weight=1)
        main.rowconfigure(0, weight=1)
        
        self._create_players_panel(left_frame)
        self._create_config_panel(right_frame)
        
        # ====================================================================
        # FOOTER (botones de acción)
        # ====================================================================
        footer = ttk.Frame(self)
        footer.pack(fill=tk.X, padx=20, pady=20)
        
        self.start_button = ttk.Button(
            footer,
            text="▶️ Iniciar Partida",
            command=self._on_start_game,
            style='Accent.TButton'
        )
        self.start_button.pack(side=tk.RIGHT, padx=5)
        
        reset_button = ttk.Button(
            footer,
            text="🔄 Reiniciar",
            command=self._on_reset
        )
        reset_button.pack(side=tk.RIGHT, padx=5)
    
    def _create_players_panel(self, parent):
        """Panel de lista de jugadores."""
        
        # Listbox de jugadores
        list_frame = ttk.Frame(parent)
        list_frame.pack(fill=tk.BOTH, expand=True)
        
        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.players_listbox = tk.Listbox(
            list_frame,
            yscrollcommand=scrollbar.set,
            font=('Arial', 11),
            height=15
        )
        self.players_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.players_listbox.yview)
        
        # Controles para agregar/quitar jugadores
        controls = ttk.Frame(parent)
        controls.pack(fill=tk.X, pady=(10, 0))
        
        self.player_name_var = tk.StringVar()
        name_entry = ttk.Entry(
            controls,
            textvariable=self.player_name_var,
            font=('Arial', 10)
        )
        name_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        name_entry.bind('<Return>', lambda e: self._on_add_player())
        
        add_button = ttk.Button(
            controls,
            text="➕ Agregar",
            command=self._on_add_player,
            width=10
        )
        add_button.pack(side=tk.LEFT, padx=2)
        
        remove_button = ttk.Button(
            controls,
            text="➖ Quitar",
            command=self._on_remove_player,
            width=10
        )
        remove_button.pack(side=tk.LEFT, padx=2)
        
        # Botón de jugadores de prueba
        test_button = ttk.Button(
            controls,
            text="🎲 Test (8)",
            command=self._add_test_players,
            width=10
        )
        test_button.pack(side=tk.LEFT, padx=2)
    
    def _create_config_panel(self, parent):
        """Panel de configuración de roles."""
        
        info_frame = ttk.Frame(parent)
        info_frame.pack(fill=tk.X, pady=(0, 10))
        
        info_label = ttk.Label(
            info_frame,
            text="Configura cuántos jugadores de cada rol habrá:",
            font=('Arial', 10),
            wraplength=300,
            justify=tk.LEFT
        )
        info_label.pack(anchor=tk.W)
        
        # Frame con scroll para configuración de roles
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
        
        # Crear controles para cada rol
        self.role_vars = {}
        
        from core.roles import Faction, get_roles_by_faction
        
        for faction in [Faction.TOWN, Faction.MAFIA, Faction.NEUTRAL]:
            # Separador de facción
            faction_label = ttk.Label(
                self.roles_config_frame,
                text=faction.value.upper(),
                font=('Arial', 11, 'bold')
            )
            faction_label.pack(anchor=tk.W, pady=(10, 5))
            
            # Roles de esta facción
            roles = get_roles_by_faction(faction)
            for role_key, role in sorted(roles.items(), key=lambda x: x[1].name):
                self._create_role_control(role_key, role.name)
        
        # Botones de configuración rápida
        quick_config = ttk.Frame(parent)
        quick_config.pack(fill=tk.X, pady=(10, 0))
        
        ttk.Label(quick_config, text="Config rápida:").pack(side=tk.LEFT, padx=(0, 5))
        
        for num in [4, 6, 8, 10]:
            btn = ttk.Button(
                quick_config,
                text=f"{num}J",
                command=lambda n=num: self._apply_recommended_config(n),
                width=5
            )
            btn.pack(side=tk.LEFT, padx=2)
    
    def _create_role_control(self, role_key: str, role_name: str):
        """Crea un control para configurar la cantidad de un rol."""
        frame = ttk.Frame(self.roles_config_frame)
        frame.pack(fill=tk.X, pady=2)
        
        label = ttk.Label(frame, text=role_name, width=20)
        label.pack(side=tk.LEFT)
        
        var = tk.IntVar(value=0)
        self.role_vars[role_key] = var
        
        spinbox = ttk.Spinbox(
            frame,
            from_=0,
            to=10,
            textvariable=var,
            width=5
        )
        spinbox.pack(side=tk.RIGHT)
    
    # ========================================================================
    # EVENT HANDLERS
    # ========================================================================
    
    def _on_add_player(self):
        """Agrega un nuevo jugador."""
        name = self.player_name_var.get().strip()
        
        if not name:
            messagebox.showwarning("Nombre vacío", "Escribe un nombre para el jugador")
            return
        
        # Crear partida si no existe
        if not self.controller.game:
            self.controller.create_game(host_name=name)
            self.player_name_var.set("")
            self.refresh()
            return
        
        # Agregar jugador
        success = self.controller.add_player(name)
        
        if success:
            self.player_name_var.set("")
            self.refresh()
        else:
            messagebox.showerror("Error", "No se pudo agregar el jugador")
    
    def _on_remove_player(self):
        """Elimina el jugador seleccionado."""
        selection = self.players_listbox.curselection()
        if not selection:
            messagebox.showinfo("Sin selección", "Selecciona un jugador para quitar")
            return
        
        index = selection[0]
        if not self.controller.game:
            return
        
        # Obtener user_id del jugador en esa posición
        players_list = list(self.controller.game.players.values())
        if index < len(players_list):
            player = players_list[index]
            
            if player.user_id == self.controller.game.host_id:
                messagebox.showwarning("No permitido", "No puedes eliminar al host")
                return
            
            success = self.controller.remove_player(player.user_id)
            if success:
                self.refresh()
    
    def _on_reset(self):
        """Reinicia la partida."""
        if not self.controller.game:
            return
        
        if messagebox.askyesno("Confirmar", "¿Reiniciar la partida y perder toda la configuración?"):
            self.controller.reset_game()
            self.refresh()
    
    def _on_start_game(self):
        """Inicia la partida."""
        if not self.controller.game:
            messagebox.showwarning("Sin partida", "Primero agrega jugadores")
            return
        
        # Aplicar configuración de roles
        self._apply_roles_config()
        
        # Intentar iniciar
        errors = self.controller.start_game()
        
        if errors:
            messagebox.showerror("No se puede iniciar", "\n".join(errors))
            return
        
        # Cambiar a vista de juego
        self.controller.app.show_game(self.controller.game)
    
    def _add_test_players(self):
        """Agrega 8 jugadores de prueba."""
        test_names = [
            "Alice", "Bob", "Charlie", "Diana",
            "Eve", "Frank", "Grace", "Henry"
        ]
        
        # Crear partida si no existe
        if not self.controller.game:
            self.controller.create_game(host_name=test_names[0])
            test_names = test_names[1:]
        
        # Agregar el resto
        for name in test_names:
            if len(self.controller.game.players) >= 8:
                break
            self.controller.add_player(name)
        
        # Aplicar configuración recomendada para 8 jugadores
        self._apply_recommended_config(8)
        
        self.refresh()
        messagebox.showinfo("Listo", "Se agregaron jugadores de prueba")
    
    def _apply_recommended_config(self, num_players: int):
        """Aplica una configuración recomendada para N jugadores."""
        config = get_recommended_config(num_players)
        
        # Resetear todos a 0
        for var in self.role_vars.values():
            var.set(0)
        
        # Aplicar configuración recomendada
        for role_key, count in config.items():
            if role_key in self.role_vars:
                self.role_vars[role_key].set(count)
        
        logger.info(f"Applied recommended config for {num_players} players")
    
    def _apply_roles_config(self):
        """Aplica la configuración de roles al juego."""
        if not self.controller.game:
            return
        
        config = {}
        for role_key, var in self.role_vars.items():
            count = var.get()
            if count > 0:
                config[role_key] = count
        
        if not config:
            # Si no hay configuración, usar default
            config = {"mafia": 1, "ciudadano": len(self.controller.game.players) - 1}
        
        self.controller.game.roles_config = config
        logger.info(f"Roles config applied: {config}")
    
    # ========================================================================
    # REFRESH
    # ========================================================================
    
    def refresh(self):
        """Actualiza la vista con el estado actual."""
        if not self.controller.game:
            self.players_listbox.delete(0, tk.END)
            self.start_button.config(state=tk.DISABLED)
            return
        
        # Actualizar lista de jugadores
        self.players_listbox.delete(0, tk.END)
        for player in self.controller.game.players.values():
            icon = "👑" if player.user_id == self.controller.game.host_id else "👤"
            self.players_listbox.insert(tk.END, f"{icon} {player.name}")
        
        # Habilitar/deshabilitar botón de inicio
        can_start = len(self.controller.game.players) >= 4
        self.start_button.config(state=tk.NORMAL if can_start else tk.DISABLED)
