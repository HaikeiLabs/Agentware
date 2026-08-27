"""Fake KEI server implementing the auth/config contract for tests.

This is a test-only HTTP server that implements the KEI API contract for:
- Token exchange (POST /auth/exchange)
- Token renewal (POST /auth/refresh)
- Token revocation (POST /auth/revoke)
- Config revision (GET /config)

It is used by contract tests to verify the client-side contract is
well-defined and to exercise the future JWT exchange behavior. The fake
server is self-contained and requires no external dependencies.
"""

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


class FakeKEIServer:
    """In-process fake KEI server for contract testing.

    Implements the auth and config contract. Tokens are opaque strings
    tracked in-memory; revocation removes them from the valid set.
    """

    def __init__(
        self,
        bootstrap_token: str = "bootstrap-secret",
        config_revision: str = "rev-1",
        token_ttl_seconds: int = 3600,
    ) -> None:
        self._bootstrap_token = bootstrap_token
        self._config_revision = config_revision
        self._token_ttl_seconds = token_ttl_seconds
        self._valid_tokens: dict[str, float] = {}
        self._revoked_tokens: set[str] = set()
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._port: int = 0

    def start(self) -> None:
        """Start the fake server on a random free port."""
        handler = self._make_handler()
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self._port = self._server.server_address[1]
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop the fake server."""
        if self._server:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None

    @property
    def port(self) -> int:
        """The port the server is listening on."""
        return self._port

    @property
    def base_url(self) -> str:
        """Base URL of the fake server."""
        return f"http://127.0.0.1:{self._port}"

    def _make_handler(self) -> type[BaseHTTPRequestHandler]:
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
                # Suppress default logging
                pass

            def _send_json(self, status: int, payload: dict[str, Any]) -> None:
                body = json.dumps(payload).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _bearer(self) -> str | None:
                auth = self.headers.get("Authorization", "")
                if auth.startswith("Bearer "):
                    return auth[len("Bearer ") :]
                return None

            def do_GET(self) -> None:  # noqa: N802
                if self.path == "/config":
                    self._send_json(
                        200,
                        {
                            "config_revision": outer._config_revision,
                            "harness_id": "fake-harness",
                        },
                    )
                else:
                    self._send_json(404, {"error": "not found"})

            def do_POST(self) -> None:  # noqa: N802
                token = self._bearer()

                if self.path == "/auth/exchange":
                    if token != outer._bootstrap_token:
                        self._send_json(401, {"error": "invalid bootstrap token"})
                        return
                    jwt = f"jwt-{int(time.time() * 1000)}"
                    outer._valid_tokens[jwt] = time.time() + outer._token_ttl_seconds
                    self._send_json(
                        200,
                        {
                            "token": jwt,
                            "token_type": "jwt",
                            "expires_in": outer._token_ttl_seconds,
                        },
                    )
                    return

                if self.path == "/auth/refresh":
                    if token is None or token not in outer._valid_tokens:
                        self._send_json(401, {"error": "invalid or expired token"})
                        return
                    if token in outer._revoked_tokens:
                        self._send_json(401, {"error": "token revoked"})
                        return
                    new_jwt = f"jwt-{int(time.time() * 1000)}-renewed"
                    outer._valid_tokens[new_jwt] = time.time() + outer._token_ttl_seconds
                    del outer._valid_tokens[token]
                    self._send_json(
                        200,
                        {
                            "token": new_jwt,
                            "token_type": "jwt",
                            "expires_in": outer._token_ttl_seconds,
                        },
                    )
                    return

                if self.path == "/auth/revoke":
                    if token is None or token not in outer._valid_tokens:
                        self._send_json(404, {"error": "unknown token"})
                        return
                    outer._revoked_tokens.add(token)
                    del outer._valid_tokens[token]
                    self._send_json(200, {"status": "revoked"})
                    return

                self._send_json(404, {"error": "not found"})

        return Handler

    def __enter__(self) -> "FakeKEIServer":
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.stop()
