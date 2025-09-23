# db/migrations.py
import sqlite3
import os
import logging

logger = logging.getLogger("mafiabot.migrations")

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS games (
    chat_id INTEGER PRIMARY KEY,
    host_id INTEGER,
    phase TEXT,
    roles_config TEXT,
    night_seconds INTEGER,
    day_seconds INTEGER,
    periodic_reminder_seconds INTEGER,
    phase_deadline INTEGER,
    created_at INTEGER,
    updated_at INTEGER
);

CREATE TABLE IF NOT EXISTS players (
    chat_id INTEGER,
    user_id INTEGER,
    name TEXT,
    role_key TEXT,
    alive INTEGER,
    blocked INTEGER,
    silenced INTEGER,
    dm_sent_ok INTEGER DEFAULT 0,
    PRIMARY KEY (chat_id, user_id)
);

CREATE TABLE IF NOT EXISTS pending_actions (
    key TEXT PRIMARY KEY,
    chat_id INTEGER,
    message_id INTEGER,
    action TEXT,
    actor_id INTEGER,
    extra_json TEXT,
    created_at INTEGER,
    expires_at INTEGER
);
"""

def init_db(db_file: str):
    db_file = os.environ.get("MAFIA_DB", db_file)
    conn = sqlite3.connect(db_file, timeout=30)
    cur = conn.cursor()
    cur.executescript(SCHEMA_SQL)
    # set schema_version if not exists
    cur.execute("SELECT COUNT(*) FROM schema_version")
    if cur.fetchone()[0] == 0:
        cur.execute("INSERT INTO schema_version (version) VALUES (1)")
    conn.commit()
    conn.close()
    logger.info("DB initialized/checked at %s", db_file)
