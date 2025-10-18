# gui/controllers/game_controller.py
"""
GUIGameController - adaptador UI entre la vista (Tkinter) y la lógica (engine/GameStateController).

Responsabilidades:
- Mantener estado de UI (bots, player_types, perspectivas, mensajes).
- Inyectar y sincronizar con GameStateController (lógica pura).
- Manejar timers y callbacks al hilo de UI (app.root.after).
- No debe contener lógica de juego compleja (esa está en engine/state_controller).
"""
import logging
import time
import random
from typing import Optional, List, Callable, Dict, Any
from threading import Thread
from types import SimpleNamespace

from gui.bots.bot_player import BotPlayer, BotDifficulty
from gui.controllers.player_perspective import PlayerPerspective
from gui.controllers.game_state_controller import GameStateController
from core.models import Game, Player, Phase
from core.engine import GameEngine
from core.roles import get_role

logger = logging.getLogger(__name__)


class GUIGameController:
    def __init__(self, app: Any, debug_mode: bool = False):
        """
        Args:
            app: referencia a la aplicación principal (MafiaGUIApp).
            debug_mode: si True muestra roles a la vista.
        """
        self.app = app
        self.game: Optional[Game] = None
        self.engine = GameEngine()
        self.debug_mode = debug_mode

        # Estado UI
        self.bots: Dict[int, BotPlayer] = {}
        self.player_types: Dict[int, str] = {}
        self.messages: List[SimpleNamespace] = []
        self.perspectives: Dict[int, PlayerPerspective] = {}

        # Callbacks (vista)
        self.on_chat_message: Optional[Callable[[Any], None]] = None
        self.on_game_update: Optional[Callable[[], None]] = None
        self.on_phase_change: Optional[Callable[[Phase], None]] = None
        self.on_player_death: Optional[Callable[[Any], None]] = None

        # Timer thread control
        self._timer_thread: Optional[Thread] = None
        self._stop_timer = False

        # Crear GameStateController (lógica pura)
        self.state_controller = GameStateController(self.engine)
        # Compatibilidad con código histórico:
        self.controller = self.state_controller

        # Subscribir a eventos (chat y game events)
        self.state_controller.event_bus.subscribe("*", self._handle_state_event)
        # on_event también para compatibilidad (se ejecutará además)
        self.state_controller.on_event = self._handle_state_event

        logger.info(f"GUIGameController initialized (debug={debug_mode})")

    # ---------------------------
    # GESTIÓN DE PARTIDA (UI-side)
    # ---------------------------
    def create_game(self, host_name: str = "Host") -> Game:
        chat_id = int(time.time() * 1000)
        host_id = 1

        self.game = Game(chat_id=chat_id, host_id=host_id)

        # Asegurar campos básicos para evitar AttributeError
        if not hasattr(self.game, "players") or self.game.players is None:
            self.game.players = {}
        self.game.players[host_id] = Player(user_id=host_id, name=host_name)

        # Inicializar contenedores
        if not hasattr(self.game, "night_actions") or self.game.night_actions is None:
            self.game.night_actions = []
        if not hasattr(self.game, "mafia_votes") or self.game.mafia_votes is None:
            self.game.mafia_votes = {}
        if not hasattr(self.game, "day_votes") or self.game.day_votes is None:
            self.game.day_votes = {}

        # Sincronizar con state_controller
        try:
            self.state_controller.set_game(self.game)
        except Exception:
            logger.exception("Failed to set game on state_controller")

        logger.info(f"Created local game {chat_id}")
        self._notify_update()
        return self.game

    def add_player(self, name: str) -> bool:
        if not self.game:
            logger.warning("Cannot add player: no game exists")
            return False
        if self.game.phase != Phase.LOBBY:
            logger.warning("Cannot add player: game already started")
            return False

        user_id = len(self.game.players) + 1
        if user_id in self.game.players:
            logger.warning(f"Player {user_id} already exists")
            return False

        self.game.players[user_id] = Player(user_id=user_id, name=name)

        # sincronizar con state controller (opcional)
        try:
            self.state_controller.set_game(self.game)
        except Exception:
            logger.exception("Failed to sync game after add_player")

        logger.info(f"Added player {name} (id={user_id})")
        self._notify_update()
        return True

    def remove_player(self, user_id: int) -> bool:
        if not self.game or user_id not in self.game.players:
            return False
        if self.game.phase != Phase.LOBBY:
            logger.warning("Cannot remove player: game already started")
            return False

        player = self.game.players.pop(user_id)
        try:
            self.state_controller.set_game(self.game)
        except Exception:
            logger.exception("Failed to sync game after remove_player")

        logger.info(f"Removed player {player.name}")
        self._notify_update()
        return True

    def start_game(self) -> List[str]:
        if not self.game:
            return ["No hay partida creada"]
        if self.game.phase != Phase.LOBBY:
            return ["La partida ya ha comenzado"]
        if len(self.game.players) < 4:
            return [f"Se necesitan al menos 4 jugadores (actual: {len(self.game.players)})"]

        # Delegamos asignación de roles al engine
        errors = self.engine.assign_roles(self.game)
        if errors:
            return errors

        # Crear perspectivas y bots
        self.initialize_perspectives()
        self.set_player_types(self.player_types)

        # Cambiar fase y sincronizar
        self.game.phase = Phase.NIGHT
        self.game.phase_deadline = int(time.time()) + getattr(self.game, "night_seconds", 300)

        try:
            self.state_controller.set_game(self.game)
        except Exception:
            logger.exception("Failed to set game on state_controller at start_game")

        logger.info(f"Game started with {len(self.game.players)} players")
        self._notify_phase_change(Phase.NIGHT)

        # Abrir ventanas de perspectiva si la app lo soporta
        if hasattr(self.app, "open_perspective_window"):
            for pid in list(self.perspectives.keys()):
                try:
                    # builder puede ser la perspectiva (view) si tu app lo requiere; aquí solo intento abrir
                    self.app.open_perspective_window(pid)
                except Exception:
                    logger.exception("Error opening perspective window for %s", pid)

        if getattr(self.game, "night_seconds", 0) > 0:
            self._start_phase_timer()

        return []

    def reset_game(self):
        if not self.game:
            return
        self._stop_timer_thread()
        try:
            self.game.reset_to_lobby()
        except Exception:
            logger.exception("Error resetting game to lobby")
        self._notify_update()

    def end_game(self):
        if self.game:
            self._stop_timer_thread()
            self.game.phase = Phase.FINISHED
            logger.info("Game ended")
            self._notify_update()

    # ---------------------------
    # ACCIONES Y RESOLUCIONES
    # ---------------------------
    def register_night_action(self, actor_id: int, target_id: int) -> bool:
        if not self.game or self.game.phase != Phase.NIGHT:
            return False
        actor = self.game.players.get(actor_id)
        if not actor or not getattr(actor, "alive", True) or not getattr(actor, "role_key", None):
            return False
        role = get_role(actor.role_key)
        if not role or not getattr(role, "has_night_action", False):
            return False

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

        from core.models import NightAction
        self.game.night_actions = [
            a for a in getattr(self.game, "night_actions", [])
            if not (a.actor_id == actor_id and a.action_type == action_type)
        ]
        self.game.night_actions.append(
            NightAction(actor_id=actor_id, target_id=target_id, action_type=action_type, priority=role.priority)
        )
        logger.info(f"Night action registered: {actor.name} -> {action_type} -> {target_id}")

        # Sincronizar con state controller: set_game no es obligatorio aquí, engine leerá game referencia
        # Publicar la actualización a la UI
        self._notify_update()
        return True

    def register_mafia_vote(self, voter_id: int, target_id: int) -> bool:
        if not self.game or self.game.phase != Phase.NIGHT:
            return False
        voter = self.game.players.get(voter_id)
        if not voter or not getattr(voter, "alive", True):
            return False
        role = get_role(voter.role_key) if getattr(voter, "role_key", None) else None
        if not role or getattr(getattr(role, "faction", None), "value", "") != "mafia":
            return False

        if not hasattr(self.game, "mafia_votes") or self.game.mafia_votes is None:
            self.game.mafia_votes = {}
        self.game.mafia_votes[voter_id] = target_id
        logger.info(f"Mafia vote: {voter.name} -> {target_id}")
        self._notify_update()
        return True

    def register_day_vote(self, voter_id: int, target_id: int) -> bool:
        if not self.game or self.game.phase != Phase.VOTING:
            return False
        voter = self.game.players.get(voter_id)
        if not voter or not getattr(voter, "alive", True) or getattr(voter, "silenced", False):
            return False

        if not hasattr(self.game, "day_votes") or self.game.day_votes is None:
            self.game.day_votes = {}
        self.game.day_votes[voter_id] = target_id
        logger.info(f"Day vote: {voter.name} -> {target_id}")
        self._notify_update()
        return True

    def resolve_night(self) -> List[str]:
        if not self.game or self.game.phase != Phase.NIGHT:
            return ["No es de noche"]

        # Ejecutar decisiones de bots (poblar night_actions, mafia_votes)
        try:
            self.execute_bot_actions()
        except Exception:
            logger.exception("Error executing bot actions from GUI controller")

        # Delegar la resolución al state_controller (publicará eventos)
        events = []
        try:
            events = self.state_controller.resolve_night(self.game)
        except Exception:
            logger.exception("Error resolving night via state_controller")

        messages: List[str] = []
        deaths = [e for e in events if getattr(e, "event_type", "") in ("death", "lynch", "bodyguard_death")]
        if deaths:
            for ev in deaths:
                victim = self.game.players.get(getattr(ev, "target_id", None))
                if victim:
                    role = get_role(getattr(victim, "role_key", None)) if getattr(victim, "role_key", None) else None
                    role_name = getattr(role, "name", "Desconocido") if role else "Desconocido"
                    messages.append(f"💀 {victim.name} ha muerto. Era {role_name}.")
                    if self.on_player_death:
                        try:
                            self.on_player_death(victim)
                        except Exception:
                            logger.exception("on_player_death callback failed")
        else:
            messages.append("✨ Esta noche no hubo muertes.")

        # Limpiar estado nocturno si existe
        try:
            if hasattr(self.game, "clear_night_state"):
                self.game.clear_night_state()
        except Exception:
            logger.exception("Error clearing night state")

        # Verificar victoria
        try:
            winner = self.engine.check_victory(self.game)
            if winner:
                self.game.phase = Phase.FINISHED
                messages.append(self._get_winner_message(winner))
                self._notify_phase_change(Phase.FINISHED)
                return messages
        except Exception:
            logger.exception("Error checking victory")

        # Cambiar a día
        self.game.phase = Phase.DAY
        self.game.phase_deadline = int(time.time()) + getattr(self.game, "day_seconds", 600)
        logger.info("Night resolved, transitioning to day")
        self._notify_phase_change(Phase.DAY)
        if getattr(self.game, "day_seconds", 0) > 0:
            self._start_phase_timer()

        # Ejecutar reportes de bots investigadores (si procede)
        try:
            self.execute_bot_chat_reports()
        except Exception:
            logger.exception("Error executing bot chat reports")

        return messages

    def start_voting(self):
        if not self.game or self.game.phase != Phase.DAY:
            return
        self.game.phase = Phase.VOTING
        self.game.phase_deadline = int(time.time()) + 120
        logger.info("Starting voting phase")
        self._notify_phase_change(Phase.VOTING)
        self._start_phase_timer()

    def resolve_votes(self) -> List[str]:
        if not self.game or self.game.phase != Phase.VOTING:
            return ["No es momento de votar"]

        lynched_id, events = self.state_controller.resolve_votes(self.game)
        messages: List[str] = []
        tie_event = next((e for e in events if getattr(e, "event_type", "") == "vote_tie"), None)
        if tie_event:
            messages.append("⚖️ Empate en la votación. No se lincha a nadie.")
        elif lynched_id:
            lynched = self.game.players.get(lynched_id)
            if lynched:
                role = get_role(getattr(lynched, "role_key", None)) if getattr(lynched, "role_key", None) else None
                role_name = getattr(role, "name", "Desconocido") if role else "Desconocido"
                messages.append(f"⚖️ {lynched.name} ha sido linchado. Era {role_name}.")
                if self.on_player_death:
                    try:
                        self.on_player_death(lynched)
                    except Exception:
                        logger.exception("on_player_death callback failed")
        else:
            messages.append("🤷 No hubo suficientes votos.")

        try:
            if hasattr(self.game, "clear_day_state"):
                self.game.clear_day_state()
        except Exception:
            logger.exception("Error clearing day state")

        # Comprobar victoria
        try:
            winner = self.engine.check_victory(self.game)
            if winner:
                self.game.phase = Phase.FINISHED
                messages.append(self._get_winner_message(winner))
                self._notify_phase_change(Phase.FINISHED)
                return messages
        except Exception:
            logger.exception("Error checking victory after votes")

        # Volver a la noche
        self.game.phase = Phase.NIGHT
        self.game.phase_deadline = int(time.time()) + getattr(self.game, "night_seconds", 300)
        logger.info("Votes resolved, transitioning to night")
        self._notify_phase_change(Phase.NIGHT)
        if getattr(self.game, "night_seconds", 0) > 0:
            self._start_phase_timer()

        return messages

    # ---------------------------
    # UTILIDADES / TIMERS / CALLBACKS
    # ---------------------------
    def get_player_role(self, user_id: int) -> Optional[str]:
        if not self.game or user_id not in self.game.players:
            return None
        player = self.game.players[user_id]
        if self.debug_mode:
            return getattr(player, "role_key", None)
        if not getattr(player, "alive", True):
            return getattr(player, "role_key", None)
        return None

    def _get_winner_message(self, winner: str) -> str:
        messages = {
            "town": "🎉 ¡El Pueblo ha ganado!",
            "mafia": "😈 ¡La Mafia ha ganado!",
            "serial": "🔪 ¡El Asesino en Serie ha ganado!",
            "jester": "🤡 ¡El Bufón ha ganado!"
        }
        return messages.get(winner, f"🏆 {winner} ha ganado!")

    def _start_phase_timer(self):
        self._stop_timer_thread()
        if not self.game or not getattr(self.game, "phase_deadline", None):
            return
        self._stop_timer = False
        self._timer_thread = Thread(target=self._timer_worker, daemon=True)
        self._timer_thread.start()

    def _stop_timer_thread(self):
        self._stop_timer = True
        if self._timer_thread and self._timer_thread.is_alive():
            self._timer_thread.join(timeout=1)

    def _timer_worker(self):
        while not self._stop_timer and self.game:
            if not getattr(self.game, "phase_deadline", None):
                break
            remaining = self.game.phase_deadline - int(time.time())
            if remaining <= 0:
                self._on_timer_expired()
                break
            time.sleep(1)

    def _on_timer_expired(self):
        if not self.game:
            return
        logger.info(f"Phase timer expired for {self.game.phase}")
        try:
            if self.game.phase == Phase.NIGHT:
                if hasattr(self.app, "root"):
                    self.app.root.after(0, self._auto_resolve_night)
                else:
                    self._auto_resolve_night()
            elif self.game.phase == Phase.DAY:
                if hasattr(self.app, "root"):
                    self.app.root.after(0, self.start_voting)
                else:
                    self.start_voting()
            elif self.game.phase == Phase.VOTING:
                if hasattr(self.app, "root"):
                    self.app.root.after(0, self._auto_resolve_votes)
                else:
                    self._auto_resolve_votes()
        except Exception:
            logger.exception("Error scheduling UI callbacks on timer expiry")

    def _auto_resolve_night(self):
        messages = self.resolve_night()
        if hasattr(self.app, "show_messages"):
            try:
                self.app.show_messages("Fin de la Noche", messages)
            except Exception:
                logger.exception("show_messages failed")

    def _auto_resolve_votes(self):
        messages = self.resolve_votes()
        if hasattr(self.app, "show_messages"):
            try:
                self.app.show_messages("Resultado de Votación", messages)
            except Exception:
                logger.exception("show_messages failed")

    def _notify_update(self):
        if self.on_game_update:
            try:
                if hasattr(self.app, "root"):
                    self.app.root.after(0, lambda: self.on_game_update())
                else:
                    self.on_game_update()
            except Exception:
                logger.exception("Error in on_game_update callback")

    def _notify_phase_change(self, new_phase: Phase):
        if self.on_phase_change:
            try:
                if hasattr(self.app, "root"):
                    self.app.root.after(0, lambda: self.on_phase_change(new_phase))
                else:
                    self.on_phase_change(new_phase)
            except Exception:
                logger.exception("Error in on_phase_change callback")

    def cleanup(self):
        self._stop_timer_thread()
        logger.info("GUIGameController cleaned up")

    # ---------------------------
    # SISTEMA DE BOTS (GUI-side decisions)
    # ---------------------------
    def create_bot_player(self, player_id: int, name: str, difficulty: str = "normal"):
        difficulty_map = {
            "bot_easy": BotDifficulty.EASY,
            "bot_normal": BotDifficulty.NORMAL,
            "bot_hard": BotDifficulty.HARD,
        }
        diff = difficulty_map.get(difficulty, BotDifficulty.NORMAL)
        bot = BotPlayer(player_id, name, diff)
        self.bots[player_id] = bot
        self.player_types[player_id] = difficulty
        logger.info(f"Created bot: {name} ({difficulty})")

    def set_player_types(self, player_types: Dict[int, str]):
        self.player_types = player_types
        for player_id, player_type in player_types.items():
            if player_type.startswith("bot"):
                player = self.game.players.get(player_id)
                if player:
                    self.create_bot_player(player_id, player.name)

    def execute_bot_actions(self):
        """Ejecuta acciones decididas por bots (llamadas a métodos del controlador)."""
        if not self.game:
            return
        for player_id, bot in list(self.bots.items()):
            if player_id not in self.game.players:
                continue
            player = self.game.players[player_id]
            if self.game.phase == Phase.NIGHT:
                target_id, action_type = bot.decide_night_action(self.game, player)
                if action_type == "mafia_vote":
                    if target_id:
                        self.register_mafia_vote(player_id, target_id)
                elif action_type and target_id:
                    self.register_night_action(player_id, target_id)
                bot.next_night()
            elif self.game.phase == Phase.VOTING:
                vote_target = bot.decide_day_vote(self.game, player)
                if vote_target:
                    self.register_day_vote(player_id, vote_target)

    def execute_bot_chat_reports(self):
        """Bots que reportan hallazgos durante el día."""
        if not self.game or self.game.phase != Phase.DAY:
            return
        for player_id, bot in list(self.bots.items()):
            player = self.game.players.get(player_id)
            if not player or not getattr(player, "alive", True) or not getattr(player, "role_key", None):
                continue
            if getattr(player, "role_key", "") in ["detective", "sheriff", "consigliere"]:
                if random.random() < getattr(getattr(bot, "config", {}), "investigator_report_chance", 0.2):
                    if getattr(bot, "last_investigation_result", None):
                        target_name, result = bot.last_investigation_result
                        report = bot.generate_investigation_report(target_name, result)
                        self.send_chat_message(player_id, report, "general")

    # ---------------------------
    # CHAT / MENSAJES
    # ---------------------------
    def send_chat_message(self, sender_id: int, text: str, channel: str = "general"):
        """
        Envía un mensaje de chat - CORREGIDO para evitar duplicados.
        """
        if not self.game or sender_id not in self.game.players:
            return False

        player = self.game.players[sender_id]
        perspective = self.perspectives.get(sender_id)

        if perspective and channel not in perspective.get_available_chat_channels():
            logger.warning(f"Player {sender_id} trying to send to forbidden channel {channel}")
            return False

        # El state_controller se encarga de publicar el mensaje en el event bus
        # Nuestro _handle_state_event lo recibirá y lo añadirá a self.messages
        # NO lo añadimos manualmente aquí para evitar duplicados
        try:
            msg = self.state_controller.register_chat_message(
                sender_id,
                text,
                is_private=(channel != "general")
            )
            # El state_controller ya publicó el mensaje
            # _handle_state_event lo procesará automáticamente
            return True
        except Exception:
            logger.exception("Error registering chat message in state controller")
            return False

    def get_visible_chat_messages(self, viewer_id: int) -> List[SimpleNamespace]:
        perspective = self.perspectives.get(viewer_id)
        if not perspective:
            return []
        try:
            return [m for m in self.messages if perspective.can_see_chat_message(m)]
        except Exception:
            logger.exception("Error filtering visible chat messages")
            return list(self.messages)

    # ---------------------------
    # PERSPECTIVAS
    # ---------------------------
    def initialize_perspectives(self):
        if not self.game:
            return
        for player_id in list(self.game.players.keys()):
            self.perspectives[player_id] = PlayerPerspective(player_id, self.game)

    def get_player_perspective(self, player_id: int) -> Optional[PlayerPerspective]:
        return self.perspectives.get(player_id)

    # ---------------------------
    # HANDLER DE EVENTOS (desde GameStateController.event_bus / on_event)
    # ---------------------------

    def _handle_state_event(self, ev: Any):
        """
        Handler de eventos - CORREGIDO para evitar duplicados.
        """
        try:
            ev_type = getattr(ev, "event_type", None)

            # Para mensajes de chat, verificar duplicados
            if ev_type == "chat":
                # Crear un ID único basado en timestamp + sender + hash del texto
                msg_id = f"{getattr(ev, 'sender_id', 0)}_{getattr(ev, 'timestamp', 0)}_{hash(getattr(ev, 'text', ''))}"

                # Si ya procesamos este mensaje, ignorarlo
                if not hasattr(self, '_processed_message_ids'):
                    self._processed_message_ids = set()

                if msg_id in self._processed_message_ids:
                    logger.debug(f"Duplicate chat message ignored: {msg_id}")
                    return

                self._processed_message_ids.add(msg_id)

                # Limpiar IDs viejos (mantener últimos 1000)
                if len(self._processed_message_ids) > 1000:
                    old_ids = list(self._processed_message_ids)[:500]
                    self._processed_message_ids -= set(old_ids)

                # Almacenar mensaje
                self.messages.append(ev)

                # Notificar UI
                if self.on_chat_message:
                    try:
                        if hasattr(self.app, "root"):
                            self.app.root.after(0, lambda e=ev: self.on_chat_message(e))
                        else:
                            self.on_chat_message(ev)
                    except Exception:
                        logger.exception("on_chat_message callback failed")
                return

            # Eventos de investigación
            if ev_type == "investigation":
                actor = getattr(ev, "actor_id", None)
                target = getattr(ev, "target_id", None)
                details = getattr(ev, "details", {}) or {}
                result = details.get("result") if isinstance(details, dict) else None

                # Si actor es bot -> almacenar en bot
                b = self.bots.get(actor)
                if b:
                    target_name = self.game.players[target].name if self.game and target in self.game.players else str(target)
                    b.last_investigation_result = (target_name, result)
                    logger.info(f"Stored investigation result for bot {getattr(b, 'name', actor)}")
                else:
                    # Humano -> enviar mensaje privado
                    text = f"🔎 Resultado investigación sobre {self.game.players[target].name if self.game and target in self.game.players else target}: {result}"
                    try:
                        if hasattr(self.app, "send_private_message"):
                            self.app.send_private_message(actor, text)
                    except Exception:
                        logger.exception("Failed delivering investigation DM to human")
                return

            # Eventos de muerte
            if ev_type in ("death", "lynch", "bodyguard_death"):
                victim_id = getattr(ev, "target_id", None)
                victim_name = (self.game.players[victim_id].name if self.game and victim_id in self.game.players else str(victim_id))
                cause = getattr(ev, "details", {}).get("cause", None) if isinstance(getattr(ev, "details", {}), dict) else None
                text = f"💀 {victim_name} ha muerto." + (f" ({cause})" if cause else "")

                # Crear mensaje de sistema
                import time
                msg = type('SimpleNamespace', (), {
                    'event_type': 'chat',
                    'sender_id': 0,
                    'sender_name': 'Sistema',
                    'text': text,
                    'channel': 'general',
                    'timestamp': int(time.time())
                })()

                # Procesar como mensaje normal (ya tiene protección contra duplicados arriba)
                self._handle_state_event(msg)

                # Notificar callback de muerte
                if self.on_player_death and self.game and victim_id in self.game.players:
                    try:
                        if hasattr(self.app, "root"):
                            self.app.root.after(0, lambda: self.on_player_death(self.game.players[victim_id]))
                        else:
                            self.on_player_death(self.game.players[victim_id])
                    except Exception:
                        logger.exception("on_player_death callback failed")
                return

            # Otros eventos -> crear mensaje informativo
            if ev_type:
                import time
                short = f"• Evento: {ev_type}"
                if hasattr(ev, 'actor_id'):
                    short += f" actor={ev.actor_id}"
                if hasattr(ev, 'target_id'):
                    short += f" target={ev.target_id}"

                msg = type('SimpleNamespace', (), {
                    'event_type': 'chat',
                    'sender_id': 0,
                    'sender_name': 'Sistema',
                    'text': short,
                    'channel': 'system',
                    'timestamp': int(time.time())
                })()

                # Procesar como mensaje (con protección de duplicados)
                self._handle_state_event(msg)
                return

        except Exception:
            logger.exception("Error handling state event")
