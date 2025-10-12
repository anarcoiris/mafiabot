"""
gui/widgets/player_card.py
Widget reutilizable para mostrar información de un jugador.
"""
import tkinter as tk
from tkinter import ttk
from typing import Optional

from core.models import Player
from core.roles import get_role


class PlayerCard(ttk.Frame):
    """Widget que muestra información de un jugador en formato de tarjeta."""
    
    def __init__(self, parent, player: Player, show_role: bool = False, 
                 selectable: bool = False, on_select=None, **kwargs):
        """
        Args:
            parent: Widget padre
            player: Objeto Player a mostrar
            show_role: Si True, muestra el rol (respeta si está muerto)
            selectable: Si True, permite seleccionar la tarjeta
            on_select: Callback cuando se selecciona (recibe player)
        """
        super().__init__(parent, **kwargs)
        
        self.player = player
        self.show_role = show_role
        self.selectable = selectable
        self.on_select = on_select
        self.selected = False
        
        self._setup_ui()
    
    def _setup_ui(self):
        """Configura la interfaz de la tarjeta."""
        
        # Frame principal con borde
        self.configure(
            relief=tk.RAISED,
            borderwidth=2,
            padding=10
        )
        
        # Header con nombre y estado
        header = ttk.Frame(self)
        header.pack(fill=tk.X, pady=(0, 5))
        
        # Icono de estado
        status_icon = "💀" if not self.player.alive else "💚"
        status_label = ttk.Label(
            header,
            text=status_icon,
            font=('Arial', 16)
        )
        status_label.pack(side=tk.LEFT, padx=(0, 5))
        
        # Nombre
        name_label = ttk.Label(
            header,
            text=self.player.name,
            font=('Arial', 12, 'bold')
        )
        name_label.pack(side=tk.LEFT)
        
        # Rol (si visible)
        if self.show_role and self.player.role_key:
            role = get_role(self.player.role_key)
            if role:
                role_frame = ttk.Frame(self)
                role_frame.pack(fill=tk.X, pady=(0, 5))
                
                # Emoji de facción
                faction_emoji = {
                    "town": "💚",
                    "mafia": "🔴",
                    "neutral": "⚪"
                }
                emoji = faction_emoji.get(role.faction.value, "❓")
                
                role_label = ttk.Label(
                    role_frame,
                    text=f"{emoji} {role.name}",
                    font=('Arial', 10),
                    foreground='blue'
                )
                role_label.pack(anchor=tk.W)
        
        # Estados especiales
        states = []
        if not self.player.alive:
            states.append("💀 Muerto")
        if self.player.blocked:
            states.append("🚫 Bloqueado")
        if self.player.silenced:
            states.append("🤐 Silenciado")
        if self.player.protected:
            states.append("🛡️ Protegido")
        
        if states:
            states_frame = ttk.Frame(self)
            states_frame.pack(fill=tk.X)
            
            for state in states:
                state_label = ttk.Label(
                    states_frame,
                    text=f"• {state}",
                    font=('Arial', 9),
                    foreground='red'
                )
                state_label.pack(anchor=tk.W)
        
        # Si es seleccionable, agregar comportamiento de click
        if self.selectable and self.on_select:
            self.bind("<Button-1>", self._on_click)
            for child in self.winfo_children():
                child.bind("<Button-1>", self._on_click)
                for subchild in child.winfo_children():
                    subchild.bind("<Button-1>", self._on_click)
            
            # Cambiar cursor
            self.configure(cursor="hand2")
    
    def _on_click(self, event=None):
        """Maneja el click en la tarjeta."""
        if self.on_select:
            self.selected = not self.selected
            self._update_selection_style()
            self.on_select(self.player)
    
    def _update_selection_style(self):
        """Actualiza el estilo visual de selección."""
        if self.selected:
            self.configure(relief=tk.SUNKEN, borderwidth=3)
        else:
            self.configure(relief=tk.RAISED, borderwidth=2)
    
    def update_player(self, player: Player):
        """Actualiza la tarjeta con nueva información del jugador."""
        self.player = player
        
        # Destruir widgets y recrear
        for widget in self.winfo_children():
            widget.destroy()
        
        self._setup_ui()


class PlayerCardGrid(ttk.Frame):
    """
    Grid de tarjetas de jugadores con scroll.
    Útil para mostrar múltiples jugadores organizadamente.
    """
    
    def __init__(self, parent, players: list, show_roles: bool = False,
                 selectable: bool = False, on_select=None, columns: int = 3, **kwargs):
        """
        Args:
            parent: Widget padre
            players: Lista de objetos Player
            show_roles: Si muestra roles
            selectable: Si permite selección
            on_select: Callback para selección
            columns: Número de columnas en el grid
        """
        super().__init__(parent, **kwargs)
        
        self.players = players
        self.show_roles = show_roles
        self.selectable = selectable
        self.on_select = on_select
        self.columns = columns
        self.cards = {}
        
        self._setup_ui()
    
    def _setup_ui(self):
        """Configura el grid con scroll."""
        
        # Canvas para scroll
        canvas = tk.Canvas(self, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        
        self.grid_frame = ttk.Frame(canvas)
        
        self.grid_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=self.grid_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Poblar con jugadores
        self.update_players(self.players)
    
    def update_players(self, players: list):
        """Actualiza el grid con nueva lista de jugadores."""
        self.players = players
        
        # Limpiar grid
        for widget in self.grid_frame.winfo_children():
            widget.destroy()
        
        self.cards.clear()
        
        # Crear tarjetas en grid
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
            
            self.cards[player.user_id] = card
        
        # Configurar pesos de columnas
        for col in range(self.columns):
            self.grid_frame.columnconfigure(col, weight=1)
    
    def get_selected_players(self) -> list:
        """Retorna lista de jugadores seleccionados."""
        return [
            card.player for card in self.cards.values() 
            if card.selected
        ]
    
    def clear_selection(self):
        """Limpia todas las selecciones."""
        for card in self.cards.values():
            card.selected = False
            card._update_selection_style()
