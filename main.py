#!/usr/bin/env python3
"""
main.py (fixed)
Versión integrada y corregida del motor "Mafia" para Telegram.
"""
from dotenv import load_dotenv
load_dotenv()

import os
import sys
import time
import json
import asyncio
import logging
import threading
import uuid
from typing import Optional, Any
from collections import Counter
from datetime import datetime, timedelta

import aiosqlite
import sqlite3
from flask import render_template_string, request, redirect, url_for, Response, jsonify, current_app

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
# DB / Schema (local fallback init)
# ----------------------------
DB_FILE = os.environ.get("MAFIA_DB", "db/mafia_complete.db")
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

# ----------------------------
# Game manager, models & engine
# ----------------------------
from game_manager import GameManager
from game_engine import assign_roles, resolve_night, resolve_votes_job
from models import *  # mantiene compatibilidad con tu models.py (GameState/PlayerState/ROLES...)

# single game manager instance
GAME = GameManager(DB_FILE)

# dashboard config
DASH_TOKEN = os.environ.get("MAFIA_DASH_TOKEN", "superlirio")
DASH_PORT = int(os.environ.get("MAFIA_DASH_PORT", "8006"))

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

# ----------------------------
# Telegram handlers & callback processing (core)
# ----------------------------
application: Optional[Application] = None  # filled in main()

async def cmd_crearpartida(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    if chat is None:
        return
    if chat.type == "private":
        await update.message.reply_text("Crea la partida en un grupo.")
        return
    try:
        GAME.create_game(chat.id, user.id)
        await update.message.reply_text(f"Partida creada por {user.first_name}. Usa /unirme para entrar.")
    except Exception:
        await update.message.reply_text("Ya existe una partida en este grupo. Si crees que es un error usa /resyncpartida.")

async def cmd_unirme(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    if chat is None:
        return
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
    if chat is None:
        return
    g = GAME.get_game(chat.id)
    if not g:
        await update.message.reply_text("No hay partida.")
        return
    if getattr(g, "phase", "lobby") != "lobby":
        await update.message.reply_text("No puedes salir una vez que la partida ha empezado.")
        return
    ok = GAME.remove_player_from_game(chat.id, user.id)
    if ok:
        await update.message.reply_text("Te has salido de la partida.")
    else:
        await update.message.reply_text("No estabas en la partida.")

async def cmd_estado(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat is None:
        return
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
    chat = update.effective_chat
    if chat is None:
        return
    g = GAME.get_game(chat.id)
    if g:
        await update.message.reply_text("La partida ya está cargada en memoria. Fase: %s" % getattr(g, "phase", "?"))
        return
    g_db = GAME._load_game_sync(chat.id)
    if g_db:
        with GAME._lock:
            GAME._games[chat.id] = g_db
        await update.message.reply_text("Partida rehidratada desde la base de datos. Fase: %s" % g_db.phase)
    else:
        await update.message.reply_text("No hay partida en la base de datos para este grupo.")

async def cmd_borrarpartida(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    if chat is None:
        return
    try:
        member = await context.bot.get_chat_member(chat.id, user.id)
        if member.status not in ("administrator", "creator"):
            await update.message.reply_text("Solo un administrador o el creador del grupo puede borrar la partida.")
            return
    except Exception:
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
            logger.exception("Error cancelando jobs en borrarpartida")

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
        extra = {"target": p.user_id, "confirmations": []}
        await GAME.insert_pending_action_async(key=key, chat_id=g.chat_id, message_id=0, action=action_tag, actor_id=actor_id, extra=extra, expires_at=int(time.time()) + expires_in)
        rows.append([InlineKeyboardButton(p.name, callback_data=f"{key}:{p.user_id}")])
    if not rows:
        return None
    return InlineKeyboardMarkup(rows)

async def prompt_night(g: GameState, application: Application):
    bot = application.bot
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

# Callback handler (central)
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

    g = None
    gctx = None
    for gg in GAME.games.values():
        if key in gg.pending_action_callbacks:
            g = gg
            gctx = gg.pending_action_callbacks[key]
            break

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
        g.pending_action_callbacks[key] = gctx

    if gctx.get("expires_at") and int(time.time()) > int(gctx["expires_at"]):
        await GAME.delete_pending_action_async(key)
        await query.edit_message_text("Esta acción ha expirado.")
        return

    expected_actor = gctx.get("actor")
    if expected_actor and expected_actor != user.id:
        await query.answer("No autorizado para pulsar este botón.", show_alert=True)
        return

    action_tag = gctx.get("action")
    # mafia_confirm
    if action_tag == "mafia_confirm":
        confs = await GAME.append_confirmation_async(key, user.id)
        confs = confs or []
        await query.edit_message_text(f"Has confirmado. Confirmaciones: {len(confs)}")
        mafia_ids = [p.user_id for p in g.players.values() if p.alive and p.role_key and ROLES[p.role_key].faction == Faction.MAFIA]
        if set(confs) >= set(mafia_ids):
            target_id = gctx.get("extra", {}).get("target")
            if target_id:
                g.night_actions.setdefault("mafia_confirmed", []).append((0, target_id))
                await GAME.delete_pending_action_async(key)
                await query.edit_message_text(f"Objetivo confirmado: {g.players[target_id].name}")
                # persist
                try:
                    GAME._persist_game(g)
                except Exception:
                    logger.exception("Error persisting after mafia_confirm")
            else:
                await query.edit_message_text("Error interno: objetivo no encontrado.")
        return

    if action_tag == "mafia_pick":
        g.mafia_votes[user.id] = target
        try:
            GAME._persist_game(g)
        except Exception:
            logger.exception("Error persisting mafia_pick")
        await query.edit_message_text(f"Tu voto de mafia ha sido registrado: {g.players[target].name}")
        asyncio.create_task(handle_mafia_votes_and_confirm(g, context.application))
        return

    # other actions
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

    if action_tag == "vote_group":
        votes = g.night_actions.setdefault("vote", [])
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

LAST_REMINDER = {}  # chat_id -> datetime

async def job_reminder(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    g = GAME.get_game(chat_id)
    if not g:
        return
    now = datetime.utcnow()
    last = LAST_REMINDER.get(chat_id)
    if last and (now - last) < timedelta(minutes=2):
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
    if chat is None:
        return
    g = GAME.get_game(chat.id)
    if not g:
        await update.message.reply_text("No hay partida en este grupo.")
        return
    if getattr(g, "phase", "lobby") != "lobby":
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
    try:
        import dashboard
        dashboard.init_dashboard(GAME, ROLES, clamp_phase_seconds, application, dash_token=DASH_TOKEN, dash_port=DASH_PORT)
        t = threading.Thread(target=dashboard.run_flask, daemon=True)
        t.start()
        logger.info("Dashboard running on port %s (token-protected)", DASH_PORT)
    except Exception:
        logger.exception("No se pudo iniciar el dashboard")

    async def _post_init(app):
        # re-sync en memoria desde DB si hay entradas huérfanas y reprograma jobs
        await asyncio.to_thread(GAME.resync_all_from_db, app)

    application.post_init = _post_init

    logger.info("Bot starting...")
    try:
        application.run_polling()
    finally:
        # best-effort shutdown / persist
        logger.info("Main finally: persisting games and shutting down")
        try:
            if hasattr(GAME, "shutdown"):
                # si game_manager implementa shutdown, úsalo
                try:
                    GAME.shutdown(wait_seconds=5)
                except Exception:
                    logger.exception("GAME.shutdown() falló")
            else:
                # fallback: persist each game usando métodos disponibles
                for g in list(GAME.games.values()):
                    try:
                        if hasattr(GAME, "_persist_game"):
                            GAME._persist_game(g)
                        elif hasattr(GAME, "persist_game"):
                            GAME.persist_game(g)
                    except Exception:
                        logger.exception("Error guardando game %s en shutdown", getattr(g, "chat_id", None))
        except Exception:
            logger.exception("Error en rutina final de shutdown")
        try:
            application.stop()
        except Exception:
            pass

if __name__ == "__main__":
    main()
