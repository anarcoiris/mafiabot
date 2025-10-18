"""
gui/controllers/network_controller.py
Network-aware game controller that bridges GUI with multiplayer server.
"""
import logging
import asyncio
from typing import Optional, List
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from gui.controllers.game_controller import GUIGameController
from gui.network.client import GameClient, ConnectionState
from gui.network.sync_manager import SyncManager
from network.messages import (
    CreateGameMessage, JoinGameMessage, LeaveGameMessage, StartGameMessage,
    NightActionMessage, MafiaVoteMessage, DayVoteMessage, ChatMessage,
    ResolveNightMessage, StartVotingMessage, ResolveVotesMessage
)
from core.models import Phase

logger = logging.getLogger(__name__)


class NetworkGameController(GUIGameController):
    """
    Game controller for network mode.

    Extends GUIGameController to route actions through network instead of local engine.
    Maintains local state synchronized with server.
    """

    def __init__(self, app, client: GameClient, debug_mode: bool = False):
        """
        Initialize network controller.

        Args:
            app: Reference to MafiaGUIApp
            client: Connected GameClient instance
            debug_mode: Debug mode flag
        """
        # Initialize parent (but we won't use its engine directly)
        super().__init__(app, debug_mode)

        self.client = client
        self.sync_manager = SyncManager(client)
        self.network_mode = True

        # Setup sync manager callbacks
        self.sync_manager.on_game_updated = self._on_network_game_updated
        self.sync_manager.on_phase_changed = self._on_network_phase_changed
        self.sync_manager.on_player_action = self._on_network_player_action
        self.sync_manager.on_error = self._on_network_error

        # Setup client callbacks
        self.client.on_state_change = self._on_connection_state_changed

        logger.info("NetworkGameController initialized")

    # ==================== Network-specific Methods ====================

    def _on_connection_state_changed(self, new_state: ConnectionState):
        """Handle connection state changes."""
        logger.info(f"Connection state changed to: {new_state.value}")

        if new_state == ConnectionState.DISCONNECTED:
            if hasattr(self.app, 'show_message'):
                self.app.show_message(
                    "Desconectado",
                    "Se perdió la conexión con el servidor",
                    "warning"
                )
        elif new_state == ConnectionState.RECONNECTING:
            if hasattr(self.app, 'show_message'):
                self.app.show_message(
                    "Reconectando",
                    "Intentando reconectar con el servidor...",
                    "info"
                )

    def _on_network_game_updated(self):
        """Handle game state update from server."""
        # Update our local game reference
        self.game = self.sync_manager.game

        # Notify UI
        self._notify_update()

    def _on_network_phase_changed(self, new_phase: Phase):
        """Handle phase change from server."""
        logger.info(f"Network phase changed to: {new_phase.value}")

        # Update local game
        if self.game:
            self.game.phase = new_phase

        # Notify UI
        self._notify_phase_change(new_phase)

    def _on_network_player_action(self, action_type: str, data: dict):
        """Handle player action events from server."""
        if action_type == 'chat_message':
            # Add to messages
            from types import SimpleNamespace
            msg = SimpleNamespace(
                sender_id=data.get('sender_id'),
                sender_name=data.get('sender_name'),
                text=data.get('text'),
                channel=data.get('channel', 'general'),
                timestamp=data.get('timestamp')
            )
            self.messages.append(msg)

            if self.on_chat_message:
                self.on_chat_message(msg)

        elif action_type == 'investigation_result':
            # Show investigation result to player
            target = data.get('target_name')
            result = data.get('result')
            text = f"🔎 Resultado de investigación sobre {target}: {result}"

            if hasattr(self.app, 'send_private_message'):
                self.app.send_private_message(self.sync_manager.player_id, text)

    def _on_network_error(self, error_message: str):
        """Handle error from server."""
        logger.error(f"Server error: {error_message}")

        if hasattr(self.app, 'show_message'):
            self.app.show_message("Error del Servidor", error_message, "error")

    # ==================== Overridden Methods (Route to Network) ====================

    def create_game(self, host_name: str = "Host"):
        """Create game on server instead of locally."""
        logger.info(f"Creating game on server as {host_name}")

        # Get roles config from current game or default
        roles_config = None
        if self.game:
            roles_config = self.game.roles_config

        # Send create game message
        msg = CreateGameMessage(
            host_name=host_name,
            roles_config=roles_config,
            night_seconds=300,
            day_seconds=600
        )
        asyncio.create_task(self.client.send_message(msg))

        # Game will be created when server responds
        # Wait a moment for response
        return None  # Will be set by server response

    def add_player(self, name: str) -> bool:
        """Add player is handled by join_game in network mode."""
        logger.warning("add_player called in network mode, use join_game instead")
        return False

    def join_game(self, game_id: int, player_name: str) -> bool:
        """Join an existing game on server."""
        logger.info(f"Joining game {game_id} as {player_name}")

        msg = JoinGameMessage(game_id, player_name)
        asyncio.create_task(self.client.send_message(msg))

        return True  # Actual result will come from server

    def remove_player(self, user_id: int) -> bool:
        """Cannot remove players in network mode (server controlled)."""
        logger.warning("Cannot remove players in network mode")
        return False

    def start_game(self) -> List[str]:
        """Start game on server."""
        if not self.game:
            return ["No hay partida"]

        logger.info(f"Starting game {self.game.chat_id} on server")

        msg = StartGameMessage(self.game.chat_id)
        asyncio.create_task(self.client.send_message(msg))

        return []  # Errors will come from server

    def register_night_action(self, actor_id: int, target_id: int) -> bool:
        """Register night action on server."""
        if not self.game:
            return False

        # Only allow if it's our turn
        if actor_id != self.sync_manager.player_id:
            logger.warning(f"Cannot submit action for other player: {actor_id}")
            return False

        logger.info(f"Submitting night action: {actor_id} -> {target_id}")

        msg = NightActionMessage(self.game.chat_id, target_id)
        asyncio.create_task(self.client.send_message(msg))

        return True

    def register_mafia_vote(self, voter_id: int, target_id: int) -> bool:
        """Register mafia vote on server."""
        if not self.game:
            return False

        if voter_id != self.sync_manager.player_id:
            return False

        logger.info(f"Submitting mafia vote: {voter_id} -> {target_id}")

        msg = MafiaVoteMessage(self.game.chat_id, target_id)
        asyncio.create_task(self.client.send_message(msg))

        return True

    def register_day_vote(self, voter_id: int, target_id: int) -> bool:
        """Register day vote on server."""
        if not self.game:
            return False

        if voter_id != self.sync_manager.player_id:
            return False

        logger.info(f"Submitting day vote: {voter_id} -> {target_id}")

        msg = DayVoteMessage(self.game.chat_id, target_id)
        asyncio.create_task(self.client.send_message(msg))

        return True

    def send_chat_message(self, sender_id: int, text: str, channel: str = "general") -> bool:
        """Send chat message through server."""
        if not self.game:
            return False

        if sender_id != self.sync_manager.player_id:
            return False

        logger.debug(f"Sending chat message: {text}")

        msg = ChatMessage(self.game.chat_id, text, channel)
        asyncio.create_task(self.client.send_message(msg))

        return True

    def resolve_night(self) -> List[str]:
        """Request night resolution from server."""
        if not self.game:
            return ["No hay partida"]

        logger.info("Requesting night resolution from server")

        msg = ResolveNightMessage(self.game.chat_id)
        asyncio.create_task(self.client.send_message(msg))

        return []  # Results will come from server

    def start_voting(self):
        """Request voting phase from server."""
        if not self.game:
            return

        logger.info("Requesting voting phase from server")

        msg = StartVotingMessage(self.game.chat_id)
        asyncio.create_task(self.client.send_message(msg))

    def resolve_votes(self) -> List[str]:
        """Request vote resolution from server."""
        if not self.game:
            return ["No hay partida"]

        logger.info("Requesting vote resolution from server")

        msg = ResolveVotesMessage(self.game.chat_id)
        asyncio.create_task(self.client.send_message(msg))

        return []

    def reset_game(self):
        """Cannot reset game in network mode."""
        logger.warning("Cannot reset game in network mode")

    def end_game(self):
        """End game (leave)."""
        if self.game:
            msg = LeaveGameMessage(self.game.chat_id)
            asyncio.create_task(self.client.send_message(msg))

        super().end_game()

    # ==================== Helper Methods ====================

    def request_game_list(self):
        """Request list of available games from server."""
        from network.messages import ListGamesMessage
        msg = ListGamesMessage()
        asyncio.create_task(self.client.send_message(msg))

    def disconnect(self):
        """Disconnect from server."""
        asyncio.create_task(self.client.disconnect())

    @property
    def is_connected(self) -> bool:
        """Check if connected to server."""
        return self.client.is_connected

    @property
    def connection_stats(self):
        """Get connection statistics."""
        return {
            'client': self.client.stats,
            'sync': self.sync_manager.sync.stats
        }
