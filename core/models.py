"""
core/models.py
Modelos de datos base para el juego de Mafia.
Completamente independiente de Telegram y persistencia.
"""
from dataclasses import dataclass, field
from typing import Dict, Optional, List, Set
from enum import Enum
import time


class Faction(Enum):
    """Facciones del juego."""
    TOWN = "town"
    MAFIA = "mafia"
    NEUTRAL = "neutral"


class Phase(Enum):
    """Fases del juego."""
    LOBBY = "lobby"
    NIGHT = "night"
    DAY = "day"
    VOTING = "voting"
    FINISHED = "finished"


@dataclass
class Role:
    """Definición de un rol en el juego."""
    key: str
    name: str
    description: str
    faction: Faction
    has_night_action: bool = False
    can_be_blocked: bool = True
    undetectable_by_detective: bool = False
    detective_signature: Optional[str] = None
    priority: int = 5  # Para resolver acciones nocturnas en orden


@dataclass
class Player:
    """Representa un jugador en la partida."""
    user_id: int
    name: str
    role_key: Optional[str] = None
    alive: bool = True
    blocked: bool = False
    silenced: bool = False
    protected: bool = False
    dm_sent_ok: bool = False
    
    def reset_night_status(self):
        """Resetea estados temporales de la noche."""
        self.blocked = False
        self.protected = False


@dataclass
class NightAction:
    """Representa una acción nocturna."""
    actor_id: int
    target_id: int
    action_type: str  # heal, block, kill, investigate, etc.
    priority: int = 5


@dataclass
class Game:
    """Estado completo de una partida."""
    chat_id: int
    host_id: int
    phase: Phase = Phase.LOBBY
    
    # Configuración
    roles_config: Dict[str, int] = field(default_factory=lambda: {
        "mafia": 1,
        "ciudadano": 3
    })
    night_seconds: int = 300
    day_seconds: int = 600
    periodic_reminder_seconds: int = 120
    
    # Estado del juego
    players: Dict[int, Player] = field(default_factory=dict)
    night_actions: List[NightAction] = field(default_factory=list)
    day_votes: Dict[int, int] = field(default_factory=dict)  # voter_id -> target_id
    mafia_votes: Dict[int, int] = field(default_factory=dict)  # mafia_id -> target_id
    
    # Control de tiempo
    phase_deadline: Optional[int] = None
    created_at: int = field(default_factory=lambda: int(time.time()))
    updated_at: int = field(default_factory=lambda: int(time.time()))
    
    # Control de jobs (nombres de jobs programados)
    job_names: Set[str] = field(default_factory=set)
    
    def get_alive_players(self) -> List[Player]:
        """Retorna lista de jugadores vivos."""
        return [p for p in self.players.values() if p.alive]
    
    def get_dead_players(self) -> List[Player]:
        """Retorna lista de jugadores muertos."""
        return [p for p in self.players.values() if not p.alive]
    
    def get_players_by_faction(self, faction: Faction) -> List[Player]:
        """Retorna jugadores vivos de una facción."""
        from .roles import ROLES  # Import local para evitar circular
        return [
            p for p in self.get_alive_players()
            if p.role_key and ROLES.get(p.role_key)
            and ROLES[p.role_key].faction == faction
        ]
    
    def reset_to_lobby(self):
        """Resetea la partida al estado inicial."""
        self.phase = Phase.LOBBY
        self.roles_config = {"mafia": 1, "ciudadano": 3}
        self.night_actions.clear()
        self.day_votes.clear()
        self.mafia_votes.clear()
        self.phase_deadline = None
        self.job_names.clear()
        
        for player in self.players.values():
            player.role_key = None
            player.alive = True
            player.blocked = False
            player.silenced = False
            player.protected = False
            player.dm_sent_ok = False
        
        self.updated_at = int(time.time())
    
    def clear_night_state(self):
        """Limpia el estado específico de la noche."""
        self.night_actions.clear()
        self.mafia_votes.clear()
        for player in self.players.values():
            player.reset_night_status()
    
    def clear_day_state(self):
        """Limpia el estado específico del día."""
        self.day_votes.clear()
        # Remover silencio
        for player in self.players.values():
            player.silenced = False


@dataclass
class GameEvent:
    """Evento que ocurre durante el juego (para logging/notificaciones)."""
    event_type: str  # death, heal, block, investigation, etc.
    timestamp: int = field(default_factory=lambda: int(time.time()))
    actor_id: Optional[int] = None
    target_id: Optional[int] = None
    details: Dict = field(default_factory=dict)