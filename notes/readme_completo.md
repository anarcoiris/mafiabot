# 🎮 Mafia Bot - Telegram + GUI

Bot de Telegram y aplicación GUI local para jugar al juego de Mafia.

## 📋 Contenido

- [Características](#características)
- [Instalación](#instalación)
- [Uso del Bot de Telegram](#uso-del-bot-de-telegram)
- [Uso de la GUI](#uso-de-la-gui)
- [Roles Disponibles](#roles-disponibles)
- [Arquitectura](#arquitectura)
- [Desarrollo](#desarrollo)

---

## ✨ Características

### Bot de Telegram
- ✅ 15 roles implementados
- ✅ Sistema de votación con botones inline
- ✅ Acciones nocturnas por mensaje privado
- ✅ Persistencia con SQLite asíncrono
- ✅ Sistema de jobs para fases automáticas
- ✅ Rate limiting anti-spam

### GUI Local
- ✅ Interfaz gráfica con Tkinter
- ✅ Modo Debug (ver todos los roles)
- ✅ Modo Testing (controlar todas las acciones)
- ✅ Configuración visual de roles
- ✅ Panel de control completo

---

## 📦 Instalación

### Requisitos
- Python 3.10 o superior
- pip instalado

### 1. Clonar repositorio

```bash
git clone https://github.com/tu-usuario/mafiabot.git
cd mafiabot
```

### 2. Crear entorno virtual (recomendado)

```bash
# Linux/Mac
python -m venv venv
source venv/bin/activate

# Windows
python -m venv venv
venv\Scripts\activate
```

### 3. Instalar dependencias

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Aplicar correcciones críticas

**handlers.py** - Línea 5:
```python
import logging
import time  # ⚠️ AÑADIR ESTA LÍNEA
from telegram import Update
```

**callbacks.py** - Línea 5:
```python
import logging
import time
from collections import Counter  # ⚠️ AÑADIR ESTA LÍNEA
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
```

### 5. Crear archivos `__init__.py`

```bash
# Crear __init__.py vacíos si no existen
touch core/__init__.py
touch persistence/__init__.py
touch bot/__init__.py
touch utils/__init__.py
touch gui/__init__.py
touch gui/views/__init__.py
touch gui/controllers/__init__.py
```

O usar los contenidos proporcionados en los artifacts.

### 6. Crear directorios de datos

```bash
mkdir -p data logs
```

### 7. Verificar instalación

```bash
python -c "from core import GameEngine; print('✅ core OK')"
python -c "from persistence import get_repository; print('✅ persistence OK')"
python -c "from bot import GameHandlers; print('✅ bot OK')"
python -c "from gui import MafiaGUIApp; print('✅ gui OK')"
```

---

## 🤖 Uso del Bot de Telegram

### 1. Obtener Token de Telegram

1. Habla con [@BotFather](https://t.me/BotFather) en Telegram
2. Usa `/newbot` y sigue las instrucciones
3. Copia el token que te da

### 2. Configurar Variables de Entorno

Crea un archivo `.env`:

```bash
cp .env.example .env
nano .env
```

Contenido:
```env
TELEGRAM_TOKEN=tu_token_aqui_123456789:ABCdef...
MAFIA_DB_PATH=data/mafia.db
```

### 3. Lanzar el Bot

```bash
python bot/main.py
```

Deberías ver:
```
============================================================
🎮 Starting Mafia Bot
============================================================
2025-01-XX 12:00:00 [INFO] Bot is ready. Starting polling...
```

### 4. Usar el Bot en Telegram

1. **En privado**: Busca tu bot y presiona "Start"
2. **En grupo**: 
   - Añade el bot al grupo
   - Ejecuta `/crearpartida`
   - Los jugadores usan `/unirme`
   - El host configura roles con `/config`
   - Inicia con `/empezar`

### Comandos del Bot

```
/crearpartida - Crear nueva partida
/unirme       - Unirse a la partida
/salirme      - Salir de la partida
/config       - Configurar roles
/empezar      - Iniciar partida (mínimo 4 jugadores)
/estado       - Ver estado actual
/roles        - Lista de roles
/help         - Mostrar ayuda
/borrarpartida - Eliminar partida (admin/host)
```

### Configurar Roles

```
/config mafia 2         # 2 mafiosos
/config doctor 1        # 1 doctor
/config detective 1     # 1 detective
/config                 # Ver configuración actual
```

---

## 🖥️ Uso de la GUI

La GUI es perfecta para:
- 🧪 **Testing**: Probar mecánicas del juego
- 🎮 **Juego Local**: Partidas sin internet
- 🐛 **Debug**: Ver todos los roles y acciones

### Modo Debug (Recomendado para empezar)

```bash
python gui/app.py --debug
```

**Características del Modo Debug:**
- ✅ Ves todos los roles asignados
- ✅ Puedes controlar cualquier jugador
- ✅ Avanzas fases manualmente
- ✅ Ver estado completo del juego

### Modo Normal

```bash
python gui/app.py
```

**Características:**
- ✅ Información privada por jugador
- ✅ Fases automáticas con timer
- ⚠️ En construcción (usa --debug por ahora)

### Flujo de Uso en GUI

#### 1. Lobby
- Click "➕ Añadir Jugador" para crear jugadores
- Configura cantidad de cada rol
- O usa "✨ Configuración Recomendada"
- Ajusta tiempos de noche/día
- Click "▶️ EMPEZAR PARTIDA"

#### 2. Durante el Juego (Modo Debug)

**Noche:**
1. Selecciona un jugador del dropdown
2. Ve su rol y acción disponible
3. Selecciona objetivo de la lista
4. Click "✓ Confirmar Acción"
5. Repite para todos los jugadores con acciones
6. Click "⏭️ Siguiente Fase" para resolver

**Día:**
- La fase de día es informativa
- Click "⏭️ Siguiente Fase" para ir a votación

**Votación:**
1. Cada jugador vota a quién linchar
2. Click "⏭️ Siguiente Fase" para contar votos
3. Se anuncia al linchado (si hay mayoría)

**Victoria:**
- El juego detecta automáticamente si alguien ganó
- Muestra mensaje con el ganador

### Atajos de Teclado (futuros)

```
F5    - Refrescar vista
Space - Siguiente fase (debug)
Esc   - Menú de pausa
```

---

## 🎭 Roles Disponibles

### 🏘️ Pueblo (Town)

| Rol | Acción | Descripción |
|-----|--------|-------------|
| **Ciudadano** | - | Sin habilidades especiales |
| **Doctor** | 🏥 Noche | Cura a un jugador cada noche |
| **Detective** | 🔍 Noche | Investiga pistas sobre un jugador |
| **Sheriff** | 🔎 Noche | Determina si alguien es CULPABLE/INOCENTE |
| **Escort** | 💃 Noche | Bloquea la acción de un jugador |
| **Guardaespaldas** | 🛡️ Noche | Muere protegiendo a alguien |
| **Vigilante** | 🔫 Noche | Puede matar (munición limitada) |

### 😈 Mafia

| Rol | Acción | Descripción |
|-----|--------|-------------|
| **Mafioso** | 🔫 Noche | Vota por objetivo de la mafia |
| **Padrino** | 👔 Noche | Inmune a investigaciones y ataques |
| **Consorte** | 💋 Noche | Bloquea + vota mafia |
| **Chantajeador** | 🤐 Noche | Silencia + vota mafia |
| **Consigliere** | 🎩 Noche | Ve el rol exacto |

### ⚖️ Neutral

| Rol | Acción | Descripción |
|-----|--------|-------------|
| **Asesino en Serie** | 🔪 Noche | Mata cada noche, gana solo |
| **Bufón** | - | Gana si lo linchan |
| **Ejecutor** | - | Debe hacer linchar a su objetivo |

---

## 🏗️ Arquitectura

```
mafiabot/
├── core/              # Lógica pura del juego
│   ├── models.py      # Game, Player, Phase, etc.
│   ├── roles.py       # Definición de 15 roles
│   └── engine.py      # Motor del juego
│
├── persistence/       # Base de datos async
│   ├── database.py    # Repository pattern
│   └── migrations.py  # Schema SQLite
│
├── bot/              # Interfaz Telegram
│   ├── main.py       # Punto de entrada
│   ├── handlers.py   # Comandos /crearpartida, etc.
│   ├── callbacks.py  # Botones inline
│   └── jobs.py       # Tareas programadas
│
├── gui/              # Interfaz gráfica
│   ├── app.py        # Aplicación principal
│   ├── views/        # Vistas (Lobby, Game)
│   └── controllers/  # Lógica de control
│
├── utils/            # Utilidades
│   ├── logging_config.py
│   └── rate_limiter.py
│
├── data/             # Base de datos
└── logs/             # Archivos de log
```

### Principios de Diseño

1. **Separación de responsabilidades**
   - `core/` no conoce Telegram ni GUI
   - `bot/` y `gui/` son adaptadores

2. **100% Async**
   - Todo el código es asíncrono
   - No hay bloqueos

3. **Repository Pattern**
   - Cache en memoria + persistencia
   - Transacciones atómicas

4. **Type Hints**
   - Todo tipado con anotaciones

---

## 🛠️ Desarrollo

### Estructura Recomendada de Trabajo

1. **Probar mecánicas en GUI**
   ```bash
   python gui/app.py --debug
   ```
   - Crear escenario de prueba
   - Verificar que funciona correctamente

2. **Adaptar al bot de Telegram**
   - La lógica ya está en `core/`
   - Solo adaptar handlers

3. **Tests unitarios**
   ```bash
   pytest tests/test_engine.py -v
   ```

### Añadir un Nuevo Rol

1. **Editar `core/roles.py`**:
```python
ROLES["nuevo_rol"] = Role(
    key="nuevo_rol",
    name="Nuevo Rol",
    description="...",
    faction=Faction.TOWN,
    has_night_action=True,
    priority=5
)
```

2. **Añadir lógica en `core/engine.py`**:
```python
# En resolve_night()
for action in [a for a in actions if a.action_type == "nueva_accion"]:
    # Tu lógica aquí
    pass
```

3. **Actualizar handlers en `bot/callbacks.py`**:
```python
action_map = {
    "nuevo_rol": "nueva_accion",
    # ...
}
```

4. **Probar en GUI**:
```bash
python gui/app.py --debug
```

### Ejecutar Tests

```bash
# Instalar pytest
pip install pytest pytest-asyncio

# Ejecutar tests
pytest tests/ -v

# Con cobertura
pip install pytest-cov
pytest --cov=core tests/
```

### Logs

**Ver logs en tiempo real:**
```bash
tail -f logs/mafiabot.log
```

**Nivel de logging:**
```python
# En main.py o app.py
setup_logging(level=logging.DEBUG)  # Más verbose
```

---

## 🐛 Troubleshooting

### Bot no arranca

**Error: TELEGRAM_TOKEN not found**
- Verifica que `.env` existe
- Verifica el formato del token

**Error: ModuleNotFoundError**
- Verifica que los `__init__.py` existen
- Activa el entorno virtual

### GUI no abre

**Error: _tkinter.TclError**
- Linux: `sudo apt install python3-tk`
- Mac: Reinstalar Python con `brew`
- Windows: Tkinter viene incluido

**Error: No module named 'gui'**
- Ejecuta desde el directorio raíz: `python gui/app.py`
- No desde dentro de gui/

### Problemas de Juego

**No recibo mensajes privados del bot**
- Debes iniciar chat con el bot antes de empezar partida
- Ve al bot y presiona "Start"

**El bot no responde en grupos**
- Verifica que Privacy Mode está OFF en @BotFather
- Asegúrate que el bot es admin del grupo

**La GUI se congela**
- Puede ser un bug en el threading
- Reporta el error con logs

---

## 📝 Roadmap

### Corto Plazo
- [ ] Modo normal de GUI (multi-ventana)
- [ ] Tests unitarios completos
- [ ] Dashboard web (Flask)
- [ ] Más roles (Arsonist, Witch, etc.)

### Medio Plazo
- [ ] GUI cliente-servidor
- [ ] Internacionalización (i18n)
- [ ] Sistema de rankings
- [ ] Estadísticas avanzadas

### Largo Plazo
- [ ] Modo competitivo
- [ ] Integraciones (Discord, WhatsApp)
- [ ] IA para jugadores NPC
- [ ] Modo torneo

---

## 🤝 Contribuir

Pull requests son bienvenidos. Para cambios importantes:

1. Fork el repositorio
2. Crea una rama (`git checkout -b feature/nueva-caracteristica`)
3. Commit tus cambios (`git commit -am 'Añadir característica'`)
4. Push a la rama (`git push origin feature/nueva-caracteristica`)
5. Crea un Pull Request

---

## 📄 Licencia

MIT License - Ver [LICENSE](LICENSE) para detalles

---

## 👥 Créditos

- Desarrollado originalmente por [tu-nombre]
- Refactorizado con arquitectura limpia
- Basado en el juego clásico de Mafia/Werewolf

---

## 📞 Soporte

- 🐛 **Issues**: [GitHub Issues](https://github.com/tu-usuario/mafiabot/issues)
- 💬 **Telegram**: @tu_usuario
- 📧 **Email**: tu@email.com

---

## 🎯 Quick Start

```bash
# 1. Instalar
git clone https://github.com/tu-usuario/mafiabot.git
cd mafiabot
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# 2. Probar GUI
python gui/app.py --debug

# 3. O lanzar bot
echo "TELEGRAM_TOKEN=tu_token" > .env
python bot/main.py
```

¡Disfruta del juego! 🎮
