"""
gui/app.py
Aplicación principal de la GUI de Mafia.
"""
import tkinter as tk
from tkinter import ttk, messagebox
import sys
import logging
from pathlib import Path

# Añadir el directorio padre al path para imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from core import GameEngine, Game, Player, Phase
from gui.views.lobby_view import LobbyView
from gui.controllers.game_controller import GUIGameController

logger = logging.getLogger(__name__)


class MafiaGUIApp:
    """Aplicación principal de la GUI."""
    
    def __init__(self, debug_mode=False):
        self.debug_mode = debug_mode
        self.root = tk.Tk()
        self.root.title("🎮 Mafia Game")
        self.root.geometry("900x700")
        
        # Configurar tema
        self.style = ttk.Style()
        self.style.theme_use('clam')
        
        # Colores
        self.colors = {
            'bg': '#2b2b2b',
            'fg': '#ffffff',
            'accent': '#4a9eff',
            'danger': '#ff4a4a',
            'success': '#4aff4a',
            'town': '#4a9eff',
            'mafia': '#ff4a4a',
            'neutral': '#ffaa4a'
        }
        
        # Configurar root
        self.root.configure(bg=self.colors['bg'])
        
        # Controller del juego
        self.controller = GUIGameController(self, debug_mode=debug_mode)
        
        # Container principal
        self.main_container = ttk.Frame(self.root)
        self.main_container.pack(fill=tk.BOTH, expand=True)
        
        # Vista actual
        self.current_view = None
        
        # Iniciar en lobby
        self.show_lobby()
        
        # Configurar cierre
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
    
    def show_lobby(self):
        """Muestra la vista de lobby."""
        if self.current_view:
            self.current_view.destroy()
        
        self.current_view = LobbyView(
            self.main_container,
            self.controller,
            self.colors
        )
        self.current_view.pack(fill=tk.BOTH, expand=True)
    
    def show_game(self, game):
        """Muestra la vista de partida."""
        if self.current_view:
            self.current_view.destroy()
        
        from gui.views.game_view import GameView
        self.current_view = GameView(
            self.main_container,
            self.controller,
            game,
            self.colors,
            debug_mode=self.debug_mode
        )
        self.current_view.pack(fill=tk.BOTH, expand=True)
    
    def show_message(self, title, message, type_="info"):
        """Muestra un mensaje al usuario."""
        if type_ == "error":
            messagebox.showerror(title, message)
        elif type_ == "warning":
            messagebox.showwarning(title, message)
        else:
            messagebox.showinfo(title, message)
    
    def on_closing(self):
        """Maneja el cierre de la aplicación."""
        if messagebox.askokcancel("Salir", "¿Quieres salir de la aplicación?"):
            self.controller.cleanup()
            self.root.destroy()
    
    def run(self):
        """Ejecuta el main loop de la aplicación."""
        logger.info("Starting Mafia GUI")
        self.root.mainloop()


def main():
    """Punto de entrada principal."""
    import argparse
    
    # Configurar logging simple
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
    )
    
    # Parsear argumentos
    parser = argparse.ArgumentParser(description="Mafia Game GUI")
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Activar modo debug (ver todos los roles)'
    )
    args = parser.parse_args()
    
    # Crear y ejecutar app
    app = MafiaGUIApp(debug_mode=args.debug)
    
    try:
        app.run()
    except KeyboardInterrupt:
        logger.info("Application stopped by user")
    except Exception as e:
        logger.exception("Fatal error in GUI")
        messagebox.showerror("Error Fatal", f"Error inesperado:\n{e}")


if __name__ == "__main__":
    main()
