"""
gui/network/sync_manager.py
Coordinates synchronization between client, state, and UI.
"""
import logging
from typing import Optional, Callable, Any
import asyncio

from gui.network.client import GameClient, ConnectionState
from gui.network.state_sync import StateSynchronizer
from network.protocol import MessageType

logger = logging.getLogger(__name__)


class SyncManager:
    """
    Coordinates synchronization between network client and game state.

    This is the glue between:
    - GameClient (network layer)
    - StateSynchronizer (state management)
    - UI (game controller)
    """

    def __init__(self, client: GameClient):
        """
        Initialize sync manager.

        Args:
            client: GameClient instance
        """
        self.client = client
        self.sync = StateSynchronizer()

        # Callbacks for UI
        self.on_game_updated: Optional[Callable[[], None]] = None
        self.on_phase_changed: Optional[Callable[[Any], None]] = None
        self.on_player_action: Optional[Callable[[str, dict], None]] = None
        self.on_error: Optional[Callable[[str], None]] = None

        # Track last known phase for change detection
        self._last_phase = None

        # Register message handlers
        self._register_handlers()

    def _register_handlers(self):
        """Register handlers for server messages."""
        # Game state updates
        self.client.on_message(MessageType.GAME_STATE_UPDATE, self._handle_state_update)

        # Game events
        self.client.on_message(MessageType.PLAYER_JOINED, self._handle_player_joined)
        self.client.on_message(MessageType.PLAYER_LEFT, self._handle_player_left)
        self.client.on_message(MessageType.GAME_STARTED, self._handle_game_started)
        self.client.on_message(MessageType.PHASE_CHANGED, self._handle_phase_changed)
        self.client.on_message(MessageType.PLAYER_DIED, self._handle_player_died)

        # Chat
        self.client.on_message(MessageType.CHAT_BROADCAST, self._handle_chat_broadcast)
        self.client.on_message(MessageType.PRIVATE_MESSAGE, self._handle_private_message)
        self.client.on_message(MessageType.INVESTIGATION_RESULT, self._handle_investigation)

        # Errors
        self.client.on_message(MessageType.ERROR, self._handle_error)

        logger.info("Registered message handlers")

    def _handle_state_update(self, message):
        """Handle game state update from server."""
        logger.debug("Received GAME_STATE_UPDATE")

        # Apply update to local state
        success = self.sync.apply_server_update(message.data)

        if success:
            # Check for phase change
            current_phase = self.sync.phase
            if current_phase and current_phase != self._last_phase:
                logger.info(f"Phase changed: {self._last_phase} -> {current_phase}")
                self._last_phase = current_phase

                if self.on_phase_changed:
                    self.on_phase_changed(current_phase)

            # Notify UI of update
            if self.on_game_updated:
                self.on_game_updated()

    def _handle_player_joined(self, message):
        """Handle player joined event."""
        data = message.data
        player_name = data.get('player_name', 'Unknown')
        logger.info(f"Player joined: {player_name}")

        # Trigger a state refresh
        if self.on_game_updated:
            self.on_game_updated()

    def _handle_player_left(self, message):
        """Handle player left event."""
        data = message.data
        player_name = data.get('player_name', 'Unknown')
        logger.info(f"Player left: {player_name}")

        if self.on_game_updated:
            self.on_game_updated()

    def _handle_game_started(self, message):
        """Handle game started event."""
        logger.info("Game started")

        if self.on_game_updated:
            self.on_game_updated()

    def _handle_phase_changed(self, message):
        """Handle phase changed event."""
        data = message.data
        new_phase_str = data.get('new_phase')
        logger.info(f"Phase changed to: {new_phase_str}")

        if self.on_phase_changed:
            from core.models import Phase
            try:
                new_phase = Phase(new_phase_str)
                self.on_phase_changed(new_phase)
            except ValueError:
                logger.warning(f"Unknown phase: {new_phase_str}")

    def _handle_player_died(self, message):
        """Handle player death event."""
        data = message.data
        player_name = data.get('player_name', 'Unknown')
        role = data.get('role', 'Unknown')
        logger.info(f"Player died: {player_name} ({role})")

        if self.on_game_updated:
            self.on_game_updated()

    def _handle_chat_broadcast(self, message):
        """Handle chat broadcast."""
        data = message.data
        sender_name = data.get('sender_name', 'Unknown')
        text = data.get('text', '')
        logger.debug(f"Chat from {sender_name}: {text}")

        # Forward to UI
        if self.on_player_action:
            self.on_player_action('chat_message', data)

    def _handle_private_message(self, message):
        """Handle private message."""
        data = message.data
        text = data.get('text', '')
        logger.info(f"Private message: {text}")

        if self.on_player_action:
            self.on_player_action('private_message', data)

    def _handle_investigation(self, message):
        """Handle investigation result."""
        data = message.data
        target = data.get('target_name', 'Unknown')
        result = data.get('result', 'Unknown')
        logger.info(f"Investigation result: {target} = {result}")

        if self.on_player_action:
            self.on_player_action('investigation_result', data)

    def _handle_error(self, message):
        """Handle error message from server."""
        data = message.data
        error_text = data.get('error', 'Unknown error')
        error_code = data.get('error_code', 'UNKNOWN')

        logger.error(f"Server error [{error_code}]: {error_text}")

        if self.on_error:
            self.on_error(error_text)

    def request_state_update(self):
        """Request fresh game state from server."""
        if not self.sync.game_id:
            logger.warning("Cannot request state: no game ID")
            return

        from network.messages import GetGameStateMessage
        msg = GetGameStateMessage(self.sync.game_id)
        asyncio.create_task(self.client.send_message(msg))

    def clear(self):
        """Clear all state."""
        self.sync.clear()
        self._last_phase = None
        logger.info("Sync manager cleared")

    @property
    def is_connected(self) -> bool:
        """Check if connected to server."""
        return self.client.is_connected

    @property
    def has_game(self) -> bool:
        """Check if we have game state."""
        return self.sync.has_state

    @property
    def game(self):
        """Get current game state."""
        return self.sync.current_state

    @property
    def player_id(self) -> Optional[int]:
        """Get our player ID."""
        return self.client.player_id

    @property
    def game_id(self) -> Optional[int]:
        """Get current game ID."""
        return self.sync.game_id
