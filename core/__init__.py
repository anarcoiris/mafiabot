"""
Core game logic package.
Pure game logic with no dependencies on UI or bot frameworks.
"""
from .engine import GameEngine
from .models import (
    Player,
    Phase,
    Game,
    ChatMessage,
    Role,
    Faction,
    NightAction,
    GameEvent
)
from .roles import ROLES, get_role

__all__ = [
    'GameEngine',
    'Player',
    'Phase',
    'Game',
    'ChatMessage',
    'Role',
    'Faction',
    'NightAction',
    'GameEvent',
    'ROLES',
    'get_role'
]
