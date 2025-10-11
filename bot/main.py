"""
bot/main.py
Punto de entrada principal del bot de Mafia.
"""
import os
import sys
import logging
import asyncio
from pathlib import Path

from dotenv import load_dotenv
from telegram.ext import Application, CommandHandler, CallbackQueryHandler

# Cargar variables de entorno
load_dotenv()

# Configurar logging
from utils.logging_config import setup_logging
setup_logging(level=logging.INFO)

logger = logging.getLogger(__name__)


async def post_init(application: Application):
    """
    Callback que se ejecuta después de inicializar la aplicación.
    Carga partidas activas y re-programa jobs.
    """
    logger.info("Running post-initialization tasks...")
    
    from persistence.database import get_repository
    from bot.jobs import reschedule_active_games
    
    try:
        repository = await get_repository()
        await reschedule_active_games(application, repository)
        logger.info("Active games rescheduled successfully")
    except Exception as e:
        logger.exception("Error during post-initialization")


async def post_shutdown(application: Application):
    """
    Callback que se ejecuta antes de cerrar la aplicación.
    Guarda todas las partidas activas.
    """
    logger.info("Running shutdown tasks...")
    
    from persistence.database import get_repository
    
    try:
        repository = await get_repository()
        await repository.shutdown()
        logger.info("Repository shutdown complete")
    except Exception as e:
        logger.exception("Error during shutdown")


def main():
    """Función principal."""
    
    # Verificar token
    token = os.getenv("TELEGRAM_TOKEN")
    if not token:
        logger.error("TELEGRAM_TOKEN not found in environment variables")
        sys.exit(1)
    
    db_path = os.getenv("MAFIA_DB_PATH", "data/mafia.db")
    
    logger.info("Starting Mafia Bot...")
    logger.info(f"Database: {db_path}")
    
    # Crear aplicación
    application = Application.builder().token(token).build()
    
    # Inicializar repository (debe hacerse antes de los handlers)
    async def init_app():
        from persistence.database import init_repository
        await init_repository(db_path)
        logger.info("Repository initialized")
    
    # Ejecutar inicialización
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(init_app())
    
    # Registrar handlers
    from persistence.database import repository
    from bot.handlers import GameHandlers
    from bot.callbacks import CallbackHandler
    
    game_handlers = GameHandlers(repository)
    callback_handler = CallbackHandler(repository)
    
    # Comandos del juego
    application.add_handler(CommandHandler("start", game_handlers.cmd_help))
    application.add_handler(CommandHandler("help", game_handlers.cmd_help))
    application.add_handler(CommandHandler("crearpartida", game_handlers.cmd_crearpartida))
    application.add_handler(CommandHandler("unirme", game_handlers.cmd_unirme))
    application.add_handler(CommandHandler("salirme", game_handlers.cmd_salirme))
    application.add_handler(CommandHandler("estado", game_handlers.cmd_estado))
    application.add_handler(CommandHandler("empezar", game_handlers.cmd_empezar))
    application.add_handler(CommandHandler("borrarpartida", game_handlers.cmd_borrarpartida))
    application.add_handler(CommandHandler("config", game_handlers.cmd_config))
    application.add_handler(CommandHandler("roles", game_handlers.cmd_roles))
    
    # Callbacks (botones inline)
    application.add_handler(CallbackQueryHandler(callback_handler.handle_callback))
    
    # Hooks de inicialización y shutdown
    application.post_init = post_init
    application.post_shutdown = post_shutdown
    
    logger.info("Bot is ready. Starting polling...")
    
    # Ejecutar bot
    try:
        application.run_polling(allowed_updates=["message", "callback_query"])
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.exception("Fatal error in main loop")
        sys.exit(1)


if __name__ == "__main__":
    main()