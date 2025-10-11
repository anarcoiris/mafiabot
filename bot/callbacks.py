"""
bot/callbacks.py
Manejo de callbacks de botones inline (acciones nocturnas y votaciones).
"""
import logging
import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from collections import Counter 

from core.models import Phase, NightAction
from core.engine import GameEngine
from core.roles import get_role, ROLES
from persistence.database import GameRepository

logger = logging.getLogger(__name__)


class CallbackHandler:
    """Gestor de callbacks de botones inline."""
    
    def __init__(self, repository: GameRepository):
        self.repository = repository
        self.engine = GameEngine()
    
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Punto de entrada principal para todos los callbacks."""
        query = update.callback_query
        await query.answer()
        
        if not query.data:
            await query.edit_message_text("❌ Callback inválido.")
            return
        
        user = update.effective_user
        if not user:
            return
        
        # Formato: action:chat_id:target_id
        parts = query.data.split(":")
        if len(parts) != 3:
            await query.edit_message_text("❌ Formato de callback inválido.")
            return
        
        action_type, chat_id_str, target_id_str = parts
        
        try:
            chat_id = int(chat_id_str)
            target_id = int(target_id_str)
        except ValueError:
            await query.edit_message_text("❌ IDs inválidos.")
            return
        
        # Cargar juego
        game = await self.repository.get(chat_id)
        if not game:
            await query.edit_message_text("❌ Partida no encontrada.")
            return
        
        # Verificar que el usuario esté en la partida
        if user.id not in game.players:
            await query.answer("❌ No estás en esta partida.", show_alert=True)
            return
        
        player = game.players[user.id]
        
        # Verificar que esté vivo
        if not player.alive:
            await query.answer("❌ Estás muerto, no puedes actuar.", show_alert=True)
            return
        
        # Enrutar según el tipo de acción
        if action_type == "night_action":
            await self._handle_night_action(query, game, player, target_id, context)
        elif action_type == "mafia_vote":
            await self._handle_mafia_vote(query, game, player, target_id)
        elif action_type == "day_vote":
            await self._handle_day_vote(query, game, player, target_id)
        else:
            await query.edit_message_text(f"❌ Tipo de acción desconocido: {action_type}")
    
    async def _handle_night_action(
        self, 
        query, 
        game, 
        actor, 
        target_id: int,
        context: ContextTypes.DEFAULT_TYPE
    ):
        """Maneja una acción nocturna."""
        if game.phase != Phase.NIGHT:
            await query.edit_message_text("❌ No es de noche.")
            return
        
        if actor.blocked:
            await query.edit_message_text("❌ Estás bloqueado, no puedes actuar.")
            return
        
        role = get_role(actor.role_key) if actor.role_key else None
        if not role or not role.has_night_action:
            await query.edit_message_text("❌ Tu rol no tiene acción nocturna.")
            return
        
        target = game.players.get(target_id)
        if not target or not target.alive:
            await query.edit_message_text("❌ Objetivo inválido.")
            return
        
        # Determinar tipo de acción según el rol
        action_map = {
            "doctor": "heal",
            "detective": "investigate",
            "sheriff": "investigate",
            "escort": "block",
            "guardaespaldas": "guard",
            "vigilante": "vigilante_kill",
            "asesino": "serial_kill",
            "consorte": "block",
            "consigliere": "investigate",
            "chantajeador": "blackmail"
        }
        
        action_name = action_map.get(role.key)
        if not action_name:
            await query.edit_message_text("❌ Acción no implementada para tu rol.")
            return
        
        # Remover acciones previas del mismo actor
        game.night_actions = [
            a for a in game.night_actions 
            if a.actor_id != actor.user_id or a.action_type != action_name
        ]
        
        # Agregar nueva acción
        night_action = NightAction(
            actor_id=actor.user_id,
            target_id=target_id,
            action_type=action_name,
            priority=role.priority
        )
        game.night_actions.append(night_action)
        
        await self.repository.save(game)
        
        action_verbs = {
            "heal": "curar",
            "investigate": "investigar",
            "block": "bloquear",
            "guard": "proteger",
            "vigilante_kill": "atacar",
            "serial_kill": "atacar",
            "blackmail": "chantajear"
        }
        
        verb = action_verbs.get(action_name, "seleccionar")
        
        await query.edit_message_text(
            f"✅ Has elegido {verb} a *{target.name}*.\n\n"
            f"Tu acción será procesada al final de la noche.",
            parse_mode="Markdown"
        )
        
        logger.info(
            f"Night action: {actor.user_id} ({role.key}) -> {action_name} -> {target_id}"
        )
    
    async def _handle_mafia_vote(self, query, game, voter, target_id: int):
        """Maneja el voto de un mafioso para elegir objetivo."""
        if game.phase != Phase.NIGHT:
            await query.edit_message_text("❌ No es de noche.")
            return
        
        role = get_role(voter.role_key) if voter.role_key else None
        if not role or role.faction.value != "mafia":
            await query.answer("❌ No eres de la mafia.", show_alert=True)
            return
        
        target = game.players.get(target_id)
        if not target or not target.alive:
            await query.edit_message_text("❌ Objetivo inválido.")
            return
        
        # Registrar voto
        game.mafia_votes[voter.user_id] = target_id
        await self.repository.save(game)
        
        await query.edit_message_text(
            f"🗳️ Has votado por matar a *{target.name}*.\n\n"
            f"Esperando a que todos los mafiosos voten...",
            parse_mode="Markdown"
        )
        
        # Verificar si todos los mafiosos han votado
        mafia_players = [
            p for p in game.players.values()
            if p.alive and p.role_key and get_role(p.role_key).faction.value == "mafia"
        ]
        
        if len(game.mafia_votes) >= len(mafia_players):
            # Todos votaron, notificar
            from collections import Counter
            votes = Counter(game.mafia_votes.values())
            chosen_target, _ = votes.most_common(1)[0]
            chosen = game.players[chosen_target]
            
            # Notificar a todos los mafiosos
            for mafia in mafia_players:
                try:
                    await query.bot.send_message(
                        mafia.user_id,
                        f"✅ La Mafia ha decidido matar a *{chosen.name}*.",
                        parse_mode="Markdown"
                    )
                except Exception as e:
                    logger.warning(f"Could not notify mafia {mafia.user_id}: {e}")
        
        logger.info(f"Mafia vote: {voter.user_id} -> {target_id}")
    
    async def _handle_day_vote(self, query, game, voter, target_id: int):
        """Maneja el voto diurno para linchamiento."""
        if game.phase != Phase.VOTING:
            await query.edit_message_text("❌ No es momento de votar.")
            return
        
        if voter.silenced:
            await query.answer("❌ Estás silenciado, no puedes votar.", show_alert=True)
            return
        
        target = game.players.get(target_id)
        if not target or not target.alive:
            await query.edit_message_text("❌ Objetivo inválido.")
            return
        
        # Registrar voto
        game.day_votes[voter.user_id] = target_id
        await self.repository.save(game)
        
        await query.edit_message_text(
            f"🗳️ Has votado por linchar a *{target.name}*.",
            parse_mode="Markdown"
        )
        
        logger.info(f"Day vote: {voter.user_id} -> {target_id}")


async def send_night_actions_prompts(repository: GameRepository, game, bot):
    """
    Envía los botones de acción nocturna a cada jugador con rol activo.
    """
    for player in game.get_alive_players():
        role = get_role(player.role_key) if player.role_key else None
        
        if not role or not role.has_night_action:
            continue
        
        # Roles de la mafia votan por objetivo común
        if role.faction.value == "mafia":
            await _send_mafia_vote_prompt(game, player, bot)
        else:
            await _send_role_action_prompt(game, player, role, bot)


async def _send_mafia_vote_prompt(game, player, bot):
    """Envía prompt de votación a un mafioso."""
    # Construir teclado con objetivos (no mafiosos)
    keyboard = []
    for target in game.get_alive_players():
        target_role = get_role(target.role_key) if target.role_key else None
        
        # No mostrar otros mafiosos
        if target_role and target_role.faction.value == "mafia":
            continue
        
        if target.user_id == player.user_id:
            continue
        
        keyboard.append([
            InlineKeyboardButton(
                target.name,
                callback_data=f"mafia_vote:{game.chat_id}:{target.user_id}"
            )
        ])
    
    if not keyboard:
        try:
            await bot.send_message(
                player.user_id,
                "🌙 No hay objetivos disponibles para la Mafia esta noche."
            )
        except Exception as e:
            logger.warning(f"Could not DM mafia {player.user_id}: {e}")
        return
    
    try:
        await bot.send_message(
            player.user_id,
            f"🌙 *Noche - Voto de la Mafia*\n\n"
            f"Elige a quién quiere matar la Mafia esta noche:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.warning(f"Could not DM mafia {player.user_id}: {e}")


async def _send_role_action_prompt(game, player, role, bot):
    """Envía prompt de acción para roles no-mafia."""
    # Construir teclado con objetivos
    keyboard = []
    for target in game.get_alive_players():
        # Algunos roles no pueden targetear a sí mismos
        if target.user_id == player.user_id and role.key != "doctor":
            continue
        
        keyboard.append([
            InlineKeyboardButton(
                target.name,
                callback_data=f"night_action:{game.chat_id}:{target.user_id}"
            )
        ])
    
    if not keyboard:
        try:
            await bot.send_message(
                player.user_id,
                f"🌙 *{role.name}*\n\nNo hay objetivos disponibles."
            )
        except Exception as e:
            logger.warning(f"Could not DM player {player.user_id}: {e}")
        return
    
    action_descriptions = {
        "doctor": "Elige a quién curar esta noche:",
        "detective": "Elige a quién investigar:",
        "sheriff": "Elige a quién investigar:",
        "escort": "Elige a quién bloquear:",
        "guardaespaldas": "Elige a quién proteger:",
        "vigilante": "Elige a quién disparar (usa una bala):",
        "asesino": "Elige a quién matar:",
        "chantajeador": "Elige a quién chantajear:"
    }
    
    description = action_descriptions.get(role.key, "Elige tu objetivo:")
    
    try:
        await bot.send_message(
            player.user_id,
            f"🌙 *{role.name}*\n\n{description}",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.warning(f"Could not DM player {player.user_id}: {e}")
        player.dm_sent_ok = False


async def send_voting_prompt(game, bot):
    """Envía el teclado de votación al grupo."""
    keyboard = []
    for player in game.get_alive_players():
        keyboard.append([
            InlineKeyboardButton(
                player.name,
                callback_data=f"day_vote:{game.chat_id}:{player.user_id}"
            )
        ])
    
    if not keyboard:
        return
    
    try:
        await bot.send_message(
            game.chat_id,
            "🗳️ *Votación*\n\n¿A quién queréis linchar?",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.exception(f"Could not send voting prompt to {game.chat_id}")