"""
gui/views/game_view.py
Vista principal durante la partida.
Versión corregida para:
 - evitar opciones incompatibles en ScrolledText (crea Text+Scrollbar manualmente)
 - limpiar callbacks del controller cuando la vista se destruye
 - manejo defensivo de widgets destruidos
"""
import tkinter as tk
from tkinter import ttk, messagebox
import logging
import time
from typing import List, Any, Optional

from core.models import Phase
from core.roles import get_role

logger = logging.getLogger(__name__)


class GameView(ttk.Frame):
    """Vista principal de la partida en curso."""

    def __init__(self, parent, controller, game, colors, debug_mode=False):
        super().__init__(parent)
        self.controller = controller
        self.game = game
        self.colors = colors
        self.debug_mode = debug_mode

        # Estado interno
        self.selected_player_id: Optional[int] = None
        self.timer_label = None

        # Referencias a widgets que pueden ser destruidos
        self.log_text: Optional[tk.Text] = None

        # Crear interfaz
        self._create_widgets()

        # Registrar callbacks (guardar referencias para poder limpiarlas)
        # Los callbacks son funciones "bound"; en destroy los quitaremos si apuntan aquí.
        self._registered_on_game_update = self.controller.on_game_update
        self._registered_on_phase_change = self.controller.on_phase_change
        self._registered_on_player_death = self.controller.on_player_death
        self._registered_on_chat_message = self.controller.on_chat_message

        self.controller.on_game_update = self.refresh
        self.controller.on_phase_change = self._on_phase_change
        self.controller.on_player_death = self._on_player_death
        self.controller.on_chat_message = self._on_chat_message_received

        # Si la vista se destruye, limpiar callbacks
        self.bind("<Destroy>", self._on_destroy, add=True)

        # Iniciar actualización de timer
        self._timer_after_id = None
        self._update_timer()

        logger.info("GameView initialized")

    def _create_widgets(self):
        """Crea todos los widgets de la vista - MEJORADO."""

        # HEADER
        header = ttk.Frame(self)
        header.pack(fill=tk.X, padx=20, pady=10)

        self.phase_label = ttk.Label(
            header,
            text="🌙 NOCHE",
            font=('Arial', 20, 'bold')
        )
        self.phase_label.pack(side=tk.LEFT)

        self.timer_label = ttk.Label(
            header,
            text="⏱️ 5:00",
            font=('Arial', 16)
        )
        self.timer_label.pack(side=tk.RIGHT)

        # Botón para abrir ventanas de perspectiva
        if not self.debug_mode:
            perspectives_btn = ttk.Button(
                header,
                text="🪟 Abrir Perspectivas",
                command=self._open_all_perspectives
            )
            perspectives_btn.pack(side=tk.RIGHT, padx=10)

        # MAIN CONTAINER con mejor distribución
        main = ttk.Frame(self)
        main.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)

        # Solo 2 columnas en lugar de 3 para mejor uso del espacio
        left_frame = ttk.LabelFrame(main, text="👥 Jugadores Vivos", padding=10)
        left_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 5))

        right_frame = ttk.Frame(main)
        right_frame.grid(row=0, column=1, sticky="nsew", padx=(5, 0))

        main.columnconfigure(0, weight=1)
        main.columnconfigure(1, weight=2)
        main.rowconfigure(0, weight=1)

        self._create_players_list(left_frame)
        self._create_right_column(right_frame)

        # Panel de chat
        chat_frame = ttk.LabelFrame(self, text="💬 Chat", padding=10)
        chat_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)

        from gui.widgets.chat_widget import ChatWidget
        host_id = getattr(self.game, "host_id", 1) if self.game else 1

        self.chat_widget = ChatWidget(
            chat_frame,
            player_id=host_id,
            on_send_message=self._on_send_chat_message,
            height=8  # Más compacto
        )
        self.chat_widget.pack(fill=tk.BOTH, expand=True)

        # FOOTER
        footer = ttk.Frame(self)
        footer.pack(fill=tk.X, padx=20, pady=10)

        # Info de fase
        self.phase_info = ttk.Label(
            footer,
            text="",
            font=('Arial', 10),
            foreground='gray'
        )
        self.phase_info.pack(side=tk.LEFT)

        self.action_button = ttk.Button(
            footer,
            text="✅ Resolver Noche",
            command=self._on_resolve_phase,
            style="Accent.TButton"
        )
        self.action_button.pack(side=tk.RIGHT, padx=5)

        back_button = ttk.Button(
            footer,
            text="🔙 Volver al Lobby",
            command=self._on_back_to_lobby
        )
        back_button.pack(side=tk.LEFT, padx=5)

        if self.debug_mode:
            debug_button = ttk.Button(
                footer,
                text="🛠 Debug",
                command=self._show_debug_info
            )
            debug_button.pack(side=tk.LEFT, padx=5)

    def _create_right_column(self, parent):
        """Crea la columna derecha con log y muertos - MEJORADO."""

        # Log de eventos (más grande)
        log_frame = ttk.LabelFrame(parent, text="📜 Eventos", padding=5)
        log_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        text_container = ttk.Frame(log_frame)
        text_container.pack(fill=tk.BOTH, expand=True)

        self.log_text = tk.Text(
            text_container,
            wrap=tk.WORD,
            height=20,  # Más alto
            font=('Consolas', 9),
            bg='#1e1e1e',
            fg='#e0e0e0',
            insertbackground='#ffffff',
            undo=False
        )
        text_scroll = ttk.Scrollbar(text_container, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=text_scroll.set)

        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        text_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        try:
            self.log_text.config(state=tk.DISABLED)
        except Exception:
            logger.exception("Warning: couldn't set log_text to DISABLED")

        # Jugadores muertos
        dead_frame = ttk.LabelFrame(parent, text="💀 Muertos", padding=5)
        dead_frame.pack(fill=tk.X, expand=False)

        # Canvas con scroll para muertos
        dead_canvas = tk.Canvas(dead_frame, height=150, highlightthickness=0)
        dead_scroll = ttk.Scrollbar(dead_frame, orient="vertical", command=dead_canvas.yview)
        self.dead_container = ttk.Frame(dead_canvas)

        self.dead_container.bind(
            "<Configure>",
            lambda e: dead_canvas.configure(scrollregion=dead_canvas.bbox("all"))
        )

        dead_canvas.create_window((0, 0), window=self.dead_container, anchor="nw")
        dead_canvas.configure(yscrollcommand=dead_scroll.set)

        dead_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        dead_scroll.pack(side=tk.RIGHT, fill=tk.Y)

    def _open_all_perspectives(self):
        """Abre todas las ventanas de perspectiva."""
        if hasattr(self.controller.app, 'open_all_perspective_windows'):
            self.controller.app.open_all_perspective_windows()
            self._log("🪟 Abriendo ventanas de perspectiva...")
        else:
            messagebox.showinfo(
                "No disponible",
                "Las ventanas de perspectiva solo están disponibles para jugadores humanos."
            )

    def _update_dead_list(self):
        """Actualiza la lista de muertos - MEJORADO con cards."""
        try:
            # Limpiar contenedor
            for widget in self.dead_container.winfo_children():
                widget.destroy()

            dead_players = self.game.get_dead_players()

            if not dead_players:
                ttk.Label(
                    self.dead_container,
                    text="(Nadie ha muerto aún)",
                    font=('Arial', 9),
                    foreground='gray'
                ).pack(pady=10)
                return

            for player in dead_players:
                self._create_dead_player_card(player)

        except Exception:
            logger.exception("Error updating dead list")

    def _create_dead_player_card(self, player):
        """Crea una tarjeta para un jugador muerto."""
        frame = ttk.Frame(self.dead_container, relief=tk.GROOVE, borderwidth=1)
        frame.pack(fill=tk.X, padx=5, pady=3)

        # Nombre
        name_label = ttk.Label(
            frame,
            text=f"💀 {player.name}",
            font=('Arial', 10, 'bold')
        )
        name_label.pack(anchor=tk.W, padx=5, pady=2)

        # Rol (siempre visible para muertos)
        role = get_role(player.role_key) if player.role_key else None
        if role:
            role_label = ttk.Label(
                frame,
                text=f"🎭 {role.name}",
                font=('Arial', 9),
                foreground='red'
            )
            role_label.pack(anchor=tk.W, padx=5, pady=(0, 2))

    def refresh(self):
        """Actualiza toda la vista - MEJORADO."""
        try:
            self._update_phase_label()
            self._update_phase_info()
            self._update_players_list()
            self._update_dead_list()
            self._update_action_button()
        except Exception:
            logger.exception("Error refreshing GameView")

    def _update_phase_info(self):
        """Actualiza la información adicional de fase."""
        if not self.game:
            return

        info_texts = {
            Phase.NIGHT: "Los jugadores con roles activos deben elegir sus objetivos.",
            Phase.DAY: "Discute con los demás jugadores para identificar sospechosos.",
            Phase.VOTING: "Vota para linchar a alguien. La mayoría decide.",
            Phase.FINISHED: "Juego terminado. Revisa los resultados arriba."
        }

        try:
            self.phase_info.config(text=info_texts.get(self.game.phase, ""))
        except Exception:
            pass

    def _create_players_list(self, parent):
        """Lista de jugadores vivos."""

        # Frame con scroll
        canvas_frame = ttk.Frame(parent)
        canvas_frame.pack(fill=tk.BOTH, expand=True)

        canvas = tk.Canvas(canvas_frame, highlightthickness=0)
        scrollbar = ttk.Scrollbar(canvas_frame, orient="vertical", command=canvas.yview)
        self.players_container = ttk.Frame(canvas)

        self.players_container.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=self.players_container, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)


    # -------------------------
    # Chat callbacks
    # -------------------------
    def _on_send_chat_message(self, player_id, text, channel):
        """Callback cuando el usuario envía un mensaje."""
        self.controller.send_chat_message(player_id, text, channel)

    def _on_chat_message_received(self, message):
        """Callback cuando llega un mensaje (del controller)."""
        if hasattr(self, 'chat_widget') and self.chat_widget:
            try:
                self.chat_widget.add_message(message)
            except Exception:
                logger.exception("Error adding chat message to widget")

    def update_chat_channels(self, player_id):
        """Actualiza canales disponibles según el rol del jugador."""
        perspective = self.controller.get_player_perspective(player_id)
        if perspective and hasattr(self, 'chat_widget') and self.chat_widget:
            channels = perspective.get_available_chat_channels()
            try:
                self.chat_widget.set_available_channels(channels)
            except Exception:
                logger.exception("Error setting available chat channels")

    # ========================================================================
    # ACTUALIZACIÓN DE INTERFAZ
    # ========================================================================

    def _update_phase_label(self):
        """Actualiza la etiqueta de fase actual."""
        if not self.game:
            return

        phase_texts = {
            Phase.NIGHT: "🌙 NOCHE",
            Phase.DAY: "☀️ DÍA",
            Phase.VOTING: "🗳️ VOTACIÓN",
            Phase.FINISHED: "🏁 TERMINADO"
        }

        try:
            self.phase_label.config(text=phase_texts.get(self.game.phase, "❓"))
        except Exception:
            logger.exception("Error updating phase label")

    def _update_players_list(self):
        """Actualiza la lista de jugadores vivos."""
        try:
            # Limpiar contenedor
            for widget in self.players_container.winfo_children():
                widget.destroy()

            alive_players = self.game.get_alive_players()

            if not alive_players:
                ttk.Label(
                    self.players_container,
                    text="(No hay jugadores vivos)",
                    font=('Arial', 9),
                    foreground='gray'
                ).pack(pady=10)
                return

            # Importar aquí para evitar circular import
            from gui.widgets.player_card import PlayerCard

            for player in alive_players:
                card = PlayerCard(
                    self.players_container,
                    player=player,
                    show_role=self.debug_mode,
                    selectable=False
                )
                card.pack(fill=tk.X, pady=2)

        except Exception:
            logger.exception("Error updating players list")

    # ========================================================================
    # EVENT HANDLERS
    # ========================================================================

    def _on_resolve_phase(self):
        """Resuelve la fase actual."""

        if self.game.phase == Phase.NIGHT:
            messages = self.controller.resolve_night()
            self._show_messages("Fin de la Noche", messages)

        elif self.game.phase == Phase.DAY:
            self.controller.start_voting()

        elif self.game.phase == Phase.VOTING:
            messages = self.controller.resolve_votes()
            self._show_messages("Resultado de Votación", messages)

    def _on_back_to_lobby(self):
        """Vuelve al lobby."""
        if messagebox.askyesno("Confirmar", "¿Volver al lobby y terminar la partida?"):
            self.controller.end_game()
            # limpiar callbacks antes de cambiar vista (por si el controller hace llamadas inmediatas)
            self._cleanup_controller_callbacks()
            self.controller.app.show_lobby()

    def _on_phase_change(self, new_phase: Phase):
        """Callback cuando cambia la fase."""
        self._log(f"🔔 Cambio de fase: {new_phase.value.upper()}")
        self.refresh()

    def _on_player_death(self, player):
        """Callback cuando muere un jugador."""
        role = get_role(player.role_key) if player.role_key else None
        role_name = role.name if role else "?"
        self._log(f"💀 {player.name} ha muerto. Era {role_name}.")

    def _show_debug_info(self):
        """Muestra información de debug."""
        info_lines = [
            f"Fase: {self.game.phase.value}",
            f"Jugadores vivos: {len(self.game.get_alive_players())}",
            f"Acciones nocturnas: {len(getattr(self.game, 'night_actions', []))}",
            f"Votos mafia: {len(getattr(self.game, 'mafia_votes', {}))}",
            f"Votos día: {len(getattr(self.game, 'day_votes', {}))}",
            "",
            "Roles:"
        ]

        for p in self.game.players.values():
            role = get_role(p.role_key) if p.role_key else None
            status = "👥" if p.alive else "💀"
            info_lines.append(f"{status} {p.name}: {role.name if role else '?'}")

        messagebox.showinfo("Debug Info", "\n".join(info_lines))

    def _show_messages(self, title: str, messages: List[str]):
        """Muestra mensajes en un diálogo."""
        text = "\n\n".join(messages)
        messagebox.showinfo(title, text)

        for msg in messages:
            self._log(msg)

    # ========================================================================
    # REFRESH Y HELPERS
    # ========================================================================
    # Removed duplicate methods - using earlier definitions

    def _update_action_button(self):
        """Actualiza el texto y estado del botón de acción."""

        button_texts = {
            Phase.NIGHT: "✅ Resolver Noche",
            Phase.DAY: "🗳️ Iniciar Votación",
            Phase.VOTING: "⚖️ Resolver Votos",
            Phase.FINISHED: "🔙 Volver al Lobby"
        }

        try:
            self.action_button.config(
                text=button_texts.get(self.game.phase, "▶️ Continuar")
            )
        except Exception:
            logger.exception("Error updating action button")

    def _update_timer(self):
        """Actualiza el timer (se llama cada segundo)."""

        try:
            if not self.game or not getattr(self.game, "phase_deadline", None):
                self.timer_label.config(text="⏱️ --:--")
            else:
                remaining = max(0, self.game.phase_deadline - int(time.time()))
                minutes = remaining // 60
                seconds = remaining % 60
                self.timer_label.config(text=f"⏱️ {minutes}:{seconds:02d}")
        except Exception:
            # widget puede estar destruido
            pass

        # Programar siguiente actualización, guardar id para poder cancelarlo
        try:
            if self.winfo_exists():
                self._timer_after_id = self.after(1000, self._update_timer)
        except Exception:
            pass

    def _log(self, message: str):
        """Agrega un mensaje al log."""

        timestamp = time.strftime("%H:%M:%S")
        full_message = f"[{timestamp}] {message}\n"

        try:
            if not self.log_text or not self.log_text.winfo_exists():
                # no hay widget donde loguear
                logger.info(full_message.strip())
                return

            self.log_text.config(state=tk.NORMAL)
            self.log_text.insert(tk.END, full_message)
            self.log_text.see(tk.END)
            self.log_text.config(state=tk.DISABLED)
        except Exception:
            # No dejar que fallos de logging rompan la app
            logger.exception("Error writing to log_text")

    # -----------------------------------------------------------------
    # Cleanup: cuando la vista se destruye, quitar los callbacks del controller
    # -----------------------------------------------------------------
    def _on_destroy(self, event):
        # event may fire many times; act only when this widget is actually gone
        if event.widget is not self:
            return
        self._cleanup_controller_callbacks()
        # cancelar timer
        try:
            if self._timer_after_id:
                self.after_cancel(self._timer_after_id)
        except Exception:
            pass

    def _cleanup_controller_callbacks(self):
        try:
            if getattr(self.controller, "on_game_update", None) is self.refresh:
                self.controller.on_game_update = self._registered_on_game_update
            if getattr(self.controller, "on_phase_change", None) is self._on_phase_change:
                self.controller.on_phase_change = self._registered_on_phase_change
            if getattr(self.controller, "on_player_death", None) is self._on_player_death:
                self.controller.on_player_death = self._registered_on_player_death
            if getattr(self.controller, "on_chat_message", None) is self._on_chat_message_received:
                self.controller.on_chat_message = self._registered_on_chat_message
        except Exception:
            logger.exception("Error cleaning up controller callbacks")
