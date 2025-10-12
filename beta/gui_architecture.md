# 🎨 Arquitectura GUI de Tkinter para Mafia Bot

## 📐 Diseño Modular

```
mafiabot/
├── core/              # ✅ Ya existe - Lógica pura del juego
├── persistence/       # ✅ Ya existe - Base de datos
├── bot/              # ✅ Ya existe - Interfaz Telegram
├── gui/              # ⭐ NUEVO - Interfaz GUI
│   ├── __init__.py
│   ├── app.py                # Aplicación principal
│   ├── views/               
│   │   ├── __init__.py
│   │   ├── lobby_view.py     # Vista de lobby/sala de espera
│   │   ├── game_view.py      # Vista de partida en curso
│   │   ├── player_view.py    # Vista individual de jugador
│   │   └── debug_view.py     # Panel de debug/control
│   ├── widgets/
│   │   ├── __init__.py
│   │   ├── player_card.py    # Widget de tarjeta de jugador
│   │   ├── action_panel.py   # Panel de acciones nocturnas
│   │   ├── vote_panel.py     # Panel de votación
│   │   └── chat_log.py       # Log de eventos
│   └── controllers/
│       ├── __init__.py
│       ├── game_controller.py   # Controlador del juego
│       └── interface_adapter.py # Adapta core a GUI
└── adapters/          # ⭐ NUEVO - Capa de abstracción
    ├── __init__.py
    └── game_interface.py    # Interfaz abstracta para bot/GUI
```

## 🎯 Modos de Funcionamiento

### Modo 1: Testing Manual (Inmediato)
- **Propósito**: Probar mecánicas del juego
- **Características**:
  - Crear múltiples jugadores locales
  - Controlar acciones de cada jugador manualmente
  - Ver estado completo del juego (modo debug)
  - Avanzar fases manualmente

### Modo 2: Juego Local (Corto plazo)
- **Propósito**: Jugar partidas completas localmente
- **Características**:
  - Múltiples ventanas (una por jugador)
  - Información privada por ventana
  - Control automático de fases
  - Logs de eventos

### Modo 3: Cliente/Servidor (Largo plazo)
- **Propósito**: Jugar en red
- **Características**:
  - Cliente GUI conecta a servidor
  - Servidor puede ser bot de Telegram o servidor dedicado
  - Sincronización de estado
  - Chat en tiempo real

## 🔌 Capa de Abstracción

### Interfaz Común

```python
# adapters/game_interface.py
from abc import ABC, abstractmethod

class GameInterface(ABC):
    """Interfaz abstracta para cualquier frontend del juego."""
    
    @abstractmethod
    async def send_message(self, recipient_id: int, text: str):
        """Envía un mensaje a un jugador."""
        pass
    
    @abstractmethod
    async def send_broadcast(self, game_id: int, text: str):
        """Envía un mensaje a todos en el juego."""
        pass
    
    @abstractmethod
    async def request_action(self, player_id: int, actions: list):
        """Solicita una acción al jugador con opciones."""
        pass
    
    @abstractmethod
    async def update_game_state(self, game):
        """Notifica cambio de estado del juego."""
        pass
```

### Implementaciones

```python
# bot/telegram_adapter.py
class TelegramAdapter(GameInterface):
    """Implementación para Telegram."""
    def __init__(self, bot):
        self.bot = bot
    
    async def send_message(self, recipient_id, text):
        await self.bot.send_message(recipient_id, text)

# gui/controllers/interface_adapter.py
class GUIAdapter(GameInterface):
    """Implementación para GUI."""
    def __init__(self, app):
        self.app = app
    
    async def send_message(self, recipient_id, text):
        # Envia mensaje a ventana del jugador
        self.app.show_message(recipient_id, text)
```

## 🖼️ Diseño de la GUI

### Vista Principal - Lobby

```
┌────────────────────────────────────────────────────┐
│ 🎮 Mafia Game - Lobby                        [ _ □ × ]
├────────────────────────────────────────────────────┤
│                                                    │
│  📋 JUGADORES (4/10)                              │
│  ┌──────────────────────────────────────────────┐ │
│  │ ✅ Alice      [Host]                         │ │
│  │ ✅ Bob                                       │ │
│  │ ✅ Charlie                                   │ │
│  │ ✅ Diana                                     │ │
│  └──────────────────────────────────────────────┘ │
│                                                    │
│  [+ Añadir Jugador]  [Importar Lista]            │
│                                                    │
│  ⚙️ CONFIGURACIÓN                                 │
│  ┌──────────────────────────────────────────────┐ │
│  │ Mafia:           [2] ▲▼                      │ │
│  │ Doctor:          [1] ▲▼                      │ │
│  │ Detective:       [1] ▲▼                      │ │
│  │ Ciudadano:       [auto]                      │ │
│  │                                               │ │
│  │ [Config Recomendada]  [Roles Avanzados >>]  │ │
│  └──────────────────────────────────────────────┘ │
│                                                    │
│  ⏱️ TIEMPOS                                       │
│  Noche: [300s] ▲▼    Día: [600s] ▲▼             │
│                                                    │
│  [🎲 Modo Debug]  [⚙️ Opciones]                  │
│                                                    │
│                    [▶️ EMPEZAR PARTIDA]           │
└────────────────────────────────────────────────────┘
```

### Vista de Partida - Jugador Individual

```
┌────────────────────────────────────────────────────┐
│ 🎮 Mafia Game - Alice                    [🌙 NOCHE]
├────────────────────────────────────────────────────┤
│  👤 Tu Rol: DOCTOR                                │
│  🏥 Puedes curar a un jugador esta noche          │
├────────────────────────────────────────────────────┤
│ JUGADORES VIVOS (6)          │  📋 TU ACCIÓN      │
│ ┌──────────────────────────┐ │  ┌───────────────┐ │
│ │ ✅ Bob                   │ │  │ Selecciona:   │ │
│ │ ✅ Charlie               │ │  │               │ │
│ │ ✅ Diana                 │ │  │ ○ Bob         │ │
│ │ ✅ Eve                   │ │  │ ○ Charlie     │ │
│ │ ✅ Frank                 │ │  │ ○ Diana       │ │
│ │                          │ │  │ ○ Eve         │ │
│ │ 💀 MUERTOS (2)           │ │  │ ○ Frank       │ │
│ │ ⚰️ George (Ciudadano)    │ │  │ ● Alice (tú)  │ │
│ │ ⚰️ Helen (Vigilante)     │ │  │               │ │
│ └──────────────────────────┘ │  │ [Confirmar]   │ │
│                              │  └───────────────┘ │
│                              │                    │
│ 📜 LOG DE EVENTOS            │  ⏱️ Tiempo:       │
│ ┌──────────────────────────┐ │  [02:45]          │
│ │ 🌙 Comienza la noche...  │ │                    │
│ │ 💀 George fue asesinado  │ │                    │
│ │ ☀️ Amanece el día 2      │ │                    │
│ │ ⚖️ Se inicia votación    │ │                    │
│ └──────────────────────────┘ │                    │
└────────────────────────────────────────────────────┘
```

### Panel de Debug (Modo Testing)

```
┌────────────────────────────────────────────────────┐
│ 🐛 Debug Panel - Vista Completa                    │
├────────────────────────────────────────────────────┤
│ 📊 ESTADO DEL JUEGO                               │
│                                                    │
│ Fase: NIGHT    Día: 2    Tiempo: 02:45           │
│                                                    │
│ ROLES REALES (Visible solo en debug)              │
│ ┌────────────────────────────────────────────────┐│
│ │ Alice    - DOCTOR       [🏥 Curó a Bob]      ││
│ │ Bob      - MAFIA        [🔫 Votó por Diana]  ││
│ │ Charlie  - DETECTIVE    [🔍 Investigó a Eve] ││
│ │ Diana    - CIUDADANO    [Sin acción]         ││
│ │ Eve      - SHERIFF      [🔎 Investigó a Bob] ││
│ │ Frank    - ESCORT       [💃 Bloqueó a Bob]   ││
│ └────────────────────────────────────────────────┘│
│                                                    │
│ ACCIONES ESTA NOCHE:                              │
│ - Mafia target: Diana                             │
│ - Doctor heal: Bob                                │
│ - Escort block: Bob (BLOQUEADO)                   │
│                                                    │
│ CONTROLES:                                         │
│ [⏭️ Siguiente Fase]  [⏸️ Pausar]  [🔄 Reiniciar] │
│                                                    │
│ [📋 Ver Logs]  [💾 Guardar Estado]  [📊 Stats]   │
└────────────────────────────────────────────────────┘
```

## 🎮 Flujo de Uso

### Modo Testing

1. **Iniciar GUI**: `python gui/app.py --debug`
2. **Crear jugadores**: Añadir 5-10 jugadores de prueba
3. **Configurar roles**: Asignar roles manualmente o aleatorio
4. **Empezar partida**: Ver panel de debug con todos los roles
5. **Controlar acciones**: Seleccionar acciones para cada jugador
6. **Avanzar fase**: Botón "Siguiente Fase" resuelve y avanza
7. **Observar**: Ver logs de eventos y estado completo

### Modo Local (Multi-ventana)

1. **Iniciar GUI**: `python gui/app.py --local`
2. **Crear jugadores**: Añadir jugadores reales
3. **Abrir ventanas**: Una ventana por jugador
4. **Empezar partida**: Roles asignados secretamente
5. **Jugar**: Cada jugador controla su ventana
6. **Automático**: Fases avanzan automáticamente

## 🔧 Implementación Técnica

### Threading Model

```python
# GUI usa thread principal
# GameEngine corre en thread separado
# Comunicación via Queue

from queue import Queue
import threading

class GUIGameController:
    def __init__(self):
        self.command_queue = Queue()
        self.event_queue = Queue()
        self.game_thread = threading.Thread(target=self._game_loop)
        self.game_thread.start()
    
    def _game_loop(self):
        while True:
            cmd = self.command_queue.get()
            # Procesar comando
            result = self.process_command(cmd)
            self.event_queue.put(result)
```

### Estado Reactivo

```python
class GameState:
    """Observable game state para GUI."""
    def __init__(self):
        self._observers = []
        self._game = None
    
    def attach(self, observer):
        self._observers.append(observer)
    
    def notify(self):
        for observer in self._observers:
            observer.update(self._game)
    
    def update_game(self, game):
        self._game = game
        self.notify()
```

## 📦 Dependencias Adicionales

```txt
# requirements_gui.txt
tk>=8.6  # Ya incluido en Python
pillow>=10.0.0  # Para imágenes/iconos
matplotlib>=3.7.0  # Para gráficos/estadísticas (opcional)
```

## 🚀 Próximos Pasos

1. ✅ Crear estructura de directorios
2. ⏳ Implementar `adapters/game_interface.py`
3. ⏳ Implementar `gui/app.py` básico
4. ⏳ Implementar `gui/views/lobby_view.py`
5. ⏳ Implementar `gui/controllers/game_controller.py`
6. ⏳ Integrar con `core/engine.py`
7. ⏳ Testing y refinamiento

¿Quieres que empiece a implementar alguna parte específica?
