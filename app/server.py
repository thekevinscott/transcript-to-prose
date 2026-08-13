"""Stdlib HTTP server. No web framework.

Routes:
  GET  /            -> static/index.html
  GET  /<file>      -> static/<file>
  GET  /api/config  -> the control + panel definitions from config.py
  POST /api/run     -> newline-delimited JSON stream of panel results
"""

import asyncio
import json
import os
import subprocess
import sys
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from . import config, runner

STATIC = Path(__file__).resolve().parent.parent / "static"

CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
    ".json": "application/json",
}

MAX_BODY = 2_000_000  # 2 MB of transcript is already absurd


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "transcript-to-prose"

    # ---- helpers ---------------------------------------------------------

    def _send(self, status, body=b"", content_type="text/plain; charset=utf-8"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _send_json(self, status, obj):
        self._send(status, json.dumps(obj).encode(), "application/json; charset=utf-8")

    def _serve_static(self, path):
        rel = "index.html" if path in ("", "/") else path.lstrip("/")
        target = (STATIC / rel).resolve()
        if not str(target).startswith(str(STATIC)) or not target.is_file():
            self._send(404, b"not found")
            return
        self._send(200, target.read_bytes(), CONTENT_TYPES.get(target.suffix, "application/octet-stream"))

    def _read_body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > MAX_BODY:
            return None
        return json.loads(self.rfile.read(length))

    # ---- routes ----------------------------------------------------------

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/config":
            self._send_json(200, config.client_config())
        else:
            self._serve_static(path)

    def do_POST(self):
        path = urlparse(self.path).path
        if path != "/api/run":
            self._send(404, b"not found")
            return

        try:
            payload = self._read_body()
        except (ValueError, json.JSONDecodeError):
            self._send_json(400, {"error": "bad json"})
            return
        if payload is None:
            self._send_json(400, {"error": "missing or oversized body"})
            return

        # Streamed NDJSON: one JSON object per line, flushed as it happens.
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Accel-Buffering", "no")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()

        def emit(event):
            line = (json.dumps(event) + "\n").encode()
            try:
                self.wfile.write(b"%x\r\n%s\r\n" % (len(line), line))
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                raise runner.ClientGone()

        try:
            asyncio.run(runner.run(payload, emit))
        except runner.ClientGone:
            self.close_connection = True
            return
        except Exception:
            traceback.print_exc()
            try:
                emit({"type": "error", "panel": None, "message": "server error, see console"})
            except runner.ClientGone:
                self.close_connection = True
                return
        try:
            self.wfile.write(b"0\r\n\r\n")
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True

    def log_message(self, fmt, *args):
        sys.stderr.write("%s %s\n" % (self.address_string(), fmt % args))


def tailnet_ip():
    """Bind to the tailnet interface only, so this isn't exposed to the LAN."""
    try:
        out = subprocess.run(
            ["tailscale", "ip", "-4"], capture_output=True, text=True, timeout=5
        )
        return out.stdout.strip().splitlines()[0].strip() or None
    except Exception:
        return None


def main():
    host = os.environ.get("TTP_HOST") or tailnet_ip() or "127.0.0.1"
    port = int(os.environ.get("TTP_PORT", "8788"))
    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    print(f"transcript-to-prose listening on http://{host}:{port}", file=sys.stderr)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
