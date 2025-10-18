"""
gui/network/state_sync.py
State synchronization between client and server.
"""
import logging
from typing import Dict, Any, Optional, Callable
from dataclasses import dataclass
import time

from core.models import Game, Player, Phase

logger = logging.getLogger(__name__)


@dataclass
class StateSnapshot:
    """Snapshot of game state at a point in time."""
    game_id: int
    phase: Phase
    players: Dict[int, Player]
    timestamp: float
    version: int = 0  # Increment on each update


class StateSynchronizer:
    """
    Manages synchronization of game state between client and server.

    The server is the source of truth. This class:
    - Maintains local copy of server state
    - Handles optimistic updates (apply locally, wait for server confirm)
    - Detects conflicts and resolves them
    - Triggers UI updates on state changes
    """

    def __init__(self):
        self.current_state: Optional[Game] = None
        self.state_version = 0
        self.pending_actions: Dict[str, Any] = {}  # action_id -> action_data

        # Callbacks
        self.on_state_updated: Optional[Callable[[Game], None]] = None
        self.on_conflict_detected: Optional[Callable[[str], None]] = None

        # Stats
        self._updates_received = 0
        self._conflicts_resolved = 0

    def apply_server_update(self, state_data: Dict[str, Any]) -> bool:
        """
        Apply a game state update from server.

        Args:
            state_data: Raw state data from server

        Returns:
            True if state was updated, False otherwise
        """
        try:
            game_id = state_data.get('game_id')
            if not game_id:
                logger.warning("State update missing game_id")
                return False

            # Parse phase
            phase_str = state_data.get('phase', 'lobby')
            try:
                phase = Phase(phase_str)
            except ValueError:
                logger.warning(f"Unknown phase: {phase_str}")
                phase = Phase.LOBBY

            # Parse players
            players_data = state_data.get('players', [])
            players = {}

            for p_data in players_data:
                player_id = p_data.get('player_id')
                if not player_id:
                    continue

                # Create Player object
                player = Player(
                    user_id=player_id,
                    name=p_data.get('name', f"Player{player_id}"),
                    role_key=p_data.get('role'),
                    alive=p_data.get('alive', True)
                )
                players[player_id] = player

            # Create or update Game object
            if self.current_state and self.current_state.chat_id == game_id:
                # Update existing game
                game = self.current_state
                game.phase = phase
                game.players = players
                game.phase_deadline = state_data.get('phase_deadline')

                # Update other fields if present
                if 'night_actions' in state_data:
                    game.night_actions = state_data['night_actions']
                if 'day_votes' in state_data:
                    game.day_votes = state_data['day_votes']
                if 'mafia_votes' in state_data:
                    game.mafia_votes = state_data['mafia_votes']

            else:
                # Create new game
                game = Game(
                    chat_id=game_id,
                    host_id=state_data.get('host_id', 1),
                    phase=phase,
                    players=players
                )
                game.phase_deadline = state_data.get('phase_deadline')

            # Update state
            self.current_state = game
            self.state_version += 1
            self._updates_received += 1

            logger.info(
                f"State updated: game={game_id}, phase={phase.value}, "
                f"players={len(players)}, version={self.state_version}"
            )

            # Notify callback
            if self.on_state_updated:
                try:
                    self.on_state_updated(game)
                except Exception as e:
                    logger.exception(f"Error in state update callback: {e}")

            return True

        except Exception as e:
            logger.exception(f"Error applying server update: {e}")
            return False

    def apply_optimistic_update(self, action_id: str, update_fn: Callable[[Game], None]) -> bool:
        """
        Apply an optimistic update locally before server confirms.

        Args:
            action_id: Unique identifier for this action
            update_fn: Function to apply the update to local state

        Returns:
            True if applied, False otherwise
        """
        if not self.current_state:
            logger.warning("Cannot apply optimistic update: no current state")
            return False

        try:
            # Apply update locally
            update_fn(self.current_state)

            # Track pending action
            self.pending_actions[action_id] = {
                'timestamp': time.time(),
                'version_applied': self.state_version
            }

            logger.debug(f"Applied optimistic update: {action_id}")

            # Notify UI
            if self.on_state_updated:
                self.on_state_updated(self.current_state)

            return True

        except Exception as e:
            logger.exception(f"Error applying optimistic update: {e}")
            return False

    def confirm_action(self, action_id: str):
        """
        Mark an action as confirmed by server.

        Args:
            action_id: ID of the action that was confirmed
        """
        if action_id in self.pending_actions:
            logger.debug(f"Action confirmed by server: {action_id}")
            del self.pending_actions[action_id]

    def rollback_action(self, action_id: str, reason: str = "Server rejected"):
        """
        Rollback an optimistic update that was rejected.

        Args:
            action_id: ID of the action to rollback
            reason: Reason for rollback
        """
        if action_id in self.pending_actions:
            logger.warning(f"Rolling back action {action_id}: {reason}")
            del self.pending_actions[action_id]
            self._conflicts_resolved += 1

            # Notify about conflict
            if self.on_conflict_detected:
                self.on_conflict_detected(reason)

            # In a real implementation, we would restore previous state
            # For now, we rely on the next server update to fix it

    def get_snapshot(self) -> Optional[StateSnapshot]:
        """
        Get a snapshot of current state.

        Returns:
            StateSnapshot if state exists, None otherwise
        """
        if not self.current_state:
            return None

        return StateSnapshot(
            game_id=self.current_state.chat_id,
            phase=self.current_state.phase,
            players=self.current_state.players.copy(),
            timestamp=time.time(),
            version=self.state_version
        )

    def clear(self):
        """Clear all state."""
        self.current_state = None
        self.state_version = 0
        self.pending_actions.clear()
        logger.info("State cleared")

    @property
    def has_state(self) -> bool:
        """Check if we have a current state."""
        return self.current_state is not None

    @property
    def game_id(self) -> Optional[int]:
        """Get current game ID."""
        return self.current_state.chat_id if self.current_state else None

    @property
    def phase(self) -> Optional[Phase]:
        """Get current phase."""
        return self.current_state.phase if self.current_state else None

    @property
    def stats(self) -> Dict[str, Any]:
        """Get synchronization statistics."""
        return {
            'has_state': self.has_state,
            'game_id': self.game_id,
            'phase': self.phase.value if self.phase else None,
            'state_version': self.state_version,
            'pending_actions': len(self.pending_actions),
            'updates_received': self._updates_received,
            'conflicts_resolved': self._conflicts_resolved
        }
