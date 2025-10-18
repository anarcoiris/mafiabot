#!/usr/bin/env python3
"""
WebSocket traffic inspector.
Captures and displays all messages between client and server in real-time.

Usage:
    python tests/debug/network_inspector.py [ws://localhost:8765]

Features:
    - Real-time message display
    - Colorized output
    - Message counts
    - Timestamps
    - JSON pretty-printing
"""
import sys
import asyncio
import json
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import websockets
from network.protocol import deserialize_message


class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    MAGENTA = '\033[95m'
    RESET = '\033[0m'
    BOLD = '\033[1m'
    DIM = '\033[2m'


class NetworkInspector:
    """WebSocket traffic inspector."""

    def __init__(self, uri: str):
        self.uri = uri
        self.messages_sent = 0
        self.messages_received = 0
        self.start_time = None

    def print_header(self):
        """Print inspector header."""
        print(f"\n{Colors.BOLD}🔍 Network Inspector{Colors.RESET}")
        print(f"{'=' * 70}")
        print(f"Server: {Colors.CYAN}{self.uri}{Colors.RESET}")
        print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'=' * 70}\n")
        print(f"{Colors.DIM}Press Ctrl+C to stop{Colors.RESET}\n")

    def format_message(self, direction: str, raw_message: str):
        """Format a message for display."""
        timestamp = datetime.now().strftime('%H:%M:%S.%f')[:-3]

        # Determine color based on direction
        if direction == "SEND":
            arrow = f"{Colors.YELLOW}→{Colors.RESET}"
            label = f"{Colors.YELLOW}CLIENT → SERVER{Colors.RESET}"
            self.messages_sent += 1
        else:
            arrow = f"{Colors.GREEN}←{Colors.RESET}"
            label = f"{Colors.GREEN}SERVER → CLIENT{Colors.RESET}"
            self.messages_received += 1

        # Try to parse as JSON
        try:
            data = json.loads(raw_message)
            msg_type = data.get('type', 'unknown')
            pretty_json = json.dumps(data, indent=2)

            # Colorize message type
            type_color = Colors.CYAN if direction == "SEND" else Colors.MAGENTA
            msg_type_colored = f"{type_color}{msg_type}{Colors.RESET}"

            print(f"{Colors.DIM}[{timestamp}]{Colors.RESET} {arrow} {label}")
            print(f"Type: {msg_type_colored}")
            print(f"{Colors.DIM}{pretty_json}{Colors.RESET}")
            print()

        except json.JSONDecodeError:
            print(f"{Colors.DIM}[{timestamp}]{Colors.RESET} {arrow} {label}")
            print(f"{Colors.RED}Invalid JSON:{Colors.RESET}")
            print(f"{Colors.DIM}{raw_message}{Colors.RESET}")
            print()

    def print_stats(self):
        """Print statistics."""
        elapsed = (datetime.now() - self.start_time).total_seconds() if self.start_time else 0
        print(f"\n{'=' * 70}")
        print(f"{Colors.BOLD}Statistics{Colors.RESET}")
        print(f"{'=' * 70}")
        print(f"Messages sent:     {Colors.YELLOW}{self.messages_sent}{Colors.RESET}")
        print(f"Messages received: {Colors.GREEN}{self.messages_received}{Colors.RESET}")
        print(f"Total messages:    {self.messages_sent + self.messages_received}")
        print(f"Elapsed time:      {elapsed:.1f}s")
        print()

    async def inspect(self):
        """Start inspecting traffic."""
        self.print_header()
        self.start_time = datetime.now()

        try:
            # Connect to server
            async with websockets.connect(self.uri) as ws:
                print(f"{Colors.GREEN}✓ Connected to server{Colors.RESET}\n")

                # Authenticate
                from network.messages import ConnectMessage
                from network.protocol import serialize_message

                connect_msg = ConnectMessage("Inspector")
                msg_str = serialize_message(connect_msg)
                await ws.send(msg_str)
                self.format_message("SEND", msg_str)

                # Listen for messages
                async for message in ws:
                    self.format_message("RECV", message)

        except websockets.exceptions.ConnectionClosed:
            print(f"\n{Colors.YELLOW}Connection closed by server{Colors.RESET}")
        except Exception as e:
            print(f"\n{Colors.RED}Error: {e}{Colors.RESET}")
        finally:
            self.print_stats()


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="WebSocket traffic inspector")
    parser.add_argument(
        'uri',
        nargs='?',
        default='ws://localhost:8765',
        help='WebSocket URI (default: ws://localhost:8765)'
    )
    args = parser.parse_args()

    inspector = NetworkInspector(args.uri)

    try:
        asyncio.run(inspector.inspect())
    except KeyboardInterrupt:
        inspector.print_stats()
        print(f"{Colors.YELLOW}Inspection stopped by user{Colors.RESET}\n")
    except Exception as e:
        print(f"\n{Colors.RED}Fatal error: {e}{Colors.RESET}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
