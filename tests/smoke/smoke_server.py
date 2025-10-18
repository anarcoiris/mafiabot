#!/usr/bin/env python3
"""
Smoke test for server functionality.
Quick validation that server starts and handles basic operations.

Usage:
    python tests/smoke/smoke_server.py

Expected runtime: ~10 seconds
"""
import sys
import asyncio
import subprocess
import time
from pathlib import Path
import io

# Fix Windows console encoding for emojis
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import websockets
from network.protocol import serialize_message, deserialize_message
from network.messages import ConnectMessage, CreateGameMessage, ListGamesMessage


class Colors:
    """ANSI color codes for terminal output."""
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'
    BOLD = '\033[1m'


def print_step(message):
    """Print test step."""
    print(f"  {Colors.BLUE}→{Colors.RESET} {message}...", end=' ', flush=True)


def print_pass():
    """Print pass indicator."""
    print(f"{Colors.GREEN}✓{Colors.RESET}")


def print_fail(error=None):
    """Print fail indicator."""
    print(f"{Colors.RED}✗{Colors.RESET}")
    if error:
        print(f"    {Colors.RED}Error: {error}{Colors.RESET}")


async def test_server_connection(uri="ws://localhost:8765"):
    """Test basic server connection."""
    try:
        async with websockets.connect(uri, open_timeout=5) as ws:
            return True
    except Exception as e:
        return False, str(e)


async def test_authentication(uri="ws://localhost:8765"):
    """Test player authentication."""
    try:
        async with websockets.connect(uri, open_timeout=5) as ws:
            # Send connect message
            msg = ConnectMessage("SmokeTestPlayer")
            await ws.send(serialize_message(msg))

            # Wait for response
            response = await asyncio.wait_for(ws.recv(), timeout=5.0)
            msg_response = deserialize_message(response)

            if msg_response.type.value == "success":
                player_id = msg_response.data.get('player_id')
                return True, player_id
            else:
                return False, f"Auth failed: {msg_response.data}"

    except Exception as e:
        return False, str(e)


async def test_game_creation(uri="ws://localhost:8765"):
    """Test game creation."""
    try:
        async with websockets.connect(uri, open_timeout=5) as ws:
            # Authenticate
            connect_msg = ConnectMessage("SmokeTestHost")
            await ws.send(serialize_message(connect_msg))
            auth_response = await ws.recv()

            # Create game
            create_msg = CreateGameMessage("SmokeTestHost")
            await ws.send(serialize_message(create_msg))

            # Wait for response
            response = await asyncio.wait_for(ws.recv(), timeout=5.0)
            msg_response = deserialize_message(response)

            if msg_response.type.value == "game_created":
                game_id = msg_response.data.get('game_id')
                return True, game_id
            else:
                return False, f"Game creation failed: {msg_response.data}"

    except Exception as e:
        return False, str(e)


async def test_game_listing(uri="ws://localhost:8765"):
    """Test listing active games."""
    try:
        async with websockets.connect(uri, open_timeout=5) as ws:
            # Authenticate
            connect_msg = ConnectMessage("SmokeTestLister")
            await ws.send(serialize_message(connect_msg))
            await ws.recv()

            # List games
            list_msg = ListGamesMessage()
            await ws.send(serialize_message(list_msg))

            # Wait for response
            response = await asyncio.wait_for(ws.recv(), timeout=5.0)
            msg_response = deserialize_message(response)

            if msg_response.type.value == "game_list":
                games = msg_response.data.get('games', [])
                return True, len(games)
            else:
                return False, f"List failed: {msg_response.data}"

    except Exception as e:
        return False, str(e)


async def run_smoke_tests():
    """Run all smoke tests."""
    print(f"\n{Colors.BOLD}🔥 Server Smoke Test{Colors.RESET}")
    print(f"{'=' * 50}\n")

    uri = "ws://localhost:8765"
    all_passed = True

    # Test 1: Connection
    print_step("Testing server connection")
    result = await test_server_connection(uri)
    if result is True:
        print_pass()
    else:
        print_fail(result[1] if isinstance(result, tuple) else "Connection failed")
        all_passed = False
        print(f"\n{Colors.YELLOW}⚠️  Make sure server is running:{Colors.RESET}")
        print(f"    python server/game_server.py --no-persist\n")
        return False

    # Test 2: Authentication
    print_step("Testing authentication")
    result = await test_authentication(uri)
    if result[0]:
        print_pass()
        print(f"    Player ID: {result[1]}")
    else:
        print_fail(result[1])
        all_passed = False

    # Test 3: Game creation
    print_step("Testing game creation")
    result = await test_game_creation(uri)
    if result[0]:
        print_pass()
        print(f"    Game ID: {result[1]}")
    else:
        print_fail(result[1])
        all_passed = False

    # Test 4: Game listing
    print_step("Testing game listing")
    result = await test_game_listing(uri)
    if result[0]:
        print_pass()
        print(f"    Active games: {result[1]}")
    else:
        print_fail(result[1])
        all_passed = False

    # Summary
    print(f"\n{'=' * 50}")
    if all_passed:
        print(f"{Colors.GREEN}{Colors.BOLD}✅ All smoke tests passed!{Colors.RESET}\n")
        return True
    else:
        print(f"{Colors.RED}{Colors.BOLD}❌ Some smoke tests failed{Colors.RESET}\n")
        return False


def main():
    """Main entry point."""
    try:
        success = asyncio.run(run_smoke_tests())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print(f"\n\n{Colors.YELLOW}Test interrupted by user{Colors.RESET}")
        sys.exit(1)
    except Exception as e:
        print(f"\n{Colors.RED}Fatal error: {e}{Colors.RESET}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
