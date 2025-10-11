"""
bot/handlers.py
Handlers de comandos de Telegram.
Inyección de dependencias: reciben repository y no importan módulos circulares.
"""
import logging
import time
from telegram import Update
from telegram.ext import ContextTypes

from core.models import Phase
from core.engine import GameEngine
from core.roles import ROLES, get_role
from persistence.database import GameRepository
from utils.rate_limiter import rate_limit

logger = logging.getLogger(__name__)


class GameHandlers:
    """Handlers de comandos del juego."""
    
    def __init__(self, repository: GameRepository):
        self.repository = repository
        self.engine = GameEngine()
    
    @rate_limit(calls=5, per_seconds=60)
    async def cmd_crearpartida(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando /crearpartida - Crea una nueva partida."""
        chat = update.effective_chat
        user = update.effective_user
        
        if not chat or not user:
            return
        
        # Solo en grupos
        if chat.type == "private":
            await update.message.reply_text(
                "❌ Debes crear la partida en un grupo, no en chat privado."
            )
            return
        
        try:
            game = await self.repository.create(chat.id, user.id)
            await update.message.reply_text(
                f"✅ Partida creada por {user.first_name}.\n\n"
                f"Usa /unirme para entrar.\n"
                f"Usa /config para configurar roles.\n"
                f"Usa /empezar cuando todos estén listos."
            )
            logger.info(f"Game {chat.id} created by {user.id}")
            
        except ValueError as e:
            await update.message.reply_text(
                f"❌ Ya existe una partida en este grupo.\n"
                f"Usa /estado para ver el estado actual o /borrarpartida para eliminarla."
            )
            logger.warning(f"Attempt to create duplicate game {chat.id}: {e}")
    
    @rate_limit(calls=3, per_seconds=30)
    async def cmd_unirme(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando /unirme - Unirse a una partida."""
        chat = update.effective_chat
        user = update.effective_user
        
        if not chat or not user:
            return
        
        game = await self.repository.get(chat.id)
        if not game:
            await update.message.reply_text(
                "❌ No hay partida en este grupo. Créala con /crearpartida"
            )
            return
        
        if game.phase != Phase.LOBBY:
            await update.message.reply_text(
                "❌ La partida ya ha comenzado. No puedes unirte ahora."
            )
            return
        
        success = await self.repository.add_player(chat.id, user.id, user.first_name)
        
        if success:
            await update.message.reply_text(
                f"✅ {user.first_name} se ha unido a la partida.\n"
                f"Jugadores: {len(game.players) + 1}"
            )
            logger.info(f"Player {user.id} joined game {chat.id}")
        else:
            await update.message.reply_text("ℹ️ Ya estabas en la partida.")
    
    @rate_limit(calls=3, per_seconds=30)
    async def cmd_salirme(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando /salirme - Salir de una partida."""
        chat = update.effective_chat
        user = update.effective_user
        
        if not chat or not user:
            return
        
        game = await self.repository.get(chat.id)
        if not game:
            await update.message.reply_text("❌ No hay partida en este grupo.")
            return
        
        if game.phase != Phase.LOBBY:
            await update.message.reply_text(
                "❌ No puedes salir una vez que la partida ha comenzado."
            )
            return
        
        success = await self.repository.remove_player(chat.id, user.id)
        
        if success:
            await update.message.reply_text(f"👋 {user.first_name} ha salido de la partida.")
            logger.info(f"Player {user.id} left game {chat.id}")
        else:
            await update.message.reply_text("❌ No estabas en la partida.")
    
    async def cmd_estado(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando /estado - Muestra el estado de la partida."""
        chat = update.effective_chat
        
        if not chat:
            return
        
        game = await self.repository.get(chat.id)
        if not game:
            await update.message.reply_text("❌ No hay partida en este grupo.")
            return
        
        lines = [
            f"📊 *Estado de la partida*",
            f"",
            f"🎮 Fase: {game.phase.value}",
            f"👥 Jugadores: {len(game.players)}",
            f"",
        ]
        
        if game.phase == Phase.LOBBY:
            lines.append("*Jugadores registrados:*")
            for p in game.players.values():
                lines.append(f"  • {p.name}")
            lines.append("")
            lines.append("Usa /empezar cuando estén listos (mínimo 4 jugadores)")
        else:
            alive = game.get_alive_players()
            dead = game.get_dead_players()
            
            lines.append(f"💚 Vivos: {len(alive)}")
            for p in alive:
                status = []
                if p.silenced:
                    status.append("🤐 silenciado")
                if p.blocked:
                    status.append("🚫 bloqueado")
                status_str = f" ({', '.join(status)})" if status else ""
                lines.append(f"  • {p.name}{status_str}")
            
            if dead:
                lines.append("")
                lines.append(f"💀 Muertos: {len(dead)}")
                for p in dead:
                    role = get_role(p.role_key) if p.role_key else None
                    role_name = role.name if role else "?"
                    lines.append(f"  • {p.name} - {role_name}")
        
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
    
    async def cmd_empezar(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando /empezar - Inicia la partida."""
        chat = update.effective_chat
        user = update.effective_user
        
        if not chat or not user:
            return
        
        game = await self.repository.get(chat.id)
        if not game:
            await update.message.reply_text("❌ No hay partida en este grupo.")
            return
        
        # Validaciones
        if game.phase != Phase.LOBBY:
            await update.message.reply_text("❌ La partida ya ha comenzado.")
            return
        
        if user.id != game.host_id:
            # Permitir que cualquier admin también pueda empezar
            try:
                member = await context.bot.get_chat_member(chat.id, user.id)
                if member.status not in ("administrator", "creator"):
                    await update.message.reply_text(
                        "❌ Solo el host o un administrador puede iniciar la partida."
                    )
                    return
            except Exception:
                await update.message.reply_text(
                    "❌ Solo el host puede iniciar la partida."
                )
                return
        
        if len(game.players) < 4:
            await update.message.reply_text(
                f"❌ Se necesitan al menos 4 jugadores. Actualmente: {len(game.players)}"
            )
            return
        
        # Asignar roles
        errors = self.engine.assign_roles(game)
        if errors:
            await update.message.reply_text(
                f"❌ Error al asignar roles:\n" + "\n".join(errors)
            )
            return
        
        # Enviar roles por DM
        failed_dms = []
        for player in game.players.values():
            role = get_role(player.role_key) if player.role_key else None
            if not role:
                continue
            
            try:
                await context.bot.send_message(
                    player.user_id,
                    f"🎭 *Tu rol: {role.name}*\n\n{role.description}",
                    parse_mode="Markdown"
                )
                player.dm_sent_ok = True
            except Exception as e:
                logger.warning(f"Could not DM player {player.user_id}: {e}")
                failed_dms.append(player.name)
                player.dm_sent_ok = False
        
        # Cambiar fase a NIGHT
        game.phase = Phase.NIGHT
        game.phase_deadline = int(time.time()) + game.night_seconds
        await self.repository.save(game)
        
        # Notificar inicio
        msg = "🌙 *¡La partida comienza!*\n\nCae la noche...\n"
        if failed_dms:
            msg += f"\n⚠️ No pude enviar DM a: {', '.join(failed_dms)}\n"
            msg += "Asegúrense de haber iniciado chat privado con el bot."
        
        await update.message.reply_text(msg, parse_mode="Markdown")
        
        # Programar fin de noche (se hace en jobs.py)
        from bot.jobs import schedule_night_end
        await schedule_night_end(context, game)
        
        logger.info(f"Game {chat.id} started with {len(game.players)} players")
    
    async def cmd_borrarpartida(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando /borrarpartida - Elimina la partida (solo admin/host)."""
        chat = update.effective_chat
        user = update.effective_user
        
        if not chat or not user:
            return
        
        game = await self.repository.get(chat.id)
        if not game:
            await update.message.reply_text("❌ No hay partida en este grupo.")
            return
        
        # Verificar permisos
        is_host = user.id == game.host_id
        is_admin = False
        
        try:
            member = await context.bot.get_chat_member(chat.id, user.id)
            is_admin = member.status in ("administrator", "creator")
        except Exception:
            pass
        
        if not is_host and not is_admin:
            await update.message.reply_text(
                "❌ Solo el host o un administrador puede borrar la partida."
            )
            return
        
        # Cancelar jobs activos
        from bot.jobs import cancel_game_jobs
        await cancel_game_jobs(context, chat.id)
        
        # Eliminar partida
        success = await self.repository.delete(chat.id)
        
        if success:
            await update.message.reply_text(
                "🗑️ Partida eliminada correctamente."
            )
            logger.info(f"Game {chat.id} deleted by {user.id}")
        else:
            await update.message.reply_text(
                "❌ Error al eliminar la partida."
            )
    
    async def cmd_config(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando /config - Muestra o configura roles."""
        chat = update.effective_chat
        user = update.effective_user
        
        if not chat or not user:
            return
        
        game = await self.repository.get(chat.id)
        if not game:
            await update.message.reply_text("❌ No hay partida en este grupo.")
            return
        
        if game.phase != Phase.LOBBY:
            await update.message.reply_text("❌ No puedes cambiar la configuración una vez iniciada la partida.")
            return
        
        if user.id != game.host_id:
            await update.message.reply_text("❌ Solo el host puede cambiar la configuración.")
            return
        
        # Si no hay argumentos, mostrar configuración actual
        if not context.args:
            lines = ["⚙️ *Configuración actual:*\n"]
            for role_key, count in game.roles_config.items():
                role = ROLES.get(role_key)
                role_name = role.name if role else role_key
                lines.append(f"  • {role_name}: {count}")
            
            lines.append("\n📝 *Para cambiar:*")
            lines.append("`/config <rol> <cantidad>`")
            lines.append("\nEjemplo: `/config mafia 2`")
            lines.append("\n*Roles disponibles:*")
            lines.append("mafia, doctor, detective, sheriff, ciudadano, escort, guardaespaldas, vigilante, asesino")
            
            await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
            return
        
        # Parsear argumentos
        if len(context.args) != 2:
            await update.message.reply_text("❌ Uso: /config <rol> <cantidad>")
            return
        
        role_key = context.args[0].lower()
        try:
            count = int(context.args[1])
        except ValueError:
            await update.message.reply_text("❌ La cantidad debe ser un número.")
            return
        
        if role_key not in ROLES:
            await update.message.reply_text(f"❌ Rol desconocido: {role_key}")
            return
        
        if count < 0:
            await update.message.reply_text("❌ La cantidad no puede ser negativa.")
            return
        
        # Actualizar configuración
        if count == 0:
            game.roles_config.pop(role_key, None)
        else:
            game.roles_config[role_key] = count
        
        await self.repository.save(game)
        
        role = ROLES[role_key]
        await update.message.reply_text(
            f"✅ {role.name}: {count}\n\nUsa /config para ver la configuración completa."
        )
        logger.info(f"Game {chat.id} config updated: {role_key}={count}")
    
    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando /help - Muestra ayuda."""
        help_text = """
🎮 *Comandos del Juego de Mafia*

*Configurar partida:*
/crearpartida - Crear una nueva partida
/unirme - Unirse a la partida
/salirme - Salir de la partida
/config - Ver/cambiar configuración de roles
/empezar - Iniciar la partida

*Durante el juego:*
/estado - Ver estado actual
/borrarpartida - Eliminar la partida (admin/host)

*Información:*
/help - Mostrar esta ayuda
/roles - Lista de roles disponibles

💡 *Cómo jugar:*
1. Crea una partida en un grupo
2. Los jugadores se unen con /unirme
3. El host configura roles con /config
4. Inicia con /empezar (mínimo 4 jugadores)
5. Durante la noche, recibirás DM con tu acción
6. Durante el día, votad para linchar sospechosos

⚠️ *Importante:* Debes iniciar chat privado con el bot antes de empezar la partida.
"""
        await update.message.reply_text(help_text, parse_mode="Markdown")
    
    async def cmd_roles(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando /roles - Lista todos los roles disponibles."""
        
        if context.args and context.args[0].lower() in ROLES:
            # Mostrar información detallada de un rol específico
            role_key = context.args[0].lower()
            role = ROLES[role_key]
            
            faction_emoji = {
                "town": "💚",
                "mafia": "🔴",
                "neutral": "⚪"
            }
            
            msg = f"{faction_emoji.get(role.faction.value, '❓')} *{role.name}*\n\n"
            msg += f"*Facción:* {role.faction.value.title()}\n"
            msg += f"*Acción nocturna:* {'Sí' if role.has_night_action else 'No'}\n\n"
            msg += f"{role.description}"
            
            await update.message.reply_text(msg, parse_mode="Markdown")
            return
        
        # Lista general de roles
        from core.roles import get_roles_by_faction, Faction
        
        msg = "🎭 *Roles Disponibles*\n\n"
        
        msg += "💚 *TOWN (Pueblo):*\n"
        for role in get_roles_by_faction(Faction.TOWN).values():
            msg += f"  • {role.name}\n"
        
        msg += "\n🔴 *MAFIA:*\n"
        for role in get_roles_by_faction(Faction.MAFIA).values():
            msg += f"  • {role.name}\n"
        
        msg += "\n⚪ *NEUTRAL:*\n"
        for role in get_roles_by_faction(Faction.NEUTRAL).values():
            msg += f"  • {role.name}\n"
        
        msg += "\n💡 Usa `/roles <nombre>` para ver detalles de un rol específico."
        
        await update.message.reply_text(msg, parse_mode="Markdown")