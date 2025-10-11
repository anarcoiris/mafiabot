"""
bot/jobs.py
Gestión de jobs/tareas programadas del bot.
"""
import logging
import time
from telegram.ext import ContextTypes
from datetime import timedelta

from core.models import Phase
from core.engine import GameEngine
from core.roles import get_role
from persistence.database import GameRepository

logger = logging.getLogger(__name__)


async def schedule_night_end(context: ContextTypes.DEFAULT_TYPE, game):
    """Programa el fin de la noche."""
    job_name = f"night_end_{game.chat_id}"
    
    # Cancelar job previo si existe
    current_jobs = context.job_queue.get_jobs_by_name(job_name)
    for job in current_jobs:
        job.schedule_removal()
    
    # Programar nuevo job
    when = game.night_seconds
    context.job_queue.run_once(
        callback=job_end_night,
        when=when,
        data={"chat_id": game.chat_id},
        name=job_name,
        chat_id=game.chat_id
    )
    
    game.job_names.add(job_name)
    logger.info(f"Scheduled night_end for game {game.chat_id} in {when}s")
    
    # También programar recordatorio periódico
    await schedule_reminder(context, game)


async def schedule_day_end(context: ContextTypes.DEFAULT_TYPE, game):
    """Programa el fin del día."""
    job_name = f"day_end_{game.chat_id}"
    
    # Cancelar job previo si existe
    current_jobs = context.job_queue.get_jobs_by_name(job_name)
    for job in current_jobs:
        job.schedule_removal()
    
    # Programar nuevo job
    when = game.day_seconds
    context.job_queue.run_once(
        callback=job_end_day,
        when=when,
        data={"chat_id": game.chat_id},
        name=job_name,
        chat_id=game.chat_id
    )
    
    game.job_names.add(job_name)
    logger.info(f"Scheduled day_end for game {game.chat_id} in {when}s")
    
    await schedule_reminder(context, game)


async def schedule_voting_end(context: ContextTypes.DEFAULT_TYPE, game, duration: int = 120):
    """Programa el fin de la votación."""
    job_name = f"voting_end_{game.chat_id}"
    
    # Cancelar job previo si existe
    current_jobs = context.job_queue.get_jobs_by_name(job_name)
    for job in current_jobs:
        job.schedule_removal()
    
    # Programar nuevo job
    context.job_queue.run_once(
        callback=job_resolve_votes,
        when=duration,
        data={"chat_id": game.chat_id},
        name=job_name,
        chat_id=game.chat_id
    )
    
    game.job_names.add(job_name)
    logger.info(f"Scheduled voting_end for game {game.chat_id} in {duration}s")


async def schedule_reminder(context: ContextTypes.DEFAULT_TYPE, game):
    """Programa recordatorios periódicos."""
    job_name = f"reminder_{game.chat_id}"
    
    # Cancelar job previo si existe
    current_jobs = context.job_queue.get_jobs_by_name(job_name)
    for job in current_jobs:
        job.schedule_removal()
    
    # Programar recordatorio cada X segundos
    context.job_queue.run_repeating(
        callback=job_reminder,
        interval=game.periodic_reminder_seconds,
        first=30,  # Primer recordatorio a los 30s
        data={"chat_id": game.chat_id},
        name=job_name,
        chat_id=game.chat_id
    )
    
    game.job_names.add(job_name)
    logger.info(f"Scheduled reminder for game {game.chat_id} every {game.periodic_reminder_seconds}s")


async def cancel_game_jobs(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    """Cancela todos los jobs de una partida."""
    patterns = [
        f"night_end_{chat_id}",
        f"day_end_{chat_id}",
        f"voting_end_{chat_id}",
        f"reminder_{chat_id}"
    ]
    
    for pattern in patterns:
        jobs = context.job_queue.get_jobs_by_name(pattern)
        for job in jobs:
            job.schedule_removal()
            logger.info(f"Cancelled job {pattern}")


# ===== Job Callbacks =====

async def job_end_night(context: ContextTypes.DEFAULT_TYPE):
    """Job que se ejecuta al final de la noche."""
    chat_id = context.job.data.get("chat_id")
    if not chat_id:
        logger.error("job_end_night called without chat_id")
        return
    
    from persistence.database import get_repository
    repository = await get_repository()
    
    game = await repository.get(chat_id)
    if not game:
        logger.warning(f"Game {chat_id} not found in job_end_night")
        return
    
    if game.phase != Phase.NIGHT:
        logger.warning(f"Game {chat_id} is not in NIGHT phase")
        return
    
    logger.info(f"Resolving night for game {chat_id}")
    
    # Resolver la noche
    engine = GameEngine()
    events = engine.resolve_night(game)
    
    # Construir mensaje de resumen
    lines = ["🌅 *Amanece...*\n"]
    
    deaths = [e for e in events if e.event_type == "death"]
    
    if not deaths:
        lines.append("✨ Esta noche no hubo muertes.")
    else:
        lines.append("💀 *Muertes esta noche:*")
        for event in deaths:
            victim = game.players.get(event.target_id)
            if victim:
                role = get_role(victim.role_key) if victim.role_key else None
                role_name = role.name if role else "Desconocido"
                lines.append(f"  • {victim.name} - Era *{role_name}*")
    
    # Notificar chantajeados
    silenced = [p for p in game.players.values() if p.alive and p.silenced]
    if silenced:
        lines.append("\n🤐 Jugadores silenciados hoy:")
        for p in silenced:
            lines.append(f"  • {p.name}")
    
    # Enviar investigaciones por DM
    investigations = [e for e in events if e.event_type == "investigation"]
    for event in investigations:
        investigator = game.players.get(event.actor_id)
        target = game.players.get(event.target_id)
        
        if investigator and target:
            result = event.details.get("result", "Sin información")
            try:
                await context.bot.send_message(
                    investigator.user_id,
                    f"🔎 *Resultado de investigación*\n\n"
                    f"Investigaste a *{target.name}*:\n"
                    f"➜ {result}",
                    parse_mode="Markdown"
                )
            except Exception as e:
                logger.warning(f"Could not send investigation result to {investigator.user_id}: {e}")
    
    # Enviar resumen al grupo
    try:
        await context.bot.send_message(
            chat_id,
            "\n".join(lines),
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.exception(f"Error sending night summary to {chat_id}")
    
    # Verificar condición de victoria
    winner = engine.check_victory(game)
    if winner:
        await announce_winner(context.bot, game, winner)
        game.phase = Phase.FINISHED
        await repository.save(game)
        await cancel_game_jobs(context, chat_id)
        return
    
    # Limpiar estado nocturno
    game.clear_night_state()
    
    # Cambiar a día
    game.phase = Phase.DAY
    game.phase_deadline = int(time.time()) + game.day_seconds
    await repository.save(game)
    
    try:
        await context.bot.send_message(
            chat_id,
            f"☀️ *Es de día*\n\n"
            f"Discutid quién creéis que es sospechoso.\n"
            f"La votación comenzará en {game.day_seconds // 60} minutos.",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.exception(f"Error sending day start message to {chat_id}")
    
    # Programar fin del día
    await schedule_day_end(context, game)


async def job_end_day(context: ContextTypes.DEFAULT_TYPE):
    """Job que se ejecuta al final del día."""
    chat_id = context.job.data.get("chat_id")
    if not chat_id:
        logger.error("job_end_day called without chat_id")
        return
    
    from persistence.database import get_repository
    repository = await get_repository()
    
    game = await repository.get(chat_id)
    if not game:
        logger.warning(f"Game {chat_id} not found in job_end_day")
        return
    
    if game.phase != Phase.DAY:
        logger.warning(f"Game {chat_id} is not in DAY phase")
        return
    
    logger.info(f"Day ended for game {chat_id}, starting voting")
    
    # Cambiar a fase de votación
    game.phase = Phase.VOTING
    game.phase_deadline = int(time.time()) + 120  # 2 minutos para votar
    await repository.save(game)
    
    try:
        await context.bot.send_message(
            chat_id,
            "🗳️ *Hora de votar*\n\n"
            "Tenéis 2 minutos para decidir a quién linchar.",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.exception(f"Error sending voting start to {chat_id}")
    
    # Enviar teclado de votación
    from bot.callbacks import send_voting_prompt
    await send_voting_prompt(game, context.bot)
    
    # Programar resolución de votos
    await schedule_voting_end(context, game, duration=120)


async def job_resolve_votes(context: ContextTypes.DEFAULT_TYPE):
    """Job que resuelve la votación diurna."""
    chat_id = context.job.data.get("chat_id")
    if not chat_id:
        logger.error("job_resolve_votes called without chat_id")
        return
    
    from persistence.database import get_repository
    repository = await get_repository()
    
    game = await repository.get(chat_id)
    if not game:
        logger.warning(f"Game {chat_id} not found in job_resolve_votes")
        return
    
    logger.info(f"Resolving votes for game {chat_id}")
    
    engine = GameEngine()
    lynched_id, events = engine.resolve_votes(game)
    
    # Verificar si hubo empate
    tie_event = next((e for e in events if e.event_type == "vote_tie"), None)
    if tie_event:
        try:
            await context.bot.send_message(
                chat_id,
                "⚖️ *Empate en la votación*\n\n"
                "No se lincha a nadie hoy.",
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.exception(f"Error sending tie message to {chat_id}")
    elif lynched_id:
        lynched = game.players.get(lynched_id)
        if lynched:
            role = get_role(lynched.role_key) if lynched.role_key else None
            role_name = role.name if role else "Desconocido"
            
            try:
                await context.bot.send_message(
                    chat_id,
                    f"⚖️ *El pueblo ha decidido*\n\n"
                    f"💀 {lynched.name} ha sido linchado.\n"
                    f"Era: *{role_name}*",
                    parse_mode="Markdown"
                )
            except Exception as e:
                logger.exception(f"Error sending lynch message to {chat_id}")
    else:
        try:
            await context.bot.send_message(
                chat_id,
                "🤷 *Sin votación*\n\nNo hubo suficientes votos. No se lincha a nadie.",
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.exception(f"Error sending no votes message to {chat_id}")
    
    # Limpiar votos del día
    game.clear_day_state()
    
    # Verificar condición de victoria
    winner = engine.check_victory(game)
    if winner:
        await announce_winner(context.bot, game, winner)
        game.phase = Phase.FINISHED
        await repository.save(game)
        await cancel_game_jobs(context, chat_id)
        return
    
    # Volver a la noche
    game.phase = Phase.NIGHT
    game.phase_deadline = int(time.time()) + game.night_seconds
    await repository.save(game)
    
    try:
        await context.bot.send_message(
            chat_id,
            "🌙 *Cae la noche...*\n\n"
            "Los jugadores con habilidades nocturnas recibirán sus opciones por DM.",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.exception(f"Error sending night start to {chat_id}")
    
    # Enviar prompts de acciones nocturnas
    from bot.callbacks import send_night_actions_prompts
    await send_night_actions_prompts(repository, game, context.bot)
    
    # Programar fin de noche
    await schedule_night_end(context, game)


async def job_reminder(context: ContextTypes.DEFAULT_TYPE):
    """Job que envía recordatorios periódicos."""
    chat_id = context.job.data.get("chat_id")
    if not chat_id:
        return
    
    from persistence.database import get_repository
    repository = await get_repository()
    
    game = await repository.get(chat_id)
    if not game:
        return
    
    # No enviar recordatorios si el juego terminó
    if game.phase == Phase.FINISHED:
        return
    
    alive_count = len(game.get_alive_players())
    
    # Calcular tiempo restante
    if game.phase_deadline:
        remaining = game.phase_deadline - int(time.time())
        if remaining < 0:
            remaining = 0
        
        minutes = remaining // 60
        seconds = remaining % 60
        time_str = f"{minutes}m {seconds}s" if minutes > 0 else f"{seconds}s"
    else:
        time_str = "desconocido"
    
    phase_emoji = {
        Phase.NIGHT: "🌙",
        Phase.DAY: "☀️",
        Phase.VOTING: "🗳️",
        Phase.LOBBY: "🎮"
    }
    
    emoji = phase_emoji.get(game.phase, "⏰")
    
    try:
        await context.bot.send_message(
            chat_id,
            f"{emoji} *Recordatorio*\n\n"
            f"Fase actual: *{game.phase.value}*\n"
            f"Jugadores vivos: {alive_count}\n"
            f"Tiempo restante: ~{time_str}",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.debug(f"Could not send reminder to {chat_id}: {e}")


async def announce_winner(bot, game, winner: str):
    """Anuncia al ganador de la partida."""
    messages = {
        "town": "🎉 *¡El Pueblo ha ganado!*\n\nTodos los enemigos han sido eliminados.",
        "mafia": "😈 *¡La Mafia ha ganado!*\n\nLa Mafia controla el pueblo.",
        "serial": "🔪 *¡El Asesino en Serie ha ganado!*\n\nEs el único superviviente.",
        "jester": "🤡 *¡El Bufón ha ganado!*\n\nConsiguió ser linchado."
    }
    
    message = messages.get(winner, f"🏆 *¡{winner} ha ganado!*")
    
    # Revelar todos los roles
    message += "\n\n*Roles revelados:*\n"
    for player in game.players.values():
        role = get_role(player.role_key) if player.role_key else None
        role_name = role.name if role else "?"
        status = "💚" if player.alive else "💀"
        message += f"{status} {player.name} - {role_name}\n"
    
    try:
        await bot.send_message(
            game.chat_id,
            message,
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.exception(f"Error announcing winner to {game.chat_id}")


async def reschedule_active_games(context: ContextTypes.DEFAULT_TYPE, repository: GameRepository):
    """
    Re-programa jobs para partidas activas después de un reinicio del bot.
    Se llama durante la inicialización.
    """
    active_games = await repository.get_all_active()
    
    for game in active_games:
        if game.phase == Phase.FINISHED or game.phase == Phase.LOBBY:
            continue
        
        try:
            # Calcular tiempo restante
            if game.phase_deadline:
                remaining = game.phase_deadline - int(time.time())
                if remaining < 0:
                    remaining = 1  # Si expiró, ejecutar inmediatamente
                
                if game.phase == Phase.NIGHT:
                    context.job_queue.run_once(
                        callback=job_end_night,
                        when=remaining,
                        data={"chat_id": game.chat_id},
                        name=f"night_end_{game.chat_id}",
                        chat_id=game.chat_id
                    )
                    logger.info(f"Rescheduled night_end for game {game.chat_id} (in {remaining}s)")
                
                elif game.phase == Phase.DAY:
                    context.job_queue.run_once(
                        callback=job_end_day,
                        when=remaining,
                        data={"chat_id": game.chat_id},
                        name=f"day_end_{game.chat_id}",
                        chat_id=game.chat_id
                    )
                    logger.info(f"Rescheduled day_end for game {game.chat_id} (in {remaining}s)")
                
                elif game.phase == Phase.VOTING:
                    context.job_queue.run_once(
                        callback=job_resolve_votes,
                        when=remaining,
                        data={"chat_id": game.chat_id},
                        name=f"voting_end_{game.chat_id}",
                        chat_id=game.chat_id
                    )
                    logger.info(f"Rescheduled voting_end for game {game.chat_id} (in {remaining}s)")
            
            # Re-programar recordatorios
            context.job_queue.run_repeating(
                callback=job_reminder,
                interval=game.periodic_reminder_seconds,
                first=30,
                data={"chat_id": game.chat_id},
                name=f"reminder_{game.chat_id}",
                chat_id=game.chat_id
            )
            
        except Exception as e:
            logger.exception(f"Error rescheduling jobs for game {game.chat_id}: {e}")