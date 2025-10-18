# 🎭 Mafia Bot para Telegram

Bot completo de Telegram para jugar al juego de Mafia (también conocido como Werewolf) en grupos.

## ✨ Características

- **15+ roles diferentes** (Town, Mafia, Neutral)
- **Acciones nocturnas** con botones inline
- **Votación diurna** interactiva
- **Persistencia** completa con SQLite
- **Re-hidratación** automática tras reinicio
- **Rate limiting** para prevenir spam
- **Logging** estructurado
- **Arquitectura limpia** sin imports circulares

## 🏗️ Arquitectura

```
mafiabot/
├── core/               # Lógica pura del juego
│   ├── models.py      # Game, Player, Role, Phase
│   ├── roles.py       # Definición de todos los roles
│   └── engine.py      # Motor del juego (resolución)
├── persistence/        # Base de datos
│   ├── database.py    # Repository async (aiosqlite)
│   └── migrations.py  # Schema y migraciones
├── bot/               # Telegram bot
│   ├── main.py        # Punto de entrada
│   ├── handlers.py    # Comandos (/crearpartida, etc.)
│   ├── callbacks.py   # Botones inline
│   └── jobs.py        # Tareas programadas
└── utils/             # Utilidades
    ├── logging_config.py
    └── rate_limiter.py
```

## 🚀 Instalación

### Requisitos

- Python 3.10+
- Token de bot de Telegram (obtener de [@BotFather](https://t.me/BotFather))

### Paso a paso

1. **Clonar el repositorio**
```bash
git clone <tu-repo>
cd mafiabot
```

2. **Crear entorno virtual**
```bash
python -m venv venv
source venv/bin/activate  # En Windows: venv\Scripts\activate
```

3. **Instalar dependencias**
```bash
pip install -r requirements.txt
```

4. **Configurar variables de entorno**
```bash
cp .env.example .env
# Edita .env y añade tu TELEGRAM_TOKEN
```

5. **Ejecutar el bot**
```bash
python bot/main.py
```

## 🎮 Cómo jugar

### Configurar una partida

1. **Crear partida en un grupo**
   ```
   /crearpartida
   ```

2. **Los jugadores se unen**
   ```
   /unirme
   ```

3. **Configurar roles (opcional)**
   ```
   /config mafia 2
   /config doctor 1
   /config detective 1
   ```

4. **Ver configuración actual**
   ```
   /config
   ```

5. **Iniciar partida (mínimo 4 jugadores)**
   ```
   /empezar
   ```

### Durante el juego

- **Noche**: Jugadores con habilidades reciben botones por DM
- **Día**: Discusión libre en el grupo
- **Votación**: Botones para votar a quién linchar
- **Repetir** hasta que una facción gane

### Comandos adicionales

```
/estado          - Ver estado actual de la partida
/roles           - Lista de roles disponibles
/roles detective - Información de un rol específico
/borrarpartida   - Eliminar partida (solo admin/host)
/help            - Mostrar ayuda
```

## 🎭 Roles Disponibles

### 💚 TOWN (Pueblo)

| Rol | Descripción |
|-----|-------------|
| **Ciudadano** | Sin habilidad especial, vota durante el día |
| **Doctor** | Cura a un jugador cada noche |
| **Detective** | Investiga a un jugador (pistas) |
| **Sheriff** | Investiga si es CULPABLE o INOCENTE |
| **Escort** | Bloquea la habilidad de alguien |
| **Guardaespaldas** | Protege a alguien, muriendo en su lugar |
| **Vigilante** | Puede disparar (3 balas) |
| **Veterano** | Puede entrar en alerta (mata visitantes) |

### 🔴 MAFIA

| Rol | Descripción |
|-----|-------------|
| **Mafioso** | Vota con la mafia para matar |
| **Padrino** | Líder, inmune, indetectable |
| **Consorte** | Mafioso con habilidad de bloqueo |
| **Consigliere** | Investigador de la mafia (ve roles exactos) |
| **Chantajeador** | Silencia a alguien durante el día |

### ⚪ NEUTRAL

| Rol | Descripción |
|-----|-------------|
| **Asesino en Serie** | Mata cada noche, gana si es el único vivo |
| **Bufón** | Gana si es linchado |
| **Superviviente** | Solo quiere sobrevivir (4 chalecos) |
| **Ejecutor** | Debe conseguir linchar a su objetivo |

## 🔧 Configuración Avanzada

### Variables de entorno

```bash
# Token del bot (REQUERIDO)
TELEGRAM_TOKEN=tu_token_aqui

# Base de datos
MAFIA_DB_PATH=data/mafia.db

# Logging
LOG_LEVEL=INFO
LOG_FILE=logs/mafiabot.log

# Dashboard (opcional)
DASHBOARD_ENABLED=true
DASHBOARD_PORT=8006
DASHBOARD_TOKEN=secreto
```

### Tiempos por defecto

Puedes ajustar los tiempos en `core/models.py`:

```python
night_seconds: int = 300        # 5 minutos
day_seconds: int = 600          # 10 minutos
periodic_reminder_seconds: int = 120  # 2 minutos
```

## 🐳 Docker

```dockerfile
FROM python:3.10-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "bot/main.py"]
```

```bash
docker build -t mafiabot .
docker run -d --name mafiabot \
  -e TELEGRAM_TOKEN=tu_token \
  -v $(pwd)/data:/app/data \
  mafiabot
```

## 📊 Base de Datos

El bot usa SQLite con las siguientes tablas:

- `games` - Partidas activas
- `players` - Jugadores en cada partida
- `pending_actions` - Votos y acciones pendientes
- `game_events` - Audit log (opcional)

### Backups

```bash
# Backup manual
cp data/mafia.db data/mafia_backup_$(date +%Y%m%d).db

# Backup automático (cron)
0 3 * * * cp /ruta/data/mafia.db /ruta/backups/mafia_$(date +\%Y\%m\%d).db
```

## 🛠️ Desarrollo

### Estructura del código

- **Sin imports circulares**: Inyección de dependencias
- **Solo async**: aiosqlite en toda la persistencia
- **Repository pattern**: Abstracción de la base de datos
- **Event loop único**: Gestionado por python-telegram-bot
- **Type hints**: En todos los métodos públicos

### Añadir un nuevo rol

1. Definir en `core/roles.py`:
```python
ROLES["nuevo_rol"] = Role(
    key="nuevo_rol",
    name="Nuevo Rol",
    description="Descripción...",
    faction=Faction.TOWN,
    has_night_action=True,
    priority=5
)
```

2. Agregar lógica en `core/engine.py` (si tiene acción especial)

3. Agregar handler en `bot/callbacks.py` (si necesita botones)

### Tests (TODO)

```bash
pytest tests/
```

## 🐛 Solución de Problemas

### El bot no responde a comandos

- Verifica que el token sea correcto
- Verifica que el bot esté agregado al grupo
- Verifica que el bot tenga permisos de enviar mensajes

### No recibo mensajes privados del bot

- Debes iniciar chat privado con el bot **antes** de `/empezar`
- Usa `/start` en chat privado con el bot

### Partida quedó atascada

```
/borrarpartida  # Como admin o host
```

O directamente en la base de datos:
```sql
DELETE FROM games WHERE chat_id = <ID>;
```

### Logs

```bash
tail -f logs/mafiabot.log
```

## 📝 Changelog

### v2.0.0 (Refactorización completa)
- ✅ Arquitectura modular sin imports circulares
- ✅ Persistencia 100% async con aiosqlite
- ✅ Repository pattern
- ✅ 15 roles implementados
- ✅ Rate limiting
- ✅ Logging estructurado
- ✅ Re-hidratación automática post-reinicio

### v1.0.0 (Legacy)
- Versión inicial con issues arquitectónicos

## 🤝 Contribuir

1. Fork el proyecto
2. Crea tu rama (`git checkout -b feature/AmazingFeature`)
3. Commit tus cambios (`git commit -m 'Add: amazing feature'`)
4. Push a la rama (`git push origin feature/AmazingFeature`)
5. Abre un Pull Request

## 📄 Licencia

MIT License - ve el archivo `LICENSE` para detalles

## 👥 Créditos

- Basado en el juego social "Mafia" / "Werewolf"
- Desarrollado con [python-telegram-bot](https://python-telegram-bot.org/)

## 📞 Soporte

- Issues: [GitHub Issues](link)
- Telegram: @tu_usuario

---

**¡Disfruta jugando!** 🎉