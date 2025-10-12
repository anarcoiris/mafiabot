# 🔧 Correcciones de Imports Necesarias

## 1. handlers.py - Añadir import de time

**Línea 5** (después de `import logging`):
```python
import logging
import time  # ⚠️ AÑADIR ESTA LÍNEA
from telegram import Update
from telegram.ext import ContextTypes
```

**Ubicación del error**: Línea ~275
```python
game.phase_deadline = int(time.time()) + game.night_seconds
```

---

## 2. callbacks.py - Añadir import de Counter

**Línea 5** (después de `import time`):
```python
import logging
import time
from collections import Counter  # ⚠️ AÑADIR ESTA LÍNEA
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
```

**Ubicación del error**: Línea ~375
```python
votes = Counter(game.mafia_votes.values())
```

---

## 3. main.py - Verificar estructura de inicialización

El archivo actual tiene un problema con el event loop. Necesita refactorización.

**Problema actual** (líneas 72-76):
```python
# ❌ Crea un loop separado del que usará el bot
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)
loop.run_until_complete(init_app())
```

**Solución**: La inicialización debe hacerse en `post_init`, no antes.

Ver archivo `main_corregido.py` para la versión correcta.

---

## Verificación después de aplicar cambios

```bash
# Verificar imports
python -c "from core import GameEngine; print('✅ core OK')"
python -c "from persistence import get_repository; print('✅ persistence OK')"
python -c "from bot import GameHandlers; print('✅ bot OK')"
python -c "from utils import setup_logging; print('✅ utils OK')"
```
