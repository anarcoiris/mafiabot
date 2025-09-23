#!/usr/bin/env python3
# game_manager.py
# Gestión de partidas + persistencia en SQLite.
# Combina API síncrona (para handlers) y helpers asíncronos (aiosqlite) para pending actions.
# Provee rehidratación, persistencia atómica, pending_actions y hooks para reprogramar jobs.

import os
import sqlite3
import aiosqlite
import threading
import asyncio
import json
import time
import logging
from typing import Optional, List, Dict, Any

from models import Game, Player
from db.migrations import init_db

logger = logging.getLogger("mafiabot.gamemgr")

DEFAULT_DB = os.environ.get("MAFIA_DB", "db/mafia_complete.db")


# Try to import engine job functions if available (used for rescheduling)
try:
    from game_engine import job_end_night, job_end_day, job_reminder, job_resolve_votes  # type: ignore
except Exception:
    job_end_night = None
    job_end_day = None
    job_reminder = None
    job_resolve_votes = None


class GameManager:
    def __init__(self, db_file: str = DEFAULT_DB):
        self.db_file = db_file
        init_db(self.db_file)  # ensure schema
        self._games: Dict[int, Game] = {}
        self._lock = threading.RLock()
        # load synchronously on init so memory is ready
        try:
            self._load_all_from_db()
        except Exception:
            logger.exception("Error loading games synchronously on startup; trying async load")
            # best-effort async load
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.create_task(self._load_all())
                else:
                    loop.run_until_complete(self._load_all())
            except Exception:
                # fallback: spawn new loop temporarily
                loop2 = asyncio.new_event_loop()
                try:
                    loop2.run_until_complete(self._load_all())
                finally:
                    try:
                        loop2.close()
                    except Exception:
                        pass

    # -------------------------
    # Low-level connections
    # -------------------------
    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_file, timeout=30, check_same_thread=False)
        # enable WAL for concurrency
        try:
            conn.execute("PRAGMA journal_mode=WAL;")
        except Exception:
            pass
        return conn

    # -------------------------
    # Async bulk load (aiosqlite)
    # -------------------------
    async def _load_all(self) -> None:
        """Carga todas las partidas y pending_actions en memoria (async)."""
        try:
            async with aiosqlite.connect(self.db_file) as db:
                # load games
                async with db.execute(
                    "SELECT chat_id, host_id, phase, roles_config, night_seconds, day_seconds, periodic_reminder_seconds, phase_deadline, created_at, updated_at FROM games"
                ) as cur:
                    rows = await cur.fetchall()
                    for row in rows:
                        try:
                            chat_id = int(row[0])
                            # players
                            async with db.execute(
                                "SELECT user_id, name, role_key, alive, blocked, silenced, dm_sent_ok FROM players WHERE chat_id=?", (chat_id,)
                            ) as pc:
                                prows = await pc.fetchall()
                                players = prows
                            g = Game.from_db_row(row, players)
                            with self._lock:
                                self._games[chat_id] = g
                        except Exception:
                            logger.exception("Error cargando fila (async) de partida")
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
                                if g:
                                    g.pending_action_callbacks[key] = {
                                        "action": action,
                                        "actor": actor_id,
                                        "extra": extra,
                                        "message_id": message_id,
                                        "expires_at": expires_at,
                                    }
                        except Exception:
                            logger.exception("Error cargando pending_action row (async)")
            logger.info("Async loaded %d games from DB", len(self._games))
        except Exception:
            logger.exception("Error en _load_all (async)")

    # -------------------------
    # Sync bulk load (sqlite3)
    # -------------------------
    def _load_all_from_db(self) -> None:
        """Carga todas las partidas y pending_actions desde DB (sync)."""
        try:
            conn = self._connect()
            cur = conn.cursor()
            cur.execute(
                "SELECT chat_id, host_id, phase, roles_config, night_seconds, day_seconds, periodic_reminder_seconds, phase_deadline, created_at, updated_at FROM games"
            )
            rows = cur.fetchall()
            for row in rows:
                try:
                    chat_id = int(row[0])
                    cur2 = conn.cursor()
                    cur2.execute(
                        "SELECT user_id, name, role_key, alive, blocked, silenced, dm_sent_ok FROM players WHERE chat_id=?", (chat_id,)
                    )
                    players = cur2.fetchall()
                    g = Game.from_db_row(row, players)
                    with self._lock:
                        self._games[chat_id] = g
                except Exception:
                    logger.exception("Error cargando fila (sync) de partida")
            # pending actions
            cur.execute(
                "SELECT key, chat_id, message_id, action, actor_id, extra_json, created_at, expires_at FROM pending_actions"
            )
            for row in cur.fetchall():
                try:
                    key, chat_id, message_id, action, actor_id, extra_json, created_at, expires_at = row
                    try:
                        extra = json.loads(extra_json) if extra_json else {}
                    except Exception:
                        extra = {}
                    with self._lock:
                        g = self._games.get(int(chat_id))
                        if g:
                            g.pending_action_callbacks[key] = {
                                "action": action,
                                "actor": actor_id,
                                "extra": extra,
                                "message_id": message_id,
                                "expires_at": expires_at,
                            }
                except Exception:
                    logger.exception("Error cargando pending_action row (sync)")
            conn.close()
            # cleanup expired pending actions to avoid stuck buttons
            try:
                self.cleanup_expired_pending_actions()
            except Exception:
                pass
            logger.info("Loaded %d games from DB (sync)", len(self._games))
        except Exception:
            logger.exception("Error en _load_all_from_db")

    # -------------------------
    # Load single game sync (helper)
    # -------------------------
    def _load_game_sync(self, chat_id: int) -> Optional[Game]:
        conn = None
        try:
            conn = self._connect()
            cur = conn.cursor()
            cur.execute(
                "SELECT chat_id, host_id, phase, roles_config, night_seconds, day_seconds, periodic_reminder_seconds, phase_deadline, created_at, updated_at FROM games WHERE chat_id=?",
                (chat_id,),
            )
            row = cur.fetchone()
            if not row:
                conn.close()
                return None
            cur.execute(
                "SELECT user_id, name, role_key, alive, blocked, silenced, dm_sent_ok FROM players WHERE chat_id=?",
                (chat_id,),
            )
            players = cur.fetchall()
            # pending actions for that chat
            cur.execute(
                "SELECT key, message_id, action, actor_id, extra_json, expires_at FROM pending_actions WHERE chat_id=?", (chat_id,)
            )
            pending_rows = cur.fetchall()
            g = Game.from_db_row(row, players)
            for prow in pending_rows:
                try:
                    key, message_id, action, actor_id, extra_json, expires_at = prow
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
                except Exception:
                    logger.exception("Error parsing pending row in _load_game_sync")
            conn.close()
            return g
        except Exception:
            logger.exception("Error cargando juego sync %s", chat_id)
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass
            return None

    # -------------------------
    # Public API: get/create/remove
    # -------------------------
    def get_game(self, chat_id: int) -> Optional[Game]:
        with self._lock:
            g = self._games.get(int(chat_id))
            if g:
                return g
        # attempt db rehydrate
        g = self._load_game_sync(int(chat_id))
        if g:
            with self._lock:
                self._games[int(chat_id)] = g
            logger.info("GameManager: rehydrated game %s from DB", chat_id)
        return g

    def create_game(self, chat_id: int, host_id: int) -> Game:
        with self._lock:
            if int(chat_id) in self._games:
                raise ValueError("Game exists in memory")
        # atomic check+insert
        conn = self._connect()
        cur = conn.cursor()
        try:
            cur.execute("BEGIN")
            cur.execute("SELECT chat_id FROM games WHERE chat_id=?", (int(chat_id),))
            if cur.fetchone():
                conn.rollback()
                conn.close()
                g = self.get_game(int(chat_id))
                raise ValueError("Game exists in DB")
            g = Game(int(chat_id), int(host_id))
            cur.execute(
                "INSERT INTO games (chat_id, host_id, phase, roles_config, night_seconds, day_seconds, periodic_reminder_seconds, phase_deadline, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                g.to_db_tuple(),
            )
            conn.commit()
            with self._lock:
                self._games[int(chat_id)] = g
            logger.info("Created game %s by host %s", chat_id, host_id)
            return g
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            logger.exception("Error creating game %s", chat_id)
            raise
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def remove_game(self, chat_id: int) -> bool:
        with self._lock:
            self._games.pop(int(chat_id), None)
        try:
            conn = self._connect()
            cur = conn.cursor()
            cur.execute("DELETE FROM players WHERE chat_id=?", (int(chat_id),))
            cur.execute("DELETE FROM pending_actions WHERE chat_id=?", (int(chat_id),))
            cur.execute("DELETE FROM games WHERE chat_id=?", (int(chat_id),))
            conn.commit()
            conn.close()
            logger.info("Removed game %s", chat_id)
            return True
        except Exception:
            logger.exception("Error removing game %s", chat_id)
            return False

    # -------------------------
    # Persistence helpers (async + sync wrapper)
    # -------------------------
    async def _persist_game_async(self, g: Game):
        try:
            async with aiosqlite.connect(self.db_file) as db:
                roles_json = json.dumps(getattr(g, "roles_config", {}), ensure_ascii=False)
                await db.execute(
                    "INSERT INTO games (chat_id, host_id, phase, roles_config, night_seconds, day_seconds, periodic_reminder_seconds, phase_deadline, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?) ON CONFLICT(chat_id) DO UPDATE SET host_id=excluded.host_id, phase=excluded.phase, roles_config=excluded.roles_config, night_seconds=excluded.night_seconds, day_seconds=excluded.day_seconds, periodic_reminder_seconds=excluded.periodic_reminder_seconds, phase_deadline=excluded.phase_deadline, updated_at=excluded.updated_at",
                    (int(g.chat_id), int(g.host_id), g.phase, roles_json, int(g.night_seconds), int(g.day_seconds), int(g.periodic_reminder_seconds), g.phase_deadline, int(getattr(g, "created_at", int(time.time()))), int(time.time())),
                )
                # upsert players: do deletes & inserts for simplicity
                await db.execute("DELETE FROM players WHERE chat_id=?", (int(g.chat_id),))
                for p in g.players.values():
                    await db.execute(
                        "INSERT INTO players (chat_id, user_id, name, role_key, alive, blocked, silenced, dm_sent_ok) VALUES (?,?,?,?,?,?,?,?)",
                        (int(g.chat_id), int(p.user_id), p.name, p.role_key, int(bool(p.alive)), int(bool(p.blocked)), int(bool(p.silenced)), int(bool(getattr(p, "dm_sent_ok", False)))),
                    )
                # pending actions
                await db.execute("DELETE FROM pending_actions WHERE chat_id=?", (int(g.chat_id),))
                for key, info in (g.pending_action_callbacks.items() if isinstance(g.pending_action_callbacks, dict) else []):
                    extra_json = json.dumps(info.get("extra", {}), ensure_ascii=False)
                    await db.execute(
                        "INSERT OR REPLACE INTO pending_actions (key, chat_id, message_id, action, actor_id, extra_json, created_at, expires_at) VALUES (?,?,?,?,?,?,?,?)",
                        (key, int(g.chat_id), info.get("message_id"), info.get("action"), info.get("actor"), extra_json, int(time.time()), info.get("expires_at")),
                    )
                await db.commit()
        except Exception:
            logger.exception("Error persisting game (async) %s", getattr(g, "chat_id", None))
            raise

    def _persist_game(self, g: Game):
        """Wrapper that schedules or runs the async persist depending on the event loop state."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # no loop running: create temp loop to run
            loop2 = asyncio.new_event_loop()
            try:
                asyncio.set_event_loop(loop2)
                loop2.run_until_complete(self._persist_game_async(g))
            finally:
                try:
                    loop2.close()
                except Exception:
                    pass
                try:
                    asyncio.set_event_loop(None)
                except Exception:
                    pass
            return

        # loop exists
        if loop.is_running():
            # schedule as task (don't block)
            try:
                asyncio.create_task(self._persist_game_async(g))
            except Exception:
                # fallback to sync run
                logger.exception("Could not schedule persist task; running synchronously")
                loop.run_until_complete(self._persist_game_async(g))
        else:
            loop.run_until_complete(self._persist_game_async(g))

    def persist_game(self, g: Game):
        with self._lock:
            g.updated_at = int(time.time())
            self._persist_game(g)

    # -------------------------
    # Player helpers
    # -------------------------
    def add_player(self, chat_id: int, user_id: int, name: str) -> bool:
        with self._lock:
            g = self.get_game(chat_id)
            if g is None:
                return False
            if int(user_id) in g.players:
                return False
            g.players[int(user_id)] = Player(int(user_id), name)
            self.persist_game(g)
            return True

    def remove_player_from_game(self, chat_id: int, user_id: int) -> bool:
        with self._lock:
            g = self.get_game(chat_id)
            if not g:
                return False
            if int(user_id) in g.players:
                del g.players[int(user_id)]
                self.persist_game(g)
                return True
            return False

    # -------------------------
    # Pending actions (async)
    # -------------------------
    async def insert_pending_action_async(
        self,
        key: str,
        chat_id: int,
        message_id: Optional[int],
        action: str,
        actor_id: Optional[int],
        extra: dict,
        expires_at: Optional[int] = None,
    ) -> bool:
        if expires_at is None:
            expires_at = int(time.time()) + 3600
        try:
            async with aiosqlite.connect(self.db_file) as db:
                await db.execute(
                    "INSERT OR REPLACE INTO pending_actions (key, chat_id, message_id, action, actor_id, extra_json, created_at, expires_at) VALUES (?,?,?,?,?,?,?,?)",
                    (key, int(chat_id), message_id, action, actor_id, json.dumps(extra, ensure_ascii=False), int(time.time()), int(expires_at)),
                )
                await db.commit()
            # update memory
            with self._lock:
                g = self._games.get(int(chat_id))
                if g:
                    g.pending_action_callbacks[key] = {"action": action, "actor": actor_id, "extra": extra, "message_id": message_id, "expires_at": expires_at}
            return True
        except Exception:
            logger.exception("Error inserting pending action %s", key)
            raise

    async def get_pending_action_async(self, key: str) -> Optional[dict]:
        try:
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
        except Exception:
            logger.exception("Error get_pending_action_async %s", key)
            return None

    async def delete_pending_action_async(self, key: str) -> bool:
        try:
            async with aiosqlite.connect(self.db_file) as db:
                await db.execute("DELETE FROM pending_actions WHERE key=?", (key,))
                await db.commit()
            with self._lock:
                for g in self._games.values():
                    if key in g.pending_action_callbacks:
                        del g.pending_action_callbacks[key]
            return True
        except Exception:
            logger.exception("Error deleting pending action %s", key)
            return False

    async def append_confirmation_async(self, key: str, user_id: int) -> Optional[List[int]]:
        """Append user_id to extra.confirmations for key and return the confirmation list."""
        try:
            async with aiosqlite.connect(self.db_file) as db:
                async with db.execute("SELECT extra_json FROM pending_actions WHERE key=?", (key,)) as cur:
                    row = await cur.fetchone()
                    if not row:
                        return None
                    extra_json = row[0] or "{}"
                    try:
                        extra = json.loads(extra_json)
                    except Exception:
                        extra = {}
                confs = extra.get("confirmations", [])
                if user_id not in confs:
                    confs.append(user_id)
                    extra["confirmations"] = confs
                    await db.execute("UPDATE pending_actions SET extra_json=? WHERE key=?", (json.dumps(extra, ensure_ascii=False), key))
                    await db.commit()
                # update memory
                with self._lock:
                    for g in self._games.values():
                        if key in g.pending_action_callbacks:
                            g.pending_action_callbacks[key]["extra"] = extra
                return confs
        except Exception:
            logger.exception("Error appending confirmation for %s", key)
            return None

    # -------------------------
    # Sync wrappers for pending (for handlers convenience)
    # -------------------------
    def insert_pending_action(self, *args, **kwargs):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # no running loop: create temporary
            loop2 = asyncio.new_event_loop()
            try:
                asyncio.set_event_loop(loop2)
                return loop2.run_until_complete(self.insert_pending_action_async(*args, **kwargs))
            finally:
                try:
                    loop2.close()
                except Exception:
                    pass
                try:
                    asyncio.set_event_loop(None)
                except Exception:
                    pass
        else:
            if loop.is_running():
                # schedule and return immediately (not ideal for immediate return)
                asyncio.create_task(self.insert_pending_action_async(*args, **kwargs))
                return True
            else:
                return loop.run_until_complete(self.insert_pending_action_async(*args, **kwargs))

    def get_pending_action(self, key: str):
        try:
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(self.get_pending_action_async(key))
        except RuntimeError:
            loop2 = asyncio.new_event_loop()
            try:
                return loop2.run_until_complete(self.get_pending_action_async(key))
            finally:
                try:
                    loop2.close()
                except Exception:
                    pass

    def delete_pending_action(self, key: str):
        try:
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(self.delete_pending_action_async(key))
        except RuntimeError:
            loop2 = asyncio.new_event_loop()
            try:
                return loop2.run_until_complete(self.delete_pending_action_async(key))
            finally:
                try:
                    loop2.close()
                except Exception:
                    pass

    def append_confirmation(self, key: str, user_id: int):
        try:
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(self.append_confirmation_async(key, user_id))
        except RuntimeError:
            loop2 = asyncio.new_event_loop()
            try:
                return loop2.run_until_complete(self.append_confirmation_async(key, user_id))
            finally:
                try:
                    loop2.close()
                except Exception:
                    pass


    # -------------------------
    # Persistencia síncrona directa (útil para shutdown)
    # -------------------------
    def _persist_game_sync(self, g: Game) -> None:
        """Persistir un Game de forma síncrona usando sqlite3 (no depende de event loop)."""
        try:
            conn = self._connect()
            cur = conn.cursor()
            roles_json = json.dumps(getattr(g, "roles_config", {}), ensure_ascii=False)
            cur.execute(
                """INSERT INTO games
                   (chat_id, host_id, phase, roles_config, night_seconds,
                    day_seconds, periodic_reminder_seconds, phase_deadline,
                    created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(chat_id) DO UPDATE SET
                     host_id=excluded.host_id,
                     phase=excluded.phase,
                     roles_config=excluded.roles_config,
                     night_seconds=excluded.night_seconds,
                     day_seconds=excluded.day_seconds,
                     periodic_reminder_seconds=excluded.periodic_reminder_seconds,
                     phase_deadline=excluded.phase_deadline,
                     updated_at=excluded.updated_at
                """,
                g.to_db_tuple(),
            )
            # upsert players determinísticamente: borramos y reinsertamos
            cur.execute("DELETE FROM players WHERE chat_id=?", (int(g.chat_id),))
            for p in g.players.values():
                cur.execute(
                    "INSERT INTO players (chat_id, user_id, name, role_key, alive, blocked, silenced, dm_sent_ok) VALUES (?,?,?,?,?,?,?,?)",
                    (int(g.chat_id), int(p.user_id), p.name, p.role_key, int(bool(p.alive)), int(bool(p.blocked)), int(bool(p.silenced)), int(bool(getattr(p, "dm_sent_ok", False)))),
                )
            # pending actions: opcionalmente persistimos
            cur.execute("DELETE FROM pending_actions WHERE chat_id=?", (int(g.chat_id),))
            for key, info in (g.pending_action_callbacks.items() if isinstance(g.pending_action_callbacks, dict) else []):
                extra_json = json.dumps(info.get("extra", {}), ensure_ascii=False)
                cur.execute(
                    "INSERT OR REPLACE INTO pending_actions (key, chat_id, message_id, action, actor_id, extra_json, created_at, expires_at) VALUES (?,?,?,?,?,?,?,?)",
                    (key, int(g.chat_id), info.get("message_id"), info.get("action"), info.get("actor"), extra_json, int(time.time()), info.get("expires_at")),
                )
            conn.commit()
        except Exception:
            logger.exception("Error persisting game (sync) %s", getattr(g, "chat_id", None))
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def shutdown(self, wait_seconds: int = 5) -> None:
        """Flush de todas las partidas a DB y cleanup. Idempotente y seguro para atexit."""
        logger.info("Shutdown: persisting all games (%d) before exit...", len(self._games))
        start = time.time()
        with self._lock:
            # snapshot keys para evitar mutation durante iteración
            games_snapshot = list(self._games.values())
        for g in games_snapshot:
            try:
                self._persist_game_sync(g)
            except Exception:
                logger.exception("Error persisting during shutdown for game %s", getattr(g, "chat_id", None))
            # optional: clear job ids to avoid trying to reschedule them later
            try:
                g.job_ids.clear()
            except Exception:
                pass
            # if time is running out, break
            if time.time() - start > wait_seconds:
                logger.warning("Shutdown: time budget expired after %.2fs", time.time() - start)
                break
        logger.info("Shutdown: persisted %d games (attempted)", len(games_snapshot))


    # -------------------------
    # Resync + job rescheduling
    # -------------------------
    def resync_all_from_db(self, application: Optional[Any] = None) -> List[int]:
        """Carga en memoria todas las partidas encontradas en la DB que no estén en memoria."""
        loaded: List[int] = []
        try:
            conn = self._connect()
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
    # Expired pending cleanup
    # -------------------------
    def cleanup_expired_pending_actions(self):
        now = int(time.time())
        try:
            conn = self._connect()
            cur = conn.cursor()
            cur.execute("DELETE FROM pending_actions WHERE expires_at IS NOT NULL AND expires_at < ?", (now,))
            deleted = cur.rowcount
            conn.commit()
            conn.close()
            if deleted:
                logger.info("Cleaned up %d expired pending_actions from DB", deleted)
        except Exception:
            logger.exception("Error cleaning expired pending_actions")

    # -------------------------
    # Expose snapshot
    # -------------------------
    @property
    def games(self) -> Dict[int, Game]:
        with self._lock:
            return dict(self._games)


# -------------------------
# Reschedule helper used by main
# -------------------------
def reschedule_jobs_on_startup(app: Any):
    """Idempotent re-scheduling of jobs for loaded games (if job functions available)."""
    try:
        with GAME._lock:
            games_copy = list(GAME._games.values())
    except Exception:
        games_copy = []
    for g in games_copy:
        try:
            if g.phase in ("night",) and g.phase_deadline:
                remaining = int(g.phase_deadline) - int(time.time())
                if remaining < 0:
                    remaining = 1
                if job_end_night and hasattr(app, "job_queue"):
                    job = app.job_queue.run_once(lambda c: asyncio.create_task(job_end_night(c, g.chat_id)), when=remaining, chat_id=g.chat_id)
                    g.job_ids["night_end"] = job.name
                # reminder
                if job_reminder and hasattr(app, "job_queue"):
                    rjob = app.job_queue.run_repeating(lambda c: asyncio.create_task(job_reminder(c, g.chat_id)), interval=g.periodic_reminder_seconds, first=30, chat_id=g.chat_id)
                    g.job_ids["reminder"] = rjob.name
            elif g.phase in ("day",) and g.phase_deadline:
                remaining = int(g.phase_deadline) - int(time.time())
                if remaining < 0:
                    remaining = 1
                if job_end_day and hasattr(app, "job_queue"):
                    job = app.job_queue.run_once(lambda c: asyncio.create_task(job_end_day(c, g.chat_id)), when=remaining, chat_id=g.chat_id)
                    g.job_ids["day_end"] = job.name
                if job_reminder and hasattr(app, "job_queue"):
                    rjob = app.job_queue.run_repeating(lambda c: asyncio.create_task(job_reminder(c, g.chat_id)), interval=g.periodic_reminder_seconds, first=30, chat_id=g.chat_id)
                    g.job_ids["reminder"] = rjob.name
        except Exception:
            logger.exception("Error rescheduling job for game %s", getattr(g, "chat_id", None))


# Single global manager instance for convenience
GAME = GameManager(DEFAULT_DB)

# -------------------------
# Shutdown hooks (atexit + signals)
# -------------------------
def _on_terminate_signal(signum, frame):
    try:
        logger.info("Signal %s received: calling GAME.shutdown()", signum)
        GAME.shutdown(wait_seconds=5)
    except Exception:
        logger.exception("Error in signal handler")
    # exit cleanly
    try:
        import sys
        sys.exit(0)
    except Exception:
        pass

import atexit
import signal
import sys

# Register atexit (best-effort)
try:
    atexit.register(lambda: GAME.shutdown(wait_seconds=5))
except Exception:
    logger.exception("Could not register atexit handler")

# Register signals
for sig in ("SIGINT", "SIGTERM"):
    try:
        sign = getattr(signal, sig)
        signal.signal(sign, _on_terminate_signal)
    except Exception:
        logger.debug("Could not bind signal %s", sig)

# Windows: SIGBREAK (CTRL+BREAK)
if hasattr(signal, "SIGBREAK"):
    try:
        signal.signal(signal.SIGBREAK, _on_terminate_signal)
    except Exception:
        logger.debug("Could not bind SIGBREAK")
