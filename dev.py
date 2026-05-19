"""
dev.py — start trading-platform (FastAPI :8081) + trading-dashboard (Next.js :3000)

Usage:  python dev.py
Stop:   Ctrl+C  (kills both child processes)
"""

from __future__ import annotations

import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent
PLATFORM_DIR = ROOT / "trading-platform"
DASHBOARD_DIR = ROOT / "trading-dashboard"


def _wait_port(port: int, name: str, timeout: int = 60) -> None:
    print(f">>> Waiting for {name} on :{port} ...", end="", flush=True)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                print(" ready.")
                return
        except OSError:
            print(".", end="", flush=True)
            time.sleep(0.5)
    print()
    sys.exit(f"ERROR: {name} did not start within {timeout}s")


def _require(cmd: str) -> str:
    # On Windows, npm is a .cmd batch file — shutil.which finds npm.cmd
    path = shutil.which(cmd) or (shutil.which(f"{cmd}.cmd") if sys.platform == "win32" else None)
    if path is None:
        sys.exit(f"ERROR: '{cmd}' not found on PATH")
    return path


def _shell_cmd(cmd: str) -> list[str]:
    """Wrap a command in a shell on Windows so .cmd scripts execute correctly."""
    if sys.platform == "win32":
        return ["cmd", "/c", cmd]
    return [cmd]


def main() -> None:
    uv = _require("uv")

    processes: list[subprocess.Popen[bytes]] = []

    try:
        print("\n>>> Starting trading-platform (uv run start) ...")
        platform = subprocess.Popen(
            [uv, "run", "start"],
            cwd=PLATFORM_DIR,
        )
        processes.append(platform)
        _wait_port(8081, "trading-platform")

        print("\n>>> Starting trading-dashboard (npm run dev) ...")
        # Use shell=True on Windows so npm.cmd is resolved by the shell,
        # and the Node.js server process stays as a child of this script.
        dashboard = subprocess.Popen(
            "npm run dev",
            cwd=DASHBOARD_DIR,
            shell=True,
        )
        processes.append(dashboard)
        _wait_port(3000, "trading-dashboard")

        print()
        print("┌─────────────────────────────────────────────┐")
        print("│  trading-platform  →  http://localhost:8081 │")
        print("│  trading-dashboard →  http://localhost:3000 │")
        print("└─────────────────────────────────────────────┘")
        print()
        print("Press Ctrl+C to stop.")

        # Keep running; only exit if the trading-platform process crashes
        # (Next.js dev server manages its own child processes separately)
        while True:
            if platform.poll() is not None:
                sys.exit(f"ERROR: trading-platform (PID {platform.pid}) exited with code {platform.returncode}")
            time.sleep(2)

    except KeyboardInterrupt:
        print("\n>>> Stopping ...")
    finally:
        for p in processes:
            if p.poll() is None:
                p.terminate()
        for p in processes:
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()
        print(">>> Done.")


if __name__ == "__main__":
    main()
