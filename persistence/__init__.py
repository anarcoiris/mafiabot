# persistence/__init__.py
"""
persistence package public API.

Este archivo reexporta la API pública del paquete persistence.
La implementación real reside en persistence.database (GameRepository,
init_repository, get_repository, etc.) y en persistence.migrations
(initialize_schema). Mantener aquí sólo reexports ayuda a evitar
import-cycles y a que `from persistence import init_repository`
funcione correctamente.
"""

from .database import (
    GameRepository,
    init_repository,
    get_repository,
    repository as _repository,  # nombre interno, exportamos 'repository' abajo
)
from .migrations import initialize_schema

# Reexportar con nombres limpios
repository = _repository

__all__ = [
    "GameRepository",
    "init_repository",
    "get_repository",
    "repository",
    "initialize_schema",
]
