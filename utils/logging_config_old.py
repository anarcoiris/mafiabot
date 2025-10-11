# utils/logging_cfg.py
import logging
import logging.handlers
import os

def setup_logging(level: int = logging.INFO, log_file: str = "mafiabot.log"):
    logger = logging.getLogger()
    logger.setLevel(level)

    # Console handler
    ch = logging.StreamHandler()
    ch.setLevel(level)
    ch_formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    ch.setFormatter(ch_formatter)

    # Rotating file handler
    fh = logging.handlers.RotatingFileHandler(
        filename=os.environ.get("MAFIABOT_LOGFILE", log_file),
        maxBytes=5*1024*1024,
        backupCount=5,
        encoding="utf-8"
    )
    fh.setLevel(level)
    fh_formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s (%(module)s:%(lineno)d): %(message)s")
    fh.setFormatter(fh_formatter)

    # Avoid adding duplicate handlers
    if not logger.handlers:
        logger.addHandler(ch)
        logger.addHandler(fh)
    else:
        # ensure our handlers exist
        names = {type(h).__name__ for h in logger.handlers}
        if "StreamHandler" not in names:
            logger.addHandler(ch)
        if "RotatingFileHandler" not in names:
            logger.addHandler(fh)

    return logger
