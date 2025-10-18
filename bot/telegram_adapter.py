# bot/telegram_adapter.py
"""
TelegramAdapter - Implementación completa de GameInterface para Telegram.
"""
from adapters.game_interface import GameInterface
from telegram import Bot


class TelegramAdapter(GameInterface):
    """Implementación de GameInterface para Telegram."""

    def __init__(self, bot: Bot):
        self.bot = bot

    async def send_message(self, recipient_id: int, text: str):
        """Envía un mensaje a un jugador específico."""
        try:
            await self.bot.send_message(chat_id=recipient_id, text=text)
        except Exception as e:
            # Log pero no propagar - el juego debe continuar aunque fallen algunos DMs
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Failed to send message to {recipient_id}: {e}")

    async def send_broadcast(self, game_id: int, text: str):
        """Envía un mensaje al grupo del juego."""
        try:
            await self.bot.send_message(chat_id=game_id, text=text)
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to broadcast to game {game_id}: {e}")
            raise

    async def request_action(self, player_id: int, actions: list):
        """
        Solicita una acción al jugador con opciones.

        Args:
            player_id: ID del usuario
            actions: Lista de tuplas (action_type, targets) o estructura similar
        """
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup

        if not actions:
            return

        # Generar texto y botones según las acciones disponibles
        text = "🌙 Es tu turno de actuar. Elige tu objetivo:"
        buttons = []

        for action_data in actions:
            if isinstance(action_data, dict):
                label = action_data.get('label', 'Acción')
                callback_data = action_data.get('callback_data', '')
                buttons.append([InlineKeyboardButton(label, callback_data=callback_data)])
            elif isinstance(action_data, tuple) and len(action_data) >= 2:
                label, callback_data = action_data[0], action_data[1]
                buttons.append([InlineKeyboardButton(label, callback_data=callback_data)])

        keyboard = InlineKeyboardMarkup(buttons) if buttons else None

        try:
            await self.bot.send_message(
                chat_id=player_id,
                text=text,
                reply_markup=keyboard
            )
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Failed to request action from {player_id}: {e}")

    async def update_game_state(self, game):
        """
        Notifica cambio de estado del juego.
        Puede enviar un mensaje de estado al grupo.
        """
        # Esta implementación es básica - se puede extender según necesidades
        pass
