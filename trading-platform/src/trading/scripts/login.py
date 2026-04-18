"""
Zerodha login — automatic access-token refresh.

Flow
----
1. Start a tiny HTTP server on 127.0.0.1:8080.
2. Open the Kite login URL in the default browser.
3. User logs in with their Zerodha credentials.
4. Zerodha redirects to http://127.0.0.1:8080/?request_token=XXX&status=success
5. Server captures the request_token, exchanges it for an access_token.
6. Writes ZERODHA_ACCESS_TOKEN to .env (creates the key if absent, updates if present).

Usage
-----
    uv run python -m trading.scripts.login

Prerequisites
-------------
In the Zerodha developer console (https://developers.kite.trade/apps),
set the Redirect URL for your app to:

    http://127.0.0.1:8080/

The API key and secret are read from .env.
"""

from __future__ import annotations

import os
import re
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from dotenv import load_dotenv


# Locate .env: walk up from this file until we find it (or fall back to cwd).
def _find_env() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / ".env"
        if candidate.exists():
            return candidate
    return Path.cwd() / ".env"


_ENV_PATH = _find_env()

load_dotenv(_ENV_PATH)

API_KEY = os.environ.get("ZERODHA_API_KEY", "")
API_SECRET = os.environ.get("ZERODHA_API_SECRET", "")

if not API_KEY or not API_SECRET:
    sys.exit("ERROR: ZERODHA_API_KEY and ZERODHA_API_SECRET must be set in .env")

_CALLBACK_HOST = "127.0.0.1"
_CALLBACK_PORT = 8080

# Shared result — set by the HTTP handler, read by main thread
_request_token: str | None = None
_server_error: str | None = None


class _CallbackHandler(BaseHTTPRequestHandler):
    """Handles the single redirect from Zerodha after login."""

    def do_GET(self) -> None:  # noqa: N802
        global _request_token, _server_error

        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        status = params.get("status", [""])[0]
        token = params.get("request_token", [""])[0]

        if status == "success" and token:
            _request_token = token
            body = b"<h2>Login successful! You can close this tab.</h2>"
            self.send_response(200)
        else:
            _server_error = params.get("message", ["Unknown error"])[0]
            body = f"<h2>Login failed: {_server_error}</h2>".encode()
            self.send_response(400)

        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

        # Shut the server down from inside the handler (non-blocking)
        threading.Thread(target=self.server.shutdown).start()

    def log_message(self, fmt: str, *args: object) -> None:
        # Suppress default access log noise
        pass


def _write_token_to_env(token: str, env_path: Path) -> None:
    """Update (or insert) ZERODHA_ACCESS_TOKEN in .env."""
    text = env_path.read_text(encoding="utf-8") if env_path.exists() else ""

    pattern = re.compile(r"^ZERODHA_ACCESS_TOKEN=.*$", re.MULTILINE)
    new_line = f"ZERODHA_ACCESS_TOKEN={token}"

    if pattern.search(text):
        text = pattern.sub(new_line, text)
    else:
        text = text.rstrip("\n") + f"\n{new_line}\n"

    env_path.write_text(text, encoding="utf-8")
    print(f"  Access token written to {env_path}")


def main() -> None:
    from trading.broker.zerodha_broker.kite_client.kite_client import KiteClient

    client = KiteClient(API_KEY)
    login_url = client.login_url()

    print("Starting local callback server on http://127.0.0.1:8080/ …")
    server = HTTPServer((_CALLBACK_HOST, _CALLBACK_PORT), _CallbackHandler)

    print(f"\nOpening browser to Zerodha login:\n  {login_url}\n")
    webbrowser.open(login_url)

    print("Waiting for Zerodha redirect (log in with your credentials) …")
    server.serve_forever()  # blocks until _CallbackHandler shuts it down

    if _server_error or not _request_token:
        sys.exit(f"ERROR: Login failed — {_server_error or 'no request_token received'}")

    print("\nRequest token received. Exchanging for access token …")
    session = client.generate_session(_request_token, API_SECRET)
    access_token: str = session["access_token"]

    _write_token_to_env(access_token, _ENV_PATH)

    print("\nLogin complete.")
    print(f"  User:         {session.get('user_name', 'unknown')}")
    print(f"  Login time:   {session.get('login_time', 'unknown')}")
    print(f"  Token prefix: {access_token[:8]}…")


if __name__ == "__main__":
    main()
