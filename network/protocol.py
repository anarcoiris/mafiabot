"""
network/protocol.py
Network protocol definitions for Mafia Bot server-client communication.
"""
import json
import uuid
from enum import Enum
from typing import Dict, Any, Optional
from dataclasses import dataclass, field, asdict


class MessageType(Enum):
    """Types of messages exchanged between client and server."""
    # Client -> Server
    CONNECT = "connect"
    DISCONNECT = "disconnect"
    CREATE_GAME = "create_game"
    JOIN_GAME = "join_game"
    LEAVE_GAME = "leave_game"
    START_GAME = "start_game"
    NIGHT_ACTION = "night_action"
    MAFIA_VOTE = "mafia_vote"
    DAY_VOTE = "day_vote"
    CHAT_MESSAGE = "chat_message"
    RESOLVE_NIGHT = "resolve_night"
    START_VOTING = "start_voting"
    RESOLVE_VOTES = "resolve_votes"
    GET_GAME_STATE = "get_game_state"
    LIST_GAMES = "list_games"

    # Server -> Client
    GAME_STATE_UPDATE = "game_state_update"
    GAME_CREATED = "game_created"
    PLAYER_JOINED = "player_joined"
    PLAYER_LEFT = "player_left"
    GAME_STARTED = "game_started"
    PHASE_CHANGED = "phase_changed"
    PLAYER_DIED = "player_died"
    CHAT_BROADCAST = "chat_broadcast"
    PRIVATE_MESSAGE = "private_message"
    INVESTIGATION_RESULT = "investigation_result"
    GAME_LIST = "game_list"

    # Bidirectional
    PING = "ping"
    PONG = "pong"
    ERROR = "error"
    SUCCESS = "success"


@dataclass
class Message:
    """Base message structure for all network communication."""
    type: MessageType
    data: Dict[str, Any] = field(default_factory=dict)
    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    reply_to: Optional[str] = None
    timestamp: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert message to dictionary for JSON serialization."""
        return {
            'type': self.type.value,
            'data': self.data,
            'message_id': self.message_id,
            'reply_to': self.reply_to,
            'timestamp': self.timestamp
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Message':
        """Create message from dictionary."""
        return cls(
            type=MessageType(data['type']),
            data=data.get('data', {}),
            message_id=data.get('message_id', str(uuid.uuid4())),
            reply_to=data.get('reply_to'),
            timestamp=data.get('timestamp')
        )


def serialize_message(message: Message) -> str:
    """Serialize a message to JSON string."""
    return json.dumps(message.to_dict())


def deserialize_message(json_str: str) -> Message:
    """Deserialize a JSON string to a Message object."""
    try:
        data = json.loads(json_str)
        return Message.from_dict(data)
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        raise ValueError(f"Invalid message format: {e}")


def create_response(original_message: Message, response_type: MessageType, data: Dict[str, Any]) -> Message:
    """Create a response message to an original message."""
    return Message(
        type=response_type,
        data=data,
        reply_to=original_message.message_id
    )


def create_error_response(original_message: Message, error_message: str, error_code: Optional[str] = None) -> Message:
    """Create an error response message."""
    return create_response(
        original_message,
        MessageType.ERROR,
        {
            'error': error_message,
            'error_code': error_code
        }
    )


def create_success_response(original_message: Message, data: Optional[Dict[str, Any]] = None) -> Message:
    """Create a success response message."""
    return create_response(
        original_message,
        MessageType.SUCCESS,
        data or {}
    )
