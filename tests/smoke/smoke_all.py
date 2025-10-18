#!/usr/bin/env python3
"""
Run all smoke tests in sequence.

Usage:
    python tests/smoke/smoke_all.py

Expected runtime: ~20 seconds
"""
import sys
import asyncio
import subprocess
from pathlib import Path
import io

import traceback
import types

# Debug wrapper to detect who closes sys.stderr
class StderrCloseWatcher:
    def __init__(self, real_stream):
        self._real = real_stream

    def write(self, *args, **kwargs):
        return self._real.write(*args, **kwargs)

    def flush(self, *a, **k):
        return getattr(self._real, "flush")(*a, **k)

    def writelines(self, *a, **k):
        return getattr(self._real, "writelines")(*a, **k)

    @property
    def closed(self):
        return getattr(self._real, "closed", True)

    def close(self):
        # Log stack trace when close is called
        try:
            tb = "".join(traceback.format_stack())
            with open("stderr_close_trace.log", "a", encoding="utf-8") as fh:
                fh.write("---- sys.stderr.close() called ----\n")
                fh.write(tb)
                fh.write("\n")
        except Exception:
            pass
        try:
            return getattr(self._real, "close")()
        except Exception:
            pass

    # delegate other attributes
    def __getattr__(self, name):
        return getattr(self._real, name)

# install watcher early (only if not already watcher)
if not isinstance(sys.stderr, StderrCloseWatcher):
    try:
        sys.stderr = StderrCloseWatcher(sys.stderr)
    except Exception:
        pass


# Fix Windows console encoding for emojis (robust)
if sys.platform == 'win32':
    try:
        # Prefer native reconfigure (Python 3.7+)
        if hasattr(sys.stdout, "reconfigure"):
            try:
                sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass
        if hasattr(sys.stderr, "reconfigure"):
            try:
                sys.stderr.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass

        # Fallback: wrap original underlying buffer safely only if not closed
        def _wrap(stream):
            try:
                if hasattr(stream, "buffer") and not getattr(stream, "closed", False):
                    return io.TextIOWrapper(stream.buffer, encoding="utf-8", errors="replace", line_buffering=True)
            except Exception:
                pass
            return stream

        sys.stdout = _wrap(sys.stdout)
        sys.stderr = _wrap(sys.stderr)

    except Exception as e:
        # Nunca sobrescribas sys.stderr sin fallback: si algo falla, log en sys.__stderr__
        try:
            print(f"[warning] Could not set utf-8 encoding for console: {e}", file=sys.__stderr__)
        except Exception:
            pass


# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tests.smoke.smoke_server import run_smoke_tests as test_server
from tests.smoke.smoke_client import run_smoke_tests as test_client


class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'
    BOLD = '\033[1m'


async def run_all_tests():
    """Run all smoke tests."""
    print(f"\n{Colors.BOLD}{'=' * 60}{Colors.RESET}")
    print(f"{Colors.BOLD}🔥 Running All Smoke Tests{Colors.RESET}")
    print(f"{Colors.BOLD}{'=' * 60}{Colors.RESET}\n")

    results = []

    # Test 1: Server
    print(f"{Colors.BOLD}[1/2] Server Tests{Colors.RESET}")
    server_passed = await test_server()
    results.append(("Server", server_passed))
    print()

    # Test 2: Client
    if server_passed:
        print(f"{Colors.BOLD}[2/2] Client Tests{Colors.RESET}")
        client_passed = await test_client()
        results.append(("Client", client_passed))
    else:
        print(f"{Colors.YELLOW}Skipping client tests (server tests failed){Colors.RESET}")
        results.append(("Client", False))

    # Summary
    print(f"\n{Colors.BOLD}{'=' * 60}{Colors.RESET}")
    print(f"{Colors.BOLD}Summary{Colors.RESET}")
    print(f"{Colors.BOLD}{'=' * 60}{Colors.RESET}\n")

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = f"{Colors.GREEN}✅ PASS{Colors.RESET}" if result else f"{Colors.RED}❌ FAIL{Colors.RESET}"
        print(f"  {status} - {name}")

    print(f"\n  Passed: {passed}/{total}")

    if passed == total:
        print(f"\n{Colors.GREEN}{Colors.BOLD}🎉 All smoke tests passed!{Colors.RESET}\n")
        return True
    else:
        print(f"\n{Colors.RED}{Colors.BOLD}⚠️  {total - passed} test suite(s) failed{Colors.RESET}\n")
        return False


def main():
    """Main entry point."""
    try:
        success = asyncio.run(run_all_tests())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print(f"\n\n{Colors.YELLOW}Tests interrupted by user{Colors.RESET}")
        sys.exit(1)
    except Exception as e:
        print(f"\n{Colors.RED}Fatal error: {e}{Colors.RESET}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
