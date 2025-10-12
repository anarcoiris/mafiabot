# 🚀 Guía Completa de Lanzamiento del Mafia Bot

## 📋 Pre-requisitos

- Python 3.10 o superior
- Token de Telegram Bot (obtener en @BotFather)
- pip instalado

## 🔧 Paso 1: Estructura de Archivos

Verifica que tienes esta estructura:

```
mafiabot/
├── core/
│   ├── __init__.py          ✅ Crear
│   ├── models.py            ✅ Ya existe
│   ├── roles.py             ✅ Ya existe
│   └── engine.py            ✅ Ya existe
├── persistence/
│   ├── __init__.py          ✅ Crear
│   ├── database.py          ✅ Ya existe
│   └── migrations.py        ✅ Ya existe
├── bot/
│   ├── __init__.py          ✅ Crear
│   ├── main.py              ⚠️ Reemplazar con versión corregida
│   ├── handlers.py          ⚠️ Añadir import time
│   ├── callbacks.py         ⚠️ Añadir import Counter
│   └── jobs.py              ✅ Ya existe
├── utils/
│   ├── __init__.py          ✅ Crear
│   ├── logging_config.py    ✅ Ya existe
│   └── rate_limiter.py      ✅ Ya existe
├── data/                    📁 Crear directorio
├── logs/                    📁 Crear directorio
├── .env                     ⚠️ Crear y configurar
├── .gitignore               ✅ Crear
├── requirements.txt         ✅ Ya existe
└── README.md               ✅ Ya existe
```

## 🛠️ Paso 2: Aplicar Correcciones

### 2.1 - Añadir imports faltantes

**handlers.py** - Línea 5:
```python
import logging
import time  # ⚠️ AÑADIR
from telegram import Update
```

**callbacks.py** - Línea 5:
```python
import logging
import time
from collections import Counter  # ⚠️ AÑADIR
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
```

### 2.2 - Reemplazar main.py

Reemplaza `bot/main.py` con la versión corregida (ver artifact `main_corregido.py`)

### 2.3 - Crear __init__.py

Crea los 4 archivos `__init__.py` vacíos o con el contenido de los artifacts:
- `core/__init__.py`
- `persistence/__init__.py`
- `bot/__init__.py`
- `utils/__init__.py`

## 📁 Paso 3: Crear Directorios

```bash
mkdir -p data logs
```

## 🔐 Paso 4: Configurar Variables de Entorno

### 4.1 - Crear .env

```bash
# Crear archivo .env
touch .env
```

### 4.2 - Editar .env

```env
# Token de Telegram (obtener en @BotFather)
TELEGRAM_TOKEN=tu_token_aqui

# Ruta de la base de datos (opcional)
MAFIA_DB_PATH=data/mafia.db

# Dashboard tokens (opcional, para futuro)
MAFIA_DASH_TOKEN=un_token_secreto
ADMIN_TOKEN=otro_token_secreto
```

**⚠️ IMPORTANTE**: 
- Reemplaza `tu_token_aqui` con tu token real
- NO compartas tu .env con nadie
- Asegúrate de que .env esté en .gitignore

### 4.3 - Crear .gitignore

```bash
cat > .gitignore << 'EOF'
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
venv/
env/
ENV/

# Base de datos
data/*.db
data/*.db-*

# Logs
logs/*.log

# Variables de entorno
.env

# IDEs
.vscode/
.idea/
*.swp

# OS
.DS_Store
Thumbs.db

# Tests
.pytest_cache/
.coverage
htmlcov/
EOF
```

## 📦 Paso 5: Instalar Dependencias

### 5.1 - Crear entorno virtual (recomendado)

```bash
# Linux/Mac
python -m venv venv
source venv/bin/activate

# Windows
python -m venv venv
venv\Scripts\activate
```

### 5.2 - Instalar requirements

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 5.3 - Verificar instalación

```bash
python -c "import telegram; print(f'✅ python-telegram-bot {telegram.__version__}')"
python -c "import aiosqlite; print('✅ aiosqlite OK')"
python -c "from dotenv import load_dotenv; print('✅ python-dotenv OK')"
```

## 🧪 Paso 6: Verificar Imports

Ejecuta estos comandos para verificar que no hay errores de import:

```bash
python -c "from core import GameEngine, ROLES; print('✅ core OK')"
python -c "from persistence import get_repository; print('✅ persistence OK')"
python -c "from bot import GameHandlers; print('✅ bot OK')"
python -c "from utils import setup_logging; print('✅ utils OK')"
```

Si alguno falla, verifica los imports y __init__.py

## 🚀 Paso 7: Lanzar el Bot

### 7.1 - Ejecución simple

```bash
python bot/main.py
```

### 7.2 - Verificar logs

Deberías ver algo como:

```
============================================================
🎮 Starting Mafia Bot
============================================================
2025-01-XX 12:00:00 [INFO] __main__: Python version: 3.10.x
2025-01-XX 12:00:00 [INFO] __main__: Working directory: /path/to/mafiabot
2025-01-XX 12:00:00 [INFO] __main__: Repository initialized: data/mafia.db
2025-01-XX 12:00:00 [INFO] __main__: Handlers registered successfully
2025-01-XX 12:00:00 [INFO] __main__: Bot is ready. Starting polling...
2025-01-XX 12:00:00 [INFO] __main__: Press Ctrl+C to stop
```

## ✅ Paso 8: Probar el Bot

### 8.1 - En Telegram

1. Busca tu bot por su username
2. Presiona "Start"
3. Crea un grupo de prueba
4. Añade el bot al grupo
5. Ejecuta comandos:

```
/crearpartida
/unirme
/estado
/help
```

### 8.2 - Verificar que funciona

- El bot debe responder a `/help`
- Debe poder crear partida con `/crearpartida`
- Los jugadores deben poder unirse con `/unirme`

## 🐛 Troubleshooting

### Error: "TELEGRAM_TOKEN not found"
- Verifica que `.env` existe
- Verifica que el token está en el formato correcto
- Verifica que no hay espacios extra

### Error: "ModuleNotFoundError: No module named 'core'"
- Verifica que estás en el directorio correcto
- Verifica que los `__init__.py` existen
- Prueba: `export PYTHONPATH="${PYTHONPATH}:$(pwd)"`

### Error: "No such table: games"
- El bot creará la DB automáticamente
- Si falla, elimina `data/mafia.db` y reinicia

### El bot no responde en grupos
- Verifica que el bot tiene permisos de administrador
- Asegúrate de que el modo privado está deshabilitado (Privacy Mode OFF en @BotFather)

### No recibo mensajes privados del bot
- Debes iniciar conversación privada con el bot antes de empezar la partida
- Ve al bot en Telegram y presiona "Start"

## 🔄 Reiniciar el Bot

```bash
# Detener: Ctrl+C

# Reiniciar
python bot/main.py
```

Las partidas activas se restaurarán automáticamente.

## 📊 Verificar Base de Datos

```bash
# Instalar sqlite3 si no lo tienes
# Linux: sudo apt install sqlite3
# Mac: brew install sqlite

# Inspeccionar DB
sqlite3 data/mafia.db

# Comandos útiles en sqlite3
.tables                    # Ver tablas
SELECT * FROM games;       # Ver partidas
SELECT * FROM players;     # Ver jugadores
.quit                      # Salir
```

## 🐳 Alternativa: Docker

Si prefieres usar Docker:

```bash
# Construir imagen
docker build -t mafiabot .

# Ejecutar
docker run -d \
  --name mafiabot \
  -e TELEGRAM_TOKEN=tu_token \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/logs:/app/logs \
  mafiabot
```

## 📝 Logs

Los logs se guardan en:
- `logs/mafiabot.log` (archivo rotativo)
- Consola (stdout)

Ver logs en tiempo real:
```bash
tail -f logs/mafiabot.log
```

## ✅ Checklist Final

- [ ] Python 3.10+ instalado
- [ ] Token de Telegram obtenido
- [ ] Estructura de directorios correcta
- [ ] Todos los __init__.py creados
- [ ] Imports corregidos (handlers.py, callbacks.py)
- [ ] main.py reemplazado con versión corregida
- [ ] .env configurado con token real
- [ ] .gitignore creado
- [ ] requirements.txt instalado
- [ ] Directorios data/ y logs/ creados
- [ ] Bot arranca sin errores
- [ ] Bot responde a /help
- [ ] Puede crear partidas

## 🎉 ¡Listo!

Si todos los pasos funcionaron, tu bot está listo para jugar. 

Para comandos avanzados y configuración de roles, consulta el README.md principal.
