"""
gui/views/game_view.py
Vista principal durante la partida.
"""
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import logging
import time

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
        self.selected_player_id = None
        self.timer_label = None
        
        # Crear interfaz
        self._create_widgets()
        
        # Registrar callbacks
        self.controller.on_game_update = self.refresh
        self.controller.on_phase_change = self._on_phase_change
        self.controller.on_player_death = self._on_player_death
        
        # Iniciar actualización de timer
        self._update_timer()
        
        logger.info("GameView initialized")
    
    def _create_widgets(self):
        """Crea todos los widgets de la vista."""
        
        # ====================================================================
        # HEADER - Información de fase
        # ====================================================================
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
        
        # ====================================================================
        # MAIN CONTAINER (3 columnas)
        # ====================================================================
        main = ttk.Frame(self)
        main.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        # Columna izquierda: Jugadores vivos
        left_frame = ttk.LabelFrame(main, text="💚 Jugadores Vivos", padding=10)
        left_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        
        # Columna central: Acciones
        center_frame = ttk.LabelFrame(main, text="🎬 Acciones", padding=10)
        center_frame.grid(row=0, column=1, sticky="nsew", padx=5)
        
        # Columna derecha: Log + Muertos
        right_frame = ttk.Frame(main)
        right_frame.grid(row=0, column=2, sticky="nsew", padx=(5, 0))
        
        main.columnconfigure(0, weight=1)
        main.columnconfigure(1, weight=2)
        main.columnconfigure(2, weight=1)
        main.rowconfigure(0, weight=1)
        
        self._create_players_list(left_frame)
        self._create_actions_panel(center_frame)
        self._create_right_panel(right_frame)
        
        # ====================================================================
        # FOOTER - Controles
        # ====================================================================
        footer = ttk.Frame(self)
        footer.pack(fill=tk.X, padx=20, pady=10)
        
        self.action_button = ttk.Button(
            footer,
            text="✅ Resolver Noche",
            command=self._on_resolve_phase,
            style='Accent.TButton'
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
                text="🐛 Debug",
                command=self._show_debug_info
            )
            debug_button.pack(side=tk.LEFT, padx=5)
    
    def _create_players_list(self, parent):
        """Lista de jugadores vivos."""
        
        # Frame con scroll
        canvas_frame = ttk.Frame(parent)
        canvas_frame.pack(fill=tk.BOTH, expand=True)
        
        canvas = tk.Canvas(canvas_frame)
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
    
    def _create_actions_panel(self, parent):
        """Panel de acciones según la fase."""
        
        self.actions_container = ttk.Frame(parent)
        self.actions_container.pack(fill=tk.BOTH, expand=True)
        
        # El contenido cambiará según la fase
        self._update_actions_panel()
    
    def _create_right_panel(self, parent):
        """Panel derecho con log y muertos."""
        
        # Log de eventos
        log_frame = ttk.LabelFrame(parent, text="📜 Eventos", padding=5)
        log_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        self.log_text = scrolledtext.ScrolledText(
            log_frame,
            wrap=tk.WORD,
            height=15,
            font=('Arial', 9),
            state=tk.DISABLED
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
        # Jugadores muertos
        dead_frame = ttk.LabelFrame(parent, text="💀 Muertos", padding=5)
        dead_frame.pack(fill=tk.BOTH, expand=False)
        
        self.dead_listbox = tk.Listbox(
            dead_frame,
            font=('Arial', 9),
            height=6
        )
        self.dead_listbox.pack(fill=tk.BOTH, expand=True)
    
    # ========================================================================
    # ACTUALIZACIÓN DE INTERFAZ
    # ========================================================================
    
    def _update_actions_panel(self):
        """Actualiza el panel de acciones según la fase actual."""
        
        # Limpiar panel
        for widget in self.actions_container.winfo_children():
            widget.destroy()
        
        if self.game.phase == Phase.NIGHT:
            self._create_night_actions()
        elif self.game.phase == Phase.DAY:
            self._create_day_discussion()
        elif self.game.phase == Phase.VOTING:
            self._create_voting_panel()
        elif self.game.phase == Phase.FINISHED:
            self._create_game_over()
    
    def _create_night_actions(self):
        """Panel de acciones nocturnas."""
        
        info = ttk.Label(
            self.actions_container,
            text="🌙 Es de noche. Los jugadores con roles activos\ndeben elegir sus objetivos.",
            font=('Arial', 11),
            justify=tk.CENTER
        )
        info.pack(pady=20)
        
        # En una GUI real, cada "jugador" tendría su propia vista
        # Aquí mostramos selector para simular
        
        if self.debug_mode or len(self.game.players) == 1:
            # Modo debug: permitir elegir por todos
            self._create_role_selectors()
        else:
            # Modo normal: solo mostrar tu rol
            placeholder = ttk.Label(
                self.actions_container,
                text="En modo multijugador, cada jugador\nvería solo su propia acción aquí.",
                font=('Arial', 10),
                foreground='gray'
            )
            placeholder.pack(pady=30)
    
    def _create_role_selectors(self):
        """Crea selectores de acción para roles activos (debug mode)."""
        
        # Frame con scroll para múltiples roles
        canvas = tk.Canvas(self.actions_container, height=400)
        scrollbar = ttk.Scrollbar(self.actions_container, orient="vertical", command=canvas.yview)
        roles_frame = ttk.Frame(canvas)
        
        roles_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=roles_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Crear selector para cada jugador con rol activo
        for player in self.game.get_alive_players():
            role = get_role(player.role_key) if player.role_key else None
            
            if not role or not role.has_night_action:
                continue
            
            self._create_role_action_widget(roles_frame, player, role)
    
    def _create_role_action_widget(self, parent, player, role):
        """Widget para que un jugador elija su acción nocturna."""
        
        frame = ttk.LabelFrame(
            parent,
            text=f"{player.name} - {role.name}",
            padding=10
        )
        frame.pack(fill=tk.X, padx=5, pady=5)
        
        # Descripción corta
        desc = ttk.Label(
            frame,
            text=role.description.split('\n')[0][:60] + "...",
            font=('Arial', 9),
            foreground='gray'
        )
        desc.pack(anchor=tk.W)
        
        # Selector de objetivo
        target_frame = ttk.Frame(frame)
        target_frame.pack(fill=tk.X, pady=(5, 0))
        
        ttk.Label(target_frame, text="Objetivo:").pack(side=tk.LEFT, padx=(0, 5))
        
        # Obtener objetivos válidos
        targets = []
        for p in self.game.get_alive_players():
            # Algunos roles no pueden targetear a sí mismos
            if p.user_id == player.user_id and role.key != "doctor":
                continue
            
            # Mafia no puede targetear a mafia
            if role.faction.value == "mafia":
                target_role = get_role(p.role_key) if p.role_key else None
                if target_role and target_role.faction.value == "mafia":
                    continue
            
            targets.append((p.user_id, p.name))
        
        target_var = tk.StringVar()
        target_combo = ttk.Combobox(
            target_frame,
            textvariable=target_var,
            values=[name for _, name in targets],
            state='readonly',
            width=15
        )
        target_combo.pack(side=tk.LEFT, padx=5)
        
        def on_select():
            selected_name = target_var.get()
            target_id = next((uid for uid, name in targets if name == selected_name), None)
            
            if target_id:
                if role.faction.value == "mafia":
                    self.controller.register_mafia_vote(player.user_id, target_id)
                else:
                    self.controller.register_night_action(player.user_id, target_id)
                
                self._log(f"✅ {player.name} eligió a {selected_name}")
        
        confirm_btn = ttk.Button(
            target_frame,
            text="Confirmar",
            command=on_select,
            width=10
        )
        confirm_btn.pack(side=tk.LEFT, padx=5)
    
    def _create_day_discussion(self):
        """Panel de discusión diurna."""
        
        info = ttk.Label(
            self.actions_container,
            text="☀️ Es de día. Discutid quién es sospechoso.\nLa votación comenzará pronto.",
            font=('Arial', 12),
            justify=tk.CENTER
        )
        info.pack(pady=30)
        
        # Temporizador visual
        if self.game.phase_deadline:
            remaining = self.game.phase_deadline - int(time.time())
            minutes = remaining // 60
            seconds = remaining % 60
            
            timer_info = ttk.Label(
                self.actions_container,
                text=f"Tiempo restante: {minutes}:{seconds:02d}",
                font=('Arial', 14, 'bold')
            )
            timer_info.pack(pady=10)
        
        # Botón para forzar votación (debug)
        if self.debug_mode:
            force_btn = ttk.Button(
                self.actions_container,
                text="⏩ Forzar Votación",
                command=self.controller.start_voting
            )
            force_btn.pack(pady=20)
    
    def _create_voting_panel(self):
        """Panel de votación."""
        
        info = ttk.Label(
            self.actions_container,
            text="🗳️ VOTACIÓN\n¿A quién queréis linchar?",
            font=('Arial', 12, 'bold'),
            justify=tk.CENTER
        )
        info.pack(pady=20)
        
        # Mostrar votos actuales
        if self.game.day_votes:
            votes_label = ttk.Label(
                self.actions_container,
                text=f"Votos registrados: {len(self.game.day_votes)}",
                font=('Arial', 10)
            )
            votes_label.pack()
        
        # Selector de voto para cada jugador vivo
        vote_frame = ttk.Frame(self.actions_container)
        vote_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        
        for voter in self.game.get_alive_players():
            if voter.silenced:
                continue
            
            self._create_vote_widget(vote_frame, voter)
    
    def _create_vote_widget(self, parent, voter):
        """Widget para que un jugador vote."""
        
        frame = ttk.Frame(parent)
        frame.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Label(frame, text=f"{voter.name}:", width=15).pack(side=tk.LEFT)
        
        # Obtener candidatos (todos los vivos excepto el votante)
        candidates = [
            (p.user_id, p.name)
            for p in self.game.get_alive_players()
            if p.user_id != voter.user_id
        ]
        
        vote_var = tk.StringVar()
        
        # Mostrar voto actual si existe
        if voter.user_id in self.game.day_votes:
            current_vote_id = self.game.day_votes[voter.user_id]
            current_name = next(
                (name for uid, name in candidates if uid == current_vote_id),
                ""
            )
            vote_var.set(current_name)
        
        vote_combo = ttk.Combobox(
            frame,
            textvariable=vote_var,
            values=[name for _, name in candidates],
            state='readonly',
            width=15
        )
        vote_combo.pack(side=tk.LEFT, padx=5)
        
        def on_vote():
            selected_name = vote_var.get()
            target_id = next((uid for uid, name in candidates if name == selected_name), None)
            
            if target_id:
                self.controller.register_day_vote(voter.user_id, target_id)
                self._log(f"🗳️ {voter.name} votó por {selected_name}")
        
        vote_btn = ttk.Button(
            frame,
            text="Votar",
            command=on_vote,
            width=8
        )
        vote_btn.pack(side=tk.LEFT, padx=5)
    
    def _create_game_over(self):
        """Panel de fin del juego."""
        
        winner_msg = "🏆 PARTIDA TERMINADA"
        
        title = ttk.Label(
            self.actions_container,
            text=winner_msg,
            font=('Arial', 18, 'bold')
        )
        title.pack(pady=30)
        
        # Mostrar todos los roles
        roles_label = ttk.Label(
            self.actions_container,
            text="Roles revelados:",
            font=('Arial', 12, 'bold')
        )
        roles_label.pack(pady=(20, 10))
        
        for player in self.game.players.values():
            role = get_role(player.role_key) if player.role_key else None
            role_name = role.name if role else "?"
            status = "💚" if player.alive else "💀"
            
            player_label = ttk.Label(
                self.actions_container,
                text=f"{status} {player.name} - {role_name}",
                font=('Arial', 10)
            )
            player_label.pack(anchor=tk.W, padx=20)
    
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
            self.controller.app.show_lobby()
    
    def _on_phase_change(self, new_phase: Phase):
        """Callback cuando cambia la fase."""
        self._log(f"📢 Cambio de fase: {new_phase.value.upper()}")
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
            f"Acciones nocturnas: {len(self.game.night_actions)}",
            f"Votos mafia: {len(self.game.mafia_votes)}",
            f"Votos día: {len(self.game.day_votes)}",
            "",
            "Roles:"
        ]
        
        for p in self.game.players.values():
            role = get_role(p.role_key) if p.role_key else None
            status = "💚" if p.alive else "💀"
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
    
    def refresh(self):
        """Actualiza toda la vista."""
        self._update_phase_label()
        self._update_players_list()
        self._update_dead_list()
        self._update_actions_panel()
        self._update_action_button()
    
    def _update_phase_label(self):
        """Actualiza el label de fase."""
        phase_icons = {
            Phase.NIGHT: "🌙 NOCHE",
            Phase.DAY: "☀️ DÍA",
            Phase.VOTING: "🗳️ VOTACIÓN",
            Phase.FINISHED: "🏁 FIN"
        }
        
        self.phase_label.config(text=phase_icons.get(self.game.phase, "🎮 JUEGO"))
    
    def _update_players_list(self):
        """Actualiza la lista de jugadores vivos."""
        
        # Limpiar
        for widget in self.players_container.winfo_children():
            widget.destroy()
        
        # Recrear
        for player in self.game.get_alive_players():
            self._create_player_card(self.players_container, player)
    
    def _create_player_card(self, parent, player):
        """Crea una tarjeta para un jugador."""
        
        frame = ttk.Frame(parent, relief=tk.RAISED, borderwidth=1)
        frame.pack(fill=tk.X, padx=5, pady=5)
        
        # Nombre
        name_label = ttk.Label(
            frame,
            text=f"👤 {player.name}",
            font=('Arial', 11, 'bold')
        )
        name_label.pack(anchor=tk.W, padx=10, pady=(5, 0))
        
        # Rol (si visible)
        role_text = self.controller.get_player_role(player.user_id)
        if role_text:
            role = get_role(role_text)
            role_label = ttk.Label(
                frame,
                text=f"🎭 {role.name if role else role_text}",
                font=('Arial', 9),
                foreground='blue'
            )
            role_label.pack(anchor=tk.W, padx=10)
        
        # Estados
        states = []
        if player.silenced:
            states.append("🤐 Silenciado")
        if player.blocked:
            states.append("🚫 Bloqueado")
        
        if states:
            state_label = ttk.Label(
                frame,
                text=" | ".join(states),
                font=('Arial', 9),
                foreground='red'
            )
            state_label.pack(anchor=tk.W, padx=10, pady=(0, 5))
    
    def _update_dead_list(self):
        """Actualiza la lista de muertos."""
        
        self.dead_listbox.delete(0, tk.END)
        
        for player in self.game.get_dead_players():
            role = get_role(player.role_key) if player.role_key else None
            role_name = role.name if role else "?"
            self.dead_listbox.insert(tk.END, f"💀 {player.name} - {role_name}")
    
    def _update_action_button(self):
        """Actualiza el texto y estado del botón de acción."""
        
        button_texts = {
            Phase.NIGHT: "✅ Resolver Noche",
            Phase.DAY: "🗳️ Iniciar Votación",
            Phase.VOTING: "⚖️ Resolver Votos",
            Phase.FINISHED: "🔙 Volver al Lobby"
        }
        
        self.action_button.config(
            text=button_texts.get(self.game.phase, "▶️ Continuar")
        )
    
    def _update_timer(self):
        """Actualiza el timer (se llama cada segundo)."""
        
        if not self.game or not self.game.phase_deadline:
            self.timer_label.config(text="⏱️ --:--")
        else:
            remaining = max(0, self.game.phase_deadline - int(time.time()))
            minutes = remaining // 60
            seconds = remaining % 60
            self.timer_label.config(text=f"⏱️ {minutes}:{seconds:02d}")
        
        # Programar siguiente actualización
        self.after(1000, self._update_timer)
    
    def _log(self, message: str):
        """Agrega un mensaje al log."""
        
        timestamp = time.strftime("%H:%M:%S")
        full_message = f"[{timestamp}] {message}\n"
        
        self.log_text.config(state=tk.NORMAL)