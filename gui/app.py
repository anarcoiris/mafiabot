"""
gui/app.py
Aplicación principal de la GUI de Mafia con soporte para ventanas múltiples.
"""
import tkinter as tk
from tkinter import ttk, messagebox
import sys
import logging
from pathlib import Path
from typing import Dict

# Añadir el directorio padre al path para imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from core import GameEngine, Game, Player, Phase
from gui.views.lobby_view import LobbyView
from gui.controllers.game_controller import GUIGameController

logger = logging.getLogger(__name__)


class MafiaGUIApp:
    """Aplicación principal de la GUI con soporte para múltiples perspectivas."""
    
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
        
        # Ventanas de perspectiva (player_id -> PerspectiveWindow)
        self.perspective_windows: Dict[int, any] = {}
        
        # Iniciar en lobby
        self.show_lobby()
        
        # Configurar cierre
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
    
    def show_lobby(self):
        """Muestra la vista de lobby."""
        # Cerrar ventanas de perspectiva si existen
        self.close_all_perspective_windows()
        
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
    
    def open_perspective_window(self, player_id: int):
        """
        Abre una ventana de perspectiva para un jugador específico.
        Solo se abre si el jugador es humano (no bot).
        """
        # Verificar que el jugador existe
        if not self.controller.game or player_id not in self.controller.game.players:
            logger.warning(f"Cannot open perspective for non-existent player {player_id}")
            return
        
        # Verificar que no es un bot
        player_type = self.controller.player_types.get(player_id, "human")
        if player_type != "human":
            logger.info(f"Skipping perspective window for bot player {player_id}")
            return
        
        # Si ya existe una ventana, traerla al frente
        if player_id in self.perspective_windows:
            try:
                window = self.perspective_windows[player_id]
                window.window.lift()
                window.window.focus_force()
                return
            except Exception:
                # La ventana fue cerrada manualmente
                del self.perspective_windows[player_id]
        
        # Crear nueva ventana
        try:
            from gui.views.perspective_window import PerspectiveWindow
            window = PerspectiveWindow(self.controller, player_id, self.colors)
            self.perspective_windows[player_id] = window
            
            # Configurar callback de cierre
            def on_close():
                if player_id in self.perspective_windows:
                    del self.perspective_windows[player_id]
                window.close()
            
            window.window.protocol("WM_DELETE_WINDOW", on_close)
            
            logger.info(f"Opened perspective window for player {player_id}")
        except Exception:
            logger.exception(f"Error opening perspective window for player {player_id}")
    
    def open_all_perspective_windows(self):
        """Abre ventanas de perspectiva para todos los jugadores humanos."""
        if not self.controller.game:
            return
        
        for player_id in self.controller.game.players.keys():
            self.open_perspective_window(player_id)
    
    def close_perspective_window(self, player_id: int):
        """Cierra la ventana de perspectiva de un jugador."""
        if player_id in self.perspective_windows:
            try:
                self.perspective_windows[player_id].close()
            except Exception:
                pass
            del self.perspective_windows[player_id]
    
    def close_all_perspective_windows(self):
        """Cierra todas las ventanas de perspectiva."""
        for player_id in list(self.perspective_windows.keys()):
            self.close_perspective_window(player_id)
    
    def show_message(self, title, message, type_="info"):
        """Muestra un mensaje al usuario."""
        if type_ == "error":
            messagebox.showerror(title, message)
        elif type_ == "warning":
            messagebox.showwarning(title, message)
        else:
            messagebox.showinfo(title, message)
    
    def show_messages(self, title: str, messages: list):
        """Muestra múltiples mensajes en un diálogo."""
        text = "\n\n".join(messages)
        messagebox.showinfo(title, text)
    
    def send_private_message(self, player_id: int, text: str):
        """Envía un mensaje privado a un jugador (aparecerá en su ventana de perspectiva)."""
        # Si tiene ventana abierta, mostrar ahí
        if player_id in self.perspective_windows:
            try:
                from core.models import ChatMessage
                import time
                
                msg = ChatMessage(
                    sender_id=0,
                    sender_name="Sistema",
                    text=text,
                    channel="system",
                    timestamp=int(time.time())
                )
                
                window = self.perspective_windows[player_id]
                if hasattr(window, 'chat_widget'):
                    window.chat_widget.add_message(msg)
            except Exception:
                logger.exception("Error sending private message to perspective window")
        
        # También registrar en el controller
        # (el controller puede tener su propio sistema de mensajes privados)
        logger.info(f"Private message to {player_id}: {text}")
    
    def on_closing(self):
        """Maneja el cierre de la aplicación."""
        if messagebox.askokcancel("Salir", "¿Quieres salir de la aplicación?"):
            self.close_all_perspective_windows()
            self.controller.cleanup()
            self.root.destroy()
    
    def run(self):
        """Ejecuta el main loop de la aplicación."""
        logger.info("Starting Mafia GUI")
        
        # Crear menú para abrir ventanas de perspectiva
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        
        windows_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Ventanas", menu=windows_menu)
        
        windows_menu.add_command(
            label="Abrir Todas las Perspectivas",
            command=self.open_all_perspective_windows
        )
        windows_menu.add_command(
            label="Cerrar Todas las Perspectivas",
            command=self.close_all_perspective_windows
        )
        
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