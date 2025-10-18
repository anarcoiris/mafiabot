"""
server/game_server.py
Main WebSocket server for Mafia Bot multiplayer functionality.
"""
import asyncio
import logging
import signal
from typing import Optional
from pathlib import Path
import sys

import websockets
from websockets.server import WebSocketServerProtocol, serve

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from network.protocol import Message, MessageType, serialize_message, deserialize_message
from network.messages import (
    GameStateUpdateMessage, GameCreatedMessage, PlayerJoinedMessage,
    PlayerLeftMessage, GameStartedMessage, PhaseChangedMessage,
    ChatBroadcastMessage, ErrorMessage, SuccessMessage, PongMessage
)
from server.connection_manager import ConnectionManager
from server.room_manager import RoomManager
from server.auth import SimpleAuthManager
from core.models import Phase
from core.roles import get_role
from persistence.database import GameRepository

logger = logging.getLogger(__name__)


class MafiaGameServer:
    """WebSocket server for multiplayer Mafia game."""

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 8765,
        db_path: Optional[str] = None
    ):
        """
        Initialize the game server.

        Args:
            host: Host address to bind to.
            port: Port to listen on.
            db_path: Optional path to SQLite database for persistence.
        """
        self.host = host
        self.port = port
        self.db_path = db_path

        self.connection_manager = ConnectionManager()
        self.auth_manager = SimpleAuthManager()
        self.room_manager: Optional[RoomManager] = None
        self.repository: Optional[GameRepository] = None

        self._server = None
        self._running = False
        self._cleanup_task: Optional[asyncio.Task] = None

    async def initialize(self):
        """Initialize server components (database, etc.)."""
        # Initialize database repository if path provided
        if self.db_path:
            try:
                from persistence import init_repository
                self.repository = await init_repository(self.db_path)
                logger.info(f"Database initialized: {self.db_path}")
            except Exception as e:
                logger.error(f"Failed to initialize database: {e}")
                logger.warning("Server will run without persistence")

        # Initialize room manager
        self.room_manager = RoomManager(repository=self.repository)

        # Start cleanup task
        self._cleanup_task = asyncio.create_task(self._periodic_cleanup())

        logger.info("Server initialized successfully")

    async def start(self):
        """Start the WebSocket server."""
        await self.initialize()

        self._running = True
        logger.info(f"Starting Mafia Game Server on {self.host}:{self.port}")

        async with serve(
            self.handle_client,
            self.host,
            self.port,
            logger=logger
        ) as server:
            self._server = server
            logger.info("✅ Server is ready and listening for connections")

            # Wait until stopped
            await self._wait_closed()

    async def stop(self):
        """Stop the WebSocket server."""
        logger.info("Stopping server...")
        self._running = False

        # Cancel cleanup task
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        # Close server
        if self._server:
            self._server.close()
            await self._server.wait_closed()

        # Shutdown database
        if self.repository:
            await self.repository.shutdown()

        logger.info("Server stopped")

    async def _wait_closed(self):
        """Wait until server is stopped."""
        while self._running:
            await asyncio.sleep(1)

    async def _periodic_cleanup(self):
        """Periodically clean up inactive games and expired tokens."""
        while self._running:
            try:
                await asyncio.sleep(300)  # Every 5 minutes

                # Cleanup inactive games (1 hour threshold)
                if self.room_manager:
                    await self.room_manager.cleanup_inactive_games(3600)

                logger.debug("Periodic cleanup completed")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in periodic cleanup: {e}")

    async def handle_client(self, websocket: WebSocketServerProtocol):
        """
        Handle a client connection.

        Args:
            websocket: The WebSocket connection.
        """
        # Register connection
        connection = await self.connection_manager.register(websocket)

        logger.info(f"Client connected: {websocket.remote_address}")

        try:
            # Handle messages
            async for raw_message in websocket:
                try:
                    message = deserialize_message(raw_message)
                    await self.handle_message(websocket, message)
                except ValueError as e:
                    logger.warning(f"Invalid message from client: {e}")
                    error_msg = ErrorMessage(str(e), "INVALID_MESSAGE")
                    await self.connection_manager.send_message(websocket, error_msg)
                except Exception as e:
                    logger.exception(f"Error handling message: {e}")
                    error_msg = ErrorMessage("Internal server error", "SERVER_ERROR")
                    await self.connection_manager.send_message(websocket, error_msg)

        except websockets.exceptions.ConnectionClosed:
            logger.info(f"Client disconnected: {websocket.remote_address}")
        except Exception as e:
            logger.exception(f"Error in client handler: {e}")
        finally:
            # Unregister connection
            await self.handle_disconnect(websocket)
            await self.connection_manager.unregister(websocket)

    async def handle_message(self, websocket: WebSocketServerProtocol, message: Message):
        """
        Handle a message from a client.

        Args:
            websocket: The WebSocket connection.
            message: The received message.
        """
        msg_type = message.type
        data = message.data

        logger.debug(f"Received message type={msg_type.value} from {websocket.remote_address}")

        # Handle message based on type
        if msg_type == MessageType.CONNECT:
            await self.handle_connect(websocket, message)
        elif msg_type == MessageType.CREATE_GAME:
            await self.handle_create_game(websocket, message)
        elif msg_type == MessageType.JOIN_GAME:
            await self.handle_join_game(websocket, message)
        elif msg_type == MessageType.LEAVE_GAME:
            await self.handle_leave_game(websocket, message)
        elif msg_type == MessageType.START_GAME:
            await self.handle_start_game(websocket, message)
        elif msg_type == MessageType.NIGHT_ACTION:
            await self.handle_night_action(websocket, message)
        elif msg_type == MessageType.MAFIA_VOTE:
            await self.handle_mafia_vote(websocket, message)
        elif msg_type == MessageType.DAY_VOTE:
            await self.handle_day_vote(websocket, message)
        elif msg_type == MessageType.CHAT_MESSAGE:
            await self.handle_chat_message(websocket, message)
        elif msg_type == MessageType.RESOLVE_NIGHT:
            await self.handle_resolve_night(websocket, message)
        elif msg_type == MessageType.START_VOTING:
            await self.handle_start_voting(websocket, message)
        elif msg_type == MessageType.RESOLVE_VOTES:
            await self.handle_resolve_votes(websocket, message)
        elif msg_type == MessageType.GET_GAME_STATE:
            await self.handle_get_game_state(websocket, message)
        elif msg_type == MessageType.LIST_GAMES:
            await self.handle_list_games(websocket, message)
        elif msg_type == MessageType.PING:
            await self.handle_ping(websocket, message)
        else:
            error_msg = ErrorMessage(f"Unknown message type: {msg_type.value}", "UNKNOWN_MESSAGE_TYPE")
            await self.connection_manager.send_message(websocket, error_msg)

    # ==================== Handler Methods ====================

    async def handle_connect(self, websocket: WebSocketServerProtocol, message: Message):
        """Handle player connection."""
        player_name = message.data.get('player_name')
        if not player_name:
            error_msg = ErrorMessage("player_name is required", "MISSING_FIELD")
            await self.connection_manager.send_message(websocket, error_msg)
            return

        # Register player and get ID
        player_id = self.auth_manager.register_player(player_name)

        # Authenticate connection
        await self.connection_manager.authenticate_connection(
            websocket, player_id, player_name
        )

        # Send success response
        success_msg = SuccessMessage(
            "Connected successfully",
            player_id=player_id,
            player_name=player_name
        )
        await self.connection_manager.send_message(websocket, success_msg)

        logger.info(f"Player {player_id} ({player_name}) authenticated")

    async def handle_disconnect(self, websocket: WebSocketServerProtocol):
        """Handle player disconnection."""
        connection = self.connection_manager.get_connection(websocket)
        if not connection or not connection.player_id:
            return

        player_id = connection.player_id
        player_name = connection.player_name

        # If player was in a game, notify others
        if connection.game_id:
            game_id = connection.game_id
            left_msg = PlayerLeftMessage(game_id, player_id, player_name or "Unknown")
            await self.connection_manager.broadcast_to_game(
                game_id, left_msg, exclude_player_id=player_id
            )

            # Note: We don't automatically remove player from game
            # They might reconnect. Game cleanup happens periodically.

        logger.info(f"Player {player_id} ({player_name}) disconnected")

    async def handle_create_game(self, websocket: WebSocketServerProtocol, message: Message):
        """Handle game creation."""
        connection = self.connection_manager.get_connection(websocket)
        if not connection or not connection.authenticated:
            error_msg = ErrorMessage("Not authenticated", "NOT_AUTHENTICATED")
            await self.connection_manager.send_message(websocket, error_msg)
            return

        host_name = message.data.get('host_name', connection.player_name)
        roles_config = message.data.get('roles_config')
        night_seconds = message.data.get('night_seconds', 300)
        day_seconds = message.data.get('day_seconds', 600)

        # Create game
        game = await self.room_manager.create_game(
            host_id=connection.player_id,
            host_name=host_name,
            roles_config=roles_config,
            night_seconds=night_seconds,
            day_seconds=day_seconds
        )

        # Associate connection with game
        await self.connection_manager.join_game(websocket, game.chat_id)

        # Send success response
        created_msg = GameCreatedMessage(game.chat_id, connection.player_id)
        await self.connection_manager.send_message(websocket, created_msg)

        logger.info(f"Game {game.chat_id} created by player {connection.player_id}")

    async def handle_join_game(self, websocket: WebSocketServerProtocol, message: Message):
        """Handle player joining a game."""
        connection = self.connection_manager.get_connection(websocket)
        if not connection or not connection.authenticated:
            error_msg = ErrorMessage("Not authenticated", "NOT_AUTHENTICATED")
            await self.connection_manager.send_message(websocket, error_msg)
            return

        game_id = message.data.get('game_id')
        if not game_id:
            error_msg = ErrorMessage("game_id is required", "MISSING_FIELD")
            await self.connection_manager.send_message(websocket, error_msg)
            return

        # Join game
        success = await self.room_manager.join_game(
            game_id,
            connection.player_id,
            connection.player_name or "Unknown"
        )

        if not success:
            error_msg = ErrorMessage("Failed to join game", "JOIN_FAILED")
            await self.connection_manager.send_message(websocket, error_msg)
            return

        # Associate connection with game
        await self.connection_manager.join_game(websocket, game_id)

        # Notify all players
        joined_msg = PlayerJoinedMessage(
            game_id, connection.player_id, connection.player_name or "Unknown"
        )
        await self.connection_manager.broadcast_to_game(game_id, joined_msg)

        # Send game state to new player
        await self.send_game_state_to_player(connection.player_id, game_id)

        logger.info(f"Player {connection.player_id} joined game {game_id}")

    async def handle_leave_game(self, websocket: WebSocketServerProtocol, message: Message):
        """Handle player leaving a game."""
        connection = self.connection_manager.get_connection(websocket)
        if not connection or not connection.authenticated:
            error_msg = ErrorMessage("Not authenticated", "NOT_AUTHENTICATED")
            await self.connection_manager.send_message(websocket, error_msg)
            return

        game_id = message.data.get('game_id')
        if not game_id:
            error_msg = ErrorMessage("game_id is required", "MISSING_FIELD")
            await self.connection_manager.send_message(websocket, error_msg)
            return

        # Leave game
        success = await self.room_manager.leave_game(game_id, connection.player_id)

        if success:
            # Disconnect connection from game
            await self.connection_manager.leave_game(websocket)

            # Notify other players
            left_msg = PlayerLeftMessage(
                game_id, connection.player_id, connection.player_name or "Unknown"
            )
            await self.connection_manager.broadcast_to_game(game_id, left_msg)

            success_msg = SuccessMessage("Left game successfully")
            await self.connection_manager.send_message(websocket, success_msg)
        else:
            error_msg = ErrorMessage("Failed to leave game", "LEAVE_FAILED")
            await self.connection_manager.send_message(websocket, error_msg)

    async def handle_start_game(self, websocket: WebSocketServerProtocol, message: Message):
        """Handle game start."""
        connection = self.connection_manager.get_connection(websocket)
        if not connection or not connection.authenticated:
            error_msg = ErrorMessage("Not authenticated", "NOT_AUTHENTICATED")
            await self.connection_manager.send_message(websocket, error_msg)
            return

        game_id = message.data.get('game_id')
        if not game_id:
            error_msg = ErrorMessage("game_id is required", "MISSING_FIELD")
            await self.connection_manager.send_message(websocket, error_msg)
            return

        # Get game room
        room = await self.room_manager.get_game_room(game_id)
        if not room:
            error_msg = ErrorMessage("Game not found", "GAME_NOT_FOUND")
            await self.connection_manager.send_message(websocket, error_msg)
            return

        # Check if player is host
        if connection.player_id != room.host_id:
            error_msg = ErrorMessage("Only host can start the game", "NOT_HOST")
            await self.connection_manager.send_message(websocket, error_msg)
            return

        game = room.game

        # Check minimum players
        if len(game.players) < 4:
            error_msg = ErrorMessage(
                f"Need at least 4 players (current: {len(game.players)})",
                "NOT_ENOUGH_PLAYERS"
            )
            await self.connection_manager.send_message(websocket, error_msg)
            return

        # Assign roles
        errors = room.engine.assign_roles(game)
        if errors:
            error_msg = ErrorMessage("; ".join(errors), "ROLE_ASSIGNMENT_FAILED")
            await self.connection_manager.send_message(websocket, error_msg)
            return

        # Start game
        game.phase = Phase.NIGHT
        await self.room_manager.update_game_state(game_id)

        # Notify all players
        started_msg = GameStartedMessage(game_id, len(game.players))
        await self.connection_manager.broadcast_to_game(game_id, started_msg)

        # Send game state with roles to all players
        await self.broadcast_game_state(game_id)

        logger.info(f"Game {game_id} started with {len(game.players)} players")

    async def handle_night_action(self, websocket: WebSocketServerProtocol, message: Message):
        """Handle night action submission."""
        connection = self.connection_manager.get_connection(websocket)
        if not connection or not connection.authenticated:
            error_msg = ErrorMessage("Not authenticated", "NOT_AUTHENTICATED")
            await self.connection_manager.send_message(websocket, error_msg)
            return

        game_id = message.data.get('game_id')
        target_id = message.data.get('target_id')

        if not game_id or target_id is None:
            error_msg = ErrorMessage("game_id and target_id are required", "MISSING_FIELD")
            await self.connection_manager.send_message(websocket, error_msg)
            return

        # Get game
        room = await self.room_manager.get_game_room(game_id)
        if not room:
            error_msg = ErrorMessage("Game not found", "GAME_NOT_FOUND")
            await self.connection_manager.send_message(websocket, error_msg)
            return

        game = room.game

        # Validate action (similar to GUI controller logic)
        player = game.players.get(connection.player_id)
        if not player or not player.alive or not player.role_key:
            error_msg = ErrorMessage("Cannot perform action", "ACTION_DENIED")
            await self.connection_manager.send_message(websocket, error_msg)
            return

        role = get_role(player.role_key)
        if not role or not role.has_night_action:
            error_msg = ErrorMessage("Your role has no night action", "NO_ACTION")
            await self.connection_manager.send_message(websocket, error_msg)
            return

        # Register action
        from core.models import NightAction
        action_type_map = {
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
        action_type = action_type_map.get(role.key)
        if not action_type:
            error_msg = ErrorMessage("Unknown action type", "INVALID_ACTION")
            await self.connection_manager.send_message(websocket, error_msg)
            return

        # Remove previous action of same type
        game.night_actions = [
            a for a in game.night_actions
            if not (a.actor_id == connection.player_id and a.action_type == action_type)
        ]

        # Add new action
        game.night_actions.append(
            NightAction(
                actor_id=connection.player_id,
                target_id=target_id,
                action_type=action_type,
                priority=role.priority
            )
        )

        await self.room_manager.update_game_state(game_id)

        # Send confirmation
        success_msg = SuccessMessage("Action submitted")
        await self.connection_manager.send_message(websocket, success_msg)

        logger.info(
            f"Player {connection.player_id} submitted night action: "
            f"{action_type} -> {target_id}"
        )

    async def handle_mafia_vote(self, websocket: WebSocketServerProtocol, message: Message):
        """Handle mafia vote submission."""
        connection = self.connection_manager.get_connection(websocket)
        if not connection or not connection.authenticated:
            return

        game_id = message.data.get('game_id')
        target_id = message.data.get('target_id')

        room = await self.room_manager.get_game_room(game_id)
        if not room:
            return

        game = room.game
        player = game.players.get(connection.player_id)
        if not player or not player.alive:
            return

        # Check if player is mafia
        role = get_role(player.role_key) if player.role_key else None
        if not role or role.faction.value != "mafia":
            error_msg = ErrorMessage("Only mafia can vote", "NOT_MAFIA")
            await self.connection_manager.send_message(websocket, error_msg)
            return

        # Register vote
        game.mafia_votes[connection.player_id] = target_id
        await self.room_manager.update_game_state(game_id)

        success_msg = SuccessMessage("Mafia vote submitted")
        await self.connection_manager.send_message(websocket, success_msg)

    async def handle_day_vote(self, websocket: WebSocketServerProtocol, message: Message):
        """Handle day vote submission."""
        connection = self.connection_manager.get_connection(websocket)
        if not connection or not connection.authenticated:
            return

        game_id = message.data.get('game_id')
        target_id = message.data.get('target_id')

        room = await self.room_manager.get_game_room(game_id)
        if not room:
            return

        game = room.game
        player = game.players.get(connection.player_id)
        if not player or not player.alive or player.silenced:
            error_msg = ErrorMessage("Cannot vote", "VOTE_DENIED")
            await self.connection_manager.send_message(websocket, error_msg)
            return

        # Register vote
        game.day_votes[connection.player_id] = target_id
        await self.room_manager.update_game_state(game_id)

        success_msg = SuccessMessage("Vote submitted")
        await self.connection_manager.send_message(websocket, success_msg)

    async def handle_chat_message(self, websocket: WebSocketServerProtocol, message: Message):
        """Handle chat message."""
        connection = self.connection_manager.get_connection(websocket)
        if not connection or not connection.authenticated:
            return

        game_id = message.data.get('game_id')
        text = message.data.get('text')
        channel = message.data.get('channel', 'general')

        if not game_id or not text:
            return

        # Broadcast chat message
        chat_msg = ChatBroadcastMessage(
            game_id, connection.player_id, connection.player_name or "Unknown", text, channel
        )
        await self.connection_manager.broadcast_to_game(game_id, chat_msg)

    async def handle_resolve_night(self, websocket: WebSocketServerProtocol, message: Message):
        """Handle night resolution."""
        # TODO: Implement night resolution
        # This would call room.engine.resolve_night(game) and broadcast results
        pass

    async def handle_start_voting(self, websocket: WebSocketServerProtocol, message: Message):
        """Handle start of voting phase."""
        # TODO: Implement voting phase start
        pass

    async def handle_resolve_votes(self, websocket: WebSocketServerProtocol, message: Message):
        """Handle vote resolution."""
        # TODO: Implement vote resolution
        pass

    async def handle_get_game_state(self, websocket: WebSocketServerProtocol, message: Message):
        """Handle game state request."""
        connection = self.connection_manager.get_connection(websocket)
        if not connection or not connection.authenticated:
            return

        game_id = message.data.get('game_id')
        if not game_id:
            return

        await self.send_game_state_to_player(connection.player_id, game_id)

    async def handle_list_games(self, websocket: WebSocketServerProtocol, message: Message):
        """Handle list games request."""
        games = await self.room_manager.list_games()

        from network.messages import GameListMessage
        list_msg = GameListMessage(games)
        await self.connection_manager.send_message(websocket, list_msg)

    async def handle_ping(self, websocket: WebSocketServerProtocol, message: Message):
        """Handle ping."""
        pong_msg = PongMessage()
        await self.connection_manager.send_message(websocket, pong_msg)

    # ==================== Helper Methods ====================

    async def send_game_state_to_player(self, player_id: int, game_id: int):
        """Send current game state to a specific player."""
        room = await self.room_manager.get_game_room(game_id)
        if not room:
            return

        game = room.game
        player = game.players.get(player_id)
        if not player:
            return

        # Prepare player list
        players_data = [
            {
                'player_id': p.user_id,
                'name': p.name,
                'alive': p.alive,
                'role': p.role_key if (not p.alive or game.phase == Phase.FINISHED) else None
            }
            for p in game.players.values()
        ]

        # Send game state
        state_msg = GameStateUpdateMessage(
            game_id=game_id,
            phase=game.phase.value,
            players=players_data,
            phase_deadline=game.phase_deadline,
            your_player_id=player_id,
            your_role=player.role_key if player.role_key else None,
            alive_players=[p.user_id for p in game.players.values() if p.alive]
        )

        await self.connection_manager.send_to_player(player_id, state_msg)

    async def broadcast_game_state(self, game_id: int):
        """Broadcast game state to all players in a game."""
        connected_players = self.connection_manager.get_connected_player_ids(game_id)
        for player_id in connected_players:
            await self.send_game_state_to_player(player_id, game_id)


async def main():
    """Entry point for running the server."""
    import argparse
    from pathlib import Path

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
    )

    # Parse arguments
    parser = argparse.ArgumentParser(description="Mafia Game Server")
    parser.add_argument(
        '--host',
        default='0.0.0.0',
        help='Host to bind to (default: 0.0.0.0)'
    )
    parser.add_argument(
        '--port',
        type=int,
        default=8765,
        help='Port to listen on (default: 8765)'
    )
    parser.add_argument(
        '--db',
        default='data/mafia_server.db',
        help='Path to SQLite database (default: data/mafia_server.db)'
    )
    parser.add_argument(
        '--no-persist',
        action='store_true',
        help='Run without database persistence'
    )
    args = parser.parse_args()

    # Create data directory if needed
    if not args.no_persist:
        db_path = Path(args.db)
        db_path.parent.mkdir(parents=True, exist_ok=True)

    # Create and start server
    server = MafiaGameServer(
        host=args.host,
        port=args.port,
        db_path=None if args.no_persist else args.db
    )

    # Handle shutdown signals (cross-platform)
    import platform

    if platform.system() != 'Windows':
        # Unix signal handling
        loop = asyncio.get_event_loop()

        def shutdown_handler(sig):
            logger.info(f"Received signal {sig}, shutting down...")
            asyncio.create_task(server.stop())

        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, lambda s=sig: shutdown_handler(s))

    # Start server
    try:
        await server.start()
    except KeyboardInterrupt:
        logger.info("Server stopped by user (Ctrl+C)")
    except Exception as e:
        logger.exception(f"Server error: {e}")
    finally:
        await server.stop()


if __name__ == "__main__":
    asyncio.run(main())
