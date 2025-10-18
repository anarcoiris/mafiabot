# 🌐 Network Mode User Guide

## Overview

The Mafia Bot GUI now supports **multiplayer network mode**, allowing players to connect over the internet and play together! This guide explains how to use the new network features.

## Quick Start

### For Players Joining a Game

1. **Start the GUI with network flag:**
   ```bash
   python gui/app.py --connect ws://server-address:8765
   ```

2. **Or use the connection dialog:**
   ```bash
   python gui/app.py
   # Then: File → Connect to Server
   ```

3. **Enter your player name**

4. **Join an existing game or wait for host to start**

### For Game Hosts

1. **Start the server:**
   ```bash
   python server/game_server.py
   ```

2. **Start the GUI and connect:**
   ```bash
   python gui/app.py --connect ws://localhost:8765
   ```

3. **Create a game in the lobby**

4. **Share your server address with other players**

5. **Start the game when everyone has joined**

## Launch Modes

### Local Mode (Default)
```bash
python gui/app.py
# or
python gui/app.py --debug
```
- **Single machine**, all players on same computer
- Uses in-memory game state
- Perfect for testing with bot players
- No network required

### Network Client Mode
```bash
python gui/app.py --connect ws://hostname:port
python gui/app.py --connect ws://192.168.1.100:8765 --player Alice
```
- **Connect to remote server**
- Multiple players from different machines
- Real-time synchronization
- Chat works across network

### Embedded Server Mode
```bash
python gui/app.py --host
python gui/app.py --host --port 9000
```
- **Starts local server + client**
- Convenience mode for hosting
- Other players can still connect remotely
- Server runs in background

### Server Only
```bash
python server/game_server.py
python server/game_server.py --port 8765 --db data/server.db
```
- **Headless server** (no GUI)
- For dedicated hosting
- Supports multiple games simultaneously
- Persistent with database

## Command-Line Arguments

### GUI Arguments

| Argument | Description | Example |
|----------|-------------|---------|
| `--connect URI` | Connect to remote server | `--connect ws://localhost:8765` |
| `--player NAME` | Set player name | `--player Alice` |
| `--host` | Start embedded server | `--host` |
| `--port PORT` | Server port (with --host) | `--port 9000` |
| `--debug` | Debug mode (show all roles) | `--debug` |

### Server Arguments

| Argument | Description | Example |
|----------|-------------|---------|
| `--host HOST` | Bind address | `--host 0.0.0.0` |
| `--port PORT` | Listen port | `--port 8765` |
| `--db PATH` | Database path | `--db data/mafia.db` |
| `--no-persist` | No database | `--no-persist` |

## Features

### ✅ What Works in Network Mode

- **Full game functionality**
  - All 15+ roles work identically
  - Night actions
  - Day voting
  - Chat system
  - Phase timers

- **Real-time updates**
  - Instant state synchronization
  - Chat messages appear immediately
  - Phase changes sync across all clients

- **Automatic reconnection**
  - Connection drops are handled gracefully
  - Automatic retry with exponential backoff
  - Game state restored on reconnect

- **Multiple games**
  - Server supports many concurrent games
  - Each game is isolated
  - Players can only be in one game at a time

### ⚠️ Current Limitations

- **No bot players in network mode** (server-controlled only)
- **No mid-game join** (must join during lobby)
- **Host powers**: Only host can start game, configure roles
- **No spectators** yet (planned for Sprint 3)

## Connection Dialog

When you select "Connect to Server" from the menu or start with `--connect`, you'll see:

```
┌────────────────────────────────────┐
│  🌐 Conectar al Servidor           │
├────────────────────────────────────┤
│  Servidor:                         │
│  [ws://localhost:8765           ]  │
│                                    │
│  Jugador:                          │
│  [Alice                         ]  │
│                                    │
│  Servidores Recientes:             │
│  • ws://localhost:8765             │
│  • ws://192.168.1.100:8765         │
│                                    │
│  Estado: ● Desconectado            │
│                                    │
│  [Conectar] [Local Rápido] [Cancelar]
└────────────────────────────────────┘
```

**Fields:**
- **Servidor**: WebSocket URI (ws:// or wss://)
- **Jugador**: Your display name (shown to other players)
- **Recientes**: Double-click to auto-fill

**Buttons:**
- **Conectar**: Attempt connection
- **Local Rápido**: Quick connect to ws://localhost:8765
- **Cancelar**: Close dialog

## Network Status Indicator

In the GUI, you'll see a connection status indicator:

```
● Conectado (localhost:8765) | Jugador: Alice (ID: 1)
```

**Status colors:**
- 🟢 **Green**: Connected and authenticated
- 🟠 **Orange**: Connecting or reconnecting
- 🔴 **Red**: Error
- ⚫ **Gray**: Disconnected

## Game Flow in Network Mode

### 1. Connect to Server
```bash
python gui/app.py --connect ws://server:8765
```

### 2. Lobby Phase
- **Host**: Click "Create Game"
- **Players**: See available games, click "Join"
- **Configure**: Host sets roles (default: 1 mafia, 3 citizens)
- **Wait**: Until minimum 4 players join

### 3. Game Start
- **Host**: Click "Start Game" when ready
- **All players**: Receive role assignment privately
- **Night phase**: Begins automatically

### 4. Night Phase
- **Players with night actions**: Submit target selection
- **Mafia**: Vote on kill target (visible only to mafia)
- **Timer**: Countdown to auto-resolution
- **Resolve**: When time expires or all actions submitted

### 5. Day Phase
- **Discussion**: Use chat to discuss
- **Investigation results**: Shown privately to investigators
- **Deaths announced**: Server broadcasts who died

### 6. Voting Phase
- **Vote**: Click on player to lynch
- **Timer**: Countdown to resolution
- **Resolve**: Highest votes gets lynched (tie = no lynch)

### 7. Victory
- **Check**: After each night/vote resolution
- **Announce**: Server broadcasts winner
- **Return to lobby**: Or disconnect

## Troubleshooting

### Can't Connect to Server

**Problem**: "Connection timeout" or "Connection refused"

**Solutions:**
1. Verify server is running: `python server/game_server.py`
2. Check server address is correct
3. Test with localhost first: `ws://localhost:8765`
4. Check firewall settings
5. Ensure port is not blocked

```bash
# Test server is listening
netstat -an | grep 8765   # Linux/Mac
netstat -an | findstr 8765  # Windows
```

### Connection Drops During Game

**Problem**: "● Reconectando..." message appears

**What happens:**
- Client automatically attempts to reconnect
- Your actions are queued locally
- When reconnected, state is synchronized
- Game continues where you left off

**If it fails:**
- Check your internet connection
- Verify server is still running
- Try manual reconnect: Menu → Reconnect

### "Game Not Found" Error

**Problem**: Server says game doesn't exist

**Causes:**
- Game was deleted (no players left)
- Server restarted without persistence
- You're connecting to wrong server

**Solutions:**
- Have host create a new game
- Use server with `--db` flag for persistence

### Permission Denied

**Problem**: Server won't start on port

**Solution:**
```bash
# Ports <1024 require root/admin
# Use port >1024 or run with elevated privileges
python server/game_server.py --port 8765  # OK
python server/game_server.py --port 80    # Requires root
```

### Other Players Can't Connect

**Problem**: You can connect locally but others can't

**Solutions:**
1. **Firewall**: Allow port 8765
   ```bash
   # Linux
   sudo ufw allow 8765/tcp

   # Windows
   netsh advfirewall firewall add rule name="Mafia" dir=in action=allow protocol=TCP localport=8765
   ```

2. **Router**: Forward port 8765 to your machine

3. **Bind address**: Use `--host 0.0.0.0` (not 127.0.0.1)
   ```bash
   python server/game_server.py --host 0.0.0.0
   ```

4. **Share public IP**: Give players your external IP
   - Find it: https://whatismyipaddress.com/
   - Format: `ws://YOUR.IP.HERE:8765`

## Security Notes

### Current Security (Sprint 2)

- ⚠️ **No encryption** (plain WebSocket, not WSS)
- ⚠️ **Simple authentication** (name-based, no passwords)
- ⚠️ **No input validation** (trust all players)

### Recommendations

**For Local Networks:**
- Current implementation is fine
- Only play with trusted friends
- Use on private WiFi only

**For Public Internet:**
- **Wait for Sprint 3** (adds TLS, JWT tokens, rate limiting)
- Or set up a VPN
- Or use port forwarding with caution

**Never:**
- Share your server publicly (no DDoS protection yet)
- Use on untrusted networks
- Share sensitive information in chat

## Best Practices

### For Hosts

1. **Test locally first**
   ```bash
   python server/game_server.py --no-persist
   python gui/app.py --connect ws://localhost:8765
   ```

2. **Use persistence for long games**
   ```bash
   python server/game_server.py --db data/mafia.db
   ```

3. **Share clear connection info**
   - Server address: `ws://IP:PORT`
   - Preferred player names
   - Time to start

4. **Wait for everyone before starting**
   - Check player list
   - Confirm in chat
   - Start only when all ready

### For Players

1. **Test connection beforehand**
   ```bash
   python gui/app.py --connect ws://host:8765
   ```

2. **Use stable connection**
   - WiFi better than mobile data
   - Close bandwidth-heavy apps
   - Stay near router

3. **Keep GUI open during game**
   - Don't minimize for too long
   - Check for disconnection warnings
   - Reconnect promptly if dropped

## Advanced Usage

### Multiple Games on One Server

The server supports multiple concurrent games:

```bash
# Start server
python server/game_server.py

# Client 1: Create Game A
python gui/app.py --connect ws://server:8765 --player Alice

# Client 2: Create Game B
python gui/app.py --connect ws://server:8765 --player Bob

# Both games run independently
```

### Custom Ports

```bash
# Server on custom port
python server/game_server.py --port 9000

# Clients connect to custom port
python gui/app.py --connect ws://server:9000
```

### LAN Party Setup

1. **Host starts server:**
   ```bash
   python server/game_server.py --host 0.0.0.0
   ```

2. **Host shares local IP** (e.g., 192.168.1.100)

3. **Players connect:**
   ```bash
   python gui/app.py --connect ws://192.168.1.100:8765
   ```

4. **Everyone on same WiFi** → Fast, low latency

## Next Steps

### Sprint 3 (Coming Soon)

- 🔐 **Security**: JWT authentication, TLS encryption
- 👥 **Features**: Spectator mode, mid-game join
- 🛡️ **Protection**: Rate limiting, input validation
- 📊 **Dashboard**: Web admin panel
- 🎮 **Polish**: Better UX, animations

### Give Feedback

Found a bug or have suggestions?
- GitHub Issues: [link]
- Discord: [link]
- Email: [link]

## Examples

### Example 1: Local Testing

```bash
# Terminal 1: Start server
python server/game_server.py --no-persist

# Terminal 2: Player 1
python gui/app.py --connect ws://localhost:8765 --player Alice

# Terminal 3: Player 2
python gui/app.py --connect ws://localhost:8765 --player Bob

# Player 1: Create game and start when both join
```

### Example 2: Internet Game

```bash
# Host Machine (Public IP: 203.0.113.42):
python server/game_server.py --host 0.0.0.0 --db data/mafia.db

# Player 1 (anywhere):
python gui/app.py --connect ws://203.0.113.42:8765

# Player 2 (anywhere):
python gui/app.py --connect ws://203.0.113.42:8765
```

### Example 3: Embedded Server

```bash
# Start server + client in one command
python gui/app.py --host --player Host

# Other players connect normally
python gui/app.py --connect ws://HOST_IP:8765
```

---

**Enjoy multiplayer Mafia!** 🎭🌐

For technical details, see:
- `server/README.md` - Server documentation
- `network/protocol.py` - Protocol specification
- `QUICKSTART_SERVER.md` - Server quick start
