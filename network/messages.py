"""
network/messages.py
Typed message creators for specific game actions.
"""
from typing import Dict, Any, Optional, List
from .protocol import Message, MessageType
import time


def create_message(msg_type: MessageType, data: Dict[str, Any]) -> Message:
    """Create a message with timestamp."""
    return Message(
        type=msg_type,
        data=data,
        timestamp=time.time()
    )


# ==================== Client -> Server Messages ====================

def ConnectMessage(player_name: str, token: Optional[str] = None, version: str = "1.0") -> Message:
    """Client connecting to server."""
    return create_message(MessageType.CONNECT, {
        'player_name': player_name,
        'token': token,
        'version': version
    })


def CreateGameMessage(
    host_name: str,
    roles_config: Optional[Dict[str, int]] = None,
    night_seconds: int = 300,
    day_seconds: int = 600
) -> Message:
    """Create a new game."""
    return create_message(MessageType.CREATE_GAME, {
        'host_name': host_name,
        'roles_config': roles_config or {'mafia': 1, 'ciudadano': 3},
        'night_seconds': night_seconds,
        'day_seconds': day_seconds
    })


def JoinGameMessage(game_id: int, player_name: str) -> Message:
    """Join an existing game."""
    return create_message(MessageType.JOIN_GAME, {
        'game_id': game_id,
        'player_name': player_name
    })


def LeaveGameMessage(game_id: int) -> Message:
    """Leave a game."""
    return create_message(MessageType.LEAVE_GAME, {
        'game_id': game_id
    })


def StartGameMessage(game_id: int) -> Message:
    """Start the game (host only)."""
    return create_message(MessageType.START_GAME, {
        'game_id': game_id
    })


def NightActionMessage(game_id: int, target_id: int) -> Message:
    """Submit a night action."""
    return create_message(MessageType.NIGHT_ACTION, {
        'game_id': game_id,
        'target_id': target_id
    })


def MafiaVoteMessage(game_id: int, target_id: int) -> Message:
    """Submit a mafia vote (mafia members only)."""
    return create_message(MessageType.MAFIA_VOTE, {
        'game_id': game_id,
        'target_id': target_id
    })


def DayVoteMessage(game_id: int, target_id: int) -> Message:
    """Submit a day vote."""
    return create_message(MessageType.DAY_VOTE, {
        'game_id': game_id,
        'target_id': target_id
    })


def ChatMessage(game_id: int, text: str, channel: str = "general") -> Message:
    """Send a chat message."""
    return create_message(MessageType.CHAT_MESSAGE, {
        'game_id': game_id,
        'text': text,
        'channel': channel
    })


def ResolveNightMessage(game_id: int) -> Message:
    """Resolve the night phase (admin/auto)."""
    return create_message(MessageType.RESOLVE_NIGHT, {
        'game_id': game_id
    })


def StartVotingMessage(game_id: int) -> Message:
    """Start the voting phase (admin/auto)."""
    return create_message(MessageType.START_VOTING, {
        'game_id': game_id
    })


def ResolveVotesMessage(game_id: int) -> Message:
    """Resolve votes (admin/auto)."""
    return create_message(MessageType.RESOLVE_VOTES, {
        'game_id': game_id
    })


def GetGameStateMessage(game_id: int) -> Message:
    """Request current game state."""
    return create_message(MessageType.GET_GAME_STATE, {
        'game_id': game_id
    })


def ListGamesMessage() -> Message:
    """List all available games."""
    return create_message(MessageType.LIST_GAMES, {})


# ==================== Server -> Client Messages ====================

def GameStateUpdateMessage(
    game_id: int,
    phase: str,
    players: List[Dict[str, Any]],
    phase_deadline: Optional[int] = None,
    your_player_id: Optional[int] = None,
    your_role: Optional[str] = None,
    alive_players: Optional[List[int]] = None,
    **extra_data
) -> Message:
    """Broadcast game state update."""
    data = {
        'game_id': game_id,
        'phase': phase,
        'players': players,
        'phase_deadline': phase_deadline,
        'your_player_id': your_player_id,
        'your_role': your_role,
        'alive_players': alive_players
    }
    data.update(extra_data)
    return create_message(MessageType.GAME_STATE_UPDATE, data)


def GameCreatedMessage(game_id: int, host_id: int) -> Message:
    """Game was created."""
    return create_message(MessageType.GAME_CREATED, {
        'game_id': game_id,
        'host_id': host_id
    })


def PlayerJoinedMessage(game_id: int, player_id: int, player_name: str) -> Message:
    """Player joined the game."""
    return create_message(MessageType.PLAYER_JOINED, {
        'game_id': game_id,
        'player_id': player_id,
        'player_name': player_name
    })


def PlayerLeftMessage(game_id: int, player_id: int, player_name: str) -> Message:
    """Player left the game."""
    return create_message(MessageType.PLAYER_LEFT, {
        'game_id': game_id,
        'player_id': player_id,
        'player_name': player_name
    })


def GameStartedMessage(game_id: int, players_count: int) -> Message:
    """Game has started."""
    return create_message(MessageType.GAME_STARTED, {
        'game_id': game_id,
        'players_count': players_count
    })


def PhaseChangedMessage(game_id: int, new_phase: str, phase_deadline: Optional[int] = None) -> Message:
    """Game phase changed."""
    return create_message(MessageType.PHASE_CHANGED, {
        'game_id': game_id,
        'new_phase': new_phase,
        'phase_deadline': phase_deadline
    })


def PlayerDiedMessage(game_id: int, player_id: int, player_name: str, role: str, cause: Optional[str] = None) -> Message:
    """Player died."""
    return create_message(MessageType.PLAYER_DIED, {
        'game_id': game_id,
        'player_id': player_id,
        'player_name': player_name,
        'role': role,
        'cause': cause
    })


def ChatBroadcastMessage(
    game_id: int,
    sender_id: int,
    sender_name: str,
    text: str,
    channel: str = "general"
) -> Message:
    """Broadcast chat message to all players."""
    return create_message(MessageType.CHAT_BROADCAST, {
        'game_id': game_id,
        'sender_id': sender_id,
        'sender_name': sender_name,
        'text': text,
        'channel': channel
    })


def PrivateMessageMessage(text: str) -> Message:
    """Send a private message to a specific player."""
    return create_message(MessageType.PRIVATE_MESSAGE, {
        'text': text
    })


def InvestigationResultMessage(target_name: str, result: str) -> Message:
    """Investigation result (sent privately)."""
    return create_message(MessageType.INVESTIGATION_RESULT, {
        'target_name': target_name,
        'result': result
    })


def GameListMessage(games: List[Dict[str, Any]]) -> Message:
    """List of available games."""
    return create_message(MessageType.GAME_LIST, {
        'games': games
    })


# ==================== Error Messages ====================

def ErrorMessage(error: str, error_code: Optional[str] = None) -> Message:
    """Error message."""
    return create_message(MessageType.ERROR, {
        'error': error,
        'error_code': error_code
    })


def SuccessMessage(message: str = "Success", **extra_data) -> Message:
    """Success message."""
    data = {'message': message}
    data.update(extra_data)
    return create_message(MessageType.SUCCESS, data)


# ==================== Ping/Pong ====================

def PingMessage() -> Message:
    """Ping message for keepalive."""
    return create_message(MessageType.PING, {})


def PongMessage() -> Message:
    """Pong response to ping."""
    return create_message(MessageType.PONG, {})
