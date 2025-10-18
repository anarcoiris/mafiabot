"""
gui/widgets/chat_widget.py - CORREGIDO
Widget de chat con colores apropiados y sin duplicados
"""
from __future__ import annotations

import time
import datetime
import logging
from typing import Optional, List, Callable
import tkinter as tk
from tkinter import ttk
from tkinter import scrolledtext

from core.models import ChatMessage

logger = logging.getLogger(__name__)


class ChatWidget(ttk.Frame):
    """Widget de chat embebible con colores corregidos."""

    def __init__(
        self,
        parent,
        player_id: int = 1,
        on_send_message: Optional[Callable[[int, str, str], Optional[bool]]] = None,
        initial_channels: Optional[List[str]] = None,
        height: int = 12,
    ):
        super().__init__(parent)
        self.player_id = player_id
        self.on_send_message = on_send_message
        self.channels = initial_channels or ["general"]
        self._message_ids = set()  # Para evitar duplicados

        # Layout
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        # Área de mensajes con colores EXPLÍCITOS
        self._text = scrolledtext.ScrolledText(
            self, 
            wrap=tk.WORD, 
            height=height,
            bg='#1e1e1e',      # Fondo oscuro
            fg='#e0e0e0',      # Texto claro
            insertbackground='#ffffff',  # Cursor blanco
            selectbackground='#4a4a4a',  # Selección gris
            selectforeground='#ffffff',  # Texto seleccionado blanco
            font=('Consolas', 10)
        )
        self._text.grid(row=0, column=0, columnspan=3, sticky="nsew", padx=4, pady=4)
        self._text.configure(state=tk.DISABLED)

        # Tags de colores por canal
        self._text.tag_configure("general", foreground="#e0e0e0")
        self._text.tag_configure("mafia", foreground="#ff6b6b")
        self._text.tag_configure("investigator", foreground="#51cf66")
        self._text.tag_configure("system", foreground="#adb5bd", font=('Consolas', 9, "italic"))
        self._text.tag_configure("timestamp", foreground="#868e96")

        # Canal
        self._channel_var = tk.StringVar(value=self.channels[0])
        self._channel_combo = ttk.Combobox(
            self, 
            values=self.channels, 
            textvariable=self._channel_var, 
            state="readonly",
            width=12
        )
        self._channel_combo.grid(row=1, column=0, sticky="w", padx=(4, 2), pady=(0, 6))

        # Entrada
        self._entry_var = tk.StringVar()
        self._entry = ttk.Entry(self, textvariable=self._entry_var)
        self._entry.grid(row=1, column=1, sticky="ew", padx=(2, 2), pady=(0, 6))
        self._entry.bind("<Return>", self._on_enter_pressed)
        self.columnconfigure(1, weight=1)

        # Botón
        self._send_btn = ttk.Button(self, text="Enviar", command=self._on_send_clicked)
        self._send_btn.grid(row=1, column=2, sticky="e", padx=(2, 4), pady=(0, 6))

    def set_player_id(self, player_id: int):
        """Actualiza el player_id."""
        self.player_id = player_id

    def set_available_channels(self, channels: List[str]):
        """Actualiza canales disponibles."""
        if not channels:
            channels = ["general"]
        self.channels = channels
        self._channel_combo.configure(values=self.channels)
        if self._channel_var.get() not in self.channels:
            self._channel_var.set(self.channels[0])

    def add_message(self, msg: ChatMessage):
        """Añade un mensaje EVITANDO DUPLICADOS."""
        # Crear ID único del mensaje
        msg_id = f"{msg.sender_id}_{msg.timestamp}_{hash(msg.text)}"
        
        # Si ya existe, ignorar
        if msg_id in self._message_ids:
            logger.debug(f"Duplicate message ignored: {msg_id}")
            return
        
        self._message_ids.add(msg_id)
        
        # Limpiar IDs viejos (mantener últimos 1000)
        if len(self._message_ids) > 1000:
            # Convertir a lista, eliminar primeros 500
            old_ids = list(self._message_ids)[:500]
            self._message_ids -= set(old_ids)

        # Formatear timestamp
        try:
            ts = int(msg.timestamp)
        except Exception:
            ts = int(time.time())
        timestr = datetime.datetime.fromtimestamp(ts).strftime("%H:%M:%S")

        # Insertar en text widget
        self._text.configure(state=tk.NORMAL)
        try:
            # Timestamp
            self._text.insert(tk.END, f"[{timestr}] ", "timestamp")
            
            # Nombre y canal
            if msg.channel and msg.channel != "general":
                header = f"{msg.sender_name} ({msg.channel}): "
            else:
                header = f"{msg.sender_name}: "
            
            self._text.insert(tk.END, header)
            
            # Texto del mensaje con tag de canal
            start = self._text.index(tk.INSERT)
            self._text.insert(tk.END, msg.text + "\n")
            end = self._text.index(tk.INSERT)
            
            # Aplicar color según canal
            tag = msg.channel if msg.channel in ["general", "mafia", "investigator", "system"] else "general"
            self._text.tag_add(tag, start, end)
            
            # Auto-scroll
            self._text.see(tk.END)
        except Exception as e:
            logger.exception(f"Error adding message to chat: {e}")
        finally:
            self._text.configure(state=tk.DISABLED)

    def clear_messages(self):
        """Limpia el historial."""
        self._text.configure(state=tk.NORMAL)
        self._text.delete("1.0", tk.END)
        self._text.configure(state=tk.DISABLED)
        self._message_ids.clear()

    def _on_enter_pressed(self, event=None):
        self._on_send_clicked()
        return "break"

    def _on_send_clicked(self):
        text = self._entry_var.get().strip()
        if not text:
            return

        channel = self._channel_var.get() or "general"

        try:
            if self.on_send_message:
                result = self.on_send_message(self.player_id, text, channel)
            else:
                result = None
        except Exception as e:
            logger.exception("Error in on_send_message callback")
            result = False

        # Callback-less mode (testing)
        if self.on_send_message is None:
            local_msg = ChatMessage(
                sender_id=self.player_id,
                sender_name=f"Player {self.player_id}",
                text=text,
                channel=channel,
                timestamp=int(time.time()),
            )
            self.add_message(local_msg)
            self._entry_var.set("")
            return

        if result is False:
            sys_msg = ChatMessage(
                sender_id=0,
                sender_name="Sistema",
                text="No se pudo enviar el mensaje.",
                channel="system",
                timestamp=int(time.time()),
            )
            self.add_message(sys_msg)
            return

        # Si el callback fue exitoso, limpiar entrada
        # (el mensaje aparecerá vía callback del controller)
        self._entry_var.set("")