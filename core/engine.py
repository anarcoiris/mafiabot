# core/engine.py
"""
Lógica pura del juego de Mafia - refactor de resolve_night en pasos pequeños y testables.
"""
import random
import logging
from typing import List, Dict, Optional, Tuple, Any
from collections import Counter, defaultdict

from .models import Game, Player, NightAction, Phase, Faction, GameEvent
from .roles import ROLES, get_role

logger = logging.getLogger(__name__)


class GameEngine:
    """Motor del juego que maneja toda la lógica."""

    def __init__(self):
        # En el futuro se puede guardar configuración o RNG seed aquí
        pass

    def assign_roles(self, game: Game) -> List[str]:
        """
        Asigna roles aleatorios a los jugadores según la configuración.
        Retorna lista de mensajes de error si algo falla.
        """
        errors = []
        if len(game.players) < 4:
            errors.append("Se necesitan al menos 4 jugadores para empezar.")
            return errors

        role_pool: List[str] = []
        for role_key, count in game.roles_config.items():
            if role_key not in ROLES:
                errors.append(f"Rol desconocido: {role_key}")
                continue
            role_pool.extend([role_key] * int(count))

        while len(role_pool) < len(game.players):
            role_pool.append("ciudadano")

        if len(role_pool) > len(game.players):
            role_pool = role_pool[:len(game.players)]

        random.shuffle(role_pool)
        player_ids = list(game.players.keys())
        random.shuffle(player_ids)

        for player_id, role_key in zip(player_ids, role_pool):
            game.players[player_id].role_key = role_key
            logger.info(f"Assigned {role_key} to player {player_id}")

        return errors

    # -------------------------
    # NOCHE: pipeline modular
    # -------------------------
    def resolve_night(self, game: Game) -> List[GameEvent]:
        """
        Resuelve la fase nocturna mediante una pipeline de pasos.
        Devuelve la lista de GameEvent generados.
        """
        if game is None:
            return []

        # Asegurar que night_actions existe y es iterable
        night_actions: List[NightAction] = list(getattr(game, "night_actions", []) or [])
        logger.debug("Starting night resolution (%d actions)", len(night_actions))

        # Normalizar: ordenar por prioridad ascendente (menor priority = antes)
        actions_sorted = sorted(night_actions, key=lambda a: getattr(a, "priority", 100))

        events: List[GameEvent] = []

        # PASO A - aplicar bloqueos (block)
        blocked_targets = self._apply_blocks(game, actions_sorted, events)

        # PASO B - aplicar curas y guardias (heal / guard)
        healed_targets, guarded_map = self._apply_protections(game, actions_sorted, events)

        # PASO C - incorporar acción colectiva de mafia basada en mafia_votes
        actions_sorted = list(actions_sorted)  # copia mutable
        self._append_mafia_action_if_any(game, actions_sorted)

        # PASO D - procesar ataques (mafia_kill, vigilante_kill, serial_kill)
        deaths, attack_events = self._process_attacks(game, actions_sorted, healed_targets, guarded_map, events)
        events.extend(attack_events)

        # PASO E - aplicar chantaje/silencios (blackmail)
        blackmail_events = self._apply_blackmail(game, actions_sorted)
        events.extend(blackmail_events)

        # PASO F - investigaciones (investigate)
        investigation_events = self._process_investigations(game, actions_sorted)
        events.extend(investigation_events)

        logger.info(
            "Night resolved for game %s: deaths=%d events=%d",
            getattr(game, "chat_id", "<unknown>"), len(deaths), len(events)
        )

        # Reset temporal flags que solo deben durar la noche (e.g., blocked)
        self._cleanup_temporary_flags(game)

        return events

    def _apply_blocks(self, game: Game, actions_sorted: List[NightAction], events: List[GameEvent]) -> set:
        """Aplica acciones de tipo 'block' y marca a objetivos como bloqueados temporalmente."""
        blocked_targets = set()
        for action in (a for a in actions_sorted if getattr(a, "action_type", "") == "block"):
            actor = game.players.get(action.actor_id)
            if not actor or not getattr(actor, "alive", True) or getattr(actor, "blocked", False):
                continue
            target = game.players.get(action.target_id)
            if target and getattr(target, "alive", True):
                # marcar bloqueo temporal en el target
                target.blocked = True
                blocked_targets.add(action.target_id)
                events.append(GameEvent(
                    event_type="block",
                    actor_id=action.actor_id,
                    target_id=action.target_id
                ))
        return blocked_targets

    def _apply_protections(self, game: Game, actions_sorted: List[NightAction], events: List[GameEvent]) -> Tuple[set, Dict[int, int]]:
        """
        Aplica curas (heal) y guardias (guard).
        Retorna (healed_targets_set, guarded_map target->guard_id).
        """
        healed = set()
        guarded: Dict[int, int] = {}

        # Heals
        for action in (a for a in actions_sorted if getattr(a, "action_type", "") == "heal"):
            actor = game.players.get(action.actor_id)
            if not actor or not getattr(actor, "alive", True) or getattr(actor, "blocked", False):
                continue
            target = game.players.get(action.target_id)
            if target and getattr(target, "alive", True):
                healed.add(action.target_id)
                events.append(GameEvent(
                    event_type="heal",
                    actor_id=action.actor_id,
                    target_id=action.target_id
                ))

        # Guards (bodyguard)
        for action in (a for a in actions_sorted if getattr(a, "action_type", "") == "guard"):
            actor = game.players.get(action.actor_id)
            if not actor or not getattr(actor, "alive", True) or getattr(actor, "blocked", False):
                continue
            target = game.players.get(action.target_id)
            if target and getattr(target, "alive", True):
                guarded[action.target_id] = action.actor_id
                events.append(GameEvent(
                    event_type="guard",
                    actor_id=action.actor_id,
                    target_id=action.target_id
                ))

        return healed, guarded

    def _append_mafia_action_if_any(self, game: Game, actions_sorted: List[NightAction]):
        """Si hay mafia_votes en el game, convertirlos en una NightAction mafia_kill y anexarla."""
        if not getattr(game, "mafia_votes", None):
            return
        if not isinstance(game.mafia_votes, dict):
            return

        # Calcular target más votado por la mafia
        if game.mafia_votes:
            vote_counts = Counter(game.mafia_votes.values())
            mafia_target, _ = vote_counts.most_common(1)[0]

            # encontrar un mafioso vivo y no bloqueado para ejecutar la acción (actor)
            mafia_attacker_id = None
            for p in game.players.values():
                if not getattr(p, "alive", True):
                    continue
                rk = getattr(p, "role_key", None)
                if not rk:
                    continue
                role = get_role(rk)
                if getattr(role, "faction", None) == Faction.MAFIA and not getattr(p, "blocked", False):
                    mafia_attacker_id = p.user_id
                    break

            if mafia_attacker_id is not None:
                actions_sorted.append(NightAction(
                    actor_id=mafia_attacker_id,
                    target_id=mafia_target,
                    action_type="mafia_kill",
                    priority=5
                ))

    def _process_attacks(
        self,
        game: Game,
        actions_sorted: List[NightAction],
        healed_targets: set,
        guarded_map: Dict[int, int],
        events_existing: List[GameEvent]
    ) -> Tuple[List[int], List[GameEvent]]:
        """
        Procesa los ataques reales y resuelve muertes/guardia/saves.
        Devuelve (deaths_list, events_list) — events_list no incluye los events_existing pasados.
        """
        deaths: List[int] = []
        events: List[GameEvent] = []

        attack_types = ("mafia_kill", "vigilante_kill", "serial_kill")
        for action in (a for a in actions_sorted if getattr(a, "action_type", "") in attack_types):
            actor = game.players.get(action.actor_id)
            target = game.players.get(action.target_id)

            if not actor or not getattr(actor, "alive", True) or getattr(actor, "blocked", False):
                continue
            if not target or not getattr(target, "alive", True):
                continue

            # inmunidades
            if getattr(target, "role_key", None) == "padrino":
                events.append(GameEvent(
                    event_type="attack_failed",
                    actor_id=action.actor_id,
                    target_id=action.target_id,
                    details={"reason": "padrino_immunity"}
                ))
                continue

            if getattr(target, "role_key", None) == "asesino":
                events.append(GameEvent(
                    event_type="attack_failed",
                    actor_id=action.actor_id,
                    target_id=action.target_id,
                    details={"reason": "serial_immunity"}
                ))
                continue

            # curado
            if action.target_id in healed_targets:
                events.append(GameEvent(
                    event_type="saved_by_heal",
                    actor_id=action.actor_id,
                    target_id=action.target_id
                ))
                continue

            # guardia (bodyguard) sacrifica al guard
            if action.target_id in guarded_map:
                guard_id = guarded_map[action.target_id]
                guard = game.players.get(guard_id)
                if guard and getattr(guard, "alive", True):
                    guard.alive = False
                    deaths.append(guard_id)
                    events.append(GameEvent(
                        event_type="bodyguard_death",
                        actor_id=guard_id,
                        target_id=action.target_id
                    ))
                continue

            # ataque exitoso
            target.alive = False
            deaths.append(action.target_id)
            events.append(GameEvent(
                event_type="death",
                actor_id=action.actor_id,
                target_id=action.target_id,
                details={"cause": action.action_type}
            ))

        return deaths, events

    def _apply_blackmail(self, game: Game, actions_sorted: List[NightAction]) -> List[GameEvent]:
        events: List[GameEvent] = []
        for action in (a for a in actions_sorted if getattr(a, "action_type", "") == "blackmail"):
            actor = game.players.get(action.actor_id)
            if not actor or not getattr(actor, "alive", True) or getattr(actor, "blocked", False):
                continue
            target = game.players.get(action.target_id)
            if target and getattr(target, "alive", True):
                target.silenced = True
                events.append(GameEvent(
                    event_type="blackmail",
                    actor_id=action.actor_id,
                    target_id=action.target_id
                ))
        return events

    def _process_investigations(self, game: Game, actions_sorted: List[NightAction]) -> List[GameEvent]:
        events: List[GameEvent] = []
        for action in (a for a in actions_sorted if getattr(a, "action_type", "") == "investigate"):
            actor = game.players.get(action.actor_id)
            if not actor or not getattr(actor, "alive", True) or getattr(actor, "blocked", False):
                continue
            target = game.players.get(action.target_id)
            if not target or not getattr(target, "alive", True):
                continue
            result = self._get_investigation_result(actor, target)
            events.append(GameEvent(
                event_type="investigation",
                actor_id=action.actor_id,
                target_id=action.target_id,
                details={"result": result, "investigator_role": getattr(actor, "role_key", None)}
            ))
        return events

    def _cleanup_temporary_flags(self, game: Game):
        """
        Limpia flags que sólo deben aplicarse durante la fase nocturna.
        Nota: algunos flags (p.ej. silenced) podrían ser persistentes por más de una fase,
        ajustar según reglas del juego.
        """
        for p in game.players.values():
            # Si 'blocked' se usa solo por noche, resetearlo
            if hasattr(p, "blocked"):
                try:
                    p.blocked = False
                except Exception:
                    pass
            # No borramos 'silenced' o 'protected' aquí si se desean persistentes;
            # si quieres que duren sólo una fase, también resetéalos.
        # limpio votos mafia para siguiente ciclo si corresponde
        try:
            if hasattr(game, "mafia_votes"):
                game.mafia_votes = {}
        except Exception:
            logger.exception("Error clearing mafia_votes")

    # -------------------------
    # INVESTIGACIÓN (helper)
    # -------------------------
    def _get_investigation_result(self, investigator: Player, target: Player) -> str:
        """Determina el resultado de una investigación."""
        target_role = get_role(getattr(target, "role_key", None)) if getattr(target, "role_key", None) else None

        if getattr(investigator, "role_key", None) == "sheriff":
            if target_role and (getattr(target_role, "faction", None) == Faction.MAFIA or getattr(target_role, "key", "") == "asesino"):
                return "CULPABLE"
            return "INOCENTE"

        if getattr(investigator, "role_key", None) == "detective":
            if not target_role:
                return "INOCENTE"
            if getattr(target_role, "undetectable_by_detective", False):
                return "INOCENTE"
            if getattr(target_role, "detective_signature", None):
                return getattr(target_role, "detective_signature")
            return "INOCENTE"

        if getattr(investigator, "role_key", None) == "consigliere":
            if target_role:
                return getattr(target_role, "name", "Desconocido")
            return "Desconocido"

        return "Sin información"

    # -------------------------
    # VOTOS / VICTORIA / OTROS
    # -------------------------
    def resolve_votes(self, game: Game) -> Tuple[Optional[int], List[GameEvent]]:
        """
        Resuelve la votación diurna.
        Retorna (linchado_id, eventos).
        """
        events: List[GameEvent] = []
        if not getattr(game, "day_votes", None):
            return None, events

        vote_counts = Counter(game.day_votes.values())
        if not vote_counts:
            return None, events

        most_voted = vote_counts.most_common()
        max_votes = most_voted[0][1]
        tied = [target for target, votes in most_voted if votes == max_votes]

        if len(tied) > 1:
            events.append(GameEvent(event_type="vote_tie", details={"tied_players": tied}))
            return None, events

        lynched_id = tied[0]
        player = game.players.get(lynched_id)
        if player and getattr(player, "alive", True):
            player.alive = False
            events.append(GameEvent(event_type="lynch", target_id=lynched_id, details={"vote_count": max_votes}))

        return lynched_id, events

    def check_victory(self, game: Game) -> Optional[str]:
        """
        Verifica condiciones de victoria.
        Retorna: "town", "mafia", "serial", "jester", None
        """
        # Obtener jugadores vivos de forma segura
        if hasattr(game, "get_alive_players"):
            alive_players = game.get_alive_players()
        else:
            alive_players = [p for p in game.players.values() if getattr(p, "alive", True)]

        if not alive_players:
            return None

        # Contar por facción de forma segura
        if hasattr(game, "get_players_by_faction"):
            mafia_alive = game.get_players_by_faction(Faction.MAFIA)
            town_alive = game.get_players_by_faction(Faction.TOWN)
        else:
            mafia_alive = []
            town_alive = []
            for p in alive_players:
                role_key = getattr(p, "role_key", None)
                if role_key:
                    role = get_role(role_key)
                    if role:
                        faction = getattr(role, "faction", None)
                        if faction == Faction.MAFIA:
                            mafia_alive.append(p)
                        elif faction == Faction.TOWN:
                            town_alive.append(p)

        # Contar asesinos en serie
        serial_alive = [p for p in alive_players if getattr(p, "role_key", None) == "asesino"]

        # Verificar condiciones de victoria
        if serial_alive and len(alive_players) == 1:
            return "serial"
        if mafia_alive and len(mafia_alive) >= len(town_alive):
            return "mafia"
        if not mafia_alive and not serial_alive:
            return "town"
        return None
