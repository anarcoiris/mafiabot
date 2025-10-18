# gui/controllers/interface_adapter.py
class GUIAdapter(GameInterface):
    """Implementación para GUI."""
    def __init__(self, app):
        self.app = app

    async def send_message(self, recipient_id, text):
        # Envia mensaje a ventana del jugador
        self.app.show_message(recipient_id, text)
