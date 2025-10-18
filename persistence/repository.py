# persistence/repository.py
import sqlite3
import threading
from typing import Optional

# Ejemplo sencillo: repo singleton thread-safe usando sqlite o dict en memoria.
# Adapta a tu implementación real (SQLAlchemy/peewee/filesystem...).

_lock = threading.Lock()
_repo_instance: Optional[dict] = None

def init_repository(db_path: Optional[str] = None):
    """Inicializa el repositorio. Si ya existe, lo devuelve."""
    global _repo_instance
    with _lock:
        if _repo_instance is None:
            # Ejemplo: repo en memoria (puedes sustituir por conexión sqlite)
            _repo_instance = {"db_path": db_path, "data": {}}
            # Si quieres usar sqlite, inicializa conexión aquí
            # conn = sqlite3.connect(db_path or ":memory:")
            # _repo_instance = {"conn": conn}
    return _repo_instance

def get_repository():
    """Devuelve la instancia inicializada; lanza si no inicializada."""
    if _repo_instance is None:
        raise RuntimeError("Repository not initialized. Call init_repository first.")
    return _repo_instance

def close_repository():
    """Cierra recursos (si usas sqlite u otros)."""
    global _repo_instance
    with _lock:
        if _repo_instance is None:
            return
        # Si hubieras abierto una conexión sqlite: cerrar aquí.
        _repo_instance = None
