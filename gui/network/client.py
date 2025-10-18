"""
gui/network/client.py
WebSocket client for connecting GUI to multiplayer server.
"""
import asyncio
import logging
import time
from typing import Optional, Callable, Dict, Any
from enum import Enum
from collections import deque
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import websockets
from websockets.client import WebSocketClientProtocol
from websockets.exceptions import ConnectionClosed, WebSocketException

from network.protocol import Message, MessageType, serialize_message, deserialize_message
from network.messages import ConnectMessage, PongMessage

logger = logging.getLogger(__name__)


class ConnectionState(Enum):
    """Connection states for the client."""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    ERROR = "error"


class GameClient:
    """
    WebSocket client for connecting to Mafia game server.

    Features:
    - Automatic reconnection with exponential backoff
    - Message queue for offline buffering
    - Heartbeat/ping mechanism
    - Event-driven message handling
    """

    def __init__(self, uri: str, reconnect_delay: float = 1.0, max_reconnect_delay: float = 60.0):
        """
        Initialize game client.

        Args:
            uri: WebSocket server URI (e.g., ws://localhost:8765)
            reconnect_delay: Initial reconnection delay in seconds
            max_reconnect_delay: Maximum reconnection delay in seconds
        """
        self.uri = uri
        self.ws: Optional[WebSocketClientProtocol] = None

        # Connection state
        self.state = ConnectionState.DISCONNECTED
        self.player_id: Optional[int] = None
        self.player_name: Optional[str] = None
        self.game_id: Optional[int] = None

        # Reconnection
        self._reconnect_delay = reconnect_delay
        self._max_reconnect_delay = max_reconnect_delay
        self._current_reconnect_delay = reconnect_delay
        self._should_reconnect = False
        self._reconnect_task: Optional[asyncio.Task] = None

        # Message handling
        self._message_handlers: Dict[MessageType, list] = {}
        self._message_queue = deque(maxlen=100)  # Buffer for offline messages
        self._receive_task: Optional[asyncio.Task] = None
        self._heartbeat_task: Optional[asyncio.Task] = None

        # Callbacks
        self.on_state_change: Optional[Callable[[ConnectionState], None]] = None
        self.on_error: Optional[Callable[[str], None]] = None

        # Stats
        self._last_message_time = 0
        self._messages_sent = 0
        self._messages_received = 0

    async def connect(self, player_name: str, auto_reconnect: bool = True) -> bool:
        """
        Connect to server and authenticate.

        Args:
            player_name: Player's display name
            auto_reconnect: Enable automatic reconnection on disconnect

        Returns:
            True if connected successfully, False otherwise
        """
        self.player_name = player_name
        self._should_reconnect = auto_reconnect

        try:
            self._set_state(ConnectionState.CONNECTING)
            logger.info(f"Connecting to {self.uri} as {player_name}")

            # Connect WebSocket
            self.ws = await websockets.connect(
                self.uri,
                ping_interval=20,
                ping_timeout=10,
                close_timeout=5
            )

            # Send CONNECT message
            connect_msg = ConnectMessage(player_name)
            await self._send_message_internal(connect_msg)

            # Wait for authentication response
            response = await asyncio.wait_for(self.ws.recv(), timeout=5.0)
            msg = deserialize_message(response)

            if msg.type == MessageType.SUCCESS:
                self.player_id = msg.data.get('player_id')
                self._set_state(ConnectionState.CONNECTED)
                self._current_reconnect_delay = self._reconnect_delay  # Reset delay

                # Start background tasks
                self._receive_task = asyncio.create_task(self._receive_loop())
                self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

                # Process queued messages
                await self._flush_message_queue()

                logger.info(f"Connected successfully as player {self.player_id}")
                return True
            else:
                error_msg = msg.data.get('error', 'Authentication failed')
                logger.error(f"Connection failed: {error_msg}")
                self._set_state(ConnectionState.ERROR)
                if self.on_error:
                    self.on_error(error_msg)
                return False

        except asyncio.TimeoutError:
            logger.error("Connection timeout")
            self._set_state(ConnectionState.ERROR)
            if self.on_error:
                self.on_error("Connection timeout")
            return False
        except Exception as e:
            logger.exception(f"Connection error: {e}")
            self._set_state(ConnectionState.ERROR)
            if self.on_error:
                self.on_error(str(e))
            return False

    async def disconnect(self):
        """Disconnect from server gracefully."""
        logger.info("Disconnecting from server")
        self._should_reconnect = False

        # Cancel background tasks
        if self._receive_task:
            self._receive_task.cancel()
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
        if self._reconnect_task:
            self._reconnect_task.cancel()

        # Close WebSocket
        if self.ws:
            try:
                await self.ws.close()
            except Exception:
                pass
            self.ws = None

        self._set_state(ConnectionState.DISCONNECTED)
        self.player_id = None
        self.game_id = None

    async def reconnect(self) -> bool:
        """
        Attempt to reconnect to server.

        Returns:
            True if reconnected successfully, False otherwise
        """
        if self.state == ConnectionState.RECONNECTING:
            logger.warning("Reconnection already in progress")
            return False

        if not self.player_name:
            logger.error("Cannot reconnect: player name not set")
            return False

        self._set_state(ConnectionState.RECONNECTING)
        logger.info(f"Reconnecting (delay: {self._current_reconnect_delay}s)")

        await asyncio.sleep(self._current_reconnect_delay)

        success = await self.connect(self.player_name, auto_reconnect=True)

        if not success:
            # Exponential backoff
            self._current_reconnect_delay = min(
                self._current_reconnect_delay * 2,
                self._max_reconnect_delay
            )

            if self._should_reconnect:
                # Schedule next reconnection attempt
                self._reconnect_task = asyncio.create_task(self.reconnect())

        return success

    async def send_message(self, message: Message) -> bool:
        """
        Send a message to server.

        Args:
            message: Message to send

        Returns:
            True if sent successfully, False otherwise
        """
        if self.state != ConnectionState.CONNECTED:
            # Queue message for later if offline
            logger.warning(f"Not connected, queuing message: {message.type.value}")
            self._message_queue.append(message)
            return False

        return await self._send_message_internal(message)

    async def _send_message_internal(self, message: Message) -> bool:
        """Internal message sending (no queue)."""
        try:
            if not self.ws:
                return False

            json_str = serialize_message(message)
            await self.ws.send(json_str)

            self._messages_sent += 1
            self._last_message_time = time.time()

            logger.debug(f"Sent message: {message.type.value}")
            return True
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            return False

    async def _flush_message_queue(self):
        """Send all queued messages."""
        while self._message_queue:
            message = self._message_queue.popleft()
            logger.info(f"Sending queued message: {message.type.value}")
            await self._send_message_internal(message)

    async def _receive_loop(self):
        """Background task to receive messages."""
        try:
            while self.ws and self.state == ConnectionState.CONNECTED:
                try:
                    raw_message = await self.ws.recv()
                    self._messages_received += 1
                    self._last_message_time = time.time()

                    # Parse message
                    message = deserialize_message(raw_message)

                    logger.debug(f"Received message: {message.type.value}")

                    # Handle pings internally
                    if message.type == MessageType.PING:
                        pong = PongMessage()
                        await self._send_message_internal(pong)
                        continue

                    # Dispatch to handlers
                    await self._dispatch_message(message)

                except ConnectionClosed:
                    logger.warning("Connection closed by server")
                    self._set_state(ConnectionState.DISCONNECTED)

                    if self._should_reconnect:
                        self._reconnect_task = asyncio.create_task(self.reconnect())
                    break
                except Exception as e:
                    logger.exception(f"Error in receive loop: {e}")

        except asyncio.CancelledError:
            logger.debug("Receive loop cancelled")

    async def _heartbeat_loop(self):
        """Background task to send periodic heartbeats."""
        try:
            while self.state == ConnectionState.CONNECTED:
                await asyncio.sleep(15)  # Every 15 seconds

                # Check if we've received any message recently
                if time.time() - self._last_message_time > 30:
                    logger.warning("No messages received for 30s, connection may be dead")
                    # Trigger reconnection
                    if self._should_reconnect:
                        await self.reconnect()
                    break

        except asyncio.CancelledError:
            logger.debug("Heartbeat loop cancelled")

    async def _dispatch_message(self, message: Message):
        """Dispatch message to registered handlers."""
        handlers = self._message_handlers.get(message.type, [])

        for handler in handlers:
            try:
                # Call handler (may be sync or async)
                result = handler(message)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.exception(f"Error in message handler: {e}")

    def on_message(self, message_type: MessageType, handler: Callable[[Message], Any]):
        """
        Register a message handler.

        Args:
            message_type: Type of message to handle
            handler: Callback function (sync or async)
        """
        if message_type not in self._message_handlers:
            self._message_handlers[message_type] = []

        self._message_handlers[message_type].append(handler)
        logger.debug(f"Registered handler for {message_type.value}")

    def remove_handler(self, message_type: MessageType, handler: Callable[[Message], Any]):
        """Remove a message handler."""
        if message_type in self._message_handlers:
            try:
                self._message_handlers[message_type].remove(handler)
            except ValueError:
                pass

    def _set_state(self, new_state: ConnectionState):
        """Update connection state and notify callback."""
        if self.state != new_state:
            old_state = self.state
            self.state = new_state
            logger.info(f"Connection state: {old_state.value} -> {new_state.value}")

            if self.on_state_change:
                try:
                    self.on_state_change(new_state)
                except Exception as e:
                    logger.exception(f"Error in state change callback: {e}")

    @property
    def is_connected(self) -> bool:
        """Check if client is connected."""
        return self.state == ConnectionState.CONNECTED

    @property
    def stats(self) -> Dict[str, Any]:
        """Get connection statistics."""
        return {
            'state': self.state.value,
            'player_id': self.player_id,
            'game_id': self.game_id,
            'messages_sent': self._messages_sent,
            'messages_received': self._messages_received,
            'queued_messages': len(self._message_queue),
            'last_message_ago': time.time() - self._last_message_time if self._last_message_time else None
        }
