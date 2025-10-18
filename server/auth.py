"""
server/auth.py
Authentication and token management for the game server.
"""
import jwt
import secrets
import time
from typing import Optional, Dict
from dataclasses import dataclass


@dataclass
class PlayerToken:
    """Represents a player's authentication token."""
    player_id: int
    player_name: str
    issued_at: float
    expires_at: float


class TokenManager:
    """Manages player authentication tokens."""

    def __init__(self, secret_key: Optional[str] = None, token_expiry_seconds: int = 86400):
        """
        Initialize token manager.

        Args:
            secret_key: Secret key for JWT signing. If None, generates a random key.
            token_expiry_seconds: Token expiry time in seconds (default: 24 hours).
        """
        self.secret_key = secret_key or secrets.token_urlsafe(32)
        self.token_expiry_seconds = token_expiry_seconds
        self._tokens: Dict[str, PlayerToken] = {}

    def generate_token(self, player_id: int, player_name: str) -> str:
        """
        Generate a new authentication token for a player.

        Args:
            player_id: Unique player identifier.
            player_name: Player's display name.

        Returns:
            JWT token string.
        """
        now = time.time()
        expires_at = now + self.token_expiry_seconds

        payload = {
            'player_id': player_id,
            'player_name': player_name,
            'iat': now,
            'exp': expires_at
        }

        token = jwt.encode(payload, self.secret_key, algorithm='HS256')

        # Store token info
        self._tokens[token] = PlayerToken(
            player_id=player_id,
            player_name=player_name,
            issued_at=now,
            expires_at=expires_at
        )

        return token

    def verify_token(self, token: str) -> Optional[PlayerToken]:
        """
        Verify and decode a token.

        Args:
            token: JWT token string.

        Returns:
            PlayerToken if valid, None otherwise.
        """
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=['HS256'])

            # Check if token is expired
            if time.time() > payload['exp']:
                # Remove expired token
                self._tokens.pop(token, None)
                return None

            return PlayerToken(
                player_id=payload['player_id'],
                player_name=payload['player_name'],
                issued_at=payload['iat'],
                expires_at=payload['exp']
            )
        except jwt.InvalidTokenError:
            return None

    def revoke_token(self, token: str) -> bool:
        """
        Revoke a token.

        Args:
            token: Token to revoke.

        Returns:
            True if token was revoked, False if not found.
        """
        if token in self._tokens:
            del self._tokens[token]
            return True
        return False

    def cleanup_expired_tokens(self):
        """Remove all expired tokens from storage."""
        now = time.time()
        expired = [
            token for token, info in self._tokens.items()
            if info.expires_at < now
        ]
        for token in expired:
            del self._tokens[token]


class SimpleAuthManager:
    """
    Simplified authentication for initial implementation.
    Just validates player names without tokens.
    """

    def __init__(self):
        self._player_counter = 0
        self._connected_players: Dict[int, str] = {}

    def register_player(self, player_name: str) -> int:
        """
        Register a new player and assign an ID.

        Args:
            player_name: Player's display name.

        Returns:
            Assigned player ID.
        """
        self._player_counter += 1
        player_id = self._player_counter
        self._connected_players[player_id] = player_name
        return player_id

    def unregister_player(self, player_id: int) -> bool:
        """
        Unregister a player.

        Args:
            player_id: Player's ID.

        Returns:
            True if player was unregistered, False if not found.
        """
        if player_id in self._connected_players:
            del self._connected_players[player_id]
            return True
        return False

    def get_player_name(self, player_id: int) -> Optional[str]:
        """Get player name by ID."""
        return self._connected_players.get(player_id)

    def is_player_registered(self, player_id: int) -> bool:
        """Check if a player is registered."""
        return player_id in self._connected_players
