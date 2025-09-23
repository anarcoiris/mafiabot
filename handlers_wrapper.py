# handlers_wrapper.py
import logging
from functools import wraps
from utils.rate_limiter import RateLimitExceeded

logger = logging.getLogger("mafiabot.handlers")

def handler_wrap(func):
    @wraps(func)
    async def wrapped(update, context, *args, **kwargs):
        try:
            return await func(update, context, *args, **kwargs)
        except RateLimitExceeded as rle:
            try:
                await context.bot.send_message(update.effective_chat.id, "⏳ Demasiadas acciones rápidas. Espera un momento.")
            except Exception:
                logger.debug("Could not notify about rate limit")
            logger.info("Rate limit hit: %s", rle)
        except Exception as e:
            logger.exception("Unhandled exception in handler %s: %s", func.__name__, e)
            try:
                await context.bot.send_message(update.effective_chat.id, "⚠️ Error interno. Inténtalo más tarde.")
            except Exception:
                logger.debug("Could not send error message to chat")
    return wrapped
