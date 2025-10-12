"""
gui/views/lobby_view.py
Vista de lobby/sala de espera para configurar la partida.
"""
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import logging

from core import ROLES, get_recommended_config, Phase

logger = logging.getLogger(__name__)


class LobbyView(ttk.Frame):
    """Vista del lobby para configurar y empezar partidas."""
    
    def __init__(self, parent, controller, colors):
        super().__init__(parent)
        self.controller = controller
        self.colors = colors
        
        # Crear juego si no existe
        if not self.controller.get_game():
            self.controller.create_game("Player 1")
        
        # Suscribirse a actualizaciones
        self.controller.on_game_update = self.refresh
        
        self.setup_ui()
        self.refresh()
    
    def setup_ui(self):
        """Configura la interfaz."""
        # Header
        header = ttk.Frame(self)
        header.pack(fill=tk.X, padx=10, pady=10)
        
        title = tk.Label(
            header,
            text="🎮 Mafia Game - Lobby",
            font=("Arial", 20, "bold"),
            bg=self.colors['bg'],
            fg=self.colors['accent']
        )
        title.pack(side=tk.LEFT)
        
        # Main container con dos columnas
        main = ttk.Frame(self)
        main.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # Columna izquierda - Jugadores
        left_col = ttk.Frame(main)
        left_col.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
        
        self.setup_players_section(left_col)
        
        # Columna derecha - Configuración
        right_col = ttk.Frame(main)
        right_col.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(5, 0))
        
        self.setup_config_section(right_col)
        
        # Footer con botones
        footer = ttk.Frame(self)
        footer.pack(fill=tk.X, padx=10, pady=10)
        
        self.setup_footer(footer)
    
    def setup_players_section(self, parent):
        """Sección de jugadores."""
        # Header
        header = tk.Label(
            parent,
            text="📋 JUGADORES",
            font=("Arial", 14, "bold"),
            bg=self.colors['bg'],
            fg=self.colors['fg']
        )
        header.pack(anchor=tk.W, pady=(0, 5))
        
        # Frame con listbox y scrollbar
        list_frame = ttk.Frame(parent)
        list_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.players_listbox = tk.Listbox(
            list_frame,
            yscrollcommand=scrollbar.set,
            font=("Arial", 11),
            bg="#1e1e1e",
            fg=self.colors['fg'],
            selectbackground=self.colors['accent'],
            relief=tk.FLAT,
            highlightthickness=1,
            highlightcolor=self.colors['accent']
        )
        self.players_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.players_listbox.yview)
        
        # Botones de gestión de jugadores
        btn_frame = ttk.Frame(parent)
        btn_frame.pack(fill=tk.X)
        
        ttk.Button(
            btn_frame,
            text="➕ Añadir Jugador",
            command=self.add_player
        ).pack(side=tk.LEFT, padx=(0, 5))
        
        ttk.Button(
            btn_frame,
            text="➖ Eliminar",
            command=self.remove_player
        ).pack(side=tk.LEFT, padx=(0, 5))
        
        ttk.Button(
            btn_frame,
            text="📝 Renombrar",
            command=self.rename_player
        ).pack(side=tk.LEFT)
    
    def setup_config_section(self, parent):
        """Sección de configuración de roles."""
        # Header
        header = tk.Label(
            parent,
            text="⚙️ CONFIGURACIÓN DE ROLES",
            font=("Arial", 14, "bold"),
            bg=self.colors['bg'],
            fg=self.colors['fg']
        )
        header.pack(anchor=tk.W, pady=(0, 5))
        
        # Frame con scroll para roles
        canvas_frame = ttk.Frame(parent)
        canvas_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        canvas = tk.Canvas(
            canvas_frame,
            bg="#1e1e1e",
            highlightthickness=0
        )
        scrollbar = ttk.Scrollbar(canvas_frame, orient=tk.VERTICAL, command=canvas.yview)
        
        self.roles_frame = ttk.Frame(canvas)
        self.roles_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=self.roles_frame, anchor=tk.NW)
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Spinboxes para roles
        self.role_spinboxes = {}
        self.populate_roles()
        
        # Botón de configuración recomendada
        ttk.Button(
            parent,
            text="✨ Usar Configuración Recomendada",
            command=self.use_recommended_config
        ).pack(fill=tk.X, pady=(5, 0))
        
        # Sección de tiempos
        times_frame = ttk.LabelFrame(parent, text="⏱️ Tiempos", padding=10)
        times_frame.pack(fill=tk.X, pady=(10, 0))
        
        # Tiempo de noche
        night_frame = ttk.Frame(times_frame)
        night_frame.pack(fill=tk.X, pady=(0, 5))
        
        tk.Label(
            night_frame,
            text="Noche (segundos):",
            bg=self.colors['bg'],
            fg=self.colors['fg']
        ).pack(side=tk.LEFT)
        
        self.night_spinbox = ttk.Spinbox(
            night_frame,
            from_=60,
            to=600,
            increment=30,
            width=10
        )
        self.night_spinbox.set(300)
        self.night_spinbox.pack(side=tk.RIGHT)
        
        # Tiempo de día
        day_frame = ttk.Frame(times_frame)
        day_frame.pack(fill=tk.X)
        
        tk.Label(
            day_frame,
            text="Día (segundos):",
            bg=self.colors['bg'],
            fg=self.colors['fg']
        ).pack(side=tk.LEFT)
        
        self.day_spinbox = ttk.Spinbox(
            day_frame,
            from_=120,
            to=900,
            increment=60,
            width=10
        )
        self.day_spinbox.set(600)
        self.day_spinbox.pack(side=tk.RIGHT)
    
    def setup_footer(self, parent):
        """Botones inferiores."""
        left_buttons = ttk.Frame(parent)
        left_buttons.pack(side=tk.LEFT)
        
        ttk.Button(
            left_buttons,
            text="🔄 Reiniciar",
            command=self.reset_game
        ).pack(side=tk.LEFT, padx=(0, 5))
        
        ttk.Button(
            left_buttons,
            text="📊 Estadísticas",
            command=self.show_stats,
            state=tk.DISABLED
        ).pack(side=tk.LEFT)
        
        # Botón principal
        self.start_button = ttk.Button(
            parent,
            text="▶️ EMPEZAR PARTIDA",
            command=self.start_game
        )
        self.start_button.pack(side=tk.RIGHT)
    
    def populate_roles(self):
        """Puebla la lista de roles con spinboxes."""
        game = self.controller.get_game()
        if not game:
            return
        
        # Limpiar frame
        for widget in self.roles_frame.winfo_children():
            widget.destroy()
        
        self.role_spinboxes.clear()
        
        # Agrupar por facción
        from core.roles import get_roles_by_faction, Faction
        
        factions = [
            (Faction.TOWN, "🏘️ Pueblo", self.colors['town']),
            (Faction.MAFIA, "😈 Mafia", self.colors['mafia']),
            (Faction.NEUTRAL, "⚖️ Neutral", self.colors['neutral'])
        ]
        
        for faction, label, color in factions:
            # Header de facción
            faction_label = tk.Label(
                self.roles_frame,
                text=label,
                font=("Arial", 11, "bold"),
                bg=self.colors['bg'],
                fg=color
            )
            faction_label.pack(anchor=tk.W, pady=(10, 5))
            
            # Roles de esta facción
            faction_roles = get_roles_by_faction(faction)
            
            for role_key, role in faction_roles.items():
                role_frame = ttk.Frame(self.roles_frame)
                role_frame.pack(fill=tk.X, pady=2)
                
                # Label del rol
                tk.Label(
                    role_frame,
                    text=f"  {role.name}:",
                    width=20,
                    anchor=tk.W,
                    bg=self.colors['bg'],
                    fg=self.colors['fg']
                ).pack(side=tk.LEFT)
                
                # Spinbox
                current_value = game.roles_config.get(role_key, 0)
                spinbox = ttk.Spinbox(
                    role_frame,
                    from_=0,
                    to=10,
                    width=8,
                    command=lambda key=role_key: self.on_role_change(key)
                )
                spinbox.set(current_value)
                spinbox.pack(side=tk.RIGHT)
                
                self.role_spinboxes[role_key] = spinbox
    
    def on_role_change(self, role_key):
        """Callback cuando cambia un rol."""
        spinbox = self.role_spinboxes.get(role_key)
        if not spinbox:
            return
        
        try:
            count = int(spinbox.get())
            self.controller.update_role_config(role_key, count)
        except ValueError:
            pass
    
    def add_player(self):
        """Añade un nuevo jugador."""
        game = self.controller.get_game()
        if not game:
            return
        
        name = simpledialog.askstring(
            "Añadir Jugador",
            "Nombre del jugador:",
            parent=self
        )
        
        if name and name.strip():
            if self.controller.add_player(name.strip()):
                self.refresh()
            else:
                messagebox.showerror(
                    "Error",
                    "No se pudo añadir el jugador.\n"
                    "Puede que el nombre ya exista."
                )
    
    def remove_player(self):
        """Elimina el jugador seleccionado."""
        selection = self.players_listbox.curselection()
        if not selection:
            messagebox.showwarning("Aviso", "Selecciona un jugador primero")
            return
        
        game = self.controller.get_game()
        if not game:
            return
        
        players = list(game.players.values())
        selected_player = players[selection[0]]
        
        if messagebox.askyesno(
            "Confirmar",
            f"¿Eliminar a '{selected_player.name}'?"
        ):
            self.controller.remove_player(selected_player.user_id)
            self.refresh()
    
    def rename_player(self):
        """Renombra el jugador seleccionado."""
        selection = self.players_listbox.curselection()
        if not selection:
            messagebox.showwarning("Aviso", "Selecciona un jugador primero")
            return
        
        game = self.controller.get_game()
        if not game:
            return
        
        players = list(game.players.values())
        selected_player = players[selection[0]]
        
        new_name = simpledialog.askstring(
            "Renombrar Jugador",
            f"Nuevo nombre para '{selected_player.name}':",
            initialvalue=selected_player.name,
            parent=self
        )
        
        if new_name and new_name.strip():
            selected_player.name = new_name.strip()
            self.refresh()
    
    def use_recommended_config(self):
        """Usa la configuración recomendada."""
        self.controller.use_recommended_config()
        self.refresh()
    
    def reset_game(self):
        """Reinicia el juego."""
        if messagebox.askyesno(
            "Confirmar",
            "¿Reiniciar la configuración?"
        ):
            self.controller.reset_game()
            self.refresh()
    
    def show_stats(self):
        """Muestra estadísticas (placeholder)."""
        messagebox.showinfo(
            "Estadísticas",
            "Funcionalidad no implementada aún"
        )
    
    def start_game(self):
        """Inicia la partida."""
        # Actualizar tiempos
        try:
            night = int(self.night_spinbox.get())
            day = int(self.day_spinbox.get())
            self.controller.update_timers(night, day)
        except ValueError:
            pass
        
        # Intentar iniciar
        success, error = self.controller.start_game()
        
        if success:
            # Cambiar a vista de juego
            game = self.controller.get_game()
            self.master.master.master.show_game(game)  # app.show_game()
        else:
            messagebox.showerror("Error", error)
    
    def refresh(self, game=None):
        """Actualiza la vista con el estado actual."""
        game = game or self.controller.get_game()
        if not game:
            return
        
        # Actualizar lista de jugadores
        self.players_listbox.delete(0, tk.END)
        
        for i, player in enumerate(game.players.values()):
            marker = "👑" if i == 0 else "✅"
            self.players_listbox.insert(tk.END, f"{marker} {player.name}")
        
        # Actualizar título con contador
        num_players = len(game.players)
        self.winfo_children()[0].winfo_children()[0].config(
            text=f"🎮 Mafia Game - Lobby ({num_players}/10)"
        )
        
        # Actualizar spinboxes de roles
        for role_key, spinbox in self.role_spinboxes.items():
            current_value = game.roles_config.get(role_key, 0)
            spinbox.set(current_value)
