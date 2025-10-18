"""
persistence/database.py
Gestión de persistencia usando solo aiosqlite (async).
Repository pattern con cache en memoria.
"""
import asyncio
import aiosqlite
import json
import logging
from typing import Optional, Dict, List, Set
from pathlib import Path
import time

from core.models import Game, Player, Phase

logger = logging.getLogger(__name__)


class GameRepository:
    """
    Repository para gestión de partidas con persistencia async.
    Mantiene cache en memoria sincronizado con la base de datos.
    """

    def __init__(self, db_path: str = "data/mafia.db"):
        self.db_path = db_path
        self._cache: Dict[int, Game] = {}
        self._lock = asyncio.Lock()
        self._initialized = False

    async def initialize(self):
        """Inicializa la base de datos y carga el cache."""
        if self._initialized:
            return

        # Crear directorio si no existe
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        # Inicializar schema
        from .migrations import initialize_schema
        await initialize_schema(self.db_path)

        # Cargar cache
        await self._load_cache()

        self._initialized = True
        logger.info(f"GameRepository initialized with {len(self._cache)} games")

    async def _load_cache(self):
        """Carga todas las partidas activas en memoria."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row

            # Cargar partidas
            async with db.execute("""
                SELECT chat_id, host_id, phase, roles_config,
                       night_seconds, day_seconds, periodic_reminder_seconds,
                       phase_deadline, created_at, updated_at
                FROM games
                WHERE phase != 'finished'
            """) as cursor:
                async for row in cursor:
                    game = await self._row_to_game(db, row)
                    async with self._lock:
                        self._cache[game.chat_id] = game

        logger.info(f"Loaded {len(self._cache)} active games into cache")

    async def _row_to_game(self, db: aiosqlite.Connection, row: aiosqlite.Row) -> Game:
        """Convierte una fila de DB a objeto Game."""
        chat_id = row['chat_id']

        # Parse roles_config
        try:
            roles_config = json.loads(row['roles_config']) if row['roles_config'] else {}
        except json.JSONDecodeError:
            roles_config = {"mafia": 1, "ciudadano": 3}

        # Crear game
        game = Game(
            chat_id=chat_id,
            host_id=row['host_id'],
            phase=Phase(row['phase']) if row['phase'] else Phase.LOBBY,
            roles_config=roles_config,
            night_seconds=row['night_seconds'] or 300,
            day_seconds=row['day_seconds'] or 600,
            periodic_reminder_seconds=row['periodic_reminder_seconds'] or 120,
            phase_deadline=row['phase_deadline'],
            created_at=row['created_at'] or int(time.time()),
            updated_at=row['updated_at'] or int(time.time())
        )

        # Cargar jugadores
        async with db.execute("""
            SELECT user_id, name, role_key, alive, blocked,
                   silenced, protected, dm_sent_ok
            FROM players
            WHERE chat_id = ?
        """, (chat_id,)) as player_cursor:
            async for player_row in player_cursor:
                # Obtener 'protected' de forma segura: aiostqlite.Row no tiene .get()
                if 'protected' in player_row.keys():
                    protected_val = player_row['protected'] if player_row['protected'] is not None else 0
                else:
                    protected_val = 0

                player = Player(
                    user_id=player_row['user_id'],
                    name=player_row['name'],
                    role_key=player_row['role_key'],
                    alive=bool(player_row['alive']),
                    blocked=bool(player_row['blocked']),
                    silenced=bool(player_row['silenced']),
                    protected=bool(protected_val),
                    dm_sent_ok=bool(player_row['dm_sent_ok'])
                )
                game.players[player.user_id] = player

        # Cargar pending_actions (votos de mafia, etc.)
        async with db.execute("""
            SELECT action_type, actor_id, target_id, data
            FROM pending_actions
            WHERE chat_id = ? AND expires_at > ?
        """, (chat_id, int(time.time()))) as action_cursor:
            async for action_row in action_cursor:
                action_type = action_row['action_type']
                actor_id = action_row['actor_id']
                target_id = action_row['target_id']

                if action_type == 'mafia_vote' and actor_id and target_id:
                    game.mafia_votes[actor_id] = target_id
                elif action_type == 'day_vote' and actor_id and target_id:
                    game.day_votes[actor_id] = target_id

        return game

    async def get(self, chat_id: int) -> Optional[Game]:
        """Obtiene una partida por chat_id (primero del cache)."""
        async with self._lock:
            if chat_id in self._cache:
                return self._cache[chat_id]

        # Si no está en cache, intentar cargar de DB
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT chat_id, host_id, phase, roles_config,
                       night_seconds, day_seconds, periodic_reminder_seconds,
                       phase_deadline, created_at, updated_at
                FROM games
                WHERE chat_id = ?
            """, (chat_id,)) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return None

                game = await self._row_to_game(db, row)

                # Agregar al cache
                async with self._lock:
                    self._cache[chat_id] = game

                return game

    async def create(self, chat_id: int, host_id: int) -> Game:
        """Crea una nueva partida."""
        async with self._lock:
            if chat_id in self._cache:
                raise ValueError(f"Game {chat_id} already exists in cache")

        # Verificar en DB por si acaso
        existing = await self.get(chat_id)
        if existing:
            raise ValueError(f"Game {chat_id} already exists in database")

        # Crear nueva partida
        game = Game(chat_id=chat_id, host_id=host_id)

        # Guardar en DB
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO games (
                    chat_id, host_id, phase, roles_config,
                    night_seconds, day_seconds, periodic_reminder_seconds,
                    phase_deadline, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                game.chat_id,
                game.host_id,
                game.phase.value,
                json.dumps(game.roles_config),
                game.night_seconds,
                game.day_seconds,
                game.periodic_reminder_seconds,
                game.phase_deadline,
                game.created_at,
                game.updated_at
            ))
            await db.commit()

        # Agregar al cache
        async with self._lock:
            self._cache[chat_id] = game

        logger.info(f"Created game {chat_id} with host {host_id}")
        return game

    async def save(self, game: Game):
        """Guarda/actualiza una partida completa (atómico)."""
        game.updated_at = int(time.time())

        async with aiosqlite.connect(self.db_path) as db:
            try:
                # Iniciar transacción explícita
                await db.execute("BEGIN")

                # Upsert game
                await db.execute("""
                    INSERT INTO games (
                        chat_id, host_id, phase, roles_config,
                        night_seconds, day_seconds, periodic_reminder_seconds,
                        phase_deadline, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(chat_id) DO UPDATE SET
                        host_id = excluded.host_id,
                        phase = excluded.phase,
                        roles_config = excluded.roles_config,
                        night_seconds = excluded.night_seconds,
                        day_seconds = excluded.day_seconds,
                        periodic_reminder_seconds = excluded.periodic_reminder_seconds,
                        phase_deadline = excluded.phase_deadline,
                        updated_at = excluded.updated_at
                """, (
                    game.chat_id,
                    game.host_id,
                    game.phase.value,
                    json.dumps(game.roles_config),
                    game.night_seconds,
                    game.day_seconds,
                    game.periodic_reminder_seconds,
                    game.phase_deadline,
                    game.created_at,
                    game.updated_at
                ))

                # Borrar jugadores existentes y reinsertar
                await db.execute("DELETE FROM players WHERE chat_id = ?", (game.chat_id,))

                for player in game.players.values():
                    await db.execute("""
                        INSERT INTO players (
                            chat_id, user_id, name, role_key, alive,
                            blocked, silenced, protected, dm_sent_ok
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        game.chat_id,
                        player.user_id,
                        player.name,
                        player.role_key,
                        int(player.alive),
                        int(player.blocked),
                        int(player.silenced),
                        int(player.protected),
                        int(player.dm_sent_ok)
                    ))

                # Guardar votos activos como pending_actions
                await db.execute("""
                    DELETE FROM pending_actions
                    WHERE chat_id = ? AND action_type IN ('mafia_vote', 'day_vote')
                """, (game.chat_id,))

                expires_at = int(time.time()) + 3600  # 1 hora

                for actor_id, target_id in game.mafia_votes.items():
                    await db.execute("""
                        INSERT INTO pending_actions (
                            chat_id, action_type, actor_id, target_id,
                            created_at, expires_at
                        ) VALUES (?, 'mafia_vote', ?, ?, ?, ?)
                    """, (game.chat_id, actor_id, target_id, int(time.time()), expires_at))

                for actor_id, target_id in game.day_votes.items():
                    await db.execute("""
                        INSERT INTO pending_actions (
                            chat_id, action_type, actor_id, target_id,
                            created_at, expires_at
                        ) VALUES (?, 'day_vote', ?, ?, ?, ?)
                    """, (game.chat_id, actor_id, target_id, int(time.time()), expires_at))

                await db.commit()

                # Actualizar cache
                async with self._lock:
                    self._cache[game.chat_id] = game

                logger.debug(f"Saved game {game.chat_id}")

            except Exception as e:
                await db.rollback()
                logger.exception(f"Error saving game {game.chat_id}")
                raise

    async def delete(self, chat_id: int) -> bool:
        """Elimina una partida completamente."""
        async with aiosqlite.connect(self.db_path) as db:
            try:
                await db.execute("BEGIN")
                await db.execute("DELETE FROM pending_actions WHERE chat_id = ?", (chat_id,))
                await db.execute("DELETE FROM players WHERE chat_id = ?", (chat_id,))
                await db.execute("DELETE FROM games WHERE chat_id = ?", (chat_id,))
                await db.commit()

                # Eliminar del cache
                async with self._lock:
                    self._cache.pop(chat_id, None)

                logger.info(f"Deleted game {chat_id}")
                return True

            except Exception as e:
                await db.rollback()
                logger.exception(f"Error deleting game {chat_id}")
                return False

    async def add_player(self, chat_id: int, user_id: int, name: str) -> bool:
        """Agrega un jugador a una partida."""
        game = await self.get(chat_id)
        if not game:
            return False

        if user_id in game.players:
            return False

        game.players[user_id] = Player(user_id=user_id, name=name)
        await self.save(game)
        return True

    async def remove_player(self, chat_id: int, user_id: int) -> bool:
        """Elimina un jugador de una partida."""
        game = await self.get(chat_id)
        if not game or user_id not in game.players:
            return False

        del game.players[user_id]
        await self.save(game)
        return True

    async def get_all_active(self) -> List[Game]:
        """Retorna todas las partidas activas."""
        async with self._lock:
            return list(self._cache.values())

    async def cleanup_expired_actions(self):
        """Limpia acciones expiradas de la base de datos."""
        async with aiosqlite.connect(self.db_path) as db:
            result = await db.execute("""
                DELETE FROM pending_actions
                WHERE expires_at < ?
            """, (int(time.time()),))
            await db.commit()

            deleted = result.rowcount if result else 0
            if deleted > 0:
                logger.info(f"Cleaned up {deleted} expired actions")

    async def shutdown(self):
        """Guarda todas las partidas del cache antes de cerrar."""
        logger.info(f"Shutting down repository, saving {len(self._cache)} games...")

        async with self._lock:
            games = list(self._cache.values())

        for game in games:
            try:
                await self.save(game)
            except Exception:
                logger.exception(f"Error saving game {game.chat_id} on shutdown")

        logger.info("Repository shutdown complete")


# Singleton global (se inicializará en main)
repository: Optional[GameRepository] = None


async def get_repository() -> GameRepository:
    """Obtiene la instancia global del repository."""
    global repository
    if repository is None:
        raise RuntimeError("Repository not initialized. Call init_repository() first.")
    return repository


async def init_repository(db_path: str = "data/mafia.db") -> GameRepository:
    """Inicializa el repository global."""
    global repository
    if repository is None:
        repository = GameRepository(db_path)
        await repository.initialize()
    return repository
