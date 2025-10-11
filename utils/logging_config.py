# utils/logging_config.py
from pathlib import Path
import logging
import logging.handlers
import os
from typing import Union, Mapping, Optional

def _resolve_level(level: Union[int, str]) -> int:
    if isinstance(level, int):
        return level
    if isinstance(level, str):
        lv = logging.getLevelName(level.upper())
        # getLevelName returns a string if unknown, int if known
        return lv if isinstance(lv, int) else logging.INFO
    return logging.INFO

def setup_logging(
    level: Union[int, str] = logging.INFO,
    log_file: str = "logs/mafiabot.log",
    env_var: str = "MAFIABOT_LOGFILE",
    max_bytes: int = 10 * 1024 * 1024,
    backup_count: int = 5,
    silence_loggers: Optional[Mapping[str, int]] = None
) -> logging.Logger:
    """
    Configura el logging de la aplicación (root logger).

    Args:
        level: nivel de logging (int o str, p.ej. logging.DEBUG o "DEBUG").
        log_file: ruta por defecto del archivo de log.
        env_var: variable de entorno que puede sobreescribir log_file.
        max_bytes: tamaño para rotación (RotatingFileHandler).
        backup_count: número de archivos de backup para rotación.
        silence_loggers: dict opcional con {logger_name: level} para silenciar librerías ruidosas.
    Returns:
        logging.Logger: logger raíz configurado.
    """
    level_int = _resolve_level(level)

    # Decidir fichero final (env tiene preferencia)
    logfile_path = os.environ.get(env_var, log_file)

    # Crear dir padre si es necesario
    try:
        Path(logfile_path).parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        # si falla la creación del directorio, seguimos sin crashear; el handler podría fallar luego
        pass

    logger = logging.getLogger()  # root logger
    logger.setLevel(level_int)

    # Formatters
    console_fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                                    datefmt="%Y-%m-%d %H:%M:%S")
    file_fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s (%(module)s:%(lineno)d): %(message)s",
                                 datefmt="%Y-%m-%d %H:%M:%S")

    # Handlers a añadir
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level_int)
    console_handler.setFormatter(console_fmt)

    try:
        file_handler = logging.handlers.RotatingFileHandler(
            filename=logfile_path,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8"
        )
        file_handler.setLevel(level_int)
        file_handler.setFormatter(file_fmt)
    except Exception:
        file_handler = None  # si no se puede crear, no rompemos la app

    # Evitar duplicar handlers: comprobación por tipo
    existing_types = tuple(type(h) for h in logger.handlers)

    def _has_handler_of_type(handler_cls):
        return any(isinstance(h, handler_cls) for h in logger.handlers)

    if not logger.handlers:
        logger.addHandler(console_handler)
        if file_handler:
            logger.addHandler(file_handler)
    else:
        # Añadir sólo si faltan
        if not _has_handler_of_type(logging.StreamHandler):
            logger.addHandler(console_handler)
        # RotatingFileHandler es subclass de FileHandler, comprobamos por clase concreta
        if file_handler and not _has_handler_of_type(logging.handlers.RotatingFileHandler):
            logger.addHandler(file_handler)

    # Silenciar loggers ruidosos si se piden
    if silence_loggers is None:
        silence_loggers = {"httpx": logging.WARNING, "telegram": logging.INFO}

    for name, lvl in silence_loggers.items():
        try:
            logging.getLogger(name).setLevel(_resolve_level(lvl))
        except Exception:
            pass

    # Devolver logger raíz
    return logger
