#!/usr/bin/env python3
"""
main.py (fixed)
Versión completa y robusta del motor "Mafia" para Telegram (monolito).
- Persistencia con SQLite (aiosqlite)
- pending_actions persistidas (UUID keys, confirmations array)
- mafia_confirm flow (unanimity by default) + timeout fallback (majority)
- re-scheduling of jobs on startup (phase_deadline persisted)
- Inline keyboards with UUID callback keys
- Flask dashboard (basic) to visualize and edit games (token-based minimal auth)
- JobQueue scheduling for night/day and reminders
- Designed to be refactorable into modules later

Requisitos:
  pip install python-telegram-bot==20.3 Flask aiosqlite python-dotenv pytest

Uso:
  set TELEGRAM_TOKEN=...
  set MAFIA_DASH_TOKEN=...
  python mafia_bot_complete_fixed.py
"""
# variables de entorno
from dotenv import load_dotenv
load_dotenv()

# bot imports
import os
import sys
import time
import json
import asyncio
import logging
import threading
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
from enum import Enum
from collections import defaultdict, Counter

import aiosqlite
import sqlite3
from flask import Flask, render_template_string, request, redirect, url_for, Response, jsonify, current_app

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

# ----------------------------
# Logging
# ----------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mafia_complete")

# ----------------------------
# DB / Schema
# ----------------------------
from game_manager import GameManager

DB_FILE = os.environ.get("MAFIA_DB", "db/mafia_complete.db")
GAME = GameManager(DB_FILE)
DASH_TOKEN = os.environ.get("MAFIA_DASH_TOKEN", "superlirio")  # minimal dashboard token
DASH_PORT = int(os.environ.get("MAFIA_DASH_PORT", "8006"))

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS games (
    chat_id INTEGER PRIMARY KEY,
    host_id INTEGER,
    phase TEXT,
    roles_config TEXT,
    night_seconds INTEGER,
    day_seconds INTEGER,
    periodic_reminder_seconds INTEGER,
    phase_deadline INTEGER
);

CREATE TABLE IF NOT EXISTS players (
    chat_id INTEGER,
    user_id INTEGER,
    name TEXT,
    role_key TEXT,
    alive INTEGER,
    blocked INTEGER,
    silenced INTEGER,
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


def init_db_sync():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.executescript(SCHEMA_SQL)
    conn.commit()
    conn.close()


init_db_sync()
# Game engine functions moved to game_engine.py
from game_engine import assign_roles, resolve_night, resolve_votes_job



# ----------------------------
# Helpers
# ----------------------------
MIN_PHASE_SECONDS = 120
MAX_PHASE_SECONDS = 7 * 24 * 3600


def clamp_phase_seconds(sec: int) -> int:
    return max(MIN_PHASE_SECONDS, min(MAX_PHASE_SECONDS, sec))


def mk_callback_key() -> str:
    return str(uuid.uuid4())


def mention(uid: int, name: str) -> str:
    return f"[{name}](tg://user?id={uid})"



# Models moved to models.py
from models import *

GAME = GameManager(DB_FILE)
def check_win_conditions_sync(g: GameState) -> Optional[str]:
    mafias = [p for p in g.players.values() if p.alive and p.role_key and ROLES[p.role_key].faction == Faction.MAFIA]
    towns = [p for p in g.players.values() if p.alive and p.role_key and ROLES[p.role_key].faction == Faction.TOWN]
    sk = [p for p in g.players.values() if p.alive and p.role_key == "asesino"]
    if not mafias and not sk:
        return "town"
    if mafias and len(mafias) >= len(towns):
        return "mafia"
    if sk and len([p for p in g.players.values() if p.alive]) == 1:
        return "serial"
    return None
    def get_game(self, chat_id: int) -> Optional[GameState]:
        with self._lock:
            g = self._games.get(chat_id)
            if g:
                return g
        # no estaba en memoria: intentar hidratar desde DB
        g_db = self._load_game_sync(chat_id)
        if g_db:
            with self._lock:
                self._games[chat_id] = g_db
            logger.info("GameManager: cargada partida %s desde DB a memoria", chat_id)
            return g_db
        return None
        def get_game(self, chat_id: int) -> Optional[GameState]:
            with self._lock:
                return self._games.get(chat_id)


    def create_game(self, chat_id: int, host_id: int) -> GameState:
        with self._lock:
            if chat_id in self._games:
                raise ValueError("Game exists")
        # chequeo en DB (para evitar inconsistencias)
        existing = self._load_game_sync(chat_id)
        if existing:
            # hidratar en memoria y abortar la creación
            with self._lock:
                self._games[chat_id] = existing
            raise ValueError("Game exists in DB (rehidratada)")

        # safe create
        g = GameState(chat_id, host_id)
        with self._lock:
            self._games[chat_id] = g
        # persistir (upsert) - no debería haber conflicto porque ya comprobamos DB
        self._persist_game(g)
        return g


    def remove_game(self, chat_id: int):
        with self._lock:
            g = self._games.pop(chat_id, None)

        async def _rm():
            async with aiosqlite.connect(self.db_file) as db:
                await db.execute("DELETE FROM players WHERE chat_id=?", (chat_id,))
                await db.execute("DELETE FROM games WHERE chat_id=?", (chat_id,))
                await db.execute("DELETE FROM pending_actions WHERE chat_id=?", (chat_id,))
                await db.commit()

        # si hay un loop corriendo, crear task; si no, ejecutar bloqueante
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # no hay loop => ejecutar sincrónicamente
            loop2 = asyncio.new_event_loop()
            asyncio.set_event_loop(loop2)
            loop2.run_until_complete(_rm())
            asyncio.set_event_loop(None)
        else:
            # estamos en loop: crear tarea asíncrona
            asyncio.create_task(_rm())
        return True
        def remove_game(self, chat_id: int):
            with self._lock:
                if chat_id in self._games:
                    del self._games[chat_id]

            async def _rm():
                async with aiosqlite.connect(self.db_file) as db:
                    await db.execute("DELETE FROM players WHERE chat_id=?", (chat_id,))
                    await db.execute("DELETE FROM games WHERE chat_id=?", (chat_id,))
                    await db.execute("DELETE FROM pending_actions WHERE chat_id=?", (chat_id,))
                    await db.commit()

            loop = asyncio.get_event_loop()
            loop.run_until_complete(_rm())

        def add_player(self, chat_id: int, user_id: int, name: str) -> bool:
            with self._lock:
                g = self.get_game(chat_id)
                if not g:
                    raise KeyError("No game")
                if user_id in g.players:
                    return False
                g.players[user_id] = PlayerState(user_id, name)
                self._persist_game(g)
                return True

        def remove_player_from_game(self, chat_id: int, user_id: int) -> bool:
            with self._lock:
                g = self.get_game(chat_id)
                if not g:
                    return False
                if user_id in g.players:
                    del g.players[user_id]
                    self._persist_game(g)
                    return True
                return False

        # --- pending_action helpers (async) ---
        async def insert_pending_action_async(
            self, key: str, chat_id: int, message_id: int, action: str, actor_id: Optional[int], extra: dict, expires_at: Optional[int] = None
        ):
            if expires_at is None:
                expires_at = int(time.time()) + 3600
            async with aiosqlite.connect(self.db_file) as db:
                await db.execute(
                    """
                    INSERT INTO pending_actions (key, chat_id, message_id, action, actor_id, extra_json, created_at, expires_at)
                    VALUES (?,?,?,?,?,?,?,?)
                    ON CONFLICT(key) DO UPDATE SET
                        chat_id=excluded.chat_id,
                        message_id=excluded.message_id,
                        action=excluded.action,
                        actor_id=excluded.actor_id,
                        extra_json=excluded.extra_json,
                        created_at=excluded.created_at,
                        expires_at=excluded.expires_at
                """,
                    (key, chat_id, message_id, action, actor_id, json.dumps(extra, ensure_ascii=False), int(time.time()), expires_at),
                )
                await db.commit()
            with self._lock:
                g = self._games.get(chat_id)
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
            # memory cleanup
            with self._lock:
                for g in self._games.values():
                    if key in g.pending_action_callbacks:
                        del g.pending_action_callbacks[key]
            return True

        async def append_confirmation_async(self, key: str, user_id: int) -> Optional[List[int]]:
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

        # synchronous wrappers for convenience
        def insert_pending_action(self, *args, **kwargs):
            return asyncio.get_event_loop().run_until_complete(self.insert_pending_action_async(*args, **kwargs))

        def get_pending_action(self, key):
            return asyncio.get_event_loop().run_until_complete(self.get_pending_action_async(key))

        def delete_pending_action(self, key):
            return asyncio.get_event_loop().run_until_complete(self.delete_pending_action_async(key))

        def append_confirmation(self, key, user_id):
            return asyncio.get_event_loop().run_until_complete(self.append_confirmation_async(key, user_id))

        @property
        def games(self):
            with self._lock:
                return dict(self._games)



    # ----------------------------
    # Game Engine (assign, resolve, check winners)
    # ----------------------------
    import random





# ----------------------------
# Telegram handlers & callback processing (core)
# ----------------------------
application: Optional[Application] = None  # filled in main()


async def cmd_crearpartida(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    if chat.type == "private":
        await update.message.reply_text("Crea la partida en un grupo.")
        return
    try:
        GAME.create_game(chat.id, user.id)
        await update.message.reply_text(f"Partida creada por {user.first_name}. Usa /unirme para entrar.")
    except Exception:
        await update.message.reply_text("Ya existe una partida en este grupo.")


async def cmd_unirme(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    g = GAME.get_game(chat.id)
    if not g:
        await update.message.reply_text("No hay partida en este grupo. Crea una con /crearpartida.")
        return
    ok = GAME.add_player(chat.id, user.id, user.first_name)
    if ok:
        await update.message.reply_text(f"{user.first_name} se ha unido a la partida.")
    else:
        await update.message.reply_text("Ya estabas en la partida.")


async def cmd_salirme(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    g = GAME.get_game(chat.id)
    if not g:
        await update.message.reply_text("No hay partida.")
        return
    if g.phase != "lobby":
        await update.message.reply_text("No puedes salir una vez que la partida ha empezado.")
        return
    ok = GAME.remove_player_from_game(chat.id, user.id)
    if ok:
        await update.message.reply_text("Te has salido de la partida.")
    else:
        await update.message.reply_text("No estabas en la partida.")


async def cmd_estado(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    g = GAME.get_game(chat.id)
    if not g:
        await update.message.reply_text("No hay partida en este grupo.")
        return
    lines = [f"Partida en chat {g.chat_id} - fase: {g.phase}", "", "Jugadores vivos:"]
    for p in g.players.values():
        if p.alive:
            lines.append(f"- {p.name} {'(silenciado)' if p.silenced else ''}")
    await update.message.reply_text("\n".join(lines))


async def cmd_resyncpartida(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando para rehidratar desde DB la partida si existe (útil cuando hay inconsistencias)."""
    chat = update.effective_chat
    user = update.effective_user
    # Intentar cargar desde DB
    g = GAME.get_game(chat.id)
    if g:
        await update.message.reply_text("La partida ya está cargada en memoria. Fase: %s" % g.phase)
        return
    # cargar desde DB
    g_db = GAME._load_game_sync(chat.id)
    if g_db:
        with GAME._lock:
            GAME._games[chat.id] = g_db
        await update.message.reply_text("Partida rehidratada desde la base de datos. Fase: %s" % g_db.phase)
    else:
        await update.message.reply_text("No hay partida en la base de datos para este grupo.")


async def cmd_borrarpartida(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Borra partida (memoria + DB). Solo admins/creador pueden ejecutar."""
    chat = update.effective_chat
    user = update.effective_user
    # verificar privilegios
    try:
        member = await context.bot.get_chat_member(chat.id, user.id)
        if member.status not in ("administrator", "creator"):
            await update.message.reply_text("Solo un administrador o el creador del grupo puede borrar la partida.")
            return
    except Exception:
        # si fallo al consultar, exigir que sea privado (fallback)
        pass

    # cancelar jobs si existen
    g = GAME.get_game(chat.id)
    if g:
        try:
            for jid in list(g.job_ids.values()):
                try:
                    j = context.job_queue.get_job(jid)
                    if j:
                        j.schedule_removal()
                except Exception:
                    pass
        except Exception:
            pass

    GAME.remove_game(chat.id)
    await update.message.reply_text("Partida borrada (memoria y base de datos).")



# build keyboard for player selection, persist pending action and return InlineKeyboardMarkup
async def build_player_keyboard_and_persist(g: GameState, actor_id: int, action_tag: str, application: Application, expires_in: int = 3600) -> Optional[InlineKeyboardMarkup]:
    rows = []
    for p in g.players.values():
        if not p.alive:
            continue
        if p.user_id == actor_id:
            continue
        key = mk_callback_key()
        # create a pending action stored in DB; message_id unknown yet (0) -> will update after send if needed
        extra = {"target": p.user_id, "confirmations": []}
        await GAME.insert_pending_action_async(key=key, chat_id=g.chat_id, message_id=0, action=action_tag, actor_id=actor_id, extra=extra, expires_at=int(time.time()) + expires_in)
        rows.append([InlineKeyboardButton(p.name, callback_data=f"{key}:{p.user_id}")])
    if not rows:
        return None
    return InlineKeyboardMarkup(rows)


async def prompt_night(g: GameState, application: Application):
    bot = application.bot
    # for each player with night action, send DM with persisted pending actions
    for p in list(g.players.values()):
        if not p.alive:
            continue
        role = ROLES.get(p.role_key) if p.role_key else None
        if not role or not role.has_night_action:
            continue
        action_tag = None
        if role.key in ("mafia", "padrino", "consorte"):
            action_tag = "mafia_pick"
        elif role.key == "doctor":
            action_tag = "heal"
        elif role.key in ("escort", "consorte"):
            action_tag = "block"
        elif role.key == "guardaespaldas":
            action_tag = "guard"
        elif role.key == "vigilante":
            action_tag = "kill"
        elif role.key == "asesino":
            action_tag = "serial_kill"
        elif role.key in ("detective", "sheriff"):
            action_tag = "investigate"
        elif role.key == "chantajeador":
            action_tag = "blackmail"
        else:
            action_tag = None
        if not action_tag:
            continue
        kb = await build_player_keyboard_and_persist(g, p.user_id, action_tag, application)
        try:
            if kb:
                sent = await bot.send_message(p.user_id, f"🌙 Noche: *{role.name}*. Elige objetivo:", parse_mode="Markdown", reply_markup=kb)
                # update persisted records for message_id to allow message edits if necessary
                async with aiosqlite.connect(GAME.db_file) as db:
                    async with db.execute("SELECT key FROM pending_actions WHERE chat_id=? AND actor_id=? AND action=? AND message_id=0", (g.chat_id, p.user_id, action_tag)) as cur:
                        rows = await cur.fetchall()
                        for (key,) in rows:
                            await db.execute("UPDATE pending_actions SET message_id=? WHERE key=?", (sent.message_id, key))
                    await db.commit()
                # update memory mapping by re-loading these pending actions (quick way)
                async with aiosqlite.connect(GAME.db_file) as db:
                    async with db.execute("SELECT key, extra_json, expires_at FROM pending_actions WHERE chat_id=? AND actor_id=? AND action=? AND message_id=?", (g.chat_id, p.user_id, action_tag, sent.message_id)) as cur:
                        rows = await cur.fetchall()
                        for row in rows:
                            key, extra_json, expires_at = row
                            try:
                                extra = json.loads(extra_json) if extra_json else {}
                            except Exception:
                                extra = {}
                            g.pending_action_callbacks[key] = {"action": action_tag, "actor": p.user_id, "extra": extra, "message_id": sent.message_id, "expires_at": expires_at}
            else:
                await bot.send_message(p.user_id, f"🌙 Noche: *{role.name}*. No hay objetivos disponibles.", parse_mode="Markdown")
        except Exception:
            logger.warning("No pude enviar DM a %s", p.user_id)


# Callback handler (central): loads pending action from memory or DB, validates, processes actions
async def cb_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data or ""
    user = update.effective_user
    if ":" not in data:
        await query.edit_message_text("Acción inválida.")
        return
    key, target_s = data.split(":", 1)
    try:
        target = int(target_s)
    except Exception:
        await query.edit_message_text("Target inválido.")
        return

    # locate pending action: memory first
    g = None
    gctx = None
    for gg in GAME.games.values():
        if key in gg.pending_action_callbacks:
            g = gg
            gctx = gg.pending_action_callbacks[key]
            break

    # if not in memory, fetch from DB
    if not gctx:
        dbrec = await GAME.get_pending_action_async(key)
        if not dbrec:
            await query.edit_message_text("Acción expirada o no válida.")
            return
        g = GAME.get_game(dbrec["chat_id"])
        if not g:
            await query.edit_message_text("Partida no encontrada.")
            return
        gctx = {"action": dbrec["action"], "actor": dbrec["actor"], "extra": dbrec["extra"], "message_id": dbrec["message_id"], "expires_at": dbrec["expires_at"]}
        # hydrate memory
        g.pending_action_callbacks[key] = gctx

    # check expiry
    if gctx.get("expires_at") and int(time.time()) > int(gctx["expires_at"]):
        await GAME.delete_pending_action_async(key)
        await query.edit_message_text("Esta acción ha expirado.")
        return

    expected_actor = gctx.get("actor")
    if expected_actor and expected_actor != user.id:
        await query.answer("No autorizado para pulsar este botón.", show_alert=True)
        return

    action_tag = gctx.get("action")
    # handle mafia_confirm
    if action_tag == "mafia_confirm":
        confs = await GAME.append_confirmation_async(key, user.id)
        confs = confs or []
        await query.edit_message_text(f"Has confirmado. Confirmaciones: {len(confs)}")
        # check unanimity (policy: unanimity)
        mafia_ids = [p.user_id for p in g.players.values() if p.alive and p.role_key and ROLES[p.role_key].faction == Faction.MAFIA]
        if set(confs) >= set(mafia_ids):
            # finalize: read target from extra
            target_id = gctx.get("extra", {}).get("target")
            if target_id:
                # store mafia_confirm target in night_actions for clarity
                g.night_actions.setdefault("mafia_confirmed", []).append((0, target_id))
                await GAME.delete_pending_action_async(key)
                await query.edit_message_text(f"Objetivo confirmado: {g.players[target_id].name}")
                GAME._persist_game(g)
            else:
                await query.edit_message_text("Error interno: objetivo no encontrado.")
        return

    # handle mafia_pick (mafia member selecting a vote)
    if action_tag == "mafia_pick":
        # Only allow mafia members to register mafia_votes via this button (actor enforced on pending action)
        g.mafia_votes[user.id] = target
        GAME._persist_game(g)
        await query.edit_message_text(f"Tu voto de mafia ha sido registrado: {g.players[target].name}")
        # attempt to start confirmation if all mafia voted
        asyncio.create_task(handle_mafia_votes_and_confirm(g, context.application))
        return

    # other actions: heal, block, guard, kill, investigate, blackmail
    if action_tag == "heal":
        g.night_actions.setdefault("heal", []).append((user.id, target))
        GAME._persist_game(g)
        await query.edit_message_text(f"Has elegido curar a {g.players[target].name}.")
        return
    if action_tag == "block":
        g.night_actions.setdefault("block", []).append((user.id, target))
        GAME._persist_game(g)
        await query.edit_message_text(f"Has elegido bloquear a {g.players[target].name}.")
        return
    if action_tag == "guard":
        g.night_actions.setdefault("guard", []).append((user.id, target))
        GAME._persist_game(g)
        await query.edit_message_text(f"Has elegido proteger a {g.players[target].name}.")
        return
    if action_tag == "kill":
        rk = g.players[user.id].role_key if user.id in g.players else None
        keyname = "serial_kill" if rk == "asesino" else "vigilante_shot"
        g.night_actions.setdefault(keyname, []).append((user.id, target))
        GAME._persist_game(g)
        await query.edit_message_text(f"Has elegido atacar a {g.players[target].name}.")
        return
    if action_tag == "investigate":
        g.night_actions.setdefault("investigate", []).append((user.id, target))
        GAME._persist_game(g)
        await query.edit_message_text(f"Has investigado a {g.players[target].name}. Resultado llegará por DM.")
        return
    if action_tag == "blackmail":
        g.night_actions.setdefault("blackmail", []).append((user.id, target))
        GAME._persist_game(g)
        await query.edit_message_text(f"Has chantajeado a {g.players[target].name}.")
        return

    # group voting pending actions: action_tag == "vote_group"
    if action_tag == "vote_group":
        # register vote: ensure each user votes only once: replace previous vote
        votes = g.night_actions.setdefault("vote", [])
        # remove existing vote by this voter if any
        votes = [vt for vt in votes if vt[0] != user.id]
        votes.append((user.id, target))
        g.night_actions["vote"] = votes
        GAME._persist_game(g)
        await query.edit_message_text(f"Has votado por {g.players[target].name}.")
        return

    await query.edit_message_text("Acción procesada.")


# handle mafia votes and create a mafia_confirm pending action (persisted) that is DM'ed to all mafiosos
async def handle_mafia_votes_and_confirm(g: GameState, application: Application, confirm_timeout: int = 60):
    mafia_ids = [p.user_id for p in g.players.values() if p.alive and p.role_key and ROLES[p.role_key].faction == Faction.MAFIA]
    if not mafia_ids:
        return
    if not set(g.mafia_votes.keys()) >= set(mafia_ids):
        return
    # compute consensus
    target, _ = Counter(g.mafia_votes.values()).most_common(1)[0]
    confirm_key = mk_callback_key()
    extra = {"target": target, "confirmations": []}
    await GAME.insert_pending_action_async(key=confirm_key, chat_id=g.chat_id, message_id=0, action="mafia_confirm", actor_id=None, extra=extra, expires_at=int(time.time()) + confirm_timeout)
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("Confirmar objetivo", callback_data=f"{confirm_key}:{target}")]])
    for mid in mafia_ids:
        try:
            sent = await application.bot.send_message(mid, f"La mafia propone matar a *{g.players[target].name}*. Pulsa confirmar.", parse_mode="Markdown", reply_markup=kb)
            await GAME.insert_pending_action_async(key=confirm_key, chat_id=g.chat_id, message_id=sent.message_id, action="mafia_confirm", actor_id=None, extra=extra, expires_at=int(time.time()) + confirm_timeout)
        except Exception:
            logger.warning("No pude DM a mafia %s", mid)
    asyncio.create_task(_mafia_confirm_timeout(g.chat_id, confirm_key, application, timeout=confirm_timeout))


async def _mafia_confirm_timeout(chat_id: int, confirm_key: str, application: Application, timeout: int = 60):
    await asyncio.sleep(timeout)
    rec = await GAME.get_pending_action_async(confirm_key)
    if not rec:
        return
    confs = rec.get("extra", {}).get("confirmations", [])
    g = GAME.get_game(chat_id)
    if not g:
        await GAME.delete_pending_action_async(confirm_key)
        return
    mafia_ids = [p.user_id for p in g.players.values() if p.alive and p.role_key and ROLES[p.role_key].faction == Faction.MAFIA]
    if set(confs) >= set(mafia_ids):
        await GAME.delete_pending_action_async(confirm_key)
        return
    if g.mafia_votes:
        target, _ = Counter(g.mafia_votes.values()).most_common(1)[0]
        g.night_actions.setdefault("mafia_confirmed", []).append((0, target))
        await GAME.delete_pending_action_async(confirm_key)
        try:
            await application.bot.send_message(chat_id, f"✅ La Mafia no confirmó por unanimidad. Se aplica la mayoría: objetivo {g.players[target].name}.")
        except Exception:
            logger.warning("No pude notificar al grupo sobre fallo de confirmación.")
        GAME._persist_game(g)
    else:
        await GAME.delete_pending_action_async(confirm_key)


# ----------------------------
# Jobs (end night/day, reminders, rescheduling)
# ----------------------------
async def job_end_night(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    g = GAME.get_game(chat_id)
    if not g:
        return
    await resolve_night(g, context.application)
    g.phase = "day"
    g.phase_deadline = int(time.time()) + g.day_seconds
    GAME._persist_game(g)
    try:
        await context.bot.send_message(chat_id, "🌞 Se hace de día. Discusión.")
    except Exception:
        pass
    context.job_queue.run_once(lambda c: asyncio.create_task(job_end_day(c, chat_id)), when=g.day_seconds, chat_id=chat_id)


async def job_end_day(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    g = GAME.get_game(chat_id)
    if not g:
        return
    g.phase = "voting"
    g.phase_deadline = int(time.time()) + 60  # voting window
    GAME._persist_game(g)
    try:
        await context.bot.send_message(chat_id, "🗳️ Fin del día. Por favor votad con los botones.")
    except Exception:
        pass
    kb_rows = []
    for p in g.players.values():
        if p.alive:
            key = mk_callback_key()
            extra = {"target": p.user_id}
            await GAME.insert_pending_action_async(key=key, chat_id=g.chat_id, message_id=0, action="vote_group", actor_id=None, extra=extra, expires_at=int(time.time()) + 60)
            kb_rows.append([InlineKeyboardButton(p.name, callback_data=f"{key}:{p.user_id}")])
    if kb_rows:
        await context.bot.send_message(chat_id, "Pulsa para votar:", reply_markup=InlineKeyboardMarkup(kb_rows))
    context.job_queue.run_once(lambda c: asyncio.create_task(job_resolve_votes(c, chat_id)), when=60, chat_id=chat_id)


async def job_resolve_votes(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    await job_resolve_votes_internal(context, chat_id)


async def job_resolve_votes_internal(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    g = GAME.get_game(chat_id)
    if not g:
        return
    await resolve_votes_job(g, context.application)


from datetime import datetime, timedelta

LAST_REMINDER = {}  # chat_id -> datetime

async def job_reminder(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    g = GAME.get_game(chat_id)
    if not g:
        return

    now = datetime.utcnow()
    last = LAST_REMINDER.get(chat_id)
    if last and (now - last) < timedelta(minutes=120):  # no enviar más de una vez cada 5 minutos
        return
    LAST_REMINDER[chat_id] = now

    try:
        await context.bot.send_message(
            chat_id,
            f"⏳ Recordatorio: fase *{g.phase}*. Jugadores vivos: {sum(1 for p in g.players.values() if p.alive)}",
            parse_mode="Markdown"
        )
    except Exception:
        logger.exception("No pude enviar recordatorio")


# ----------------------------
# Command to start game
# ----------------------------
async def cmd_empezar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    g = GAME.get_game(chat.id)
    if not g:
        await update.message.reply_text("No hay partida en este grupo.")
        return
    if g.phase != "lobby":
        await update.message.reply_text("La partida ya ha comenzado.")
        return
    if len(g.players) < 4:
        await update.message.reply_text("Se necesitan al menos 4 jugadores.")
        return
    assign_roles(g)
    # DM roles
    for p in g.players.values():
        try:
            role = ROLES.get(p.role_key)
            await context.bot.send_message(p.user_id, f"Tu rol: *{role.name if role else '??'}*\n{role.description if role else ''}", parse_mode="Markdown")
        except Exception:
            await update.message.reply_text(f"No pude enviar DM a {p.name}; pídeles que inicien chat con el bot.")
    # set phase and schedule night end
    g.phase = "night"
    g.phase_deadline = int(time.time()) + g.night_seconds
    GAME._persist_game(g)
    await context.bot.send_message(chat.id, "🌙 Empieza la noche. Los jugadores con habilidades recibirán un DM.")
    await prompt_night(g, context.application)
    try:
        if g.job_ids.get("night_end"):
            j = context.job_queue.get_job(g.job_ids["night_end"])
            if j:
                j.schedule_removal()
    except Exception:
        pass
    job = context.job_queue.run_once(lambda c: asyncio.create_task(job_end_night(c, g.chat_id)), when=g.night_seconds, chat_id=g.chat_id)
    g.job_ids["night_end"] = job.name
    rjob = context.job_queue.run_repeating(lambda c: asyncio.create_task(job_reminder(c, g.chat_id)), interval=g.periodic_reminder_seconds, first=30, chat_id=g.chat_id)
    g.job_ids["reminder"] = rjob.name
    GAME._persist_game(g)


# ----------------------------
# Dashboard (Flask) - minimal token auth (PATCHED)
# ----------------------------


# ----------------------------
# Startup: re-schedule jobs saved in DB/phase_deadline if any
# ----------------------------
def reschedule_jobs_on_startup(app: Application):
    with GAME._lock:
        for g in GAME._games.values():
            try:
                if g.phase in ("night",) and g.phase_deadline:
                    remaining = g.phase_deadline - int(time.time())
                    if remaining < 0:
                        remaining = 1
                    job = app.job_queue.run_once(lambda c: asyncio.create_task(job_end_night(c, g.chat_id)), when=remaining, chat_id=g.chat_id)
                    g.job_ids["night_end"] = job.name
                    rjob = app.job_queue.run_repeating(lambda c: asyncio.create_task(job_reminder(c, g.chat_id)), interval=g.periodic_reminder_seconds, first=30, chat_id=g.chat_id)
                    g.job_ids["reminder"] = rjob.name
                elif g.phase in ("day",) and g.phase_deadline:
                    remaining = g.phase_deadline - int(time.time())
                    if remaining < 0:
                        remaining = 1
                    job = app.job_queue.run_once(lambda c: asyncio.create_task(job_end_day(c, g.chat_id)), when=remaining, chat_id=g.chat_id)
                    g.job_ids["day_end"] = job.name
                    rjob = app.job_queue.run_repeating(lambda c: asyncio.create_task(job_reminder(c, g.chat_id)), interval=g.periodic_reminder_seconds, first=30, chat_id=g.chat_id)
                    g.job_ids["reminder"] = rjob.name
            except Exception:
                logger.exception("Error rescheduling job for game %s", g.chat_id)


# ----------------------------
# Main bootstrap
# ----------------------------
def main():
    global application
    token = os.environ.get("TELEGRAM_TOKEN")
    if not token:
        print("Set TELEGRAM_TOKEN")
        sys.exit(1)
    application = Application.builder().token(token).build()

    # register handlers
    application.add_handler(CommandHandler("crearpartida", cmd_crearpartida))
    application.add_handler(CommandHandler("unirme", cmd_unirme))
    application.add_handler(CommandHandler("salirme", cmd_salirme))
    application.add_handler(CommandHandler("estado", cmd_estado))
    application.add_handler(CommandHandler("empezar", cmd_empezar))
    application.add_handler(CommandHandler("resyncpartida", cmd_resyncpartida))
    application.add_handler(CommandHandler("borrarpartida", cmd_borrarpartida))
    application.add_handler(CallbackQueryHandler(cb_handler))
    # inicializar dashboard sin crear import circular
    import dashboard
    from dashboard import run_flask

    dashboard.init_dashboard(GAME, ROLES, clamp_phase_seconds, application, dash_token=DASH_TOKEN, dash_port=DASH_PORT)
    t = threading.Thread(target=dashboard.run_flask, daemon=True)
    t.start()
    logger.info("Dashboard running on port %s (token-protected)", DASH_PORT)


    # launch Flask dashboard thread
    t = threading.Thread(target=run_flask, daemon=True)
    t.start()
    logger.info("Dashboard running on port %s (token-protected)", DASH_PORT)

    async def _post_init(app):
        # re-sync en memoria desde DB si hay entradas huérfanas y reprograma jobs
        await asyncio.to_thread(GAME.resync_all_from_db, app)

    application.post_init = _post_init

    logger.info("Bot starting...")
    application.run_polling()


if __name__ == "__main__":
    main()
