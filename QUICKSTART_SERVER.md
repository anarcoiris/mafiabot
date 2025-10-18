# 🚀 Quick Start: Multiplayer Server

This guide will get you up and running with the Mafia Bot multiplayer server in 5 minutes.

## Sprint 1 Complete ✅

The following features are now implemented and ready to use:

- ✅ WebSocket server with room management
- ✅ Player authentication
- ✅ Multiple game rooms
- ✅ Lobby system (create/join/leave)
- ✅ Game state synchronization
- ✅ Night actions and voting
- ✅ Chat system
- ✅ Database persistence (optional)
- ✅ Connection management with reconnection handling

## Installation

### 1. Install Dependencies

```bash
# Install all dependencies (includes server requirements)
pip install -r requirements.txt

# Or just server-specific dependencies
pip install -r requirements_server.txt
```

### 2. Verify Installation

```bash
python -c "import websockets; print('✅ websockets OK')"
python -c "import jwt; print('✅ PyJWT OK')"
```

## Running the Server

### Basic Usage (No Persistence)

Perfect for testing and development:

```bash
python server/game_server.py --no-persist
```

You should see:

```
2025-10-14 10:00:00 [INFO] Starting Mafia Game Server on 0.0.0.0:8765
2025-10-14 10:00:00 [INFO] Database initialized: None
2025-10-14 10:00:00 [INFO] Server initialized successfully
2025-10-14 10:00:00 [INFO] ✅ Server is ready and listening for connections
```

### With Database Persistence

Games will survive server restarts:

```bash
python server/game_server.py --db data/mafia_server.db
```

### Custom Configuration

```bash
# Custom host and port
python server/game_server.py --host 0.0.0.0 --port 9000

# All options
python server/game_server.py --host 0.0.0.0 --port 8765 --db data/mafia_server.db
```

## Testing the Server

### Option 1: Automated Tests

```bash
# Start server in one terminal
python server/game_server.py --no-persist

# Run tests in another terminal
python server/test_server.py
```

Expected output:

```
🧪 Testing basic connection...
✅ Connected to ws://localhost:8765
→ Sent CONNECT message
← Received success: {'message': 'Connected successfully', 'player_id': 1, ...}
✅ Authenticated as player 1

🧪 Testing game creation...
✅ Connected as player 1
→ Sent CREATE_GAME message
← Received game_created: {'game_id': 1001, 'host_id': 1}
✅ Game created: 1001

...

Test Summary
============================================================
✅ PASS - Basic Connection
✅ PASS - Game Creation
✅ PASS - Multiple Players
✅ PASS - List Games

Passed: 4/4

🎉 All tests passed!
```

### Option 2: Manual Testing with wscat

Install wscat:

```bash
npm install -g wscat
```

Connect and test:

```bash
wscat -c ws://localhost:8765
```

Then send JSON messages:

```json
// Connect
{"type": "connect", "data": {"player_name": "Alice"}, "message_id": "1"}

// Create game
{"type": "create_game", "data": {"host_name": "Alice"}, "message_id": "2"}

// List games
{"type": "list_games", "data": {}, "message_id": "3"}
```

## Architecture Overview

```
┌──────────────────────────────────────────────────────────┐
│                  MafiaGameServer                         │
│                                                          │
│  ┌────────────────┐  ┌─────────────────┐               │
│  │ Connection     │  │ Room            │               │
│  │ Manager        │  │ Manager         │               │
│  │                │  │                 │               │
│  │ - Tracks WSs   │  │ - Multiple games│               │
│  │ - Auth         │  │ - State mgmt    │               │
│  │ - Broadcast    │  │ - Persistence   │               │
│  └────────────────┘  └─────────────────┘               │
│                                                          │
│  ┌──────────────────────────────────────┐               │
│  │          Game Engine                 │               │
│  │  (Reuses core/engine.py)             │               │
│  └──────────────────────────────────────┘               │
└──────────────────────────────────────────────────────────┘
                        ▲
                        │ WebSocket (JSON)
                        │
        ┌───────────────┼───────────────┐
        │               │               │
    Client 1        Client 2        Client N
```

## File Structure

```
server/
├── __init__.py              # Package init
├── game_server.py           # Main server (run this)
├── connection_manager.py    # WebSocket connection handling
├── room_manager.py          # Multiple game room management
├── auth.py                  # Authentication & tokens
├── test_server.py           # Test script
└── README.md                # Detailed docs

network/
├── __init__.py
├── protocol.py              # Message protocol definitions
└── messages.py              # Message constructors
```

## Protocol Quick Reference

### Client → Server Messages

| Message Type | Purpose | Required Fields |
|-------------|---------|-----------------|
| `connect` | Authenticate | `player_name` |
| `create_game` | Create new game | `host_name`, `roles_config` (opt) |
| `join_game` | Join existing game | `game_id`, `player_name` |
| `leave_game` | Leave game | `game_id` |
| `start_game` | Start game (host) | `game_id` |
| `night_action` | Submit night action | `game_id`, `target_id` |
| `mafia_vote` | Mafia kill vote | `game_id`, `target_id` |
| `day_vote` | Day lynch vote | `game_id`, `target_id` |
| `chat_message` | Send chat | `game_id`, `text`, `channel` |
| `list_games` | Get active games | - |

### Server → Client Messages

| Message Type | Purpose | When Sent |
|-------------|---------|-----------|
| `success` | Action succeeded | After most requests |
| `error` | Action failed | On errors |
| `game_created` | Game created | After create_game |
| `player_joined` | Player joined | Broadcast when join |
| `player_left` | Player left | Broadcast when leave |
| `game_started` | Game started | Broadcast when start |
| `game_state_update` | Full game state | Periodically |
| `phase_changed` | Phase transition | On phase change |
| `player_died` | Death notification | After resolution |
| `chat_broadcast` | Chat message | From any player |

## Example Game Flow

```
Terminal 1 (Server):
$ python server/game_server.py --no-persist

Terminal 2 (Player 1 - Host):
$ wscat -c ws://localhost:8765
> {"type": "connect", "data": {"player_name": "Alice"}, "message_id": "1"}
< {"type": "success", "data": {"player_id": 1, ...}}
> {"type": "create_game", "data": {"host_name": "Alice"}, "message_id": "2"}
< {"type": "game_created", "data": {"game_id": 1001, ...}}

Terminal 3 (Player 2):
$ wscat -c ws://localhost:8765
> {"type": "connect", "data": {"player_name": "Bob"}, "message_id": "1"}
< {"type": "success", "data": {"player_id": 2, ...}}
> {"type": "join_game", "data": {"game_id": 1001, "player_name": "Bob"}, "message_id": "2"}
< {"type": "player_joined", "data": {"game_id": 1001, "player_id": 2, ...}}

Terminal 2 (Player 1 - Host):
< {"type": "player_joined", "data": {"game_id": 1001, "player_id": 2, ...}}
(repeats for players 3 and 4...)
> {"type": "start_game", "data": {"game_id": 1001}, "message_id": "3"}
< {"type": "game_started", "data": {...}}
< {"type": "game_state_update", "data": {"your_role": "doctor", ...}}

(Game proceeds with night actions, voting, etc.)
```

## Troubleshooting

### Server won't start

**Error: `Address already in use`**
```bash
# Check what's using the port
netstat -an | findstr 8765  # Windows
lsof -i :8765               # Mac/Linux

# Use a different port
python server/game_server.py --port 8766
```

**Error: `ModuleNotFoundError: No module named 'websockets'`**
```bash
pip install websockets
```

### Can't connect from another machine

**Firewall blocking:**
```bash
# Windows
netsh advfirewall firewall add rule name="Mafia Server" dir=in action=allow protocol=TCP localport=8765

# Linux
sudo ufw allow 8765/tcp

# Mac
# System Preferences → Security & Privacy → Firewall → Options
```

**Check server is listening on 0.0.0.0:**
```bash
python server/game_server.py --host 0.0.0.0 --port 8765
```

### Database errors

**Error: `Failed to persist game`**
- Ensure `data/` directory exists and is writable
- Try `--no-persist` to bypass database temporarily

## Next Steps

### Sprint 2: GUI Client (Next Phase)

Sprint 2 will add:
- GUI client that connects to this server
- Connection dialog in tkinter app
- Network game state synchronization
- Real-time updates

### For Now: Testing

The server is fully functional for testing with WebSocket clients:

1. **Automated tests**: `python server/test_server.py`
2. **Manual testing**: Use `wscat` or write simple Python client
3. **Load testing**: Connect multiple clients simultaneously

### Documentation

- Server details: `server/README.md`
- Protocol reference: `network/protocol.py`
- Message types: `network/messages.py`

## Support

If you encounter issues:

1. Check the logs for error messages
2. Verify all dependencies are installed
3. Test with `--no-persist` first
4. Review `server/README.md` for detailed docs
5. Run `python server/test_server.py` for diagnostics

---

**Status**: Sprint 1 Complete ✅
**Next**: Sprint 2 - GUI Client Implementation

Enjoy the multiplayer server! 🎮
