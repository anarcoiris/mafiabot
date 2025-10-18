# gui/widgets/player_card.py
"""
Widget reutilizable para mostrar información de un jugador.
"""
import tkinter as tk
from tkinter import ttk
from typing import Optional, Callable

from core.models import Player
from core.roles import get_role


class PlayerCard(ttk.Frame):
    """Widget que muestra información de un jugador en formato de tarjeta."""

    def __init__(
        self,
        parent,
        player: Player,
        show_role: bool = False,
        selectable: bool = False,
        on_select: Optional[Callable] = None,
        **kwargs
    ):
        super().__init__(parent, **kwargs)

        self.player = player
        self.show_role = show_role
        self.selectable = selectable
        self.on_select = on_select
        self.selected = False

        self._setup_ui()

    def _setup_ui(self):
        """Configura la interfaz de la tarjeta."""

        # Asegurarse de no pasar kwargs inválidos a configure
        try:
            self["relief"] = tk.RAISED
            self["borderwidth"] = 2
            # padding es soportado por ttk.Frame al crearlo; si no, ignorar
            try:
                self["padding"] = 10
            except Exception:
                pass
        except Exception:
            pass

        header = ttk.Frame(self)
        header.pack(fill=tk.X, pady=(0, 5))

        status_icon = "💀" if not getattr(self.player, "alive", True) else "💚"
        status_label = ttk.Label(header, text=status_icon, font=("Arial", 16))
        status_label.pack(side=tk.LEFT, padx=(0, 5))

        name_label = ttk.Label(header, text=self.player.name, font=("Arial", 12, "bold"))
        name_label.pack(side=tk.LEFT)

        if self.show_role and getattr(self.player, "role_key", None):
            role = get_role(self.player.role_key)
            if role:
                role_frame = ttk.Frame(self)
                role_frame.pack(fill=tk.X, pady=(0, 5))

                faction_emoji = {"town": "💚", "mafia": "🔴", "neutral": "⚪"}
                emoji = faction_emoji.get(getattr(getattr(role, "faction", None), "value", ""), "❓")

                role_label = ttk.Label(role_frame, text=f"{emoji} {role.name}", font=("Arial", 10), foreground="blue")
                role_label.pack(anchor=tk.W)

        states = []
        if not getattr(self.player, "alive", True):
            states.append("💀 Muerto")
        if getattr(self.player, "blocked", False):
            states.append("🚫 Bloqueado")
        if getattr(self.player, "silenced", False):
            states.append("🤐 Silenciado")
        if getattr(self.player, "protected", False):
            states.append("🛡️ Protegido")

        if states:
            states_frame = ttk.Frame(self)
            states_frame.pack(fill=tk.X)
            for state in states:
                state_label = ttk.Label(states_frame, text=f"• {state}", font=("Arial", 9), foreground="red")
                state_label.pack(anchor=tk.W)

        # Si seleccionable, enlazar clicks (con defensas)
        if self.selectable and self.on_select:
            self.bind("<Button-1>", self._on_click)
            # Intentar bind en hijos actuales (si hay widgets anidados)
            for child in self.winfo_children():
                try:
                    child.bind("<Button-1>", self._on_click)
                except Exception:
                    pass
            try:
                self.configure(cursor="hand2")
            except Exception:
                pass

    def _on_click(self, event=None):
        if self.on_select:
            self.selected = not self.selected
            self._update_selection_style()
            try:
                self.on_select(self.player)
            except Exception:
                # evitar que un callback externo rompa la UI
                pass

    def _update_selection_style(self):
        try:
            if self.selected:
                self.configure(relief=tk.SUNKEN, borderwidth=3)
            else:
                self.configure(relief=tk.RAISED, borderwidth=2)
        except Exception:
            pass

    def update_player(self, player: Player):
        """Actualiza la tarjeta con nueva información del jugador."""
        self.player = player
        for widget in list(self.winfo_children()):
            try:
                widget.destroy()
            except Exception:
                pass
        self._setup_ui()


class PlayerCardGrid(ttk.Frame):
    """Grid de tarjetas de jugadores con scroll."""

    def __init__(self, parent, players: list, show_roles: bool = False,
                 selectable: bool = False, on_select: Optional[Callable] = None, columns: int = 3, **kwargs):
        super().__init__(parent, **kwargs)

        self.players = players
        self.show_roles = show_roles
        self.selectable = selectable
        self.on_select = on_select
        self.columns = columns
        self.cards = {}

        self._setup_ui()

    def _setup_ui(self):
        canvas = tk.Canvas(self, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)

        self.grid_frame = ttk.Frame(canvas)

        self.grid_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

        canvas.create_window((0, 0), window=self.grid_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.update_players(self.players)

    def update_players(self, players: list):
        self.players = players
        for widget in list(self.grid_frame.winfo_children()):
            try:
                widget.destroy()
            except Exception:
                pass
        self.cards.clear()

        for i, player in enumerate(players):
            row = i // self.columns
            col = i % self.columns
            card = PlayerCard(
                self.grid_frame,
                player,
                show_role=self.show_roles,
                selectable=self.selectable,
                on_select=self.on_select
            )
            card.grid(row=row, column=col, padx=5, pady=5, sticky="nsew")
            self.cards[getattr(player, "user_id", i)] = card

        for col in range(self.columns):
            try:
                self.grid_frame.columnconfigure(col, weight=1)
            except Exception:
                pass

    def get_selected_players(self) -> list:
        return [card.player for card in self.cards.values() if card.selected]

    def clear_selection(self):
        for card in self.cards.values():
            card.selected = False
            card._update_selection_style()
