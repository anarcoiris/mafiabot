#!/usr/bin/env python3
# Auto-generated models module (corrected)
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
from enum import Enum
from collections import defaultdict

# ----------------------------
class Faction(Enum):
    TOWN = "town"
    MAFIA = "mafia"
    NEUTRAL = "neutral"


@dataclass
class Role:
    key: str
    name: str
    faction: Faction
    has_night_action: bool = False
    detective_signature: Optional[str] = None
    sheriff_detects_as_guilty: bool = False
    undetectable_by_detective: bool = False
    description: str = ""


ROLES: Dict[str, Role] = {}


def reg_role(r: Role):
    ROLES[r.key] = r


# Register roles (as requested)
reg_role(Role("mafia", "Mafioso", Faction.MAFIA, True, detective_signature="ARMA", description="Miembro de la Mafia."))
reg_role(Role("padrino", "Padrino", Faction.MAFIA, True, detective_signature=None, undetectable_by_detective=True, description="Líder mafioso (no detectable)."))
reg_role(Role("doctor", "Doctor", Faction.TOWN, True, detective_signature="CUCHILLO", description="Cura por la noche."))
reg_role(Role("detective", "Detective", Faction.TOWN, True, description="Investiga firmas."))
reg_role(Role("sheriff", "Sheriff", Faction.TOWN, True, sheriff_detects_as_guilty=True, description="Detecta mafia/asesino."))
reg_role(Role("escort", "Escort", Faction.TOWN, True, detective_signature="BLOQUEADOR", description="Bloqueador nocturno."))
reg_role(Role("consorte", "Consorte", Faction.MAFIA, True, detective_signature="BLOQUEADOR", description="Bloqueador (Mafia)."))
reg_role(Role("chantajeador", "Chantajeador", Faction.MAFIA, True, detective_signature="SUSPECTO", description="Chantajea (silencia)."))
reg_role(Role("guardaespaldas", "Guardaespaldas", Faction.TOWN, True, description="Protege sacrificándose."))
reg_role(Role("vigilante", "Vigilante", Faction.TOWN, True, detective_signature="ARMA", description="Puede disparar por la noche."))
reg_role(Role("asesino", "AsesinoEnSerie", Faction.NEUTRAL, True, detective_signature="CUCHILLO", description="Neutral: asesino nocturno."))
reg_role(Role("ciudadano", "Ciudadano", Faction.TOWN, False, description="Sin habilidad."))


# ----------------------------
@dataclass
class PlayerState:
    user_id: int
    name: str
    role_key: Optional[str] = None
    alive: bool = True
    blocked: bool = False
    silenced: bool = False


@dataclass
class GameState:
    chat_id: int
    host_id: int
    phase: str = "lobby"
    roles_config: Dict[str, int] = field(default_factory=lambda: {"mafia": 1, "ciudadano": 3})
    night_seconds: int = 300
    day_seconds: int = 600
    periodic_reminder_seconds: int = 120
    phase_deadline: Optional[int] = None
    players: Dict[int, PlayerState] = field(default_factory=dict)
    # runtime transient
    night_actions: Dict[str, List[Tuple[int, int]]] = field(default_factory=lambda: defaultdict(list))
    mafia_votes: Dict[int, int] = field(default_factory=dict)
    pending_action_callbacks: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    job_ids: Dict[str, str] = field(default_factory=dict)


__all__ = ["Faction", "Role", "ROLES", "reg_role", "PlayerState", "GameState"]
