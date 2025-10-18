# Mafia Bot Multiplayer Server

WebSocket server implementation for multiplayer Mafia game. Allows multiple players to connect over the internet and play together.

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
# Or server-specific only:
pip install -r requirements_server.txt
```

### 2. Run the Server

```bash
# Basic (no persistence)
python server/game_server.py --no-persist

# With database persistence
python server/game_server.py --db data/mafia_server.db

# Custom host/port
python server/game_server.py --host 0.0.0.0 --port 8765
```

### 3. Test Connection

You can test the server using a WebSocket client or the GUI client (coming in Sprint 2).

## Server Architecture

```
┌─────────────────────────────────┐
│     MafiaGameServer             │
│  - WebSocket handler            │
│  - Message routing              │
└────────┬─────────┬─────────────┘
         │         │
    ┌────▼───┐ ┌──▼───────────┐
    │ Conn   │ │ Room         │
    │ Manager│ │ Manager      │
    └────┬───┘ └──┬───────────┘
         │        │
    ┌────▼────────▼───────┐
    │  GameEngine         │
    │  - core/engine.py   │
    │  - core/models.py   │
    └─────────────────────┘
```

## Protocol

The server uses JSON WebSocket messages. See `network/protocol.py` for full documentation.

### Message Types

**Client → Server:**
- `CONNECT` - Authenticate and get player ID
- `CREATE_GAME` - Create a new game room
- `JOIN_GAME` - Join an existing game
- `LEAVE_GAME` - Leave current game
- `START_GAME` - Start the game (host only)
- `NIGHT_ACTION` - Submit night action
- `MAFIA_VOTE` - Mafia vote for kill target
- `DAY_VOTE` - Vote during day phase
- `CHAT_MESSAGE` - Send chat message
- `LIST_GAMES` - Get list of active games

**Server → Client:**
- `GAME_STATE_UPDATE` - Current game state
- `PLAYER_JOINED` - Player joined game
- `PLAYER_LEFT` - Player left game
- `GAME_STARTED` - Game has started
- `PHASE_CHANGED` - Phase transition
- `PLAYER_DIED` - Player death notification
- `CHAT_BROADCAST` - Chat message to all
- `INVESTIGATION_RESULT` - Private investigation result
- `ERROR` - Error message
- `SUCCESS` - Success confirmation

### Example Message Flow

```json
// Client connects
→ {
  "type": "connect",
  "data": {"player_name": "Alice"},
  "message_id": "uuid-1234"
}

← {
  "type": "success",
  "data": {
    "message": "Connected successfully",
    "player_id": 1,
    "player_name": "Alice"
  },
  "reply_to": "uuid-1234"
}

// Client creates game
→ {
  "type": "create_game",
  "data": {
    "host_name": "Alice",
    "roles_config": {"mafia": 2, "doctor": 1, "detective": 1}
  }
}

← {
  "type": "game_created",
  "data": {"game_id": 1001, "host_id": 1}
}

// Other players join
→ {
  "type": "join_game",
  "data": {"game_id": 1001, "player_name": "Bob"}
}

← {
  "type": "player_joined",
  "data": {
    "game_id": 1001,
    "player_id": 2,
    "player_name": "Bob"
  }
}

// Host starts game
→ {
  "type": "start_game",
  "data": {"game_id": 1001}
}

← {
  "type": "game_started",
  "data": {"game_id": 1001, "players_count": 5}
}

// Each player receives their role
← {
  "type": "game_state_update",
  "data": {
    "game_id": 1001,
    "phase": "night",
    "your_player_id": 1,
    "your_role": "doctor",
    "players": [...]
  }
}
```

## Configuration

### Command Line Arguments

- `--host` - Host address to bind to (default: 0.0.0.0)
- `--port` - Port to listen on (default: 8765)
- `--db` - Path to SQLite database (default: data/mafia_server.db)
- `--no-persist` - Run without database persistence

### Environment Variables

You can also configure via environment variables:

```bash
export MAFIA_SERVER_HOST=0.0.0.0
export MAFIA_SERVER_PORT=8765
export MAFIA_DB_PATH=data/mafia_server.db
```

## Features

### Current (Sprint 1)
- ✅ WebSocket server with multiple game rooms
- ✅ Player authentication (simple ID-based)
- ✅ Lobby system (create/join/leave games)
- ✅ Game state synchronization
- ✅ Night actions and voting
- ✅ Chat system
- ✅ Database persistence (optional)
- ✅ Automatic reconnection handling
- ✅ Inactive game cleanup

### Planned (Sprint 3)
- ⏳ JWT token authentication
- ⏳ TLS/SSL support
- ⏳ Public/private game rooms
- ⏳ Spectator mode
- ⏳ Admin dashboard
- ⏳ Player ban/kick
- ⏳ Game replay/history

## Deployment

### Docker (Coming Soon)

```bash
docker build -t mafiabot-server .
docker run -d \
  -p 8765:8765 \
  -v $(pwd)/data:/app/data \
  mafiabot-server
```

### Production

For production, use a process manager like systemd or supervisor:

```ini
# /etc/systemd/system/mafiabot-server.service
[Unit]
Description=Mafia Bot Multiplayer Server
After=network.target

[Service]
Type=simple
User=mafiabot
WorkingDirectory=/opt/mafiabot
ExecStart=/opt/mafiabot/venv/bin/python server/game_server.py
Restart=always

[Install]
WantedBy=multi-user.target
```

## Security Considerations

### Current Implementation
- Player IDs are sequential (not secure for production)
- No TLS encryption yet
- No rate limiting on connections
- No input sanitization beyond basic validation

### For Production (Sprint 3)
- Use JWT tokens for authentication
- Enable TLS/SSL for encrypted connections
- Add rate limiting per IP
- Sanitize all user inputs
- Implement proper session management

## Monitoring

### Logs

The server logs all important events:

```
2025-10-14 10:00:00 [INFO] Starting Mafia Game Server on 0.0.0.0:8765
2025-10-14 10:00:01 [INFO] ✅ Server is ready and listening for connections
2025-10-14 10:00:05 [INFO] Client connected: ('192.168.1.100', 54321)
2025-10-14 10:00:06 [INFO] Player 1 (Alice) authenticated
2025-10-14 10:00:10 [INFO] Game 1001 created by player 1 (Alice)
```

### Stats

You can query server stats via internal methods:

```python
# In future admin dashboard
print(f"Active games: {server.room_manager.game_count}")
print(f"Connected players: {server.connection_manager.authenticated_count}")
```

## Troubleshooting

### Server won't start

**Error**: `Address already in use`
- Another process is using port 8765
- Change port: `--port 8766`

**Error**: `Permission denied`
- Ports < 1024 require root on Linux
- Use port > 1024 or run with sudo

### Clients can't connect

**Check firewall:**
```bash
# Linux
sudo ufw allow 8765/tcp

# Windows
netsh advfirewall firewall add rule name="Mafia Server" dir=in action=allow protocol=TCP localport=8765
```

**Check if server is listening:**
```bash
netstat -an | grep 8765
# or
ss -tlnp | grep 8765
```

### Game state not persisting

- Ensure database path is writable
- Check logs for database errors
- Try running with `--no-persist` to bypass DB issues

## Development

### Running Tests

```bash
# Test server connectivity
python -m pytest tests/test_server.py

# Test protocol
python -m pytest tests/test_protocol.py
```

### Adding New Message Types

1. Add to `MessageType` enum in `network/protocol.py`
2. Create message constructor in `network/messages.py`
3. Add handler in `MafiaGameServer.handle_message()`
4. Update documentation

## Next Steps (Sprint 2)

The next sprint will add:
- GUI client that connects to this server
- Connection UI in the tkinter app
- Automatic game state synchronization
- Network mode toggle (local vs. server)

See the main project README for the complete roadmap.
