"""
gui/views/connection_view.py
Connection dialog for connecting to multiplayer server.
"""
import tkinter as tk
from tkinter import ttk, messagebox
import asyncio
import logging
import json
from pathlib import Path

from gui.network.client import GameClient, ConnectionState
from gui.widgets.connection_status import ConnectionStatusWidget

logger = logging.getLogger(__name__)


class ConnectionDialog:
    """
    Dialog for connecting to Mafia multiplayer server.

    Features:
    - Server address input
    - Player name input
    - Recent servers list
    - Connection status
    - Quick connect to localhost
    """

    def __init__(self, parent, on_connected=None):
        """
        Initialize connection dialog.

        Args:
            parent: Parent window
            on_connected: Callback when successfully connected (receives GameClient)
        """
        self.parent = parent
        self.on_connected = on_connected
        self.client: GameClient = None

        # Recent servers (load from config)
        self.recent_servers = self._load_recent_servers()

        # Create dialog window
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("Conectar al Servidor")
        self.dialog.geometry("450x400")
        self.dialog.resizable(False, False)
        self.dialog.transient(parent)
        self.dialog.grab_set()

        # Center dialog
        self._center_dialog()

        # Create UI
        self._create_widgets()

        # Protocol handler for window close
        self.dialog.protocol("WM_DELETE_WINDOW", self._on_cancel)

    def _center_dialog(self):
        """Center dialog on parent window."""
        self.dialog.update_idletasks()

        # Get parent position
        parent_x = self.parent.winfo_x()
        parent_y = self.parent.winfo_y()
        parent_width = self.parent.winfo_width()
        parent_height = self.parent.winfo_height()

        # Calculate center position
        dialog_width = self.dialog.winfo_width()
        dialog_height = self.dialog.winfo_height()

        x = parent_x + (parent_width - dialog_width) // 2
        y = parent_y + (parent_height - dialog_height) // 2

        self.dialog.geometry(f"+{x}+{y}")

    def _create_widgets(self):
        """Create dialog widgets."""
        # Main container
        main_frame = ttk.Frame(self.dialog, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Title
        title_label = ttk.Label(
            main_frame,
            text="🌐 Conectar al Servidor Multiplayer",
            font=('Arial', 12, 'bold')
        )
        title_label.pack(pady=(0, 20))

        # Server address
        server_frame = ttk.LabelFrame(main_frame, text="Servidor", padding="10")
        server_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(server_frame, text="Dirección:").pack(anchor=tk.W)
        self.server_entry = ttk.Entry(server_frame, width=40)
        self.server_entry.pack(fill=tk.X, pady=(5, 0))
        self.server_entry.insert(0, "ws://localhost:8765")

        # Player name
        player_frame = ttk.LabelFrame(main_frame, text="Jugador", padding="10")
        player_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(player_frame, text="Nombre:").pack(anchor=tk.W)
        self.name_entry = ttk.Entry(player_frame, width=40)
        self.name_entry.pack(fill=tk.X, pady=(5, 0))
        self.name_entry.insert(0, "Jugador")
        self.name_entry.select_range(0, tk.END)
        self.name_entry.focus()

        # Recent servers
        recent_frame = ttk.LabelFrame(main_frame, text="Servidores Recientes", padding="10")
        recent_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        # Listbox with scrollbar
        list_frame = ttk.Frame(recent_frame)
        list_frame.pack(fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.recent_listbox = tk.Listbox(
            list_frame,
            height=5,
            yscrollcommand=scrollbar.set
        )
        self.recent_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.recent_listbox.yview)

        # Populate recent servers
        for server in self.recent_servers:
            self.recent_listbox.insert(tk.END, server)

        # Double-click to select
        self.recent_listbox.bind('<Double-Button-1>', self._on_recent_selected)

        # Connection status
        status_frame = ttk.Frame(main_frame)
        status_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(status_frame, text="Estado:").pack(side=tk.LEFT)
        self.status_widget = ConnectionStatusWidget(status_frame)
        self.status_widget.pack(side=tk.LEFT, padx=(10, 0))

        # Buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X)

        self.connect_button = ttk.Button(
            button_frame,
            text="Conectar",
            command=self._on_connect,
            width=15
        )
        self.connect_button.pack(side=tk.LEFT, padx=(0, 5))

        self.quick_local_button = ttk.Button(
            button_frame,
            text="Local Rápido",
            command=self._on_quick_local,
            width=15
        )
        self.quick_local_button.pack(side=tk.LEFT, padx=(0, 5))

        self.cancel_button = ttk.Button(
            button_frame,
            text="Cancelar",
            command=self._on_cancel,
            width=15
        )
        self.cancel_button.pack(side=tk.RIGHT)

        # Enter key binds to connect
        self.server_entry.bind('<Return>', lambda e: self._on_connect())
        self.name_entry.bind('<Return>', lambda e: self._on_connect())

    def _on_recent_selected(self, event):
        """Handle selection from recent servers list."""
        selection = self.recent_listbox.curselection()
        if selection:
            server = self.recent_listbox.get(selection[0])
            self.server_entry.delete(0, tk.END)
            self.server_entry.insert(0, server)

    def _on_quick_local(self):
        """Quick connect to localhost."""
        self.server_entry.delete(0, tk.END)
        self.server_entry.insert(0, "ws://localhost:8765")
        self._on_connect()

    def _on_connect(self):
        """Handle connect button click."""
        server_uri = self.server_entry.get().strip()
        player_name = self.name_entry.get().strip()

        if not server_uri:
            messagebox.showerror("Error", "Por favor ingresa la dirección del servidor")
            return

        if not player_name:
            messagebox.showerror("Error", "Por favor ingresa tu nombre")
            return

        # Validate URI format
        if not server_uri.startswith(('ws://', 'wss://')):
            server_uri = 'ws://' + server_uri

        # Disable buttons during connection
        self.connect_button.config(state='disabled', text='Conectando...')
        self.quick_local_button.config(state='disabled')

        # Update status
        self.status_widget.set_status('connecting', server_uri)

        # Create client and connect
        self.client = GameClient(server_uri)
        self.client.on_state_change = self._on_connection_state_changed

        # Connect asynchronously
        asyncio.create_task(self._connect_async(server_uri, player_name))

    async def _connect_async(self, server_uri: str, player_name: str):
        """Async connection handler."""
        try:
            success = await self.client.connect(player_name, auto_reconnect=True)

            if success:
                # Add to recent servers
                self._add_recent_server(server_uri)
                self._save_recent_servers()

                # Update status
                self.status_widget.set_status('connected', server_uri)
                self.status_widget.set_player_info(
                    self.client.player_id,
                    self.client.player_name
                )

                # Close dialog and notify
                self.dialog.after(500, self._on_success)
            else:
                # Connection failed
                self.status_widget.set_status('error', server_uri)
                messagebox.showerror(
                    "Error de Conexión",
                    "No se pudo conectar al servidor.\nVerifica la dirección y que el servidor esté activo."
                )
                self._reset_buttons()

        except Exception as e:
            logger.exception(f"Connection error: {e}")
            self.status_widget.set_status('error', server_uri)
            messagebox.showerror(
                "Error",
                f"Error al conectar:\n{str(e)}"
            )
            self._reset_buttons()

    def _on_connection_state_changed(self, new_state: ConnectionState):
        """Handle connection state changes."""
        logger.info(f"Connection state: {new_state.value}")

    def _on_success(self):
        """Handle successful connection."""
        if self.on_connected and self.client:
            self.on_connected(self.client)

        self.dialog.destroy()

    def _on_cancel(self):
        """Handle cancel button click."""
        if self.client:
            asyncio.create_task(self.client.disconnect())

        self.dialog.destroy()

    def _reset_buttons(self):
        """Re-enable buttons after failed connection."""
        self.connect_button.config(state='normal', text='Conectar')
        self.quick_local_button.config(state='normal')

    def _add_recent_server(self, server_uri: str):
        """Add server to recent list."""
        # Remove if already in list
        if server_uri in self.recent_servers:
            self.recent_servers.remove(server_uri)

        # Add to beginning
        self.recent_servers.insert(0, server_uri)

        # Keep only last 10
        self.recent_servers = self.recent_servers[:10]

    def _load_recent_servers(self) -> list:
        """Load recent servers from config file."""
        config_file = Path.home() / '.mafiabot' / 'recent_servers.json'

        if config_file.exists():
            try:
                with open(config_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load recent servers: {e}")

        return ['ws://localhost:8765']

    def _save_recent_servers(self):
        """Save recent servers to config file."""
        config_dir = Path.home() / '.mafiabot'
        config_dir.mkdir(exist_ok=True)

        config_file = config_dir / 'recent_servers.json'

        try:
            with open(config_file, 'w') as f:
                json.dump(self.recent_servers, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save recent servers: {e}")
