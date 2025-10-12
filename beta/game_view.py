"""
gui/views/game_view.py
Vista principal del juego en curso.
"""
import tkinter as tk
from tkinter import ttk, messagebox
import logging
import time

from core import Phase, get_role

logger = logging.getLogger(__name__)


class GameView(ttk.Frame):
    """Vista del juego en curso."""
    
    def __init__(self, parent, controller, game, colors, debug_mode=False):
        super().__init__(parent)
        self.controller = controller
        self.game = game
        self.colors = colors
        self.debug_mode = debug_mode
        
        # Jugador actual (en modo normal, solo muestra info de un jugador)
        self.current_player_id = None
        
        # Suscribirse a actualizaciones
        self.controller.on_game_update = self.refresh
        self.controller.on_phase_change = self.on_phase_change
        
        self.setup_ui()
        self.refresh()
        
        # Timer para actualizar countdown
        self.update_timer()
    
    def setup_ui(self):
        """Configura la interfaz."""
        # Header con fase actual
        self.header = ttk.Frame(self)
        self.header.pack(fill=tk.X, padx=10, pady=10)
        
        self.phase_label = tk.Label(
            self.header,
            text="",
            font=("Arial", 18, "bold"),
            bg=self.colors['bg'],
            fg=self.colors['accent']
        )
        self.phase_label.pack(side=tk.LEFT)
        
        self.timer_label = tk.Label(
            self.header,
            text="",
            font=("Arial", 14),
            bg=self.colors['bg'],
            fg=self.colors['fg']
        )
        self.timer_label.pack(side=tk.RIGHT)
        
        # Modo debug
        if self.debug_mode:
            self.setup_debug_ui()
        else:
            self.setup_normal_ui()
    
    def setup_debug_ui(self):
        """UI en modo debug - muestra todos los roles."""
        # Main container
        main = ttk.Frame(self)
        main.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # Panel izquierdo - Estado del juego
        left_panel = ttk.LabelFrame(main, text="🐛 Estado del Juego (Debug)", padding=10)
        left_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
        
        # Lista de jugadores con roles visibles
        self.debug_text = tk.Text(
            left_panel,
            font=("Courier", 10),
            bg="#1e1e1e",
            fg=self.colors['fg'],
            wrap=tk.WORD,
            relief=tk.FLAT
        )
        self.debug_text.pack(fill=tk.BOTH, expand=True)
        
        # Panel derecho - Controles
        right_panel = ttk.LabelFrame(main, text="🎮 Controles", padding=10)
        right_panel.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(5, 0))
        
        # Selector de jugador
        player_frame = ttk.Frame(right_panel)
        player_frame.pack(fill=tk.X, pady=(0, 10))
        
        tk.Label(
            player_frame,
            text="Jugador activo:",
            bg=self.colors['bg'],
            fg=self.colors['fg']
        ).pack(anchor=tk.W)
        
        self.player_combo = ttk.Combobox(player_frame, state="readonly")
        self.player_combo.pack(fill=tk.X, pady=(5, 0))
        self.player_combo.bind("<<ComboboxSelected>>", self.on_player_select)
        
        # Panel de acciones
        self.action_panel = ttk.LabelFrame(right_panel, text="Acción", padding=10)
        self.action_panel.pack(fill=tk.BOTH, expand=True, pady=(10, 0))
        
        # Info del jugador seleccionado
        self.player_info_label = tk.Label(
            self.action_panel,
            text="Selecciona un jugador",
            bg=self.colors['bg'],
            fg=self.colors['fg'],
            justify=tk.LEFT,
            wraplength=250
        )
        self.player_info_label.pack(anchor=tk.W, pady=(0, 10))
        
        # Lista de objetivos
        tk.Label(
            self.action_panel,
            text="Objetivo:",
            bg=self.colors['bg'],
            fg=self.colors['fg']
        ).pack(anchor=tk.W)
        
        self.target_listbox = tk.Listbox(
            self.action_panel,
            height=10,
            bg="#1e1e1e",
            fg=self.colors['fg'],
            selectbackground=self.colors['accent']
        )
        self.target_listbox.pack(fill=tk.BOTH, expand=True, pady=(5, 10))
        
        # Botón de confirmar acción
        self.action_button = ttk.Button(
            self.action_panel,
            text="✓ Confirmar Acción",
            command=self.submit_action
        )
        self.action_button.pack(fill=tk.X)
        
        # Footer con controles de fase
        footer = ttk.Frame(self)
        footer.pack(fill=tk.X, padx=10, pady=10)
        
        ttk.Button(
            footer,
            text="⏭️ Siguiente Fase",
            command=self.advance_phase
        ).pack(side=tk.LEFT, padx=(0, 5))
        
        ttk.Button(
            footer,
            text="🔄 Reiniciar",
            command=self.reset_game
        ).pack(side=tk.LEFT, padx=(0, 5))
        
        ttk.Button(
            footer,
            text="⬅️ Volver al Lobby",
            command=self.back_to_lobby
        ).pack(side=tk.RIGHT)
    
    def setup_normal_ui(self):
        """UI en modo normal - solo info del jugador actual."""
        # TODO: Implementar modo normal
        # Por ahora usar debug mode
        placeholder = tk.Label(
            self,
            text="Modo normal: En construcción\n\nUsa --debug para probar",
            font=("Arial", 14),
            bg=self.colors['bg'],
            fg=self.colors['fg']
        )
        placeholder.pack(expand=True)
    
    def on_player_select(self, event=None):
        """Callback cuando se selecciona un jugador."""
        if not self.debug_mode:
            return
        
        selection = self.player_combo.get()
        if not selection:
            return
        
        # Extraer ID del formato "Name (ID)"
        try:
            player_id = int(selection.split("(")[-1].rstrip(")"))
            self.current_player_id = player_id
            self.update_action_panel()
        except (ValueError, IndexError):
            pass
    
    def update_action_panel(self):
        """Actualiza el panel de acciones según el jugador seleccionado."""
        if not self.current_player_id:
            return
        
        player = self.game.players.get(self.current_player_id)
        if not player:
            return
        
        role = get_role(player.role_key) if player.role_key else None
        
        # Actualizar info
        if not player.alive:
            self.player_info_label.config(
                text=f"💀 {player.name} está muerto"
            )
            self.target_listbox.delete(0, tk.END)
            self.action_button.config(state=tk.DISABLED)
            return
        
        if not role or not role.has_night_action:
            self.player_info_label.config(
                text=f"{player.name}\n{role.name if role else 'Sin rol'}\n\nSin acción nocturna"
            )
            self.target_listbox.delete(0, tk.END)
            self.action_button.config(state=tk.DISABLED)
            return
        
        # Actualizar según fase
        if self.game.phase == Phase.NIGHT:
            action_desc = self.get_action_description(role)
            self.player_info_label.config(
                text=f"{player.name}\n{role.name}\n\n{action_desc}"
            )
            
            # Poblar lista de objetivos
            self.target_listbox.delete(0, tk.END)
            for target in self.game.get_alive_players():
                # Algunos roles no pueden targetear a sí mismos
                if target.user_id == player.user_id and role.key not in ["doctor"]:
                    continue
                self.target_listbox.insert(tk.END, target.name)
            
            self.action_button.config(state=tk.NORMAL)
        
        elif self.game.phase == Phase.VOTING:
            self.player_info_label.config(
                text=f"{player.name}\n{role.name}\n\n🗳️ Vota a quién linchar"
            )
            
            # Poblar con jugadores vivos
            self.target_listbox.delete(0, tk.END)
            for target in self.game.get_alive_players():
                self.target_listbox.insert(tk.END, target.name)
            
            self.action_button.config(state=tk.NORMAL)
        else:
            self.player_info_label.config(
                text=f"{player.name}\n{role.name}\n\nEsperando..."
            )
            self.action_button.config(state=tk.DISABLED)
    
    def get_action_description(self, role):
        """Retorna la descripción de la acción del rol."""
        actions = {
            "doctor": "Selecciona a quién curar",
            "detective": "Selecciona a quién investigar",
            "sheriff": "Selecciona a quién investigar",
            "escort": "Selecciona a quién bloquear",
            "guardaespaldas": "Selecciona a quién proteger",
            "vigilante": "Selecciona a quién disparar",
            "mafia": "Vota a quién matar",
            "padrino": "Vota a quién matar",
            "consorte": "Selecciona a quién bloquear",
            "chantajeador": "Selecciona a quién silenciar",
            "consigliere": "Selecciona a quién investigar",
            "asesino": "Selecciona a quién matar"
        }
        return actions.get(role.key, "Acción nocturna")
    
    def submit_action(self):
        """Envía la acción del jugador actual."""
        if not self.current_player_id:
            return
        
        selection = self.target_listbox.curselection()
        if not selection:
            messagebox.showwarning("Aviso", "Selecciona un objetivo")
            return
        
        player = self.game.players.get(self.current_player_id)
        if not player:
            return
        
        # Obtener target
        target_name = self.target_listbox.get(selection[0])
        target = next(
            (p for p in self.game.players.values() if p.name == target_name),
            None
        )
        
        if not target:
            return
        
        role = get_role(player.role_key) if player.role_key else None
        if not role:
            return
        
        # Determinar tipo de acción
        if self.game.phase == Phase.VOTING:
            self.controller.submit_vote(player.user_id, target.user_id)
            messagebox.showinfo("OK", f"Voto registrado: {target.name}")
        else:
            action_types = {
                "doctor": "heal",
                "detective": "investigate",
                "sheriff": "investigate",
                "escort": "block",
                "guardaespaldas": "guard",
                "vigilante": "vigilante_kill",
                "consorte": "block",
                "chantajeador": "blackmail",
                "consigliere": "investigate",
                "asesino": "serial_kill"
            }
            
            action_type = action_types.get(role.key)
            if action_type:
                self.controller.submit_action(
                    player.user_id,
                    action_type,
                    target.user_id
                )
                messagebox.showinfo("OK", f"Acción registrada: {target.name}")
    
    def advance_phase(self):
        """Avanza a la siguiente fase."""
        self.controller.advance_phase()
    
    def reset_game(self):
        """Reinicia el juego."""
        if messagebox.askyesno("Confirmar", "¿Reiniciar la partida?"):
            self.controller.reset_game()
            self.back_to_lobby()
    
    def back_to_lobby(self):
        """Vuelve al lobby."""
        self.master.master.master.show_lobby()
    
    def on_phase_change(self, new_phase):
        """Callback cuando cambia la fase."""
        phase_messages = {
            Phase.NIGHT: "🌙 Comienza la noche...",
            Phase.DAY: "☀️ Amanece...",
            Phase.VOTING: "🗳️ Hora de votar...",
            Phase.FINISHED: "🏁 ¡Juego terminado!"
        }
        
        message = phase_messages.get(new_phase, f"Fase: {new_phase.value}")
        messagebox.showinfo("Cambio de Fase", message)
        
        self.refresh()
    
    def update_timer(self):
        """Actualiza el timer del countdown."""
        if not self.game or not self.game.phase_deadline:
            self.timer_label.config(text="⏱️ --:--")
        else:
            remaining = max(0, self.game.phase_deadline - int(time.time()))
            minutes = remaining // 60
            seconds = remaining % 60
            self.timer_label.config(text=f"⏱️ {minutes:02d}:{seconds:02d}")
        
        # Programar siguiente actualización
        self.after(1000, self.update_timer)
    
    def refresh(self, game=None):
        """Actualiza la vista."""
        game = game or self.controller.get_game()
        if not game:
            return
        
        self.game = game
        
        # Actualizar header
        phase_emojis = {
            Phase.NIGHT: "🌙",
            Phase.DAY: "☀️",
            Phase.VOTING: "🗳️",
            Phase.FINISHED: "🏁"
        }
        
        emoji = phase_emojis.get(game.phase, "🎮")
        self.phase_label.config(
            text=f"{emoji} {game.phase.value.upper()}"
        )
        
        if not self.debug_mode:
            return
        
        # Actualizar vista debug
        self.update_debug_view()
        self.update_player_combo()
        self.update_action_panel()
    
    def update_debug_view(self):
        """Actualiza la vista de debug con todos los roles."""
        self.debug_text.delete(1.0, tk.END)
        
        # Header
        self.debug_text.insert(tk.END, f"═══ DEBUG VIEW ═══\n\n")
        self.debug_text.insert(tk.END, f"Fase: {self.game.phase.value}\n")
        self.debug_text.insert(tk.END, f"Jugadores vivos: {len(self.game.get_alive_players())}\n\n")
        
        # Jugadores
        self.debug_text.insert(tk.END, "JUGADORES:\n")
        self.debug_text.insert(tk.END, "─" * 50 + "\n")
        
        for player in self.game.players.values():
            status = "✅" if player.alive else "💀"
            role = get_role(player.role_key) if player.role_key else None
            role_name = role.name if role else "?"
            
            line = f"{status} {player.name:<15} {role_name:<20}"
            
            if player.blocked:
                line += " [BLOQUEADO]"
            if player.silenced:
                line += " [SILENCIADO]"
            
            self.debug_text.insert(tk.END, line + "\n")
        
        # Acciones registradas
        if self.game.phase == Phase.NIGHT and self.game.night_actions:
            self.debug_text.insert(tk.END, f"\nACCIONES NOCTURNAS:\n")
            self.debug_text.insert(tk.END, "─" * 50 + "\n")
            for action in self.game.night_actions:
                actor = self.game.players.get(action.actor_id)
                target = self.game.players.get(action.target_id)
                if actor and target:
                    self.debug_text.insert(
                        tk.END,
                        f"• {actor.name} → {action.action_type} → {target.name}\n"
                    )
        
        # Votos registrados
        if self.game.phase == Phase.VOTING and self.game.day_votes:
            self.debug_text.insert(tk.END, f"\nVOTOS:\n")
            self.debug_text.insert(tk.END, "─" * 50 + "\n")
            for voter_id, target_id in self.game.day_votes.items():
                voter = self.game.players.get(voter_id)
                target = self.game.players.get(target_id)
                if voter and target:
                    self.debug_text.insert(
                        tk.END,
                        f"• {voter.name} → {target.name}\n"
                    )
    
    def update_player_combo(self):
        """Actualiza el combobox de jugadores."""
        players = [
            f"{p.name} ({p.user_id})"
            for p in self.game.players.values()
        ]
        self.player_combo['values'] = players
        
        if not self.current_player_id and players:
            self.player_combo.current(0)
            self.on_player_select()
