class UIGameController:
    def __init__(self, state_controller: GameStateController, app):
        self.state = state_controller
        self.app = app  # Solo aquí tocas Tkinter

        # Suscribirse a eventos agnósticos
        self.state.on_event = self._handle_game_event

    def _handle_game_event(self, event: GameEvent):
        """Convierte evento agnóstico a UI updates"""
        self.app.root.after(0, self._update_ui_for_event, event)
