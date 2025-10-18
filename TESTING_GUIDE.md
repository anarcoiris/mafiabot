# 🧪 Testing Guide

## Overview

Comprehensive testing infrastructure for Mafia Bot, covering:
- **Smoke Tests**: Quick validation (30 seconds)
- **Unit Tests**: Component-level tests
- **Integration Tests**: System-level tests
- **Debug Tools**: Interactive debugging utilities

## Quick Start

### Run All Smoke Tests (30 seconds)

```bash
# Make sure server is running first
python server/game_server.py --no-persist

# In another terminal, run smoke tests
python tests/smoke/smoke_all.py
```

**Expected output:**
```
🔥 Running All Smoke Tests
============================================================

[1/2] Server Tests
  → Testing server connection... ✓
  → Testing authentication... ✓
  → Testing game creation... ✓
  → Testing game listing... ✓

[2/2] Client Tests
  → Creating client... ✓
  → Connecting to server... ✓
  → Sending messages... ✓
  → Checking statistics... ✓
  → Disconnecting cleanly... ✓
  → Testing reconnection... ✓

============================================================
Summary
============================================================
  ✅ PASS - Server
  ✅ PASS - Client

  Passed: 2/2

🎉 All smoke tests passed!
```

## Test Structure

```
tests/
├── smoke/              # Quick validation tests
│   ├── smoke_server.py     # Server smoke test
│   ├── smoke_client.py     # Client smoke test
│   └── smoke_all.py        # Run all smoke tests
│
├── unit/               # Unit tests (TODO)
│   ├── test_protocol.py
│   ├── test_messages.py
│   ├── test_client.py
│   └── test_state_sync.py
│
├── integration/        # Integration tests (TODO)
│   ├── test_server_client.py
│   ├── test_game_flow.py
│   └── test_multiplayer.py
│
└── debug/             # Debug utilities
    ├── network_inspector.py  # WebSocket traffic inspector
    ├── debug_server.py       # Server debugging (TODO)
    └── state_validator.py    # State validator (TODO)
```

## Smoke Tests

### Individual Smoke Tests

**Server test:**
```bash
python tests/smoke/smoke_server.py
```

Tests:
- Server connection
- Authentication
- Game creation
- Game listing

**Client test:**
```bash
python tests/smoke/smoke_client.py
```

Tests:
- Client creation
- Connection to server
- Message sending
- Statistics tracking
- Clean disconnection
- Reconnection

**All tests:**
```bash
python tests/smoke/smoke_all.py
```

Runs both server and client tests in sequence.

### When to Run Smoke Tests

- ✅ After making changes to server/client code
- ✅ Before committing code
- ✅ After pulling new changes
- ✅ When troubleshooting connectivity issues
- ✅ As part of CI/CD pipeline

### Interpreting Results

**All tests pass:**
```
✅ All smoke tests passed!
```
→ Good to go! Core functionality works.

**Server tests fail:**
```
❌ Some smoke tests failed
⚠️  Make sure server is running:
    python server/game_server.py --no-persist
```
→ Start the server and try again.

**Client tests fail:**
```
✅ PASS - Server
❌ FAIL - Client
```
→ Server is fine, but client has issues. Check:
- Network connectivity
- Client code changes
- Error messages in output

## Debug Tools

### Network Inspector

**Real-time WebSocket traffic monitoring:**

```bash
python tests/debug/network_inspector.py
```

**Features:**
- Shows all messages between client and server
- Colorized output (sent = yellow, received = green)
- Pretty-printed JSON
- Message counts and statistics
- Timestamps

**Example output:**
```
🔍 Network Inspector
======================================================================
Server: ws://localhost:8765
Started: 2025-10-14 15:30:45
======================================================================

[15:30:45.123] → CLIENT → SERVER
Type: connect
{
  "type": "connect",
  "data": {
    "player_name": "Inspector"
  },
  "message_id": "abc-123"
}

[15:30:45.156] ← SERVER → CLIENT
Type: success
{
  "type": "success",
  "data": {
    "player_id": 1,
    "player_name": "Inspector"
  },
  "reply_to": "abc-123"
}

Press Ctrl+C to stop...
```

**Custom server:**
```bash
python tests/debug/network_inspector.py ws://192.168.1.100:8765
```

### When to Use Debug Tools

**Network Inspector:**
- 🔍 Debugging connection issues
- 📊 Monitoring message flow
- 🐛 Finding protocol bugs
- 📝 Understanding server behavior
- 🎓 Learning the protocol

## Unit Tests (Coming Soon)

### Running Unit Tests

```bash
pytest tests/unit/ -v
```

**With coverage:**
```bash
pytest tests/unit/ -v --cov=gui/network --cov=server
```

### Test Categories

| Test File | Component | Coverage Target |
|-----------|-----------|-----------------|
| `test_protocol.py` | Message protocol | 95%+ |
| `test_messages.py` | Message constructors | 95%+ |
| `test_client.py` | WebSocket client | 90%+ |
| `test_state_sync.py` | State synchronization | 90%+ |
| `test_sync_manager.py` | Sync coordinator | 85%+ |

## Integration Tests (Coming Soon)

### Running Integration Tests

```bash
pytest tests/integration/ -v
```

**Individual test:**
```bash
pytest tests/integration/test_server_client.py -v
```

### Test Scenarios

- **Basic Communication**: Client ↔ Server handshake
- **Game Flow**: Complete game from lobby to victory
- **Multiplayer**: Multiple clients simultaneously
- **Reconnection**: Network interruption recovery
- **Concurrent Games**: Multiple games on one server

## Continuous Testing

### Watch Mode

```bash
# Install pytest-watch
pip install pytest-watch

# Watch unit tests
ptw tests/unit/

# Watch all tests
ptw tests/
```

Files are automatically re-tested when changed.

### Pre-commit Hook

Create `.git/hooks/pre-commit`:

```bash
#!/bin/bash
# Run smoke tests before commit

echo "Running smoke tests..."
python tests/smoke/smoke_all.py

if [ $? -ne 0 ]; then
    echo "❌ Smoke tests failed. Commit aborted."
    exit 1
fi

echo "✅ Smoke tests passed. Proceeding with commit."
exit 0
```

Make it executable:
```bash
chmod +x .git/hooks/pre-commit
```

## Troubleshooting

### Smoke Tests Fail

**Problem**: Connection refused

**Solution**:
1. Start server: `python server/game_server.py --no-persist`
2. Wait 2 seconds for startup
3. Run tests again

**Problem**: Tests timeout

**Solution**:
1. Check server logs: `tail -f logs/*.log`
2. Verify port 8765 is not blocked
3. Try different port: `python server/game_server.py --port 9000`

**Problem**: Random failures

**Solution**:
1. Run tests individually to isolate issue
2. Check for resource conflicts (multiple servers running)
3. Restart server between test runs

### Debug Tools Don't Work

**Problem**: Network inspector can't connect

**Solution**:
1. Verify server is running
2. Check URI is correct
3. Test basic connection: `python tests/smoke/smoke_server.py`

**Problem**: No messages shown

**Solution**:
1. Inspector connects but server might not be sending data
2. Try sending a message from another client
3. Check server logs for errors

## Best Practices

### For Developers

1. **Run smoke tests** after every change
2. **Write tests** for new features
3. **Use debug tools** when investigating issues
4. **Check coverage** regularly
5. **Keep tests fast** (< 1 minute total)

### For CI/CD

1. **Always run smoke tests** first (fastest feedback)
2. **Run unit tests** on every commit
3. **Run integration tests** before merge
4. **Generate coverage reports**
5. **Fail builds** on test failures

### Writing Tests

**Good test:**
```python
async def test_client_connection():
    """Test that client can connect to server."""
    client = GameClient("ws://localhost:8765")
    success = await client.connect("TestPlayer")

    assert success is True
    assert client.player_id is not None
    assert client.is_connected is True

    await client.disconnect()
```

**Test naming:**
- `test_<component>_<scenario>_<expected_behavior>`
- Example: `test_client_reconnection_after_disconnect`

**Test structure:**
1. **Arrange**: Set up test data
2. **Act**: Execute the operation
3. **Assert**: Verify the result
4. **Cleanup**: Clean up resources

## Test Coverage Goals

| Component | Target | Current | Status |
|-----------|--------|---------|--------|
| Protocol | 95% | TBD | ⏳ |
| Client | 90% | TBD | ⏳ |
| State Sync | 90% | TBD | ⏳ |
| Server | 85% | TBD | ⏳ |
| Controllers | 80% | TBD | ⏳ |

## Performance Benchmarks

### Smoke Tests

| Test Suite | Target Time | Status |
|------------|-------------|--------|
| Server | < 10s | ✅ |
| Client | < 10s | ✅ |
| All | < 30s | ✅ |

### Unit Tests

| Test Suite | Target Time | Status |
|------------|-------------|--------|
| Protocol | < 5s | ⏳ |
| Messages | < 5s | ⏳ |
| Client | < 10s | ⏳ |
| State Sync | < 10s | ⏳ |
| All Unit | < 2min | ⏳ |

### Integration Tests

| Test Suite | Target Time | Status |
|------------|-------------|--------|
| Server-Client | < 1min | ⏳ |
| Game Flow | < 2min | ⏳ |
| Multiplayer | < 2min | ⏳ |
| All Integration | < 5min | ⏳ |

## Next Steps

### Phase 1: Smoke Tests ✅
- ✅ Server smoke test
- ✅ Client smoke test
- ✅ Combined runner
- ✅ Network inspector

### Phase 2: Unit Tests ⏳
- ⏳ Protocol tests
- ⏳ Message tests
- ⏳ Client tests
- ⏳ State sync tests

### Phase 3: Integration Tests ⏳
- ⏳ Server-client communication
- ⏳ Full game flow
- ⏳ Multiple clients
- ⏳ Reconnection scenarios

### Phase 4: Debug Tools ⏳
- ✅ Network inspector
- ⏳ Debug server
- ⏳ State validator
- ⏳ Performance profiler

## Resources

### Documentation
- `server/README.md` - Server documentation
- `NETWORK_MODE_GUIDE.md` - Network mode guide
- `network/protocol.py` - Protocol specification

### Tools
- **pytest**: Testing framework
- **pytest-asyncio**: Async test support
- **pytest-cov**: Coverage reporting
- **pytest-watch**: Watch mode

### Installation
```bash
pip install pytest pytest-asyncio pytest-cov pytest-watch
```

---

**Testing Status**: Smoke tests complete ✅
**Next**: Unit tests implementation
**Goal**: 85%+ code coverage across critical components

Happy testing! 🧪
