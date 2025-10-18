"""
gui/controllers/player_perspective.py - NUEVO ARCHIVO
Controla qué ve y puede hacer cada jugador.
"""
from typing import List, Optional
import logging

from core.models import Game, Player, Phase, Faction, ChatMessage
from core.roles import get_role

logger = logging.getLogger(__name__)


class PlayerPerspective:
    """
    Limita lo que ve y puede hacer un jugador específico.
    Implementa reglas de privacidad y restricciones de rol.
    """

    def __init__(self, player_id: int, game: Game):
        """
        Args:
            player_id: ID del jugador cuya perspectiva aplicamos
            game: Referencia al estado del juego
        """
        self.player_id = player_id
        self.game = game

    @property
    def player(self) -> Optional[Player]:
        """Retorna el jugador cuya perspectiva es esta."""
        return self.game.players.get(self.player_id)

    # ========================================================================
    # VISIBILIDAD DE JUGADORES
    # ========================================================================

    def get_visible_players(self) -> List[Player]:
        """
        Retorna jugadores que este jugador puede ver.

        Reglas:
        - Si está vivo: ve solo jugadores vivos
        - Si está muerto: ve todos los jugadores (observador)
        - Host (player_id == host_id) en debug: ve todos
        """
        player = self.player
        if not player:
            return []

        # Muertos ven a todos
        if not player.alive:
            return list(self.game.players.values())

        # Vivos ven solo a vivos
        return self.game.get_alive_players()

    def can_see_player_role(self, other_player_id: int) -> bool:
        """
        Retorna True si puede ver el rol de otro jugador.

        Reglas:
        - Su propio rol: siempre
        - Otros vivos: solo si está muerto o es investigador que investigó
        - Otros muertos: siempre (roles revelados al morir)
        """
        if other_player_id == self.player_id:
            return True  # Siempre ve su propio rol

        other_player = self.game.players.get(other_player_id)
        if not other_player:
            return False

        # Si el otro está muerto, todos ven su rol
        if not other_player.alive:
            return True

        # Si yo estoy muerto, veo todos los roles
        if not self.player.alive:
            return True

        # Investigadores/Sheriffs/Consigliere solo ven si ya investigaron
        # (esto se manejaría en game_controller con historial)
        # Por ahora: solo muertos
        return False

    # ========================================================================
    # CANALES DE CHAT DISPONIBLES
    # ========================================================================

    def get_available_chat_channels(self) -> List[str]:
        """
        Retorna canales de chat que puede usar/ver.

        Reglas:
        - Todos: "general"
        - Mafia: "general" + "mafia"
        - Investigadores: "general" + "investigator" (futuro)
        - Muertos: ninguno (no pueden hablar)
        """
        player = self.player
        if not player or not player.alive:
            return []

        channels = ["general"]

        # Si es mafia, añadir canal mafia
        if player.role_key:
            role = get_role(player.role_key)
            if role and role.faction == Faction.MAFIA:
                channels.append("mafia")

        return channels

    def can_see_chat_message(self, message: ChatMessage) -> bool:
        """
        Retorna True si puede ver un mensaje de chat.

        Reglas:
        - "general": todos ven
        - "mafia": solo mafiosos viven ven
        - "investigator": solo investigadores viven ven (futuro)
        """
        player = self.player
        if not player or not player.alive:
            return False  # Muertos no ven chat

        if message.channel == "general":
            return True

        if message.channel == "mafia":
            if player.role_key:
                role = get_role(player.role_key)
                return role and role.faction == Faction.MAFIA
            return False

        if message.channel == "investigator":
            if player.role_key:
                return player.role_key in ["detective", "sheriff", "consigliere"]
            return False

        return False

    # ========================================================================
    # ACCIONES DISPONIBLES
    # ========================================================================

    def get_available_actions(self) -> List[str]:
        """
        Retorna acciones que puede realizar.

        Returns:
            Lista de action_type que puede hacer: ["heal", "investigate", "vote", etc.]
        """
        player = self.player
        if not player or not player.alive:
            return []

        if not player.role_key:
            return []

        role = get_role(player.role_key)
        if not role:
            return []

        actions = []

        # Acciones según la fase
        if self.game.phase == Phase.NIGHT and role.has_night_action:
            # Mapeo de roles a acciones
            action_map = {
                "doctor": "heal",
                "detective": "investigate",
                "sheriff": "investigate",
                "escort": "block",
                "guardaespaldas": "guard",
                "vigilante": "vigilante_kill",
                "asesino": "serial_kill",
                "consorte": "block",
                "consigliere": "investigate",
                "chantajeador": "blackmail",
                "mafia": "mafia_vote",
                "padrino": "mafia_vote",
            }

            action = action_map.get(role.key)
            if action:
                actions.append(action)

        elif self.game.phase == Phase.VOTING and not player.silenced:
            actions.append("day_vote")

        return actions

    def can_perform_action(self, action_type: str) -> bool:
        """Valida si puede realizar una acción específica."""
        return action_type in self.get_available_actions()

    # ========================================================================
    # INFORMACIÓN DEL ESTADO DEL JUEGO
    # ========================================================================

    def get_game_phase_info(self) -> str:
        """Retorna información sobre la fase actual que puede ver."""
        return self.game.phase.value

    def get_night_actions_visible(self) -> int:
        """Retorna número de acciones nocturnas registradas (si es muerto)."""
        if not self.player or self.player.alive:
            return 0  # Vivos no ven esto

        return len(self.game.night_actions)

    def get_day_votes_visible(self) -> int:
        """Retorna número de votos registrados (en votación)."""
        if not self.player or not self.player.alive:
            return 0

        return len(self.game.day_votes)

    # ========================================================================
    # RESTRICCIONES EN ACCIONES
    # ========================================================================

    def get_valid_targets(self, action_type: str) -> List[Player]:
        """
        Retorna lista de jugadores válidos como objetivo para una acción.

        Aplicar restricciones:
        - No puede targetear a muertos (excepto para investigar si está muerto)
        - No puede targetear a sí mismo (excepto doctor)
        - Mafia no puede targetear a mafia
        - etc.
        """
        player = self.player
        if not player or not player.alive:
            return []

        candidates = self.get_visible_players()

        # Filtro 1: Acción básica
        if action_type in ["heal", "guard"]:
            # Doctor puede curarse a sí mismo, guardaespaldas no
            if action_type == "guard":
                candidates = [p for p in candidates if p.user_id != player.user_id]

        elif action_type in ["investigate", "block", "blackmail"]:
            # No pueden targetear a sí mismos
            candidates = [p for p in candidates if p.user_id != player.user_id]

        elif action_type in ["vigilante_kill", "serial_kill", "day_vote", "mafia_vote"]:
            # No pueden votar/disparar a sí mismos
            candidates = [p for p in candidates if p.user_id != player.user_id]

        # Filtro 2: Restricciones por rol
        role = get_role(player.role_key) if player.role_key else None
        if role and role.faction == Faction.MAFIA:
            if action_type in ["vigilante_kill", "serial_kill", "mafia_vote", "day_vote"]:
                # Mafia no puede atacar/votar a otros mafiosos
                non_mafia = [
                    p for p in candidates
                    if not p.role_key or get_role(p.role_key).faction != Faction.MAFIA
                ]
                candidates = non_mafia if non_mafia else candidates

        return candidates

    # ========================================================================
    # INFORMACIÓN DE DEPURACIÓN
    # ========================================================================

    def get_debug_info(self) -> dict:
        """Retorna información de debug sobre la perspectiva."""
        player = self.player
        if not player:
            return {}

        return {
            "player_id": self.player_id,
            "player_name": player.name,
            "player_role": player.role_key,
            "is_alive": player.alive,
            "visible_players_count": len(self.get_visible_players()),
            "available_channels": self.get_available_chat_channels(),
            "available_actions": self.get_available_actions(),
            "is_silenced": player.silenced,
            "is_blocked": player.blocked,
        }
