"""Local loopback HTTP server to receive TikTok OAuth redirect (desktop flow)."""

from __future__ import annotations

import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer


class _ReuseHTTPServer(HTTPServer):
    allow_reuse_address = True
def run_oauth_loopback(
    port: int,
    expected_state: str,
    timeout_s: float = 300.0,
    *,
    success_html_body: str | None = None,
) -> tuple[str | None, str | None]:
    """
    Listen on 127.0.0.1:port for one GET with ?code= or ?error=.
    Returns (authorization_code, error_string).
    """
    result: dict[str, str | None] = {"code": None, "err": None}
    ev = threading.Event()

    def finish(code: str | None, err: str | None, state: str | None) -> None:
        if state and state != expected_state:
            result["err"] = "state_mismatch"
        elif err:
            result["err"] = err
        else:
            result["code"] = code
        ev.set()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args: object) -> None:
            return

        def do_GET(self) -> None:
            parsed = urllib.parse.urlparse(self.path)
            qs = urllib.parse.parse_qs(parsed.query)
            err = (qs.get("error") or [None])[0]
            code = (qs.get("code") or [None])[0]
            state = (qs.get("state") or [None])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            body = success_html_body or (
                "<html><body><p>TikTok authorization received. You can close this tab.</p></body></html>"
            )
            self.wfile.write(body.encode("utf-8"))
            finish(code, err, state)

    server = _ReuseHTTPServer(("127.0.0.1", port), Handler)

    def serve_loop() -> None:
        end = time.time() + timeout_s
        while not ev.is_set() and time.time() < end:
            server.timeout = 1.0
            server.handle_request()
        try:
            server.server_close()
        except Exception:
            pass

    t = threading.Thread(target=serve_loop, daemon=True)
    t.start()
    ev.wait(timeout=timeout_s + 5)
    try:
        server.shutdown()
    except Exception:
        pass
    t.join(timeout=2)
    return result.get("code"), result.get("err")
