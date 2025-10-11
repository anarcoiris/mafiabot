"""
core/engine.py
Lógica pura del juego de Mafia.
Sin dependencias de Telegram ni persistencia.
"""
import random
import logging
from typing import List, Dict, Optional, Tuple
from collections import Counter

from .models import Game, Player, NightAction, Phase, Faction, GameEvent
from .roles import ROLES, get_role

logger = logging.getLogger(__name__)


class GameEngine:
    """Motor del juego que maneja toda la lógica."""
    
    @staticmethod
    def assign_roles(game: Game) -> List[str]:
        """
        Asigna roles aleatorios a los jugadores según la configuración.
        Retorna lista de mensajes de error si algo falla.
        """
        errors = []
        
        if len(game.players) < 4:
            errors.append("Se necesitan al menos 4 jugadores para empezar.")
            return errors
        
        # Construir pool de roles
        role_pool: List[str] = []
        for role_key, count in game.roles_config.items():
            if role_key not in ROLES:
                errors.append(f"Rol desconocido: {role_key}")
                continue
            role_pool.extend([role_key] * int(count))
        
        # Rellenar con ciudadanos si faltan roles
        while len(role_pool) < len(game.players):
            role_pool.append("ciudadano")
        
        # Recortar si sobran roles
        if len(role_pool) > len(game.players):
            role_pool = role_pool[:len(game.players)]
        
        # Asignar aleatoriamente
        random.shuffle(role_pool)
        player_ids = list(game.players.keys())
        random.shuffle(player_ids)
        
        for player_id, role_key in zip(player_ids, role_pool):
            game.players[player_id].role_key = role_key
            logger.info(f"Assigned {role_key} to player {player_id}")
        
        return errors
    
    @staticmethod
    def resolve_night(game: Game) -> List[GameEvent]:
        """
        Resuelve todas las acciones nocturnas.
        Retorna lista de eventos ocurridos.
        """
        events: List[GameEvent] = []
        
        # Ordenar acciones por prioridad
        actions_sorted = sorted(game.night_actions, key=lambda a: a.priority)
        
        # Aplicar bloqueos primero
        blocked_players = set()
        for action in [a for a in actions_sorted if a.action_type == "block"]:
            actor = game.players.get(action.actor_id)
            if not actor or not actor.alive or actor.blocked:
                continue
            
            target = game.players.get(action.target_id)
            if target and target.alive:
                target.blocked = True
                blocked_players.add(action.target_id)
                events.append(GameEvent(
                    event_type="block",
                    actor_id=action.actor_id,
                    target_id=action.target_id
                ))
        
        # Protecciones (doctor, guardaespaldas)
        healed_players = set()
        guarded_players: Dict[int, int] = {}  # target_id -> guard_id
        
        for action in [a for a in actions_sorted if a.action_type == "heal"]:
            actor = game.players.get(action.actor_id)
            if not actor or not actor.alive or actor.blocked:
                continue
            
            target = game.players.get(action.target_id)
            if target and target.alive:
                healed_players.add(action.target_id)
                events.append(GameEvent(
                    event_type="heal",
                    actor_id=action.actor_id,
                    target_id=action.target_id
                ))
        
        for action in [a for a in actions_sorted if a.action_type == "guard"]:
            actor = game.players.get(action.actor_id)
            if not actor or not actor.alive or actor.blocked:
                continue
            
            target = game.players.get(action.target_id)
            if target and target.alive:
                guarded_players[action.target_id] = action.actor_id
                events.append(GameEvent(
                    event_type="guard",
                    actor_id=action.actor_id,
                    target_id=action.target_id
                ))
        
        # Resolver ataques (mafia, vigilante, serial killer)
        deaths = []
        
        # Ataque de la mafia (usar mafia_votes para determinar objetivo)
        if game.mafia_votes:
            target_counts = Counter(game.mafia_votes.values())
            if target_counts:
                mafia_target, _ = target_counts.most_common(1)[0]
                
                # Encontrar un mafioso vivo no bloqueado para ejecutar
                mafia_attacker = None
                for player in game.players.values():
                    if (player.alive and player.role_key 
                        and get_role(player.role_key).faction == Faction.MAFIA
                        and not player.blocked):
                        mafia_attacker = player.user_id
                        break
                
                if mafia_attacker:
                    action = NightAction(
                        actor_id=mafia_attacker,
                        target_id=mafia_target,
                        action_type="mafia_kill",
                        priority=5
                    )
                    actions_sorted.append(action)
        
        # Procesar todos los ataques
        for action in [a for a in actions_sorted if a.action_type in 
                      ("mafia_kill", "vigilante_kill", "serial_kill")]:
            actor = game.players.get(action.actor_id)
            target = game.players.get(action.target_id)
            
            if not actor or not actor.alive or actor.blocked:
                continue
            
            if not target or not target.alive:
                continue
            
            # Padrino es inmune a ataques nocturnos
            if target.role_key == "padrino":
                events.append(GameEvent(
                    event_type="attack_failed",
                    actor_id=action.actor_id,
                    target_id=action.target_id,
                    details={"reason": "padrino_immunity"}
                ))
                continue
            
            # Serial killer es inmune
            if target.role_key == "asesino":
                events.append(GameEvent(
                    event_type="attack_failed",
                    actor_id=action.actor_id,
                    target_id=action.target_id,
                    details={"reason": "serial_immunity"}
                ))
                continue
            
            # Check si fue curado
            if action.target_id in healed_players:
                events.append(GameEvent(
                    event_type="saved_by_heal",
                    actor_id=action.actor_id,
                    target_id=action.target_id
                ))
                continue
            
            # Check si tiene guardaespaldas
            if action.target_id in guarded_players:
                guard_id = guarded_players[action.target_id]
                guard = game.players[guard_id]
                guard.alive = False
                deaths.append(guard_id)
                events.append(GameEvent(
                    event_type="bodyguard_death",
                    actor_id=guard_id,
                    target_id=action.target_id
                ))
                continue
            
            # El ataque tiene éxito
            target.alive = False
            deaths.append(action.target_id)
            events.append(GameEvent(
                event_type="death",
                actor_id=action.actor_id,
                target_id=action.target_id,
                details={"cause": action.action_type}
            ))
        
        # Chantaje/silenciado
        for action in [a for a in actions_sorted if a.action_type == "blackmail"]:
            actor = game.players.get(action.actor_id)
            if not actor or not actor.alive or actor.blocked:
                continue
            
            target = game.players.get(action.target_id)
            if target and target.alive:
                target.silenced = True
                events.append(GameEvent(
                    event_type="blackmail",
                    actor_id=action.actor_id,
                    target_id=action.target_id
                ))
        
        # Investigaciones (no matan, solo info)
        for action in [a for a in actions_sorted if a.action_type == "investigate"]:
            actor = game.players.get(action.actor_id)
            if not actor or not actor.alive or actor.blocked:
                continue
            
            target = game.players.get(action.target_id)
            if not target or not target.alive:
                continue
            
            # Determinar resultado según el rol del investigador
            result = GameEngine._get_investigation_result(actor, target)
            events.append(GameEvent(
                event_type="investigation",
                actor_id=action.actor_id,
                target_id=action.target_id,
                details={"result": result, "investigator_role": actor.role_key}
            ))
        
        logger.info(f"Night resolved for game {game.chat_id}: {len(deaths)} deaths, {len(events)} total events")
        return events
    
    @staticmethod
    def _get_investigation_result(investigator: Player, target: Player) -> str:
        """Determina el resultado de una investigación."""
        target_role = get_role(target.role_key) if target.role_key else None
        
        if investigator.role_key == "sheriff":
            # Sheriff detecta mafia y serial killer
            if target_role and (target_role.faction == Faction.MAFIA 
                               or target_role.key == "asesino"):
                return "CULPABLE"
            return "INOCENTE"
        
        elif investigator.role_key == "detective":
            # Detective obtiene pistas más detalladas
            if not target_role:
                return "INOCENTE"
            if target_role.undetectable_by_detective:
                return "INOCENTE"
            if target_role.detective_signature:
                return target_role.detective_signature
            return "INOCENTE"
        
        elif investigator.role_key == "consigliere":
            # Consigliere (mafia) ve el rol exacto
            if target_role:
                return target_role.name
            return "Desconocido"
        
        return "Sin información"
    
    @staticmethod
    def resolve_votes(game: Game) -> Tuple[Optional[int], List[GameEvent]]:
        """
        Resuelve la votación diurna.
        Retorna (linchado_id, eventos).
        """
        events = []
        
        if not game.day_votes:
            return None, events
        
        # Contar votos
        vote_counts = Counter(game.day_votes.values())
        
        if not vote_counts:
            return None, events
        
        # Obtener el más votado
        most_voted = vote_counts.most_common()
        max_votes = most_voted[0][1]
        
        # Check empate
        tied = [target for target, votes in most_voted if votes == max_votes]
        
        if len(tied) > 1:
            events.append(GameEvent(
                event_type="vote_tie",
                details={"tied_players": tied}
            ))
            return None, events
        
        # Linchar al más votado
        lynched_id = tied[0]
        player = game.players.get(lynched_id)
        
        if player and player.alive:
            player.alive = False
            events.append(GameEvent(
                event_type="lynch",
                target_id=lynched_id,
                details={"vote_count": max_votes}
            ))
        
        return lynched_id, events
    
    @staticmethod
    def check_victory(game: Game) -> Optional[str]:
        """
        Verifica condiciones de victoria.
        Retorna: "town", "mafia", "serial", "jester", None
        """
        alive_players = game.get_alive_players()
        
        if not alive_players:
            return None
        
        mafia_alive = game.get_players_by_faction(Faction.MAFIA)
        town_alive = game.get_players_by_faction(Faction.TOWN)
        serial_alive = [p for p in alive_players if p.role_key == "asesino"]
        
        # Serial killer gana si es el único vivo
        if serial_alive and len(alive_players) == 1:
            return "serial"
        
        # Mafia gana si iguala o supera a town
        if mafia_alive and len(mafia_alive) >= len(town_alive):
            return "mafia"
        
        # Town gana si no hay mafia ni serial killer
        if not mafia_alive and not serial_alive:
            return "town"
        
        return None