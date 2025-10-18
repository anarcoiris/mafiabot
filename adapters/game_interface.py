# adapters/game_interface.py
from abc import ABC, abstractmethod

class GameInterface(ABC):
    """Interfaz abstracta para cualquier frontend del juego."""

    @abstractmethod
    async def send_message(self, recipient_id: int, text: str):
        """Envía un mensaje a un jugador."""
        pass

    @abstractmethod
    async def send_broadcast(self, game_id: int, text: str):
        """Envía un mensaje a todos en el juego."""
        pass

    @abstractmethod
    async def request_action(self, player_id: int, actions: list):
        """Solicita una acción al jugador con opciones."""
        pass

    @abstractmethod
    async def update_game_state(self, game):
        """Notifica cambio de estado del juego."""
        pass
