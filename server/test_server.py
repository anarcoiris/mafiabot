"""
server/test_server.py
Simple test script to verify server functionality.
"""
import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import websockets
from network.protocol import serialize_message, deserialize_message
from network.messages import (
    ConnectMessage, CreateGameMessage, JoinGameMessage,
    StartGameMessage, ListGamesMessage
)


async def test_basic_connection():
    """Test basic server connection and authentication."""
    print("🧪 Testing basic connection...")

    uri = "ws://localhost:8765"

    try:
        async with websockets.connect(uri) as websocket:
            print(f"✅ Connected to {uri}")

            # Send connect message
            connect_msg = ConnectMessage("TestPlayer")
            await websocket.send(serialize_message(connect_msg))
            print("→ Sent CONNECT message")

            # Receive response
            response = await websocket.recv()
            msg = deserialize_message(response)
            print(f"← Received {msg.type.value}: {msg.data}")

            if msg.type.value == "success":
                player_id = msg.data.get('player_id')
                print(f"✅ Authenticated as player {player_id}")
                return True
            else:
                print(f"❌ Authentication failed: {msg.data}")
                return False

    except Exception as e:
        print(f"❌ Connection failed: {e}")
        return False


async def test_game_creation():
    """Test game creation flow."""
    print("\n🧪 Testing game creation...")

    uri = "ws://localhost:8765"

    try:
        async with websockets.connect(uri) as websocket:
            # Connect
            connect_msg = ConnectMessage("HostPlayer")
            await websocket.send(serialize_message(connect_msg))
            response = await websocket.recv()
            msg = deserialize_message(response)

            if msg.type.value != "success":
                print(f"❌ Failed to connect: {msg.data}")
                return False

            player_id = msg.data.get('player_id')
            print(f"✅ Connected as player {player_id}")

            # Create game
            create_msg = CreateGameMessage("HostPlayer", {'mafia': 1, 'ciudadano': 3})
            await websocket.send(serialize_message(create_msg))
            print("→ Sent CREATE_GAME message")

            response = await websocket.recv()
            msg = deserialize_message(response)
            print(f"← Received {msg.type.value}: {msg.data}")

            if msg.type.value == "game_created":
                game_id = msg.data.get('game_id')
                print(f"✅ Game created: {game_id}")
                return True
            else:
                print(f"❌ Game creation failed: {msg.data}")
                return False

    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False


async def test_multiple_players():
    """Test multiple players joining the same game."""
    print("\n🧪 Testing multiple players...")

    uri = "ws://localhost:8765"

    try:
        # Player 1: Create game
        async with websockets.connect(uri) as ws1:
            # Connect player 1
            connect_msg = ConnectMessage("Player1")
            await ws1.send(serialize_message(connect_msg))
            response = await ws1.recv()
            msg = deserialize_message(response)
            player1_id = msg.data.get('player_id')
            print(f"✅ Player 1 connected: {player1_id}")

            # Create game
            create_msg = CreateGameMessage("Player1")
            await ws1.send(serialize_message(create_msg))
            response = await ws1.recv()
            msg = deserialize_message(response)
            game_id = msg.data.get('game_id')
            print(f"✅ Game created: {game_id}")

            # Player 2: Join game
            async with websockets.connect(uri) as ws2:
                # Connect player 2
                connect_msg = ConnectMessage("Player2")
                await ws2.send(serialize_message(connect_msg))
                response = await ws2.recv()
                msg = deserialize_message(response)
                player2_id = msg.data.get('player_id')
                print(f"✅ Player 2 connected: {player2_id}")

                # Join game
                join_msg = JoinGameMessage(game_id, "Player2")
                await ws2.send(serialize_message(join_msg))

                # Both players should receive player_joined message
                # Player 2 gets response
                response = await ws2.recv()
                msg = deserialize_message(response)
                print(f"← Player 2 received: {msg.type.value}")

                # Player 1 gets broadcast
                response = await ws1.recv()
                msg = deserialize_message(response)
                print(f"← Player 1 received broadcast: {msg.type.value}")

                if msg.type.value == "player_joined":
                    print(f"✅ Player 2 joined successfully")
                    return True
                else:
                    print(f"❌ Unexpected message: {msg.type.value}")
                    return False

    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_list_games():
    """Test listing active games."""
    print("\n🧪 Testing game listing...")

    uri = "ws://localhost:8765"

    try:
        async with websockets.connect(uri) as websocket:
            # Connect
            connect_msg = ConnectMessage("ListTester")
            await websocket.send(serialize_message(connect_msg))
            await websocket.recv()

            # List games
            list_msg = ListGamesMessage()
            await websocket.send(serialize_message(list_msg))
            print("→ Sent LIST_GAMES message")

            response = await websocket.recv()
            msg = deserialize_message(response)
            print(f"← Received {msg.type.value}")

            if msg.type.value == "game_list":
                games = msg.data.get('games', [])
                print(f"✅ Found {len(games)} active game(s)")
                for game in games:
                    print(f"   - Game {game['game_id']}: "
                          f"{game['player_count']} players, "
                          f"phase={game['phase']}")
                return True
            else:
                print(f"❌ Unexpected response: {msg.type.value}")
                return False

    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False


async def run_all_tests():
    """Run all tests."""
    print("=" * 60)
    print("Mafia Bot Server Tests")
    print("=" * 60)
    print("\n⚠️  Make sure the server is running:")
    print("   python server/game_server.py --no-persist\n")

    await asyncio.sleep(1)

    results = []

    # Test 1: Basic connection
    results.append(("Basic Connection", await test_basic_connection()))

    # Test 2: Game creation
    results.append(("Game Creation", await test_game_creation()))

    # Test 3: Multiple players
    results.append(("Multiple Players", await test_multiple_players()))

    # Test 4: List games
    results.append(("List Games", await test_list_games()))

    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} - {test_name}")

    print(f"\nPassed: {passed}/{total}")

    if passed == total:
        print("\n🎉 All tests passed!")
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")


if __name__ == "__main__":
    try:
        asyncio.run(run_all_tests())
    except KeyboardInterrupt:
        print("\n\nTests interrupted by user")
    except Exception as e:
        print(f"\n\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
