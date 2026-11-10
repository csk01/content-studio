"""OAuth 2.0 authorization-code flow with PKCE using a localhost loopback redirect."""

from __future__ import annotations

import base64
import hashlib
import secrets
import time
import webbrowser
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

from studio.core.errors import AuthExpiredError
from studio.core.models import Credential
from studio.core.ports import PlatformAdapter

_PAGE = (
    "<html><body style='font-family:sans-serif'><h3>{msg}</h3>"
    "<p>You can close this tab and return to the terminal.</p></body></html>"
)


def make_pkce() -> tuple[str, str]:
    """Return (code_verifier, S256 code_challenge)."""
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return verifier, base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


class _Handler(BaseHTTPRequestHandler):
    params: dict[str, str] = {}

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path != "/callback":
            self.send_response(404)
            self.end_headers()
            return
        type(self).params = {k: v[0] for k, v in parse_qs(parsed.query).items()}
        ok = "code" in type(self).params
        body = _PAGE.format(msg="Authorization received" if ok else "Authorization failed")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body.encode())

    def log_message(self, format: str, *args: object) -> None:  # silence request logging
        return


def run_authorization(
    adapter: PlatformAdapter,
    *,
    open_url: Callable[[str], object] = webbrowser.open,
    announce: Callable[[str], None] = print,
    timeout: float = 300.0,
) -> Credential:
    """Open the consent page and wait for the redirect to 127.0.0.1. Returns a Credential."""
    verifier, challenge = make_pkce()
    state = secrets.token_urlsafe(24)

    handler = type("Handler", (_Handler,), {"params": {}})
    server = HTTPServer(("127.0.0.1", adapter.redirect_port), handler)
    server.timeout = 1.0  # poll interval; overall limit enforced by `deadline`
    deadline = time.monotonic() + timeout
    redirect_uri = f"http://{adapter.redirect_host}:{server.server_port}/callback"
    url = adapter.authorization_url(state, challenge, redirect_uri)

    announce("Opening your browser to authorize. If it does not open, visit:\n" + url)
    open_url(url)
    try:
        # Browsers may make extra requests (e.g. favicon); keep serving until /callback arrives.
        while not handler.params and time.monotonic() < deadline:
            server.handle_request()
    finally:
        server.server_close()

    params = handler.params
    if not params:
        raise AuthExpiredError("Timed out waiting for authorization")
    if params.get("state") != state:
        raise AuthExpiredError("Authorization state mismatch; aborting")
    if "error" in params:
        raise AuthExpiredError(f"Authorization denied: {params['error']}")
    return adapter.exchange_code(params["code"], verifier, redirect_uri)
