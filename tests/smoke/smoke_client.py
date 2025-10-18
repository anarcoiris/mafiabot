#!/usr/bin/env python3
"""
Smoke test for GUI network client.
Quick validation of client connectivity and basic operations.

Usage:
    python tests/smoke/smoke_client.py

Expected runtime: ~10 seconds
"""
import sys
import asyncio
from pathlib import Path
import io

# Fix Windows console encoding for emojis
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from gui.network.client import GameClient, ConnectionState
from network.messages import CreateGameMessage, ListGamesMessage


class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'
    BOLD = '\033[1m'


def print_step(message):
    print(f"  {Colors.BLUE}→{Colors.RESET} {message}...", end=' ', flush=True)


def print_pass():
    print(f"{Colors.GREEN}✓{Colors.RESET}")


def print_fail(error=None):
    print(f"{Colors.RED}✗{Colors.RESET}")
    if error:
        print(f"    {Colors.RED}Error: {error}{Colors.RESET}")


async def test_client_creation():
    """Test client instantiation."""
    try:
        client = GameClient("ws://localhost:8765")
        return True, client
    except Exception as e:
        return False, str(e), None


async def test_client_connection(client):
    """Test client connection."""
    try:
        success = await asyncio.wait_for(
            client.connect("SmokeTestClient", auto_reconnect=False),
            timeout=10.0
        )
        return success, client.player_id
    except asyncio.TimeoutError:
        return False, "Connection timeout"
    except Exception as e:
        return False, str(e)


async def test_client_messaging(client):
    """Test client message sending."""
    try:
        msg = ListGamesMessage()
        success = await client.send_message(msg)
        await asyncio.sleep(0.5)  # Wait for response
        return success, None
    except Exception as e:
        return False, str(e)


async def test_client_stats(client):
    """Test client statistics."""
    try:
        stats = client.stats
        required_keys = ['state', 'player_id', 'messages_sent', 'messages_received']
        for key in required_keys:
            if key not in stats:
                return False, f"Missing stat: {key}"
        return True, stats
    except Exception as e:
        return False, str(e)


async def test_client_disconnect(client):
    """Test clean disconnection."""
    try:
        await client.disconnect()
        if client.state == ConnectionState.DISCONNECTED:
            return True, None
        else:
            return False, f"State is {client.state.value}, expected disconnected"
    except Exception as e:
        return False, str(e)


async def test_client_reconnection():
    """Test reconnection capability."""
    try:
        client = GameClient("ws://localhost:8765")

        # Connect
        await client.connect("ReconnectTest", auto_reconnect=False)

        # Disconnect
        await client.disconnect()

        # Reconnect
        success = await client.connect("ReconnectTest", auto_reconnect=False)

        await client.disconnect()
        return success, None
    except Exception as e:
        return False, str(e)


async def run_smoke_tests():
    """Run all client smoke tests."""
    print(f"\n{Colors.BOLD}🔥 Client Smoke Test{Colors.RESET}")
    print(f"{'=' * 50}\n")

    all_passed = True
    client = None

    # Test 1: Client creation
    print_step("Creating client")
    result = await test_client_creation()
    if result[0]:
        print_pass()
        client = result[1]
    else:
        print_fail(result[1])
        all_passed = False
        return False

    # Test 2: Connection
    print_step("Connecting to server")
    result = await test_client_connection(client)
    if result[0]:
        print_pass()
        print(f"    Player ID: {result[1]}")
    else:
        print_fail(result[1])
        all_passed = False
        print(f"\n{Colors.YELLOW}⚠️  Make sure server is running:{Colors.RESET}")
        print(f"    python server/game_server.py --no-persist\n")
        return False

    # Test 3: Messaging
    print_step("Sending messages")
    result = await test_client_messaging(client)
    if result[0]:
        print_pass()
    else:
        print_fail(result[1])
        all_passed = False

    # Test 4: Statistics
    print_step("Checking statistics")
    result = await test_client_stats(client)
    if result[0]:
        print_pass()
        stats = result[1]
        print(f"    Sent: {stats['messages_sent']}, Received: {stats['messages_received']}")
    else:
        print_fail(result[1])
        all_passed = False

    # Test 5: Disconnection
    print_step("Disconnecting cleanly")
    result = await test_client_disconnect(client)
    if result[0]:
        print_pass()
    else:
        print_fail(result[1])
        all_passed = False

    # Test 6: Reconnection
    print_step("Testing reconnection")
    result = await test_client_reconnection()
    if result[0]:
        print_pass()
    else:
        print_fail(result[1])
        all_passed = False

    # Summary
    print(f"\n{'=' * 50}")
    if all_passed:
        print(f"{Colors.GREEN}{Colors.BOLD}✅ All client smoke tests passed!{Colors.RESET}\n")
        return True
    else:
        print(f"{Colors.RED}{Colors.BOLD}❌ Some client tests failed{Colors.RESET}\n")
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
