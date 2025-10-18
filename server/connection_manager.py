"""
server/connection_manager.py
Manages WebSocket connections and message routing.
"""
import asyncio
import logging
from typing import Dict, Set, Optional
from dataclasses import dataclass, field
import websockets
from websockets.server import WebSocketServerProtocol

from network.protocol import Message, serialize_message, deserialize_message

logger = logging.getLogger(__name__)


@dataclass
class Connection:
    """Represents a client connection."""
    websocket: WebSocketServerProtocol
    player_id: Optional[int] = None
    player_name: Optional[str] = None
    game_id: Optional[int] = None
    authenticated: bool = False
    connected_at: float = field(default_factory=lambda: asyncio.get_event_loop().time())


class ConnectionManager:
    """Manages all client connections to the server."""

    def __init__(self):
        # websocket -> Connection
        self._connections: Dict[WebSocketServerProtocol, Connection] = {}
        # player_id -> Connection
        self._player_connections: Dict[int, Connection] = {}
        # game_id -> Set[Connection]
        self._game_connections: Dict[int, Set[Connection]] = {}

        self._lock = asyncio.Lock()

    async def register(self, websocket: WebSocketServerProtocol) -> Connection:
        """
        Register a new WebSocket connection.

        Args:
            websocket: The WebSocket connection.

        Returns:
            Connection object.
        """
        async with self._lock:
            connection = Connection(websocket=websocket)
            self._connections[websocket] = connection
            logger.info(f"New connection registered: {id(websocket)}")
            return connection

    async def unregister(self, websocket: WebSocketServerProtocol):
        """
        Unregister a WebSocket connection.

        Args:
            websocket: The WebSocket connection to unregister.
        """
        async with self._lock:
            connection = self._connections.get(websocket)
            if not connection:
                return

            # Remove from player connections
            if connection.player_id:
                self._player_connections.pop(connection.player_id, None)

            # Remove from game connections
            if connection.game_id:
                game_conns = self._game_connections.get(connection.game_id)
                if game_conns:
                    game_conns.discard(connection)
                    if not game_conns:
                        del self._game_connections[connection.game_id]

            # Remove main connection
            del self._connections[websocket]

            logger.info(
                f"Connection unregistered: player_id={connection.player_id}, "
                f"game_id={connection.game_id}"
            )

    async def authenticate_connection(
        self,
        websocket: WebSocketServerProtocol,
        player_id: int,
        player_name: str
    ):
        """
        Authenticate a connection and associate it with a player.

        Args:
            websocket: The WebSocket connection.
            player_id: Player's unique ID.
            player_name: Player's display name.
        """
        async with self._lock:
            connection = self._connections.get(websocket)
            if not connection:
                raise ValueError("Connection not found")

            connection.player_id = player_id
            connection.player_name = player_name
            connection.authenticated = True

            # Add to player connections (handle reconnection)
            old_conn = self._player_connections.get(player_id)
            if old_conn and old_conn.websocket != websocket:
                logger.info(f"Player {player_id} reconnecting, closing old connection")
                try:
                    await old_conn.websocket.close(1000, "Reconnected from another client")
                except Exception:
                    pass

            self._player_connections[player_id] = connection

            logger.info(f"Connection authenticated: player_id={player_id}, name={player_name}")

    async def join_game(self, websocket: WebSocketServerProtocol, game_id: int):
        """
        Associate a connection with a game.

        Args:
            websocket: The WebSocket connection.
            game_id: Game ID to join.
        """
        async with self._lock:
            connection = self._connections.get(websocket)
            if not connection:
                raise ValueError("Connection not found")

            # Leave previous game if any
            if connection.game_id:
                await self._leave_game_internal(connection)

            # Join new game
            connection.game_id = game_id
            if game_id not in self._game_connections:
                self._game_connections[game_id] = set()
            self._game_connections[game_id].add(connection)

            logger.info(
                f"Player {connection.player_id} ({connection.player_name}) "
                f"joined game {game_id}"
            )

    async def leave_game(self, websocket: WebSocketServerProtocol):
        """
        Remove a connection from its current game.

        Args:
            websocket: The WebSocket connection.
        """
        async with self._lock:
            connection = self._connections.get(websocket)
            if connection:
                await self._leave_game_internal(connection)

    async def _leave_game_internal(self, connection: Connection):
        """Internal helper to leave game (must be called with lock held)."""
        if not connection.game_id:
            return

        game_id = connection.game_id
        game_conns = self._game_connections.get(game_id)
        if game_conns:
            game_conns.discard(connection)
            if not game_conns:
                del self._game_connections[game_id]

        logger.info(
            f"Player {connection.player_id} ({connection.player_name}) "
            f"left game {game_id}"
        )
        connection.game_id = None

    async def send_message(self, websocket: WebSocketServerProtocol, message: Message):
        """
        Send a message to a specific WebSocket connection.

        Args:
            websocket: Target WebSocket connection.
            message: Message to send.
        """
        try:
            json_str = serialize_message(message)
            await websocket.send(json_str)
            logger.debug(f"Sent message type={message.type.value} to {id(websocket)}")
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            # Connection might be dead, will be cleaned up by handler

    async def send_to_player(self, player_id: int, message: Message) -> bool:
        """
        Send a message to a specific player.

        Args:
            player_id: Target player ID.
            message: Message to send.

        Returns:
            True if message was sent, False if player not connected.
        """
        connection = self._player_connections.get(player_id)
        if not connection:
            logger.warning(f"Cannot send to player {player_id}: not connected")
            return False

        await self.send_message(connection.websocket, message)
        return True

    async def broadcast_to_game(self, game_id: int, message: Message, exclude_player_id: Optional[int] = None):
        """
        Broadcast a message to all players in a game.

        Args:
            game_id: Target game ID.
            message: Message to broadcast.
            exclude_player_id: Optional player ID to exclude from broadcast.
        """
        game_conns = self._game_connections.get(game_id)
        if not game_conns:
            logger.warning(f"Cannot broadcast to game {game_id}: no connections")
            return

        tasks = []
        for connection in game_conns:
            if exclude_player_id and connection.player_id == exclude_player_id:
                continue
            tasks.append(self.send_message(connection.websocket, message))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        logger.debug(
            f"Broadcasted message type={message.type.value} to game {game_id} "
            f"({len(tasks)} recipients)"
        )

    def get_connection(self, websocket: WebSocketServerProtocol) -> Optional[Connection]:
        """Get connection info for a WebSocket."""
        return self._connections.get(websocket)

    def get_player_connection(self, player_id: int) -> Optional[Connection]:
        """Get connection info for a player."""
        return self._player_connections.get(player_id)

    def get_game_connections(self, game_id: int) -> Set[Connection]:
        """Get all connections for a game."""
        return self._game_connections.get(game_id, set()).copy()

    def get_connected_player_ids(self, game_id: int) -> Set[int]:
        """Get all connected player IDs in a game."""
        game_conns = self._game_connections.get(game_id, set())
        return {conn.player_id for conn in game_conns if conn.player_id}

    @property
    def connection_count(self) -> int:
        """Get total number of connections."""
        return len(self._connections)

    @property
    def authenticated_count(self) -> int:
        """Get number of authenticated connections."""
        return len(self._player_connections)
