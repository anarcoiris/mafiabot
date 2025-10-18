"""
gui/bots/bot_player.py - NUEVO ARCHIVO
Sistema de IA para jugadores automáticos.
"""
import random
import logging
from typing import Optional, List, Tuple
from enum import Enum
from dataclasses import dataclass

from core.models import Game, Player, Phase, Faction
from core.roles import get_role

logger = logging.getLogger(__name__)


class BotDifficulty(Enum):
    """Niveles de dificultad para bots."""
    EASY = "easy"
    NORMAL = "normal"
    HARD = "hard"


@dataclass
class BotConfig:
    """Configuración de comportamiento del bot."""
    # Probabilidades (0.0 a 1.0)
    chat_frequency: float = 0.3  # Qué tan seguido habla
    first_night_caution: bool = True  # No ataca primera noche
    investigator_report_chance: float = 0.8  # Reporta hallazgos


class BotPlayer:
    """
    Jugador controlado por IA.
    Toma decisiones autónomamente según dificultad.
    """

    def __init__(self, player_id: int, name: str, difficulty: BotDifficulty = BotDifficulty.NORMAL):
        """
        Args:
            player_id: ID único del bot
            name: Nombre para mostrar
            difficulty: Nivel de dificultad
        """
        self.player_id = player_id
        self.name = name
        self.difficulty = difficulty
        self.config = self._get_config_for_difficulty(difficulty)
        self.night_count = 0  # Contador de noches para lógica de "primera noche"
        self.last_investigation_result = None  # Para reportar al chat

    def _get_config_for_difficulty(self, difficulty: BotDifficulty) -> BotConfig:
        """Retorna configuración según dificultad."""
        configs = {
            BotDifficulty.EASY: BotConfig(
                chat_frequency=0.2,
                first_night_caution=True,
                investigator_report_chance=0.5
            ),
            BotDifficulty.NORMAL: BotConfig(
                chat_frequency=0.3,
                first_night_caution=True,
                investigator_report_chance=0.7
            ),
            BotDifficulty.HARD: BotConfig(
                chat_frequency=0.5,
                first_night_caution=False,
                investigator_report_chance=0.9
            ),
        }
        return configs.get(difficulty, configs[BotDifficulty.NORMAL])

    # ========================================================================
    # DECISIONES NOCTURNAS
    # ========================================================================

    def decide_night_action(self, game: Game, player: Player) -> Tuple[Optional[int], Optional[str]]:
        """
        Decide qué acción nocturna realizar - CORREGIDO.

        Returns:
            (target_id, action_type) o (None, None) si no hay acción
        """
        if not player.alive or not player.role_key:
            return None, None

        role = get_role(player.role_key)
        if not role or not role.has_night_action:
            return None, None

        # CORREGIDO: Primera noche (night_count == 0) tiene lógica especial
        # pero NO debe impedir a la mafia votar
        if self.night_count == 0 and self.config.first_night_caution:
            if role.key == "doctor":
                target = self._pick_random_target(game, player, exclude_self=False)
                return target, "heal"
            elif role.key in ["detective", "sheriff", "consigliere"]:
                target = self._pick_random_target(game, player, exclude_self=True)
                return target, "investigate"
            elif role.key == "guardaespaldas":
                target = self._pick_random_target(game, player, exclude_self=True)
                return target, "guard"
            # MAFIA SÍ puede votar primera noche
            elif role.key in ["mafia", "padrino"]:
                # Retornar tipo especial para indicar voto de mafia
                target = self.decide_mafia_vote(game, player)
                return target, "mafia_vote"
            # Otros roles peligrosos no actúan primera noche
            else:
                return None, None

        # Acciones según rol (noches posteriores)
        if role.key == "doctor":
            return self._decide_doctor_action(game, player)

        elif role.key == "detective":
            return self._decide_detective_action(game, player)

        elif role.key == "sheriff":
            return self._decide_sheriff_action(game, player)

        elif role.key == "escort":
            return self._decide_escort_action(game, player)

        elif role.key == "guardaespaldas":
            return self._decide_guard_action(game, player)

        elif role.key == "vigilante":
            return self._decide_vigilante_action(game, player)

        elif role.key in ["mafia", "padrino"]:
            # Retornar tipo especial para voto de mafia
            target = self.decide_mafia_vote(game, player)
            return target, "mafia_vote"

        elif role.key == "consorte":
            return self._decide_escort_action(game, player)

        elif role.key == "chantajeador":
            return self._decide_blackmailer_action(game, player)

        elif role.key == "consigliere":
            return self._decide_consigliere_action(game, player)

        elif role.key == "asesino":
            return self._decide_serial_killer_action(game, player)

        return None, None

    def _decide_vigilante_action(self, game: Game, player: Player) -> Tuple[Optional[int], str]:
        """Vigilante elige a quién disparar - CORREGIDO."""
        # Primera noche no dispara (ya manejado arriba, pero por si acaso)
        if self.night_count == 0:
            return None, None

        if self.difficulty == BotDifficulty.EASY:
            target = self._pick_random_target(game, player, exclude_self=True)
        else:
            target = self._pick_suspicious_player(game, player)
            target = target.user_id if target else None

        return target, "vigilante_kill" if target else None

    def decide_mafia_vote(self, game: Game, player: Player) -> Optional[int]:
        """Mafia elige objetivo para matar (voto interno) - CORREGIDO."""
        # Solo puede votar a no-mafiosos
        non_mafia = [
            p for p in game.get_alive_players()
            if p.user_id != player.user_id and (
                not p.role_key or get_role(p.role_key).faction != Faction.MAFIA
            )
        ]

        if not non_mafia:
            return None

        if self.difficulty == BotDifficulty.EASY:
            return random.choice(non_mafia).user_id
        else:
            # Intenta identificar roles peligrosos
            return self._pick_dangerous_target(game, non_mafia).user_id

    def _pick_suspicious_player(self, game: Game, player: Player,
                               from_list: Optional[List[Player]] = None) -> Optional[Player]:
        """Elige al jugador más "sospechoso" - CORREGIDO."""
        if from_list is None:
            from_list = game.get_alive_players()

        candidates = [p for p in from_list if p.user_id != player.user_id]

        if not candidates:
            return None

        # Simple heurística mejorada
        # Priorizar: 1) No habla en chat, 2) Aleatorio
        return random.choice(candidates)

    def should_send_chat_message(self) -> bool:
        """Retorna True si el bot debería enviar un mensaje."""
        return random.random() < self.config.chat_frequency

    def generate_investigation_report(self, target_name: str, result: str) -> str:
        """Genera un reporte de investigación para el chat."""
        reports = [
            f"He investigado a {target_name}: {result}",
            f"Mis hallazgos sobre {target_name}: {result}",
            f"Información sobre {target_name} - {result}",
            f"Investigué a {target_name} y encontré: {result}",
        ]
        return random.choice(reports)

    def generate_casual_message(self) -> Optional[str]:
        """Genera un mensaje casual para el chat."""
        messages = [
            "Hmm... algo no me cuadra.",
            "¿Alguien tiene alguna pista?",
            "Esto se está poniendo interesante.",
            "Debemos ser cuidadosos.",
            "¿Quién parece sospechoso?",
            "Necesitamos más información.",
        ]

        if random.random() < 0.3:  # 30% de probabilidad
            return random.choice(messages)

        return None

    def _decide_doctor_action(self, game: Game, player: Player) -> Tuple[Optional[int], str]:
        """Doctor elige a quién curar."""
        if self.difficulty == BotDifficulty.EASY:
            # Cura al azar
            target = self._pick_random_target(game, player, exclude_self=False)
        else:
            # Cura a jugadores que parecen importantes (médio / sin protección obvia)
            target = self._pick_smart_target(game, player)

        return target, "heal"

    def _decide_detective_action(self, game: Game, player: Player) -> Tuple[Optional[int], str]:
        """Detective elige a quién investigar."""
        target = self._pick_random_target(game, player, exclude_self=True)
        return target, "investigate"

    def _decide_sheriff_action(self, game: Game, player: Player) -> Tuple[Optional[int], str]:
        """Sheriff elige a quién investigar."""
        target = self._pick_random_target(game, player, exclude_self=True)
        return target, "investigate"

    def _decide_escort_action(self, game: Game, player: Player) -> Tuple[Optional[int], str]:
        """Escort bloquea a alguien."""
        target = self._pick_random_target(game, player, exclude_self=True)
        return target, "block"

    def _decide_guard_action(self, game: Game, player: Player) -> Tuple[Optional[int], str]:
        """Guardaespaldas protege a alguien."""
        if self.difficulty == BotDifficulty.EASY:
            target = self._pick_random_target(game, player, exclude_self=True)
        else:
            # Intenta proteger a "líderes" o investigadores
            target = self._pick_smart_target(game, player)

        return target, "guard"

    def _decide_vigilante_action(self, game: Game, player: Player) -> Tuple[Optional[int], str]:
        """Vigilante elige a quién disparar."""
        if self.night_count == 0:
            # Primera noche no dispara
            return None, None

        if self.difficulty == BotDifficulty.EASY:
            # Dispara al azar (peligro de matar aliados)
            target = self._pick_random_target(game, player, exclude_self=True)
        else:
            # Intenta disparar a sospechosos
            target = self._pick_suspicious_player(game, player)

        return target, "vigilante_kill"

    def _decide_blackmailer_action(self, game: Game, player: Player) -> Tuple[Optional[int], str]:
        """Chantajeador silencia a alguien (mafia)."""
        # Silencia a alguien que no sea mafia
        alive_non_mafia = [
            p for p in game.get_alive_players()
            if p.user_id != player.user_id and (not p.role_key or get_role(p.role_key).faction != Faction.MAFIA)
        ]

        if alive_non_mafia:
            target = random.choice(alive_non_mafia)
            return target.user_id, "blackmail"

        return None, None

    def _decide_consigliere_action(self, game: Game, player: Player) -> Tuple[Optional[int], str]:
        """Consigliere investiga a alguien (mafia)."""
        target = self._pick_random_target(game, player, exclude_self=True, exclude_faction=Faction.MAFIA)
        return target, "investigate"

    def _decide_serial_killer_action(self, game: Game, player: Player) -> Tuple[Optional[int], str]:
        """Asesino en serie elige víctima."""
        target = self._pick_random_target(game, player, exclude_self=True)
        return target, "serial_kill"

    # ========================================================================
    # DECISIONES DE VOTACIÓN
    # ========================================================================

    def decide_day_vote(self, game: Game, player: Player) -> Optional[int]:
        """
        Decide a quién votar para linchar.
        IMPORTANTE: No vota a miembros de su facción (si es mafia).
        """
        if not player.alive or player.silenced:
            return None

        # Obtener candidatos
        candidates = [p for p in game.get_alive_players() if p.user_id != player.user_id]

        if not candidates:
            return None

        # Si es mafia: NO votar a otros mafiosos
        if player.role_key and get_role(player.role_key).faction == Faction.MAFIA:
            non_mafia_candidates = [
                p for p in candidates
                if not p.role_key or get_role(p.role_key).faction != Faction.MAFIA
            ]
            candidates = non_mafia_candidates if non_mafia_candidates else candidates

        if self.difficulty == BotDifficulty.EASY:
            # Vota al azar entre candidatos válidos
            return random.choice(candidates).user_id if candidates else None

        else:
            # Vota a alguien "sospechoso"
            return self._pick_suspicious_player(game, player, from_list=candidates).user_id


    # ========================================================================
    # HELPERS PARA DECISIONES
    # ========================================================================

    def _pick_random_target(self, game: Game, player: Player,
                           exclude_self: bool = True,
                           exclude_faction: Optional[Faction] = None) -> Optional[int]:
        """Elige un objetivo aleatorio con filtros."""
        candidates = game.get_alive_players()

        if exclude_self:
            candidates = [p for p in candidates if p.user_id != player.user_id]

        if exclude_faction:
            candidates = [
                p for p in candidates
                if not p.role_key or get_role(p.role_key).faction != exclude_faction
            ]

        return random.choice(candidates).user_id if candidates else None

    def _pick_smart_target(self, game: Game, player: Player) -> Optional[int]:
        """Elige objetivo inteligente (prioriza habladores/activos)."""
        candidates = [p for p in game.get_alive_players() if p.user_id != player.user_id]

        if not candidates:
            return None

        # Prioridad: personajes que hayan hablado mucho en chat (simulado)
        # Para ahora, solo aleatorio pero podría mejorarse
        return random.choice(candidates).user_id

    def _pick_suspicious_player(self, game: Game, player: Player,
                               from_list: Optional[List[Player]] = None) -> Optional[Player]:
        """Elige al jugador más "sospechoso"."""
        if from_list is None:
            from_list = game.get_alive_players()

        candidates = [p for p in from_list if p.user_id != player.user_id]

        if not candidates:
            return None

        # Simple heurística: jugadores que hablan menos parecen sospechosos
        # (En una IA real, analizaría patrones de voto, mensajes, etc.)
        return random.choice(candidates)

    def _pick_dangerous_target(self, game: Game, candidates: List[Player]) -> Player:
        """Mafia elige objetivo peligroso (doctor, sheriff, etc.)."""
        # Roles peligrosos que la mafia quiere eliminar
        dangerous_roles = ["doctor", "sheriff", "detective", "vigilante", "guardaespaldas"]

        # Intentar encontrar uno de esos roles
        for candidate in candidates:
            if candidate.role_key in dangerous_roles:
                return candidate

        # Si no encuentra, elegir al azar
        return random.choice(candidates)

    # ========================================================================
    # REPORTES DE CHAT
    # ========================================================================

    def should_send_chat_message(self) -> bool:
        """Retorna True si el bot debería enviar un mensaje."""
        return random.random() < self.config.chat_frequency

    def generate_investigation_report(self, target_name: str, result: str) -> str:
        """Genera un reporte de investigación para el chat."""
        reporter_role = "Investigador"  # Simplificado

        reports = [
            f"He investigado a {target_name}... {result}.",
            f"Mis hallazgos sobre {target_name}: {result}",
            f"Interesante. {target_name} parece ser {result}",
        ]

        return random.choice(reports)

    def record_investigation_result(self, target_name: str, result: str):
        """Guarda resultado de investigación para reportar después."""
        self.last_investigation_result = (target_name, result)

    def next_night(self):
        """Llamado al comenzar una nueva noche."""
        self.night_count += 1
        logger.info(f"Bot {self.name} entra en noche #{self.night_count}")
