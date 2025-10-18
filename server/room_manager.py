"""
server/room_manager.py
Manages multiple game rooms and their states.
"""
import asyncio
import logging
from typing import Dict, Optional, List
from dataclasses import dataclass
import time

from core.models import Game, Player, Phase
from core.engine import GameEngine
from persistence.database import GameRepository

logger = logging.getLogger(__name__)


@dataclass
class GameRoom:
    """Represents a game room with its associated game state."""
    game: Game
    engine: GameEngine
    host_id: int
    created_at: float
    last_activity: float

    def update_activity(self):
        """Update last activity timestamp."""
        self.last_activity = time.time()


class RoomManager:
    """Manages multiple game rooms."""

    def __init__(self, repository: Optional[GameRepository] = None):
        """
        Initialize room manager.

        Args:
            repository: Optional database repository for persistence.
        """
        self.repository = repository
        self._rooms: Dict[int, GameRoom] = {}  # game_id -> GameRoom
        self._player_games: Dict[int, int] = {}  # player_id -> game_id
        self._game_counter = int(time.time() * 1000)  # Use timestamp-based IDs
        self._lock = asyncio.Lock()

    async def create_game(
        self,
        host_id: int,
        host_name: str,
        roles_config: Optional[Dict[str, int]] = None,
        night_seconds: int = 300,
        day_seconds: int = 600
    ) -> Game:
        """
        Create a new game room.

        Args:
            host_id: ID of the player creating the game.
            host_name: Name of the host player.
            roles_config: Configuration of roles for the game.
            night_seconds: Duration of night phase in seconds.
            day_seconds: Duration of day phase in seconds.

        Returns:
            The created Game object.
        """
        async with self._lock:
            self._game_counter += 1
            game_id = self._game_counter

            # Create game instance
            game = Game(
                chat_id=game_id,
                host_id=host_id,
                phase=Phase.LOBBY,
                roles_config=roles_config or {'mafia': 1, 'ciudadano': 3},
                night_seconds=night_seconds,
                day_seconds=day_seconds
            )

            # Add host as first player
            game.players[host_id] = Player(user_id=host_id, name=host_name)

            # Create room
            room = GameRoom(
                game=game,
                engine=GameEngine(),
                host_id=host_id,
                created_at=time.time(),
                last_activity=time.time()
            )

            self._rooms[game_id] = room
            self._player_games[host_id] = game_id

            logger.info(
                f"Game {game_id} created by player {host_id} ({host_name})"
            )

            # Persist to database if available
            if self.repository:
                try:
                    await self.repository.save_game(game)
                except Exception as e:
                    logger.error(f"Failed to persist game {game_id}: {e}")

            return game

    async def get_game(self, game_id: int) -> Optional[Game]:
        """
        Get a game by its ID.

        Args:
            game_id: The game ID.

        Returns:
            Game object if found, None otherwise.
        """
        room = self._rooms.get(game_id)
        if room:
            room.update_activity()
            return room.game
        return None

    async def get_game_room(self, game_id: int) -> Optional[GameRoom]:
        """
        Get a game room by its ID.

        Args:
            game_id: The game ID.

        Returns:
            GameRoom object if found, None otherwise.
        """
        room = self._rooms.get(game_id)
        if room:
            room.update_activity()
        return room

    async def join_game(self, game_id: int, player_id: int, player_name: str) -> bool:
        """
        Add a player to a game.

        Args:
            game_id: The game ID.
            player_id: Player's ID.
            player_name: Player's display name.

        Returns:
            True if player joined successfully, False otherwise.
        """
        async with self._lock:
            room = self._rooms.get(game_id)
            if not room:
                logger.warning(f"Cannot join game {game_id}: game not found")
                return False

            game = room.game

            # Check if game has started
            if game.phase != Phase.LOBBY:
                logger.warning(
                    f"Cannot join game {game_id}: game already started "
                    f"(phase={game.phase})"
                )
                return False

            # Check if player is already in another game
            if player_id in self._player_games:
                old_game_id = self._player_games[player_id]
                if old_game_id != game_id:
                    logger.warning(
                        f"Player {player_id} is already in game {old_game_id}, "
                        f"leaving automatically"
                    )
                    await self.leave_game(old_game_id, player_id)

            # Add player to game
            if player_id not in game.players:
                game.players[player_id] = Player(user_id=player_id, name=player_name)
                self._player_games[player_id] = game_id
                room.update_activity()

                logger.info(
                    f"Player {player_id} ({player_name}) joined game {game_id}"
                )

                # Persist change
                if self.repository:
                    try:
                        await self.repository.save_game(game)
                    except Exception as e:
                        logger.error(f"Failed to persist game {game_id}: {e}")

                return True

            return False

    async def leave_game(self, game_id: int, player_id: int) -> bool:
        """
        Remove a player from a game.

        Args:
            game_id: The game ID.
            player_id: Player's ID.

        Returns:
            True if player left successfully, False otherwise.
        """
        async with self._lock:
            room = self._rooms.get(game_id)
            if not room:
                return False

            game = room.game

            # Cannot leave if game has started
            if game.phase != Phase.LOBBY:
                logger.warning(
                    f"Cannot leave game {game_id}: game already started"
                )
                return False

            # Remove player
            if player_id in game.players:
                player_name = game.players[player_id].name
                del game.players[player_id]
                self._player_games.pop(player_id, None)
                room.update_activity()

                logger.info(
                    f"Player {player_id} ({player_name}) left game {game_id}"
                )

                # If host left and there are other players, assign new host
                if player_id == room.host_id and game.players:
                    new_host_id = next(iter(game.players.keys()))
                    room.host_id = new_host_id
                    game.host_id = new_host_id
                    logger.info(
                        f"New host for game {game_id}: {new_host_id}"
                    )

                # If no players left, delete game
                if not game.players:
                    await self.delete_game(game_id)
                elif self.repository:
                    try:
                        await self.repository.save_game(game)
                    except Exception as e:
                        logger.error(f"Failed to persist game {game_id}: {e}")

                return True

            return False

    async def delete_game(self, game_id: int) -> bool:
        """
        Delete a game room.

        Args:
            game_id: The game ID.

        Returns:
            True if game was deleted, False if not found.
        """
        async with self._lock:
            room = self._rooms.get(game_id)
            if not room:
                return False

            # Remove all player associations
            players_to_remove = [
                pid for pid, gid in self._player_games.items()
                if gid == game_id
            ]
            for player_id in players_to_remove:
                del self._player_games[player_id]

            # Delete room
            del self._rooms[game_id]

            logger.info(f"Game {game_id} deleted")

            # Delete from database
            if self.repository:
                try:
                    await self.repository.delete_game(game_id)
                except Exception as e:
                    logger.error(f"Failed to delete game {game_id} from DB: {e}")

            return True

    async def get_player_game_id(self, player_id: int) -> Optional[int]:
        """
        Get the game ID that a player is currently in.

        Args:
            player_id: Player's ID.

        Returns:
            Game ID if player is in a game, None otherwise.
        """
        return self._player_games.get(player_id)

    async def list_games(self) -> List[Dict]:
        """
        Get a list of all active games with summary info.

        Returns:
            List of game summaries.
        """
        games = []
        for game_id, room in self._rooms.items():
            game = room.game
            games.append({
                'game_id': game_id,
                'host_id': room.host_id,
                'phase': game.phase.value,
                'player_count': len(game.players),
                'created_at': room.created_at,
                'last_activity': room.last_activity
            })
        return games

    async def update_game_state(self, game_id: int) -> bool:
        """
        Persist current game state to database.

        Args:
            game_id: The game ID.

        Returns:
            True if persisted successfully, False otherwise.
        """
        room = self._rooms.get(game_id)
        if not room or not self.repository:
            return False

        try:
            await self.repository.save_game(room.game)
            room.update_activity()
            return True
        except Exception as e:
            logger.error(f"Failed to update game {game_id}: {e}")
            return False

    async def cleanup_inactive_games(self, max_inactive_seconds: int = 3600):
        """
        Remove games that have been inactive for too long.

        Args:
            max_inactive_seconds: Maximum inactivity time in seconds before cleanup.
        """
        now = time.time()
        games_to_delete = []

        for game_id, room in self._rooms.items():
            if now - room.last_activity > max_inactive_seconds:
                games_to_delete.append(game_id)

        for game_id in games_to_delete:
            logger.info(f"Cleaning up inactive game {game_id}")
            await self.delete_game(game_id)

    @property
    def game_count(self) -> int:
        """Get number of active games."""
        return len(self._rooms)

    @property
    def player_count(self) -> int:
        """Get number of players in games."""
        return len(self._player_games)
