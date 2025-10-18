# gui/controllers/game_state_controller.py
"""
GameStateController - lógica pura del juego, independiente de UI.

Responsabilidades:
- Ejecutar resolución de fases (noche/votos) usando el engine.
- Registrar/normalizar mensajes de chat.
- Publicar eventos en un bus agnóstico.
- No realiza operaciones de UI ni threading.
"""
from typing import Optional, List, Any, Callable, Tuple
from collections import defaultdict
from types import SimpleNamespace
import time
import logging

logger = logging.getLogger(__name__)

# Tipos genéricos para evitar dependencias fuertes
GameEvent = Any
Game = Any
GameEngine = Any


class GameEventBus:
    """Event bus simple (no bloqueante). Suscriptores por event_type (str)."""

    def __init__(self):
        self.subscribers = defaultdict(list)

    def subscribe(self, event_type: str, callback: Callable[[Any], None]):
        """Registra un callback para un tipo de evento."""
        self.subscribers[event_type].append(callback)

    def publish(self, event: Any):
        """
        Publica un evento a todos los subscriptores del tipo event.event_type (si existe).
        Si event no tiene event_type, se publica en la clave '*' (broadcast).
        """
        event_type = getattr(event, "event_type", "*")
        # publicar en event_type y también en '*' para listeners globales
        targets = list(self.subscribers.get(event_type, [])) + list(self.subscribers.get("*", []))
        for callback in targets:
            try:
                callback(event)
            except Exception:
                logger.exception("Error in event subscriber callback")


class GameStateController:
    """
    Capa de lógica independiente de UI.

    - Mantiene referencia al engine (GameEngine).
    - Puede mantener una partida actual (game), pero la mayoría de métodos acepta 'game' como argumento.
    - Expone un event_bus para que adaptadores (UI, bot, tests) se suscriban.
    - Llama opcionalmente a self.on_event(ev) para compatibilidad.
    """

    def __init__(self, engine: GameEngine):
        self.engine = engine
        self.game: Optional[Game] = None
        self.on_event: Optional[Callable[[GameEvent], None]] = None
        self.event_bus = GameEventBus()

    def set_game(self, game: Game):
        """Asociar/actualizar la partida gestionada por este controlador."""
        self.game = game

    def resolve_night(self, game: Optional[Game] = None) -> List[GameEvent]:
        """
        Resuelve la fase de noche usando el engine y publica los eventos resultantes.
        Devuelve la lista de eventos generados por el engine.
        """
        if game is None:
            game = self.game
        if game is None:
            return []

        # Delegar la resolución al engine
        events = []
        try:
            events = self.engine.resolve_night(game) or []
        except Exception:
            logger.exception("Engine failed resolving night")
            events = []

        # Normalizar (asegurar que cada event tiene event_type) y publicar
        normalized = []
        for ev in events:
            if not hasattr(ev, "event_type"):
                # si es un dict-like, transformarlo (conservador)
                try:
                    ev_type = ev.get("event_type", "unknown") if isinstance(ev, dict) else "unknown"
                except Exception:
                    ev_type = "unknown"
                ns = SimpleNamespace(event_type=ev_type, **(ev if isinstance(ev, dict) else {}))
                ev = ns
            normalized.append(ev)

        # Callback on_event (compatibilidad)
        if self.on_event:
            try:
                for ev in normalized:
                    self.on_event(ev)
            except Exception:
                logger.exception("Error calling on_event callback")

        # Publicar en bus
        try:
            for ev in normalized:
                self.event_bus.publish(ev)
        except Exception:
            logger.exception("Error publishing events to bus")

        return normalized

    def resolve_votes(self, game: Optional[Game] = None) -> Tuple[Any, List[GameEvent]]:
        """Wrapper para delegar resolución de votos al engine."""
        if game is None:
            game = self.game
        if game is None:
            return None, []

        try:
            lynched_id, events = self.engine.resolve_votes(game)
        except Exception:
            logger.exception("Engine failed resolving votes")
            return None, []

        # Normalizar/publish
        normalized = []
        for ev in events or []:
            if not hasattr(ev, "event_type") and isinstance(ev, dict):
                ev = SimpleNamespace(**ev)
            normalized.append(ev)

        try:
            for ev in normalized:
                self.event_bus.publish(ev)
        except Exception:
            logger.exception("Error publishing vote events")
        return lynched_id, normalized

    def register_chat_message(self, sender_id: int, text: str, is_private: bool = False) -> SimpleNamespace:
        """
        Normaliza y publica un mensaje de chat.
        Retorna el objeto message (SimpleNamespace) con los campos esperados por la UI.
        """
        # Intentar obtener información del jugador desde self.game
        player = None
        try:
            if self.game and getattr(self.game, "players", None):
                player = self.game.players.get(sender_id)
            # Si engine tiene get_player, preferirlo
            if player is None and hasattr(self.engine, "get_player"):
                try:
                    p = self.engine.get_player(sender_id)
                    if p:
                        player = p
                except Exception:
                    pass
        except Exception:
            logger.exception("Error obtaining player for chat message")

        sender_name = getattr(player, "name", f"user_{sender_id}")
        msg = SimpleNamespace(
            event_type="chat",
            sender_id=sender_id,
            sender_name=sender_name,
            text=text,
            channel="private" if is_private else "general",
            timestamp=int(time.time())
        )

        # Publish on bus (broadcast)
        try:
            self.event_bus.publish(msg)
        except Exception:
            logger.exception("Error publishing chat message to event bus")

        # Also call on_event if present (backward compatibility)
        if self.on_event:
            try:
                self.on_event(msg)
            except Exception:
                logger.exception("Error calling on_event for chat message")

        return msg

    # Convenience wrapper: add player (UI may call)
    def add_player(self, game: Optional[Game], user_id: int, name: str) -> bool:
        if game is None:
            game = self.game
        if game is None:
            return False

        # Prefer engine API if available
        if hasattr(self.engine, "add_player"):
            try:
                self.engine.add_player(game, user_id, name)
                return True
            except Exception:
                logger.exception("Error adding player via engine")
                return False

        # Fallback: mutate game.players
        try:
            game.players[user_id] = type("P", (), {"user_id": user_id, "name": name})()
            return True
        except Exception:
            logger.exception("Fallback add_player failed")
            return False
