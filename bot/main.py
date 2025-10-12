"""
bot/main.py
Punto de entrada principal del bot de Mafia.
Versión corregida sin event loops manuales.
"""
import os
import sys
import logging
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
    Aquí inicializamos la DB y registramos handlers.
    """
    logger.info("Running post-initialization tasks...")
    
    try:
        # 1. Inicializar repository
        db_path = os.getenv("MAFIA_DB_PATH", "data/mafia.db")
        
        from persistence import init_repository
        repository = await init_repository(db_path)
        logger.info(f"Repository initialized: {db_path}")
        
        # 2. Registrar handlers
        from bot.handlers import GameHandlers
        from bot.callbacks import CallbackHandler
        
        handlers = GameHandlers(repository)
        callback_handler = CallbackHandler(repository)
        
        # Comandos del juego
        application.add_handler(CommandHandler("start", handlers.cmd_help))
        application.add_handler(CommandHandler("help", handlers.cmd_help))
        application.add_handler(CommandHandler("crearpartida", handlers.cmd_crearpartida))
        application.add_handler(CommandHandler("unirme", handlers.cmd_unirme))
        application.add_handler(CommandHandler("salirme", handlers.cmd_salirme))
        application.add_handler(CommandHandler("estado", handlers.cmd_estado))
        application.add_handler(CommandHandler("empezar", handlers.cmd_empezar))
        application.add_handler(CommandHandler("borrarpartida", handlers.cmd_borrarpartida))
        application.add_handler(CommandHandler("config", handlers.cmd_config))
        application.add_handler(CommandHandler("roles", handlers.cmd_roles))
        
        # Callbacks (botones inline)
        application.add_handler(CallbackQueryHandler(callback_handler.handle_callback))
        
        logger.info("Handlers registered successfully")
        
        # 3. Re-schedule jobs para partidas activas
        from bot.jobs import reschedule_active_games
        await reschedule_active_games(application, repository)
        logger.info("Active games rescheduled")
        
    except Exception as e:
        logger.exception("Error during post-initialization")
        raise


async def post_shutdown(application: Application):
    """
    Callback que se ejecuta antes de cerrar la aplicación.
    Guarda todas las partidas activas.
    """
    logger.info("Running shutdown tasks...")
    
    try:
        from persistence import get_repository
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
        logger.error("Create a .env file with: TELEGRAM_TOKEN=your_token_here")
        sys.exit(1)
    
    logger.info("=" * 60)
    logger.info("🎮 Starting Mafia Bot")
    logger.info("=" * 60)
    logger.info(f"Python version: {sys.version}")
    logger.info(f"Working directory: {os.getcwd()}")
    
    # Crear aplicación
    application = Application.builder().token(token).build()
    
    # Hooks de inicialización y shutdown
    application.post_init = post_init
    application.post_shutdown = post_shutdown
    
    logger.info("Bot is ready. Starting polling...")
    logger.info("Press Ctrl+C to stop")
    
    # Ejecutar bot
    try:
        application.run_polling(
            allowed_updates=["message", "callback_query"],
            drop_pending_updates=True  # Ignorar mensajes antiguos al reiniciar
        )
    except KeyboardInterrupt:
        logger.info("Bot stopped by user (Ctrl+C)")
    except Exception as e:
        logger.exception("Fatal error in main loop")
        sys.exit(1)


if __name__ == "__main__":
    main()
