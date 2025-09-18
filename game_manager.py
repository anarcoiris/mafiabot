#!/usr/bin/env python3
# game_manager.py
# Gestión de partidas + persistencia en SQLite (sin mezclar con handlers).
# Compatible con python-telegram-bot async usage: métodos síncronos para handlers y wrappers asíncronos.

import sqlite3
import aiosqlite
import threading
import asyncio
import json
import time
import logging
from typing import Optional, List, Dict, Any

from models import GameState, PlayerState

logger = logging.getLogger(__name__)

DEFAULT_DB = "mafia_complete.db"


class GameManager:
    def __init__(self, db_file: str = DEFAULT_DB):
        self.db_file = db_file
        self._games: Dict[int, GameState] = {}
        self._lock = threading.RLock()

        # Ensure DB schema exists
        try:
            conn = sqlite3.connect(self.db_file)
            cur = conn.cursor()
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS games (
                    chat_id INTEGER PRIMARY KEY,
                    host_id INTEGER,
                    phase TEXT,
                    roles_config TEXT,
                    night_seconds INTEGER,
                    day_seconds INTEGER,
                    periodic_reminder_seconds INTEGER,
                    phase_deadline INTEGER
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS players (
                    chat_id INTEGER,
                    user_id INTEGER,
                    name TEXT,
                    role_key TEXT,
                    alive INTEGER,
                    blocked INTEGER,
                    silenced INTEGER,
                    PRIMARY KEY (chat_id, user_id)
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS pending_actions (
                    key TEXT PRIMARY KEY,
                    chat_id INTEGER,
                    message_id INTEGER,
                    action TEXT,
                    actor_id INTEGER,
                    extra_json TEXT,
                    created_at INTEGER,
                    expires_at INTEGER
                )
                """
            )
            conn.commit()
            conn.close()
        except Exception:
            logger.exception("Error creando/esquivando esquema DB")

        # Load existing games into memory (safe: run synchronous here using a loop)
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(self._load_all())
            finally:
                # don't unset global event loop here (leave as-is)
                pass
        else:
            # We are in an event loop: schedule the loading as a task (best-effort)
            try:
                loop.create_task(self._load_all())
            except Exception:
                # fallback to blocking call in new loop
                loop2 = asyncio.new_event_loop()
                asyncio.set_event_loop(loop2)
                try:
                    loop2.run_until_complete(self._load_all())
                finally:
                    asyncio.set_event_loop(loop)

    # -------------------------
    # Low-level persistence (async)
    # -------------------------
    async def _load_all(self) -> None:
        """Carga todas las partidas y pending_actions en memoria (async)."""
        try:
            async with aiosqlite.connect(self.db_file) as db:
                # load games
                async with db.execute(
                    "SELECT chat_id, host_id, phase, roles_config, night_seconds, day_seconds, periodic_reminder_seconds, phase_deadline FROM games"
                ) as cur:
                    rows = await cur.fetchall()
                    for row in rows:
                        try:
                            chat_id, host_id, phase, roles_json, night_s, day_s, periodic, deadline = row
                            g = GameState(chat_id, host_id)
                            g.phase = phase or "lobby"
                            if roles_json:
                                try:
                                    g.roles_config = json.loads(roles_json)
                                except Exception:
                                    pass
                            g.night_seconds = int(night_s) if night_s is not None else g.night_seconds
                            g.day_seconds = int(day_s) if day_s is not None else g.day_seconds
                            g.periodic_reminder_seconds = int(periodic) if periodic is not None else g.periodic_reminder_seconds
                            g.phase_deadline = deadline
                            # load players
                            async with db.execute(
                                "SELECT user_id, name, role_key, alive, blocked, silenced FROM players WHERE chat_id=?", (chat_id,)
                            ) as pc:
                                prows = await pc.fetchall()
                                for p in prows:
                                    uid, name, role_key, alive, blocked, silenced = p
                                    g.players[int(uid)] = PlayerState(int(uid), name, role_key, bool(alive), bool(blocked), bool(silenced))
                            with self._lock:
                                self._games[int(chat_id)] = g
                        except Exception:
                            logger.exception("Error cargando fila de partida")
                # load pending_actions
                async with db.execute(
                    "SELECT key, chat_id, message_id, action, actor_id, extra_json, created_at, expires_at FROM pending_actions"
                ) as cur:
                    rows = await cur.fetchall()
                    for row in rows:
                        try:
                            key, chat_id, message_id, action, actor_id, extra_json, created_at, expires_at = row
                            try:
                                extra = json.loads(extra_json) if extra_json else {}
                            except Exception:
                                extra = {}
                            with self._lock:
                                g = self._games.get(int(chat_id))
                                if g is not None:
                                    g.pending_action_callbacks[key] = {
                                        "action": action,
                                        "actor": actor_id,
                                        "extra": extra,
                                        "message_id": message_id,
                                        "expires_at": expires_at,
                                    }
                        except Exception:
                            logger.exception("Error cargando pending_action row")
            logger.info("Loaded %d games from DB", len(self._games))
        except Exception:
            logger.exception("Error en _load_all")

    # -------------------------
    # Helper: cargar juego desde DB (síncrono)
    # -------------------------
    def _load_game_sync(self, chat_id: int) -> Optional[GameState]:
        """Carga un GameState completo desde la DB (síncrono)."""
        conn = None
        try:
            conn = sqlite3.connect(self.db_file)
            cur = conn.cursor()
            cur.execute(
                "SELECT chat_id, host_id, phase, roles_config, night_seconds, day_seconds, periodic_reminder_seconds, phase_deadline FROM games WHERE chat_id=?",
                (chat_id,),
            )
            row = cur.fetchone()
            if not row:
                conn.close()
                return None
            chat_id_db, host_id, phase, roles_json, night_s, day_s, periodic, deadline = row
            g = GameState(chat_id_db, host_id)
            g.phase = phase or "lobby"
            if roles_json:
                try:
                    g.roles_config = json.loads(roles_json)
                except Exception:
                    pass
            g.night_seconds = int(night_s) if night_s is not None else g.night_seconds
            g.day_seconds = int(day_s) if day_s is not None else g.day_seconds
            g.periodic_reminder_seconds = int(periodic) if periodic is not None else g.periodic_reminder_seconds
            g.phase_deadline = deadline

            # players
            cur.execute("SELECT user_id, name, role_key, alive, blocked, silenced FROM players WHERE chat_id=?", (chat_id_db,))
            for p in cur.fetchall():
                uid, name, role_key, alive, blocked, silenced = p
                g.players[int(uid)] = PlayerState(int(uid), name, role_key, bool(alive), bool(blocked), bool(silenced))

            # pending actions
            cur.execute("SELECT key, message_id, action, actor_id, extra_json, expires_at FROM pending_actions WHERE chat_id=?", (chat_id_db,))
            for row in cur.fetchall():
                key, message_id, action, actor_id, extra_json, expires_at = row
                try:
                    extra = json.loads(extra_json) if extra_json else {}
                except Exception:
                    extra = {}
                g.pending_action_callbacks[key] = {
                    "action": action,
                    "actor": actor_id,
                    "extra": extra,
                    "message_id": message_id,
                    "expires_at": expires_at,
                }

            conn.close()
            return g
        except Exception:
            logger.exception("Error cargando juego desde DB (sync) para chat %s", chat_id)
            try:
                if conn:
                    conn.close()
            except Exception:
                pass
            return None

    # -------------------------
    # get_game: memoria -> DB
    # -------------------------
    def get_game(self, chat_id: int) -> Optional[GameState]:
        with self._lock:
            g = self._games.get(int(chat_id))
            if g:
                return g
        # not in memory: try to load from DB
        g_db = self._load_game_sync(int(chat_id))
        if g_db:
            with self._lock:
                self._games[int(chat_id)] = g_db
            logger.info("GameManager: cargada partida %s desde DB a memoria", chat_id)
            return g_db
        return None

    # -------------------------
    # create_game: safe create + persist
    # -------------------------
    def create_game(self, chat_id: int, host_id: int) -> GameState:
        with self._lock:
            if int(chat_id) in self._games:
                raise ValueError("Game exists")
        # check DB
        existing = self._load_game_sync(int(chat_id))
        if existing:
            with self._lock:
                self._games[int(chat_id)] = existing
            raise ValueError("Game exists in DB (rehidratada)")

        g = GameState(int(chat_id), int(host_id))
        with self._lock:
            self._games[int(chat_id)] = g
        # persist
        self._persist_game(g)
        return g

    # -------------------------
    # remove_game: safe removal
    # -------------------------
    def remove_game(self, chat_id: int) -> bool:
        with self._lock:
            g = self._games.pop(int(chat_id), None)

        async def _rm():
            async with aiosqlite.connect(self.db_file) as db:
                await db.execute("DELETE FROM players WHERE chat_id=?", (int(chat_id),))
                await db.execute("DELETE FROM games WHERE chat_id=?", (int(chat_id),))
                await db.execute("DELETE FROM pending_actions WHERE chat_id=?", (int(chat_id),))
                await db.commit()

        # if loop running schedule; else run blocking
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop2 = asyncio.new_event_loop()
            asyncio.set_event_loop(loop2)
            loop2.run_until_complete(_rm())
            asyncio.set_event_loop(None)
        else:
            asyncio.create_task(_rm())
        return True

    # -------------------------
    # Async persist helper
    # -------------------------
    async def _persist_game_async(self, g: GameState):
        try:
            async with aiosqlite.connect(self.db_file) as db:
                roles_json = json.dumps(getattr(g, "roles_config", {}), ensure_ascii=False)
                await db.execute(
                    "INSERT OR REPLACE INTO games (chat_id, host_id, phase, roles_config, night_seconds, day_seconds, periodic_reminder_seconds, phase_deadline) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (int(g.chat_id), int(g.host_id), g.phase, roles_json, int(g.night_seconds), int(g.day_seconds), int(g.periodic_reminder_seconds), g.phase_deadline),
                )
                # upsert players: delete and insert (simple)
                await db.execute("DELETE FROM players WHERE chat_id=?", (int(g.chat_id),))
                for p in g.players.values():
                    await db.execute(
                        "INSERT INTO players (chat_id, user_id, name, role_key, alive, blocked, silenced) VALUES (?,?,?,?,?,?,?)",
                        (int(g.chat_id), int(p.user_id), p.name, p.role_key, int(bool(p.alive)), int(bool(p.blocked)), int(bool(p.silenced))),
                    )
                # pending actions
                await db.execute("DELETE FROM pending_actions WHERE chat_id=?", (int(g.chat_id),))
                for key, info in g.pending_action_callbacks.items():
                    extra_json = json.dumps(info.get("extra", {}), ensure_ascii=False)
                    await db.execute(
                        "INSERT INTO pending_actions (key, chat_id, message_id, action, actor_id, extra_json, created_at, expires_at) VALUES (?,?,?,?,?,?,?,?)",
                        (key, int(g.chat_id), info.get("message_id"), info.get("action"), info.get("actor"), extra_json, int(time.time()), info.get("expires_at")),
                    )
                await db.commit()
        except Exception:
            logger.exception("Error persisting game %s", getattr(g, "chat_id", None))
            raise

    def _persist_game(self, g: GameState):
        """Wrapper to call async persist from sync contexts safely."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # no running loop: create temporary
            loop2 = asyncio.new_event_loop()
            asyncio.set_event_loop(loop2)
            try:
                loop2.run_until_complete(self._persist_game_async(g))
            finally:
                asyncio.set_event_loop(None)
            return

        # if loop running, schedule task (don't block)
        try:
            if loop.is_running():
                asyncio.create_task(self._persist_game_async(g))
            else:
                loop.run_until_complete(self._persist_game_async(g))
        except Exception:
            logger.exception("Error scheduling persist for game %s", getattr(g, "chat_id", None))

    # -------------------------
    # Player helpers
    # -------------------------
    def add_player(self, chat_id: int, user_id: int, name: str) -> bool:
        g = self.get_game(chat_id)
        if g is None:
            return False
        with self._lock:
            if int(user_id) in g.players:
                return False
            g.players[int(user_id)] = PlayerState(int(user_id), name)
        self._persist_game(g)
        return True

    def remove_player_from_game(self, chat_id: int, user_id: int) -> bool:
        g = self.get_game(chat_id)
        if not g:
            return False
        with self._lock:
            if int(user_id) not in g.players:
                return False
            g.players.pop(int(user_id), None)
        self._persist_game(g)
        return True

    # -------------------------
    # Pending actions async helpers
    # -------------------------
    async def insert_pending_action_async(self, key: str, chat_id: int, message_id: int, action: str, actor_id: Optional[int], extra: dict, expires_at: Optional[int] = None):
        if expires_at is None:
            expires_at = int(time.time()) + 3600
        async with aiosqlite.connect(self.db_file) as db:
            await db.execute(
                "INSERT OR REPLACE INTO pending_actions (key, chat_id, message_id, action, actor_id, extra_json, created_at, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (key, int(chat_id), message_id, action, actor_id, json.dumps(extra, ensure_ascii=False), int(time.time()), expires_at),
            )
            await db.commit()
        with self._lock:
            g = self._games.get(int(chat_id))
            if g:
                g.pending_action_callbacks[key] = {"action": action, "actor": actor_id, "extra": extra, "message_id": message_id, "expires_at": expires_at}
        return True

    async def get_pending_action_async(self, key: str) -> Optional[dict]:
        async with aiosqlite.connect(self.db_file) as db:
            async with db.execute("SELECT key, chat_id, message_id, action, actor_id, extra_json, created_at, expires_at FROM pending_actions WHERE key=?", (key,)) as cur:
                row = await cur.fetchone()
                if not row:
                    return None
                k, chat_id, message_id, action, actor_id, extra_json, created_at, expires_at = row
                try:
                    extra = json.loads(extra_json) if extra_json else {}
                except Exception:
                    extra = {}
                return {"key": k, "chat_id": chat_id, "message_id": message_id, "action": action, "actor": actor_id, "extra": extra, "created_at": created_at, "expires_at": expires_at}

    async def delete_pending_action_async(self, key: str):
        async with aiosqlite.connect(self.db_file) as db:
            await db.execute("DELETE FROM pending_actions WHERE key=?", (key,))
            await db.commit()
        with self._lock:
            for g in self._games.values():
                if key in g.pending_action_callbacks:
                    del g.pending_action_callbacks[key]
        return True

    # Sync wrappers
    def insert_pending_action(self, *args, **kwargs):
        return asyncio.get_event_loop().run_until_complete(self.insert_pending_action_async(*args, **kwargs))

    def get_pending_action(self, key):
        return asyncio.get_event_loop().run_until_complete(self.get_pending_action_async(key))

    def delete_pending_action(self, key):
        return asyncio.get_event_loop().run_until_complete(self.delete_pending_action_async(key))

    # -------------------------
    # Resync all from DB (sync API)
    # -------------------------
    def resync_all_from_db(self, application: Optional[Any] = None) -> List[int]:
        """Carga en memoria todas las partidas encontradas en la DB que no estén en memoria.
        Devuelve la lista de chat_id cargados.
        """
        loaded = []
        try:
            conn = sqlite3.connect(self.db_file)
            cur = conn.cursor()
            cur.execute("SELECT chat_id FROM games")
            rows = [r[0] for r in cur.fetchall()]
            conn.close()
        except Exception:
            logger.exception("Error listando juegos en DB para resync_all")
            return loaded

        for cid in rows:
            with self._lock:
                if int(cid) in self._games:
                    continue
            g = self._load_game_sync(int(cid))
            if g:
                with self._lock:
                    self._games[int(cid)] = g
                loaded.append(int(cid))

        logger.info("Resynchronized %d games from DB: %s", len(loaded), loaded)
        # if application passed, try to reschedule jobs (best-effort)
        if application:
            try:
                resched = globals().get("reschedule_jobs_on_startup")
                if callable(resched):
                    try:
                        resched(application)
                    except Exception:
                        logger.exception("Error rescheduling after resync")
            except Exception:
                logger.exception("Error rescheduling after resync (outer)")
        return loaded

    # -------------------------
    # Expose snapshot of games
    # -------------------------
    @property
    def games(self):
        with self._lock:
            return dict(self._games)
