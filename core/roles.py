"""
core/roles.py
Definición de todos los roles del juego de Mafia.
Sin dependencias de Telegram ni persistencia.
"""
from dataclasses import dataclass
from typing import Dict, Optional
from enum import Enum

from .models import Faction


@dataclass
class Role:
    """Definición completa de un rol del juego."""
    key: str
    name: str
    description: str
    faction: Faction
    has_night_action: bool = False
    priority: int = 5  # Para ordenar acciones nocturnas (menor = antes)
    
    # Detección
    detective_signature: Optional[str] = None
    undetectable_by_detective: bool = False
    sheriff_detects_as_guilty: bool = False
    
    # Capacidades especiales
    can_be_blocked: bool = True
    immune_to_attacks: bool = False
    
    def __post_init__(self):
        """Validación básica."""
        if self.priority < 0 or self.priority > 10:
            raise ValueError(f"Priority must be between 0-10, got {self.priority}")


# ============================================================================
# DEFINICIÓN DE ROLES
# ============================================================================

ROLES: Dict[str, Role] = {
    # ------------------------------------------------------------------------
    # PUEBLO (TOWN)
    # ------------------------------------------------------------------------
    "ciudadano": Role(
        key="ciudadano",
        name="Ciudadano",
        description=(
            "🏘️ **Ciudadano**\n\n"
            "Eres un ciudadano común del pueblo. No tienes habilidades especiales, "
            "pero tu voto durante el día es crucial para identificar y eliminar a los mafiosos.\n\n"
            "**Objetivo:** Eliminar a toda la Mafia y amenazas neutrales."
        ),
        faction=Faction.TOWN,
        has_night_action=False
    ),
    
    "doctor": Role(
        key="doctor",
        name="Doctor",
        description=(
            "🏥 **Doctor**\n\n"
            "Cada noche puedes proteger a un jugador (incluyéndote a ti mismo) de un ataque mortal. "
            "Si el jugador protegido es atacado, sobrevivirá.\n\n"
            "**Habilidad:** Curar a un jugador cada noche\n"
            "**Objetivo:** Proteger al pueblo y eliminar a la Mafia"
        ),
        faction=Faction.TOWN,
        has_night_action=True,
        priority=3,  # Antes de los ataques
        detective_signature="CUCHILLO"
    ),
    
    "detective": Role(
        key="detective",
        name="Detective",
        description=(
            "🔍 **Detective**\n\n"
            "Cada noche puedes investigar a un jugador y descubrir pistas sobre su identidad. "
            "Recibirás información sobre objetos o características asociadas con su rol.\n\n"
            "**Habilidad:** Investigar a un jugador cada noche\n"
            "**Nota:** Algunos roles pueden engañarte\n"
            "**Objetivo:** Usar tus investigaciones para identificar a la Mafia"
        ),
        faction=Faction.TOWN,
        has_night_action=True,
        priority=4
    ),
    
    "sheriff": Role(
        key="sheriff",
        name="Sheriff",
        description=(
            "🔎 **Sheriff**\n\n"
            "Cada noche puedes investigar a un jugador y determinar si es CULPABLE o INOCENTE. "
            "Detectarás a miembros de la Mafia y al Asesino en Serie como culpables.\n\n"
            "**Habilidad:** Investigar alineación cada noche\n"
            "**Nota:** El Padrino aparecerá como inocente\n"
            "**Objetivo:** Identificar y eliminar a los criminales"
        ),
        faction=Faction.TOWN,
        has_night_action=True,
        priority=4,
        sheriff_detects_as_guilty=False  # El sheriff no se detecta a sí mismo como culpable
    ),
    
    "escort": Role(
        key="escort",
        name="Escort",
        description=(
            "💃 **Escort**\n\n"
            "Cada noche puedes distraer a un jugador, bloqueando su acción nocturna. "
            "Si bloqueas a un mafioso durante su ataque, salvarás a su víctima.\n\n"
            "**Habilidad:** Bloquear la acción de un jugador\n"
            "**Nota:** No puedes bloquearte a ti mismo\n"
            "**Objetivo:** Proteger al pueblo bloqueando amenazas"
        ),
        faction=Faction.TOWN,
        has_night_action=True,
        priority=1,  # Primera prioridad para bloquear antes que todo
        detective_signature="BLOQUEADOR"
    ),
    
    "guardaespaldas": Role(
        key="guardaespaldas",
        name="Guardaespaldas",
        description=(
            "🛡️ **Guardaespaldas**\n\n"
            "Cada noche puedes proteger a un jugador. Si es atacado, morirás tú en su lugar, "
            "pero el atacado sobrevivirá.\n\n"
            "**Habilidad:** Proteger con tu vida a un jugador\n"
            "**Nota:** No puedes protegerte a ti mismo\n"
            "**Objetivo:** Sacrificarte por ciudadanos importantes"
        ),
        faction=Faction.TOWN,
        has_night_action=True,
        priority=2  # Antes de ataques pero después de bloqueos
    ),
    
    "vigilante": Role(
        key="vigilante",
        name="Vigilante",
        description=(
            "🔫 **Vigilante**\n\n"
            "Eres un justiciero que puede disparar y matar a un jugador durante la noche. "
            "Ten cuidado: si matas a un ciudadano inocente, te sentirás culpable.\n\n"
            "**Habilidad:** Disparar a un jugador (munición limitada)\n"
            "**Riesgo:** Puedes matar accidentalmente a aliados\n"
            "**Objetivo:** Eliminar criminales por tu cuenta"
        ),
        faction=Faction.TOWN,
        has_night_action=True,
        priority=5,
        detective_signature="ARMA"
    ),
    
    # ------------------------------------------------------------------------
    # MAFIA
    # ------------------------------------------------------------------------
    "mafia": Role(
        key="mafia",
        name="Mafioso",
        description=(
            "🔴 **Mafioso**\n\n"
            "Eres miembro de la Mafia. Cada noche, todos los mafiosos votan en secreto "
            "para elegir a quién asesinar. Debes eliminar a todos los ciudadanos para ganar.\n\n"
            "**Habilidad:** Votar por un objetivo cada noche\n"
            "**Objetivo:** Que la Mafia iguale o supere en número al pueblo"
        ),
        faction=Faction.MAFIA,
        has_night_action=True,
        priority=5,
        detective_signature="ARMA",
        sheriff_detects_as_guilty=True
    ),
    
    "padrino": Role(
        key="padrino",
        name="Padrino",
        description=(
            "👔 **Padrino**\n\n"
            "Eres el líder de la Mafia. Apareces como INOCENTE ante investigaciones "
            "y eres inmune a ataques nocturnos directos. Participas en los asesinatos de la Mafia.\n\n"
            "**Habilidad:** Inmunidad a investigaciones y ataques\n"
            "**Objetivo:** Que la Mafia controle el pueblo"
        ),
        faction=Faction.MAFIA,
        has_night_action=True,
        priority=5,
        undetectable_by_detective=True,  # No deja firma
        sheriff_detects_as_guilty=False,  # Aparece como inocente
        immune_to_attacks=True
    ),
    
    "consorte": Role(
        key="consorte",
        name="Consorte",
        description=(
            "💋 **Consorte**\n\n"
            "Eres miembro de la Mafia con habilidad de distracción. Cada noche puedes "
            "bloquear la acción de un jugador, igual que el Escort del pueblo.\n\n"
            "**Habilidad:** Bloquear acciones + voto de la Mafia\n"
            "**Objetivo:** Proteger a la Mafia y eliminar al pueblo"
        ),
        faction=Faction.MAFIA,
        has_night_action=True,
        priority=1,  # Bloquea primero
        detective_signature="BLOQUEADOR",
        sheriff_detects_as_guilty=True
    ),
    
    "chantajeador": Role(
        key="chantajeador",
        name="Chantajeador",
        description=(
            "🤐 **Chantajeador**\n\n"
            "Miembro de la Mafia que puede silenciar a un jugador. La víctima no podrá "
            "hablar ni votar durante el día siguiente.\n\n"
            "**Habilidad:** Silenciar a un jugador + voto de la Mafia\n"
            "**Objetivo:** Eliminar voces importantes del pueblo"
        ),
        faction=Faction.MAFIA,
        has_night_action=True,
        priority=1,
        detective_signature="SUSPECTO",
        sheriff_detects_as_guilty=True
    ),
    
    "consigliere": Role(
        key="consigliere",
        name="Consigliere",
        description=(
            "🎩 **Consigliere**\n\n"
            "Eres el consejero de la Mafia. Cada noche puedes investigar a un jugador "
            "y descubrir su rol exacto, sin importar inmunidades.\n\n"
            "**Habilidad:** Descubrir el rol exacto de cualquier jugador\n"
            "**Objetivo:** Usar tu información para guiar a la Mafia"
        ),
        faction=Faction.MAFIA,
        has_night_action=True,
        priority=4,
        detective_signature="SUSPECTO",
        sheriff_detects_as_guilty=True
    ),
    
    # ------------------------------------------------------------------------
    # NEUTRAL
    # ------------------------------------------------------------------------
    "asesino": Role(
        key="asesino",
        name="Asesino en Serie",
        description=(
            "🔪 **Asesino en Serie**\n\n"
            "Eres un asesino solitario. Cada noche puedes matar a un jugador. "
            "Eres inmune a ataques nocturnos directos. Ganas si eres el único superviviente.\n\n"
            "**Habilidad:** Matar cada noche + inmunidad\n"
            "**Objetivo:** Ser el único superviviente"
        ),
        faction=Faction.NEUTRAL,
        has_night_action=True,
        priority=6,  # Última prioridad de ataque
        detective_signature="CUCHILLO",
        sheriff_detects_as_guilty=True,
        immune_to_attacks=True
    ),
    
    "bufon": Role(
        key="bufon",
        name="Bufón",
        description=(
            "🤡 **Bufón**\n\n"
            "Tu objetivo es ser linchado durante el día. Si lo consigues, ganas inmediatamente. "
            "Eres inmune a ataques nocturnos.\n\n"
            "**Objetivo:** Hacer que el pueblo te linche\n"
            "**Nota:** Si mueres de noche o sobrevives, pierdes"
        ),
        faction=Faction.NEUTRAL,
        has_night_action=False,
        immune_to_attacks=True,
        detective_signature="EXTRAÑO"
    ),
    
    "ejecutor": Role(
        key="ejecutor",
        name="Ejecutor",
        description=(
            "⚔️ **Ejecutor**\n\n"
            "Se te asigna secretamente un objetivo del pueblo. Debes lograr que sea linchado. "
            "Si lo consigues, ganas. Si tu objetivo muere de noche, te conviertes en Bufón.\n\n"
            "**Objetivo:** Hacer que tu objetivo sea linchado\n"
            "**Nota:** Solo tú sabes quién es tu objetivo"
        ),
        faction=Faction.NEUTRAL,
        has_night_action=False,
        detective_signature="VENDETTA"
    ),
}


# ============================================================================
# FUNCIONES HELPER
# ============================================================================

def get_role(key: str) -> Optional[Role]:
    """
    Obtiene un rol por su clave.
    
    Args:
        key: Clave del rol (ej: "mafia", "doctor")
    
    Returns:
        Role object o None si no existe
    """
    return ROLES.get(key)


def get_roles_by_faction(faction: Faction) -> Dict[str, Role]:
    """
    Obtiene todos los roles de una facción.
    
    Args:
        faction: Faction enum (TOWN, MAFIA, NEUTRAL)
    
    Returns:
        Diccionario {key: Role} de roles de esa facción
    """
    return {
        key: role 
        for key, role in ROLES.items() 
        if role.faction == faction
    }


def get_all_roles() -> Dict[str, Role]:
    """Retorna todos los roles disponibles."""
    return ROLES.copy()


def get_roles_with_night_action() -> Dict[str, Role]:
    """Retorna solo roles con acción nocturna."""
    return {
        key: role 
        for key, role in ROLES.items() 
        if role.has_night_action
    }


def validate_role_key(key: str) -> bool:
    """
    Valida que una clave de rol exista.
    
    Args:
        key: Clave a validar
    
    Returns:
        True si el rol existe
    """
    return key in ROLES


def get_role_name(key: str) -> str:
    """
    Obtiene el nombre legible de un rol.
    
    Args:
        key: Clave del rol
    
    Returns:
        Nombre del rol o "Desconocido" si no existe
    """
    role = ROLES.get(key)
    return role.name if role else "Desconocido"


def get_default_role() -> str:
    """Retorna la clave del rol por defecto (Ciudadano)."""
    return "ciudadano"


# ============================================================================
# CONFIGURACIONES RECOMENDADAS
# ============================================================================

RECOMMENDED_CONFIGS = {
    4: {"mafia": 1, "doctor": 1, "detective": 1, "ciudadano": 1},
    5: {"mafia": 1, "doctor": 1, "detective": 1, "ciudadano": 2},
    6: {"mafia": 1, "doctor": 1, "detective": 1, "escort": 1, "ciudadano": 2},
    7: {"mafia": 2, "doctor": 1, "detective": 1, "escort": 1, "ciudadano": 2},
    8: {"mafia": 2, "padrino": 1, "doctor": 1, "detective": 1, "sheriff": 1, "ciudadano": 2},
    9: {"mafia": 2, "padrino": 1, "doctor": 1, "detective": 1, "sheriff": 1, "guardaespaldas": 1, "ciudadano": 2},
    10: {"mafia": 2, "padrino": 1, "consigliere": 1, "doctor": 1, "detective": 1, "sheriff": 1, "vigilante": 1, "ciudadano": 2},
}


def get_recommended_config(num_players: int) -> Dict[str, int]:
    """
    Obtiene una configuración recomendada para X jugadores.
    
    Args:
        num_players: Número de jugadores
    
    Returns:
        Diccionario {role_key: count}
    """
    if num_players in RECOMMENDED_CONFIGS:
        return RECOMMENDED_CONFIGS[num_players].copy()
    
    # Para números no definidos, usar proporción simple
    num_mafia = max(1, num_players // 4)
    num_special = max(1, num_players // 3)
    num_citizens = num_players - num_mafia - num_special
    
    return {
        "mafia": num_mafia,
        "doctor": 1,
        "detective": 1 if num_special >= 2 else 0,
        "ciudadano": max(1, num_citizens)
    }