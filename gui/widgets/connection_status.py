"""
gui/widgets/connection_status.py
Widget to display connection status.
"""
import tkinter as tk
from tkinter import ttk
import logging

logger = logging.getLogger(__name__)


class ConnectionStatusWidget(ttk.Frame):
    """Widget showing connection status with colored indicator."""

    STATUS_COLORS = {
        'connected': '#4aff4a',      # Green
        'connecting': '#ffaa4a',     # Orange
        'reconnecting': '#ffaa4a',   # Orange
        'disconnected': '#666666',   # Gray
        'error': '#ff4a4a'           # Red
    }

    STATUS_TEXT = {
        'connected': '● Conectado',
        'connecting': '● Conectando...',
        'reconnecting': '● Reconectando...',
        'disconnected': '● Desconectado',
        'error': '● Error de conexión'
    }

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)

        self._current_status = 'disconnected'
        self._server_uri = None

        # Create UI
        self._create_widgets()

    def _create_widgets(self):
        """Create widget components."""
        # Status indicator (colored circle)
        self.status_canvas = tk.Canvas(
            self,
            width=12,
            height=12,
            highlightthickness=0,
            bg=self['background'] if 'background' in self.keys() else 'white'
        )
        self.status_canvas.pack(side=tk.LEFT, padx=(0, 5))

        self.status_circle = self.status_canvas.create_oval(
            2, 2, 10, 10,
            fill=self.STATUS_COLORS['disconnected'],
            outline=''
        )

        # Status label
        self.status_label = ttk.Label(
            self,
            text=self.STATUS_TEXT['disconnected'],
            font=('Arial', 9)
        )
        self.status_label.pack(side=tk.LEFT)

        # Server info label (optional)
        self.server_label = ttk.Label(
            self,
            text='',
            font=('Arial', 8),
            foreground='#888888'
        )
        self.server_label.pack(side=tk.LEFT, padx=(10, 0))

    def set_status(self, status: str, server_uri: str = None):
        """
        Update connection status.

        Args:
            status: One of 'connected', 'connecting', 'reconnecting', 'disconnected', 'error'
            server_uri: Optional server URI to display
        """
        if status not in self.STATUS_COLORS:
            logger.warning(f"Unknown status: {status}")
            status = 'disconnected'

        self._current_status = status
        self._server_uri = server_uri

        # Update indicator color
        color = self.STATUS_COLORS[status]
        self.status_canvas.itemconfig(self.status_circle, fill=color)

        # Update status text
        text = self.STATUS_TEXT[status]
        self.status_label.config(text=text)

        # Update server info
        if server_uri:
            # Shorten URI for display
            display_uri = server_uri.replace('ws://', '').replace('wss://', '')
            if len(display_uri) > 30:
                display_uri = display_uri[:27] + '...'
            self.server_label.config(text=f'({display_uri})')
        else:
            self.server_label.config(text='')

        logger.debug(f"Status updated: {status}")

    def set_player_info(self, player_id: int, player_name: str):
        """
        Display player information.

        Args:
            player_id: Player's ID
            player_name: Player's name
        """
        info_text = f"| Jugador: {player_name} (ID: {player_id})"
        self.server_label.config(text=self.server_label['text'] + ' ' + info_text)

    def clear(self):
        """Clear all status information."""
        self.set_status('disconnected')
        self._server_uri = None

    @property
    def current_status(self) -> str:
        """Get current status."""
        return self._current_status


class NetworkIndicator(ttk.Frame):
    """
    Network activity indicator showing sent/received message stats.
    """

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)

        self._messages_sent = 0
        self._messages_received = 0

        self._create_widgets()

    def _create_widgets(self):
        """Create widget components."""
        # Sent indicator
        self.sent_label = ttk.Label(
            self,
            text="↑ 0",
            font=('Arial', 8),
            foreground='#4a9eff'
        )
        self.sent_label.pack(side=tk.LEFT, padx=2)

        # Received indicator
        self.received_label = ttk.Label(
            self,
            text="↓ 0",
            font=('Arial', 8),
            foreground='#4aff4a'
        )
        self.received_label.pack(side=tk.LEFT, padx=2)

    def update_stats(self, sent: int, received: int):
        """
        Update message statistics.

        Args:
            sent: Number of messages sent
            received: Number of messages received
        """
        self._messages_sent = sent
        self._messages_received = received

        self.sent_label.config(text=f"↑ {sent}")
        self.received_label.config(text=f"↓ {received}")

    def increment_sent(self):
        """Increment sent counter."""
        self._messages_sent += 1
        self.sent_label.config(text=f"↑ {self._messages_sent}")

    def increment_received(self):
        """Increment received counter."""
        self._messages_received += 1
        self.received_label.config(text=f"↓ {self._messages_received}")

    def reset(self):
        """Reset counters."""
        self.update_stats(0, 0)
