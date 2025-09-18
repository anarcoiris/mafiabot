#!/usr/bin/env python3
# game_engine.py
# Encapsula la lógica pura de la partida: asignación de roles, resolución de la noche,
# resolución de las votaciones y comprobación de condiciones de victoria.
# Diseñado para ser tolerante en tiempo de import: intenta usar GAME si está disponible,
# y resuelve helpers externos (prompt_night, job_end_night) en tiempo de ejecución.

import random
import json
import logging
from typing import Optional, Any, List, Tuple
from collections import Counter, defaultdict

from models import GameState, PlayerState, ROLES, Faction

logger = logging.getLogger(__name__)

# Intentamos importar GAME si el módulo game_manager lo expone. Si no está disponible
# en tiempo de import no fallamos: GAME puede asignarse más tarde por main.
try:
    from game_manager import GAME
except Exception:
    GAME = None

# Resolución dinámica de funciones auxiliares que viven en el main (prompt_night, job_end_night, ...)
def _resolve_external(name: str):
    """Intenta localizar una función auxiliar en el módulo principal del bot."""
    try:
        import importlib
        # intenta el nombre del módulo principal del proyecto
        mod = importlib.import_module("mafiabot3a")
        return getattr(mod, name, None)
    except Exception:
        try:
            mod = importlib.import_module("__main__")
            return getattr(mod, name, None)
        except Exception:
            return None

# ----------------------------
# API pública: assign_roles
# ----------------------------
def assign_roles(g: GameState) -> None:
    """Asigna roles a los jugadores según g.roles_config. Rellena con 'ciudadano' si faltan plazas."""
    ids = list(g.players.keys())
    random.shuffle(ids)
    pool: List[str] = []
    for rkey, count in (g.roles_config or {}).items():
        try:
            c = int(count)
        except Exception:
            c = 0
        for _ in range(max(0, c)):
            pool.append(rkey)
    while len(pool) < len(ids):
        pool.append("ciudadano")
    random.shuffle(pool)
    for uid, rkey in zip(ids, pool):
        if uid in g.players:
            g.players[uid].role_key = rkey
    logger.info("Roles assigned for game %s", g.chat_id)


# ----------------------------
# Resolución de la noche
# ----------------------------
async def resolve_night(g: GameState, application: Any) -> None:
    """Resolver acciones nocturnas y notificar resultados por bot/application.
    - Lee g.night_actions y g.mafia_votes.
    - Persiste estado vía GAME._persist_game si GAME existe.
    - No depende de functions externas; intenta llamar a helper externos solo si existen.
    """
    bot = getattr(application, "bot", None)
    logger.info("Resolving night for game %s", g.chat_id)
    log_lines: List[str] = []

    # apply blocks
    blocked = set()
    for actor, target in g.night_actions.get("block", []):
        a = g.players.get(actor)
        if a and a.alive:
            blocked.add(target)
    for b in blocked:
        if b in g.players:
            g.players[b].blocked = True

    # mafia collective target (majority)
    mafia_target = None
    if getattr(g, "mafia_votes", None):
        cnt = Counter(g.mafia_votes.values())
        if cnt:
            mafia_target = cnt.most_common(1)[0][0]

    attacks: List[Tuple[int, int, str]] = []
    if mafia_target:
        # pick a source mafia actor not blocked
        source = next((uid for uid, p in g.players.items() if p.role_key in ("mafia", "padrino", "consorte") and p.alive and not p.blocked), None)
        if source is not None:
            attacks.append((source, mafia_target, "mafia"))

    for actor, target in g.night_actions.get("vigilante_shot", []):
        a = g.players.get(actor)
        if a and a.alive and not a.blocked:
            attacks.append((actor, target, "vigilante"))

    for actor, target in g.night_actions.get("serial_kill", []):
        a = g.players.get(actor)
        if a and a.alive and not a.blocked:
            attacks.append((actor, target, "asesino"))

    # heals and guards
    heals = set()
    for actor, target in g.night_actions.get("heal", []):
        a = g.players.get(actor)
        if a and a.alive and not a.blocked:
            heals.add(target)

    guards = {}
    for actor, target in g.night_actions.get("guard", []):
        a = g.players.get(actor)
        if a and a.alive and not a.blocked:
            guards[target] = actor

    deaths: List[int] = []
    for attacker, target, kind in attacks:
        if target not in g.players or not g.players[target].alive:
            continue
        if target in heals:
            log_lines.append(f"- {g.players[target].name} fue curado/a y sobrevivió a un ataque.")
            continue
        if target in guards:
            guard_id = guards[target]
            if guard_id in g.players and g.players[guard_id].alive:
                g.players[guard_id].alive = False
                deaths.append(guard_id)
                log_lines.append(f"- {g.players[guard_id].name} (Guardaespaldas) murió protegiendo a {g.players[target].name}.")
                continue
        # otherwise target dies
        g.players[target].alive = False
        deaths.append(target)
        role_name = (ROLES.get(g.players[target].role_key).name if g.players[target].role_key and ROLES.get(g.players[target].role_key) else "?")
        log_lines.append(f"- {g.players[target].name} fue asesinado/a. Era *{role_name}*.")

    # blackmail / silence
    for actor, target in g.night_actions.get("blackmail", []):
        a = g.players.get(actor)
        if a and a.alive and not a.blocked and g.players.get(target) and g.players[target].alive:
            g.players[target].silenced = True
            log_lines.append(f"- {g.players[target].name} fue chantajeado/a y estará silenciado durante el día.")

    # investigations (detective/sheriff)
    for actor, target in g.night_actions.get("investigate", []):
        inv = g.players.get(actor)
        if not inv or not inv.alive or inv.blocked:
            continue
        if target not in g.players or not g.players[target].alive:
            res = "No válido (jugador no disponible)."
        else:
            target_role_key = g.players[target].role_key
            target_role = ROLES.get(target_role_key) if target_role_key else None
            if inv.role_key == "sheriff":
                if target_role and (target_role.faction == Faction.MAFIA or target_role.key == "asesino"):
                    res = "CULPABLE"
                else:
                    res = "INOCENTE"
            else:
                if target_role is None:
                    res = "INOCENTE"
                elif getattr(target_role, "undetectable_by_detective", False):
                    res = "INOCENTE"
                elif getattr(target_role, "detective_signature", None):
                    res = f"Firma: {target_role.detective_signature}"
                else:
                    res = "INOCENTE"
        if bot:
            try:
                await bot.send_message(actor, f"🔎 Resultado de investigación: {res}")
            except Exception:
                logger.warning("No se pudo DM a investigador %s", actor)

    # announce summary
    if not log_lines:
        log_lines = ["Esta noche no hubo muertes."]
    summary = "*Resumen de la noche:*\n" + "\n".join(log_lines)
    if bot:
        try:
            await bot.send_message(g.chat_id, summary, parse_mode="Markdown")
        except Exception:
            logger.exception("Error enviando resumen de noche")

    # cleanup
    g.night_actions.clear()
    g.mafia_votes.clear()
    for p in g.players.values():
        p.blocked = False
    g.phase_deadline = None

    # persist
    if GAME:
        try:
            GAME._persist_game(g)
        except Exception:
            logger.exception("Error persisting game after night resolution")
    else:
        logger.debug("GAME not available; skipping persistence after resolve_night")

    # check victory
    winner = check_win_conditions_sync(g)
    if winner:
        if bot:
            try:
                if winner == "town":
                    await bot.send_message(g.chat_id, "🎉 ¡El Pueblo gana!")
                elif winner == "mafia":
                    await bot.send_message(g.chat_id, "😈 ¡La Mafia gana!")
                elif winner == "serial":
                    await bot.send_message(g.chat_id, "🔪 El Asesino en Serie ha ganado.")
            except Exception:
                logger.exception("Error anunciando ganador")
        g.phase = "inactive"
        if GAME:
            GAME._persist_game(g)
        return

    return


# ----------------------------
# Resolución de votaciones de día (job)
# ----------------------------
async def resolve_votes_job(g: GameState, application: Any) -> None:
    """Resolver votos diurnos, persistir, anunciar y programar la noche."""
    bot = getattr(application, "bot", None)
    votes = [t for (v, t) in g.night_actions.get("vote", [])]
    if not votes:
        if bot:
            await bot.send_message(g.chat_id, "No hubo votos. No se lincha a nadie.")
            await bot.send_message(g.chat_id, "🌙 Vuelve la noche.")
        g.phase = "night"
        if GAME:
            GAME._persist_game(g)
        # prompt night if available
        prompt_night = _resolve_external("prompt_night")
        if prompt_night:
            try:
                await prompt_night(g, application)
            except Exception:
                logger.exception("Error calling prompt_night")
        # schedule night end if possible
        try:
            application.job_queue.run_once(lambda c: __import__("asyncio").create_task(_resolve_external("job_end_night")(c, g.chat_id)), when=g.night_seconds, chat_id=g.chat_id)
        except Exception:
            logger.debug("Could not schedule night end (job queue missing or job_end_night not found)")
        return

    cnt = Counter(votes)
    chosen, _ = cnt.most_common(1)[0]
    top = [t for t, c in cnt.items() if c == cnt[chosen]]
    if len(top) > 1:
        if bot:
            await bot.send_message(g.chat_id, "Empate en la votación. No se lincha a nadie.")
    else:
        if chosen in g.players and g.players[chosen].alive:
            g.players[chosen].alive = False
            role_name = (ROLES.get(g.players[chosen].role_key).name if g.players[chosen].role_key and ROLES.get(g.players[chosen].role_key) else "?")
            if bot:
                await bot.send_message(g.chat_id, f"⚖️ El pueblo linchó a {g.players[chosen].name}. Era *{role_name}*.", parse_mode="Markdown")
    if GAME:
        GAME._persist_game(g)

    # check win
    winner = check_win_conditions_sync(g)
    if winner:
        if bot:
            try:
                if winner == "town":
                    await bot.send_message(g.chat_id, "🎉 ¡El Pueblo gana!")
                elif winner == "mafia":
                    await bot.send_message(g.chat_id, "😈 ¡La Mafia gana!")
                elif winner == "serial":
                    await bot.send_message(g.chat_id, "🔪 El Asesino en Serie ha ganado.")
            except Exception:
                logger.exception("Error announcing winner in resolve_votes_job")
        g.phase = "inactive"
        if GAME:
            GAME._persist_game(g)
        return

    # continue to night
    g.phase = "night"
    if GAME:
        GAME._persist_game(g)
    if bot:
        await bot.send_message(g.chat_id, "🌙 Comienza la noche.")
    prompt_night = _resolve_external("prompt_night")
    if prompt_night:
        try:
            await prompt_night(g, application)
        except Exception:
            logger.exception("Error calling prompt_night in resolve_votes_job")
    # schedule night end if job queue available
    try:
        application.job_queue.run_once(lambda c: __import__("asyncio").create_task(_resolve_external("job_end_night")(c, g.chat_id)), when=g.night_seconds, chat_id=g.chat_id)
    except Exception:
        logger.debug("Could not schedule night end (job queue missing or job_end_night not found)")


# ----------------------------
# Check win conditions
# ----------------------------
def check_win_conditions_sync(g: GameState) -> Optional[str]:
    """Return 'town', 'mafia', 'serial' or None depending on GameState."""
    mafias = [p for p in g.players.values() if p.alive and p.role_key and ROLES.get(p.role_key) and ROLES[p.role_key].faction == Faction.MAFIA]
    towns = [p for p in g.players.values() if p.alive and p.role_key and ROLES.get(p.role_key) and ROLES[p.role_key].faction == Faction.TOWN]
    sk = [p for p in g.players.values() if p.alive and p.role_key == "asesino"]
    if not mafias and not sk:
        return "town"
    if mafias and len(mafias) >= len(towns):
        return "mafia"
    if sk and len([p for p in g.players.values() if p.alive]) == 1:
        return "serial"
    return None
