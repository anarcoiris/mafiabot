"""
persistence/migrations.py
Gestión del schema de la base de datos.
"""
import aiosqlite
import logging

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

-- Tabla de versión del schema
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at INTEGER NOT NULL
);

-- Tabla principal de partidas
CREATE TABLE IF NOT EXISTS games (
    chat_id INTEGER PRIMARY KEY,
    host_id INTEGER NOT NULL,
    phase TEXT NOT NULL DEFAULT 'lobby',
    roles_config TEXT NOT NULL,
    night_seconds INTEGER NOT NULL DEFAULT 300,
    day_seconds INTEGER NOT NULL DEFAULT 600,
    periodic_reminder_seconds INTEGER NOT NULL DEFAULT 120,
    phase_deadline INTEGER,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_games_phase ON games(phase);
CREATE INDEX IF NOT EXISTS idx_games_updated ON games(updated_at);

-- Tabla de jugadores
CREATE TABLE IF NOT EXISTS players (
    chat_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    role_key TEXT,
    alive INTEGER NOT NULL DEFAULT 1,
    blocked INTEGER NOT NULL DEFAULT 0,
    silenced INTEGER NOT NULL DEFAULT 0,
    protected INTEGER NOT NULL DEFAULT 0,
    dm_sent_ok INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (chat_id, user_id),
    FOREIGN KEY (chat_id) REFERENCES games(chat_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_players_chat ON players(chat_id);
CREATE INDEX IF NOT EXISTS idx_players_alive ON players(chat_id, alive);

-- Tabla de acciones pendientes (votos, callbacks, etc.)
CREATE TABLE IF NOT EXISTS pending_actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    action_type TEXT NOT NULL,
    actor_id INTEGER,
    target_id INTEGER,
    data TEXT,
    message_id INTEGER,
    created_at INTEGER NOT NULL,
    expires_at INTEGER NOT NULL,
    FOREIGN KEY (chat_id) REFERENCES games(chat_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_pending_chat ON pending_actions(chat_id);
CREATE INDEX IF NOT EXISTS idx_pending_expires ON pending_actions(expires_at);
CREATE INDEX IF NOT EXISTS idx_pending_type ON pending_actions(action_type);

-- Tabla de eventos del juego (opcional, para audit log)
CREATE TABLE IF NOT EXISTS game_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    actor_id INTEGER,
    target_id INTEGER,
    details TEXT,
    timestamp INTEGER NOT NULL,
    FOREIGN KEY (chat_id) REFERENCES games(chat_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_events_chat ON game_events(chat_id);
CREATE INDEX IF NOT EXISTS idx_events_timestamp ON game_events(timestamp);
"""


async def initialize_schema(db_path: str):
    """Inicializa el schema de la base de datos."""
    async with aiosqlite.connect(db_path) as db:
        # Ejecutar schema
        await db.executescript(SCHEMA_SQL)
        
        # Verificar versión
        async with db.execute("SELECT version FROM schema_version LIMIT 1") as cursor:
            row = await cursor.fetchone()
            current_version = row[0] if row else 0
        
        if current_version == 0:
            # Primera vez, insertar versión
            import time
            await db.execute(
                "INSERT INTO schema_version (version, applied_at) VALUES (?, ?)",
                (SCHEMA_VERSION, int(time.time()))
            )
            await db.commit()
            logger.info(f"Initialized database schema version {SCHEMA_VERSION}")
        elif current_version < SCHEMA_VERSION:
            # Migración necesaria
            await apply_migrations(db, current_version)
        else:
            logger.info(f"Database schema is up to date (version {current_version})")


async def apply_migrations(db: aiosqlite.Connection, from_version: int):
    """Aplica migraciones pendientes."""
    import time
    
    # Ejemplo de migración futura
    if from_version < 2:
        # await db.execute("ALTER TABLE games ADD COLUMN new_field TEXT")
        pass
    
    # Actualizar versión
    await db.execute(
        "UPDATE schema_version SET version = ?, applied_at = ?",
        (SCHEMA_VERSION, int(time.time()))
    )
    await db.commit()
    
    logger.info(f"Migrated database from version {from_version} to {SCHEMA_VERSION}")