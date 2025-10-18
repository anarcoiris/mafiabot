"""
gui/views/perspective_window.py - NUEVO
Ventana individual para la perspectiva de cada jugador.
"""
import tkinter as tk
from tkinter import ttk, messagebox
import logging
from typing import Optional

from core.models import Phase, Player
from core.roles import get_role
from gui.widgets.chat_widget import ChatWidget

logger = logging.getLogger(__name__)


class PerspectiveWindow:
    """Ventana de perspectiva individual para un jugador."""

    def __init__(self, controller, player_id: int, colors: dict):
        self.controller = controller
        self.player_id = player_id
        self.colors = colors
        self.perspective = controller.get_player_perspective(player_id)
        
        if not self.perspective:
            logger.error(f"No perspective found for player {player_id}")
            return

        self.player = self.perspective.player
        if not self.player:
            logger.error(f"No player found for id {player_id}")
            return

        # Crear ventana Toplevel
        self.window = tk.Toplevel()
        self.window.title(f"🎭 Mafia - {self.player.name}")
        self.window.geometry("800x600")
        self.window.configure(bg=colors.get('bg', '#2b2b2b'))

        # Estado
        self.selected_target_id: Optional[int] = None
        
        # Crear interfaz
        self._create_widgets()
        
        # Registrar para actualizaciones
        self._setup_callbacks()

        # Actualizar canales de chat según rol
        self._update_chat_channels()

        logger.info(f"Perspective window opened for {self.player.name}")

    def _create_widgets(self):
        """Crea la interfaz de la ventana."""
        
        # Header con info del jugador
        header = ttk.Frame(self.window)
        header.pack(fill=tk.X, padx=10, pady=10)

        player_label = ttk.Label(
            header,
            text=f"👤 {self.player.name}",
            font=('Arial', 16, 'bold')
        )
        player_label.pack(side=tk.LEFT)

        # Mostrar rol si está asignado
        if self.player.role_key:
            role = get_role(self.player.role_key)
            if role:
                role_label = ttk.Label(
                    header,
                    text=f"🎭 {role.name}",
                    font=('Arial', 14),
                    foreground='blue'
                )
                role_label.pack(side=tk.LEFT, padx=20)

        # Estado del jugador
        self.status_label = ttk.Label(
            header,
            text=self._get_status_text(),
            font=('Arial', 12)
        )
        self.status_label.pack(side=tk.RIGHT)

        # Separador
        ttk.Separator(self.window, orient='horizontal').pack(fill=tk.X, padx=10)

        # Contenedor principal
        main = ttk.Frame(self.window)
        main.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Panel de acción (izquierda)
        action_frame = ttk.LabelFrame(main, text="🎬 Acciones", padding=10)
        action_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 5))

        self.action_container = ttk.Frame(action_frame)
        self.action_container.pack(fill=tk.BOTH, expand=True)

        # Panel de jugadores (centro)
        players_frame = ttk.LabelFrame(main, text="👥 Jugadores", padding=10)
        players_frame.grid(row=0, column=1, sticky="nsew", padx=5)

        # Canvas con scroll para jugadores
        canvas = tk.Canvas(players_frame, highlightthickness=0, height=300)
        scrollbar = ttk.Scrollbar(players_frame, orient="vertical", command=canvas.yview)
        self.players_container = ttk.Frame(canvas)

        self.players_container.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=self.players_container, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Chat (abajo)
        chat_frame = ttk.LabelFrame(main, text="💬 Chat", padding=10)
        chat_frame.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(10, 0))

        self.chat_widget = ChatWidget(
            chat_frame,
            player_id=self.player_id,
            on_send_message=self._on_send_chat
        )
        self.chat_widget.pack(fill=tk.BOTH, expand=True)

        # Configurar grid weights
        main.columnconfigure(0, weight=1)
        main.columnconfigure(1, weight=2)
        main.rowconfigure(0, weight=2)
        main.rowconfigure(1, weight=1)

        # Actualizar contenido inicial
        self.refresh()

    def _get_status_text(self) -> str:
        """Obtiene el texto de estado del jugador."""
        if not self.player.alive:
            return "💀 MUERTO"
        
        states = []
        if self.player.blocked:
            states.append("🚫 Bloqueado")
        if self.player.silenced:
            states.append("🤐 Silenciado")
        if self.player.protected:
            states.append("🛡️ Protegido")
        
        return " | ".join(states) if states else "✅ Activo"

    def _update_action_panel(self):
        """Actualiza el panel de acciones según la fase."""
        # Limpiar
        for widget in self.action_container.winfo_children():
            widget.destroy()

        game = self.controller.game
        if not game:
            return

        # Si el jugador está muerto, no puede actuar
        if not self.player.alive:
            ttk.Label(
                self.action_container,
                text="💀 Estás muerto.\nObserva el juego.",
                font=('Arial', 12),
                justify=tk.CENTER
            ).pack(pady=30)
            return

        # Según la fase
        if game.phase == Phase.NIGHT:
            self._create_night_action_panel()
        elif game.phase == Phase.DAY:
            self._create_day_discussion_panel()
        elif game.phase == Phase.VOTING:
            self._create_voting_panel()
        elif game.phase == Phase.FINISHED:
            self._create_finished_panel()

    def _create_night_action_panel(self):
        """Panel para acciones nocturnas."""
        if not self.player.role_key:
            ttk.Label(
                self.action_container,
                text="🌙 Es de noche.\nEspera...",
                font=('Arial', 11)
            ).pack(pady=20)
            return

        role = get_role(self.player.role_key)
        if not role or not role.has_night_action:
            ttk.Label(
                self.action_container,
                text="🌙 Es de noche.\nNo tienes acción nocturna.",
                font=('Arial', 11)
            ).pack(pady=20)
            return

        # Mostrar descripción de la acción
        ttk.Label(
            self.action_container,
            text=f"🎯 {role.name}",
            font=('Arial', 12, 'bold')
        ).pack(pady=(0, 10))

        ttk.Label(
            self.action_container,
            text="Selecciona un objetivo en\nla lista de jugadores →",
            font=('Arial', 10),
            justify=tk.CENTER
        ).pack(pady=10)

        # Botón para confirmar acción
        self.action_button = ttk.Button(
            self.action_container,
            text="✅ Confirmar Acción",
            command=self._on_confirm_action,
            state=tk.DISABLED
        )
        self.action_button.pack(pady=20)

        # Info de acción realizada
        self.action_status = ttk.Label(
            self.action_container,
            text="",
            font=('Arial', 9),
            foreground='gray'
        )
        self.action_status.pack()

    def _create_day_discussion_panel(self):
        """Panel para discusión diurna."""
        ttk.Label(
            self.action_container,
            text="☀️ DÍA",
            font=('Arial', 14, 'bold')
        ).pack(pady=20)

        ttk.Label(
            self.action_container,
            text="Discute con los demás\njugadores en el chat.",
            font=('Arial', 10),
            justify=tk.CENTER
        ).pack(pady=10)

    def _create_voting_panel(self):
        """Panel para votación."""
        if self.player.silenced:
            ttk.Label(
                self.action_container,
                text="🤐 SILENCIADO",
                font=('Arial', 14, 'bold'),
                foreground='red'
            ).pack(pady=20)
            ttk.Label(
                self.action_container,
                text="No puedes votar.",
                font=('Arial', 10)
            ).pack()
            return

        ttk.Label(
            self.action_container,
            text="🗳️ VOTACIÓN",
            font=('Arial', 14, 'bold')
        ).pack(pady=20)

        ttk.Label(
            self.action_container,
            text="Selecciona a quién\nquieres linchar →",
            font=('Arial', 10),
            justify=tk.CENTER
        ).pack(pady=10)

        self.vote_button = ttk.Button(
            self.action_container,
            text="🗳️ Votar",
            command=self._on_vote,
            state=tk.DISABLED
        )
        self.vote_button.pack(pady=20)

        self.vote_status = ttk.Label(
            self.action_container,
            text="",
            font=('Arial', 9),
            foreground='gray'
        )
        self.vote_status.pack()

    def _create_finished_panel(self):
        """Panel de juego terminado."""
        ttk.Label(
            self.action_container,
            text="🏁 JUEGO TERMINADO",
            font=('Arial', 14, 'bold')
        ).pack(pady=30)

    def _update_players_list(self):
        """Actualiza la lista de jugadores visibles."""
        for widget in self.players_container.winfo_children():
            widget.destroy()

        visible_players = self.perspective.get_visible_players()

        for player in visible_players:
            self._create_player_button(player)

    def _create_player_button(self, player: Player):
        """Crea un botón/card para un jugador."""
        frame = ttk.Frame(self.players_container, relief=tk.RAISED, borderwidth=1)
        frame.pack(fill=tk.X, padx=5, pady=5)

        # Icono de estado
        if not player.alive:
            icon = "💀"
        elif player.user_id == self.player_id:
            icon = "⭐"  # Yo
        else:
            icon = "👤"

        # Botón principal
        btn = ttk.Button(
            frame,
            text=f"{icon} {player.name}",
            command=lambda: self._on_select_player(player.user_id)
        )
        btn.pack(fill=tk.X, padx=5, pady=5)

        # Mostrar rol si puede verlo
        if self.perspective.can_see_player_role(player.user_id):
            role = get_role(player.role_key) if player.role_key else None
            if role:
                role_label = ttk.Label(
                    frame,
                    text=f"🎭 {role.name}",
                    font=('Arial', 9),
                    foreground='blue'
                )
                role_label.pack(anchor=tk.W, padx=10, pady=(0, 5))

    def _on_select_player(self, player_id: int):
        """Callback cuando se selecciona un jugador."""
        # Verificar si es un target válido
        game = self.controller.game
        if not game:
            return

        if game.phase == Phase.NIGHT:
            # Validar con perspective
            available_actions = self.perspective.get_available_actions()
            if not available_actions:
                messagebox.showwarning("No disponible", "No puedes realizar acciones ahora.")
                return

            action_type = available_actions[0]  # Tomar primera acción disponible
            valid_targets = self.perspective.get_valid_targets(action_type)
            
            if not any(p.user_id == player_id for p in valid_targets):
                messagebox.showwarning("Objetivo inválido", "No puedes seleccionar a este jugador.")
                return

            self.selected_target_id = player_id
            if hasattr(self, 'action_button'):
                self.action_button.config(state=tk.NORMAL)
            
            target_name = game.players[player_id].name
            if hasattr(self, 'action_status'):
                self.action_status.config(text=f"Objetivo: {target_name}")

        elif game.phase == Phase.VOTING:
            if self.player.silenced:
                messagebox.showwarning("Silenciado", "No puedes votar.")
                return

            self.selected_target_id = player_id
            if hasattr(self, 'vote_button'):
                self.vote_button.config(state=tk.NORMAL)
            
            target_name = game.players[player_id].name
            if hasattr(self, 'vote_status'):
                self.vote_status.config(text=f"Votar a: {target_name}")

    def _on_confirm_action(self):
        """Confirma la acción nocturna."""
        if not self.selected_target_id:
            return

        game = self.controller.game
        if not game or game.phase != Phase.NIGHT:
            return

        # Determinar tipo de acción
        role = get_role(self.player.role_key) if self.player.role_key else None
        if not role:
            return

        # Registrar la acción
        success = False
        if role.faction.value == "mafia" and role.key in ["mafia", "padrino"]:
            success = self.controller.register_mafia_vote(self.player_id, self.selected_target_id)
        else:
            success = self.controller.register_night_action(self.player_id, self.selected_target_id)

        if success:
            target_name = game.players[self.selected_target_id].name
            self.action_status.config(
                text=f"✅ Acción confirmada: {target_name}",
                foreground='green'
            )
            self.action_button.config(state=tk.DISABLED)
            messagebox.showinfo("Confirmado", f"Acción registrada sobre {target_name}.")
        else:
            messagebox.showerror("Error", "No se pudo registrar la acción.")

    def _on_vote(self):
        """Confirma el voto."""
        if not self.selected_target_id:
            return

        game = self.controller.game
        if not game or game.phase != Phase.VOTING:
            return

        success = self.controller.register_day_vote(self.player_id, self.selected_target_id)

        if success:
            target_name = game.players[self.selected_target_id].name
            self.vote_status.config(
                text=f"✅ Voto registrado: {target_name}",
                foreground='green'
            )
            self.vote_button.config(state=tk.DISABLED)
            messagebox.showinfo("Confirmado", f"Has votado por {target_name}.")
        else:
            messagebox.showerror("Error", "No se pudo registrar el voto.")

    def _on_send_chat(self, player_id: int, text: str, channel: str) -> bool:
        """Callback para enviar mensajes de chat."""
        return self.controller.send_chat_message(player_id, text, channel)

    def _update_chat_channels(self):
        """Actualiza los canales de chat disponibles según el rol."""
        channels = self.perspective.get_available_chat_channels()
        if hasattr(self, 'chat_widget'):
            self.chat_widget.set_available_channels(channels)

    def _setup_callbacks(self):
        """Configura callbacks para recibir actualizaciones."""
        # Estos callbacks deben ser llamados por el controller cuando haya cambios
        # Por ahora, usaremos polling periódico
        self._schedule_refresh()

    def _schedule_refresh(self):
        """Programa el próximo refresh."""
        try:
            if self.window.winfo_exists():
                self.window.after(1000, self._do_refresh)
        except Exception:
            pass

    def _do_refresh(self):
        """Ejecuta refresh y replanifica."""
        try:
            self.refresh()
            self._schedule_refresh()
        except Exception:
            logger.exception("Error in perspective window refresh")

    def refresh(self):
        """Actualiza toda la ventana."""
        try:
            self.status_label.config(text=self._get_status_text())
            self._update_action_panel()
            self._update_players_list()
            
            # Actualizar mensajes de chat
            if hasattr(self, 'chat_widget'):
                visible_messages = self.controller.get_visible_chat_messages(self.player_id)
                # Solo añadir mensajes nuevos
                for msg in visible_messages:
                    self.chat_widget.add_message(msg)
        except Exception:
            logger.exception("Error refreshing perspective window")

    def close(self):
        """Cierra la ventana."""
        try:
            self.window.destroy()
        except Exception:
            pass