"""
gui/controllers/game_controller.py
Controlador del juego para la GUI.
Actúa como intermediario entre la UI y el motor del juego.
"""
import logging
import asyncio
from typing import Optional, List, Callable
from threading import Thread
import time

from core.models import Game, Player, Phase
from core.engine import GameEngine
from core.roles import get_role, get_default_role

logger = logging.getLogger(__name__)


class GUIGameController:
    """
    Controlador del juego para interfaz GUI.
    Gestiona el estado del juego sin depender de Telegram ni persistencia.
    """
    
    def __init__(self, app, debug_mode: bool = False):
        """
        Args:
            app: Referencia a MafiaGUIApp
            debug_mode: Si True, permite ver todos los roles
        """
        self.app = app
        self.game: Optional[Game] = None
        self.engine = GameEngine()
        self.debug_mode = debug_mode
        
        # Callbacks para actualizar la UI
        self.on_game_update: Optional[Callable] = None
        self.on_phase_change: Optional[Callable] = None
        self.on_player_death: Optional[Callable] = None
        
        # Thread para timers (opcional)
        self._timer_thread: Optional[Thread] = None
        self._stop_timer = False
        
        logger.info(f"GUIGameController initialized (debug={debug_mode})")
    
    # ========================================================================
    # GESTIÓN DE PARTIDA
    # ========================================================================
    
    def create_game(self, host_name: str = "Host") -> Game:
        """Crea una nueva partida local."""
        # Usar chat_id ficticio para GUI (número positivo)
        chat_id = int(time.time())
        host_id = 1  # ID ficticio para el host
        
        self.game = Game(chat_id=chat_id, host_id=host_id)
        
        # Agregar host como primer jugador
        self.game.players[host_id] = Player(user_id=host_id, name=host_name)
        
        logger.info(f"Created local game {chat_id}")
        self._notify_update()
        
        return self.game
    
    def add_player(self, name: str) -> bool:
        """Agrega un jugador a la partida."""
        if not self.game:
            logger.warning("Cannot add player: no game exists")
            return False
        
        if self.game.phase != Phase.LOBBY:
            logger.warning("Cannot add player: game already started")
            return False
        
        # Generar ID único
        user_id = len(self.game.players) + 1
        
        if user_id in self.game.players:
            logger.warning(f"Player {user_id} already exists")
            return False
        
        self.game.players[user_id] = Player(user_id=user_id, name=name)
        logger.info(f"Added player {name} (id={user_id})")
        self._notify_update()
        
        return True
    
    def remove_player(self, user_id: int) -> bool:
        """Elimina un jugador de la partida."""
        if not self.game or user_id not in self.game.players:
            return False
        
        if self.game.phase != Phase.LOBBY:
            logger.warning("Cannot remove player: game already started")
            return False
        
        player = self.game.players.pop(user_id)
        logger.info(f"Removed player {player.name}")
        self._notify_update()
        
        return True
    
    def start_game(self) -> List[str]:
        """
        Inicia la partida.
        
        Returns:
            Lista de errores (vacía si todo OK)
        """
        if not self.game:
            return ["No hay partida creada"]
        
        if self.game.phase != Phase.LOBBY:
            return ["La partida ya ha comenzado"]
        
        if len(self.game.players) < 4:
            return [f"Se necesitan al menos 4 jugadores (actual: {len(self.game.players)})"]
        
        # Asignar roles
        errors = self.engine.assign_roles(self.game)
        if errors:
            return errors
        
        # Cambiar a fase NIGHT
        self.game.phase = Phase.NIGHT
        self.game.phase_deadline = int(time.time()) + self.game.night_seconds
        
        logger.info(f"Game started with {len(self.game.players)} players")
        self._notify_phase_change(Phase.NIGHT)
        
        # Iniciar timer automático (opcional)
        if self.game.night_seconds > 0:
            self._start_phase_timer()
        
        return []
    
    def reset_game(self):
        """Resetea la partida al estado de lobby."""
        if not self.game:
            return
        
        self._stop_timer_thread()
        self.game.reset_to_lobby()
        
        logger.info("Game reset to lobby")
        self._notify_update()
    
    def end_game(self):
        """Termina la partida completamente."""
        if self.game:
            self._stop_timer_thread()
            self.game.phase = Phase.FINISHED
            logger.info("Game ended")
            self._notify_update()
    
    # ========================================================================
    # ACCIONES DE JUEGO
    # ========================================================================
    
    def register_night_action(self, actor_id: int, target_id: int) -> bool:
        """
        Registra una acción nocturna.
        
        Args:
            actor_id: ID del jugador que actúa
            target_id: ID del objetivo
        
        Returns:
            True si se registró correctamente
        """
        if not self.game or self.game.phase != Phase.NIGHT:
            return False
        
        actor = self.game.players.get(actor_id)
        if not actor or not actor.alive or not actor.role_key:
            return False
        
        role = get_role(actor.role_key)
        if not role or not role.has_night_action:
            return False
        
        # Mapeo de roles a tipos de acción
        action_map = {
            "doctor": "heal",
            "detective": "investigate",
            "sheriff": "investigate",
            "escort": "block",
            "guardaespaldas": "guard",
            "vigilante": "vigilante_kill",
            "asesino": "serial_kill",
            "consorte": "block",
            "consigliere": "investigate",
            "chantajeador": "blackmail"
        }
        
        action_type = action_map.get(role.key)
        if not action_type:
            return False
        
        # Remover acciones previas del mismo actor
        from core.models import NightAction
        self.game.night_actions = [
            a for a in self.game.night_actions
            if a.actor_id != actor_id or a.action_type != action_type
        ]
        
        # Agregar nueva acción
        self.game.night_actions.append(
            NightAction(
                actor_id=actor_id,
                target_id=target_id,
                action_type=action_type,
                priority=role.priority
            )
        )
        
        logger.info(f"Night action registered: {actor.name} -> {action_type} -> {target_id}")
        self._notify_update()
        
        return True
    
    def register_mafia_vote(self, voter_id: int, target_id: int) -> bool:
        """Registra el voto de un mafioso."""
        if not self.game or self.game.phase != Phase.NIGHT:
            return False
        
        voter = self.game.players.get(voter_id)
        if not voter or not voter.alive:
            return False
        
        role = get_role(voter.role_key) if voter.role_key else None
        if not role or role.faction.value != "mafia":
            return False
        
        self.game.mafia_votes[voter_id] = target_id
        logger.info(f"Mafia vote: {voter.name} -> {target_id}")
        self._notify_update()
        
        return True
    
    def register_day_vote(self, voter_id: int, target_id: int) -> bool:
        """Registra un voto diurno."""
        if not self.game or self.game.phase != Phase.VOTING:
            return False
        
        voter = self.game.players.get(voter_id)
        if not voter or not voter.alive or voter.silenced:
            return False
        
        self.game.day_votes[voter_id] = target_id
        logger.info(f"Day vote: {voter.name} -> {target_id}")
        self._notify_update()
        
        return True
    
    # ========================================================================
    # RESOLUCIÓN DE FASES
    # ========================================================================
    
    def resolve_night(self) -> List[str]:
        """
        Resuelve la noche y retorna mensajes de eventos.
        
        Returns:
            Lista de mensajes describiendo lo ocurrido
        """
        if not self.game or self.game.phase != Phase.NIGHT:
            return ["No es de noche"]
        
        events = self.engine.resolve_night(self.game)
        messages = []
        
        # Procesar muertes
        deaths = [e for e in events if e.event_type == "death"]
        if deaths:
            for event in deaths:
                victim = self.game.players.get(event.target_id)
                if victim:
                    role = get_role(victim.role_key) if victim.role_key else None
                    role_name = role.name if role else "Desconocido"
                    messages.append(f"💀 {victim.name} ha muerto. Era {role_name}.")
                    
                    if self.on_player_death:
                        self.on_player_death(victim)
        else:
            messages.append("✨ Esta noche no hubo muertes.")
        
        # Limpiar estado nocturno
        self.game.clear_night_state()
        
        # Verificar victoria
        winner = self.engine.check_victory(self.game)
        if winner:
            self.game.phase = Phase.FINISHED
            messages.append(self._get_winner_message(winner))
            self._notify_phase_change(Phase.FINISHED)
            return messages
        
        # Cambiar a día
        self.game.phase = Phase.DAY
        self.game.phase_deadline = int(time.time()) + self.game.day_seconds
        
        logger.info("Night resolved, transitioning to day")
        self._notify_phase_change(Phase.DAY)
        
        if self.game.day_seconds > 0:
            self._start_phase_timer()
        
        return messages
    
    def start_voting(self):
        """Inicia la fase de votación."""
        if not self.game or self.game.phase != Phase.DAY:
            return
        
        self.game.phase = Phase.VOTING
        self.game.phase_deadline = int(time.time()) + 120  # 2 minutos
        
        logger.info("Starting voting phase")
        self._notify_phase_change(Phase.VOTING)
        
        self._start_phase_timer()
    
    def resolve_votes(self) -> List[str]:
        """
        Resuelve la votación diurna.
        
        Returns:
            Lista de mensajes describiendo el resultado
        """
        if not self.game or self.game.phase != Phase.VOTING:
            return ["No es momento de votar"]
        
        lynched_id, events = self.engine.resolve_votes(self.game)
        messages = []
        
        # Verificar resultado
        tie_event = next((e for e in events if e.event_type == "vote_tie"), None)
        
        if tie_event:
            messages.append("⚖️ Empate en la votación. No se lincha a nadie.")
        elif lynched_id:
            lynched = self.game.players.get(lynched_id)
            if lynched:
                role = get_role(lynched.role_key) if lynched.role_key else None
                role_name = role.name if role else "Desconocido"
                messages.append(f"⚖️ {lynched.name} ha sido linchado. Era {role_name}.")
                
                if self.on_player_death:
                    self.on_player_death(lynched)
        else:
            messages.append("🤷 No hubo suficientes votos.")
        
        # Limpiar votos
        self.game.clear_day_state()
        
        # Verificar victoria
        winner = self.engine.check_victory(self.game)
        if winner:
            self.game.phase = Phase.FINISHED
            messages.append(self._get_winner_message(winner))
            self._notify_phase_change(Phase.FINISHED)
            return messages
        
        # Volver a la noche
        self.game.phase = Phase.NIGHT
        self.game.phase_deadline = int(time.time()) + self.game.night_seconds
        
        logger.info("Votes resolved, transitioning to night")
        self._notify_phase_change(Phase.NIGHT)
        
        if self.game.night_seconds > 0:
            self._start_phase_timer()
        
        return messages
    
    # ========================================================================
    # UTILIDADES
    # ========================================================================
    
    def get_player_role(self, user_id: int) -> Optional[str]:
        """Obtiene el rol de un jugador (respeta debug_mode)."""
        if not self.game or user_id not in self.game.players:
            return None
        
        player = self.game.players[user_id]
        
        # En debug mode, siempre mostrar
        if self.debug_mode:
            return player.role_key
        
        # Solo mostrar si está muerto
        if not player.alive:
            return player.role_key
        
        return None
    
    def _get_winner_message(self, winner: str) -> str:
        """Genera mensaje de victoria."""
        messages = {
            "town": "🎉 ¡El Pueblo ha ganado!",
            "mafia": "😈 ¡La Mafia ha ganado!",
            "serial": "🔪 ¡El Asesino en Serie ha ganado!",
            "jester": "🤡 ¡El Bufón ha ganado!"
        }
        return messages.get(winner, f"🏆 {winner} ha ganado!")
    
    # ========================================================================
    # TIMERS Y CALLBACKS
    # ========================================================================
    
    def _start_phase_timer(self):
        """Inicia un timer para cambio automático de fase."""
        self._stop_timer_thread()
        
        if not self.game or not self.game.phase_deadline:
            return
        
        self._stop_timer = False
        self._timer_thread = Thread(target=self._timer_worker, daemon=True)
        self._timer_thread.start()
    
    def _stop_timer_thread(self):
        """Detiene el thread del timer."""
        self._stop_timer = True
        if self._timer_thread and self._timer_thread.is_alive():
            self._timer_thread.join(timeout=1)
    
    def _timer_worker(self):
        """Worker thread para timer de fase."""
        while not self._stop_timer and self.game:
            if not self.game.phase_deadline:
                break
            
            remaining = self.game.phase_deadline - int(time.time())
            
            if remaining <= 0:
                # Tiempo agotado, avanzar fase
                self._on_timer_expired()
                break
            
            time.sleep(1)
    
    def _on_timer_expired(self):
        """Callback cuando expira el timer de fase."""
        if not self.game:
            return
        
        logger.info(f"Phase timer expired for {self.game.phase}")
        
        if self.game.phase == Phase.NIGHT:
            # Auto-resolver noche
            try:
                self.app.root.after(0, self._auto_resolve_night)
            except Exception as e:
                logger.exception("Error auto-resolving night")
        
        elif self.game.phase == Phase.DAY:
            # Auto-iniciar votación
            try:
                self.app.root.after(0, self.start_voting)
            except Exception as e:
                logger.exception("Error starting voting")
        
        elif self.game.phase == Phase.VOTING:
            # Auto-resolver votos
            try:
                self.app.root.after(0, self._auto_resolve_votes)
            except Exception as e:
                logger.exception("Error auto-resolving votes")
    
    def _auto_resolve_night(self):
        """Auto-resuelve la noche (llamado desde UI thread)."""
        messages = self.resolve_night()
        # La UI debería mostrar estos mensajes
        if hasattr(self.app, 'show_messages'):
            self.app.show_messages("Fin de la Noche", messages)
    
    def _auto_resolve_votes(self):
        """Auto-resuelve votos (llamado desde UI thread)."""
        messages = self.resolve_votes()
        if hasattr(self.app, 'show_messages'):
            self.app.show_messages("Resultado de Votación", messages)
    
    def _notify_update(self):
        """Notifica a la UI que hubo un cambio."""
        if self.on_game_update:
            try:
                self.on_game_update()
            except Exception as e:
                logger.exception("Error in on_game_update callback")
    
    def _notify_phase_change(self, new_phase: Phase):
        """Notifica cambio de fase."""
        if self.on_phase_change:
            try:
                self.on_phase_change(new_phase)
            except Exception as e:
                logger.exception("Error in on_phase_change callback")
    
    def cleanup(self):
        """Limpieza al cerrar."""
        self._stop_timer_thread()
        logger.info("GUIGameController cleaned up")
