"""Web-Dashboard: stdlib-HTTP-Server, JSON-API und Server-Sent-Events.

Keine externen Abhängigkeiten, keine CDNs – läuft auch ohne Internet.
ACHTUNG: keine Authentifizierung. Nur im eigenen Netz betreiben
(oder `[web] bind = "127.0.0.1"` + SSH-Tunnel).
"""
import json
import logging
import os
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

log = logging.getLogger("web")
STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
ASSETS = {
    "/icon.svg": "image/svg+xml", "/icon-small.svg": "image/svg+xml",
    "/favicon.ico": "image/x-icon", "/apple-touch-icon.png": "image/png",
    "/icon-192.png": "image/png", "/manifest.webmanifest": "application/manifest+json",
}


class RingLog(logging.Handler):
    """Hält die letzten N Logzeilen für das Dashboard vor."""

    def __init__(self, size=500):
        super().__init__()
        self.buf = deque(maxlen=size)
        self.seq = 0
        self._buf_lock = threading.Lock()   # NICHT self.lock – gehört logging.Handler

    def emit(self, record):
        try:
            line = self.format(record)
        except Exception:   # noqa: BLE001
            return
        with self._buf_lock:
            self.seq += 1
            self.buf.append((self.seq, record.levelname, line))

    def since(self, seq):
        with self._buf_lock:
            return [x for x in self.buf if x[0] > seq]


def make_handler(bridge, ringlog):
    class Handler(BaseHTTPRequestHandler):
        server_version = "wheelbridge"

        def log_message(self, *args):   # kein Access-Log-Spam
            pass

        def _send(self, code, body, ctype):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj, code=200):
            self._send(code, json.dumps(obj).encode(), "application/json; charset=utf-8")

        def _body(self):
            n = int(self.headers.get("Content-Length") or 0)
            if n > 65536:
                raise ValueError("Request zu groß")
            data = json.loads(self.rfile.read(n) or b"{}")
            if not isinstance(data, dict):
                raise ValueError("JSON-Objekt erwartet")
            return data

        def do_GET(self):
            path = self.path.split("?", 1)[0]
            if path in ("/", "/index.html"):
                with open(os.path.join(STATIC, "index.html"), "rb") as f:
                    self._send(200, f.read(), "text/html; charset=utf-8")
            elif path in ASSETS:
                with open(os.path.join(STATIC, path.lstrip("/")), "rb") as f:
                    self._send(200, f.read(), ASSETS[path])
            elif path == "/api/status":
                self._json(bridge.status())
            elif path == "/api/config":
                self._json({"effective": bridge.cfg, "overrides": bridge.overrides})
            elif path == "/api/log":
                self._json(ringlog.since(0))
            elif path == "/api/stream":
                self._stream()
            else:
                self._json({"ok": False, "error": "not found"}, 404)

        def _stream(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            last = 0
            try:
                while bridge.running:
                    lines = ringlog.since(last)
                    if lines:
                        last = lines[-1][0]
                    msg = json.dumps({"status": bridge.status(), "log": lines})
                    self.wfile.write(f"data: {msg}\n\n".encode())
                    self.wfile.flush()
                    time.sleep(0.1)
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass

        def do_POST(self):
            path = self.path.split("?", 1)[0]
            try:
                if path == "/api/config":
                    bridge.update_settings(self._body())
                    self._json({"ok": True, "config": bridge.cfg})
                elif path == "/api/config/reset":
                    bridge.reset_settings()
                    self._json({"ok": True, "config": bridge.cfg})
                elif path == "/api/action/rumble":
                    bridge.test_rumble()
                    self._json({"ok": True})
                elif path == "/api/action/reconnect":
                    bridge.need_reset.set()
                    self._json({"ok": True})
                else:
                    self._json({"ok": False, "error": "not found"}, 404)
            except (ValueError, TypeError, KeyError) as e:
                self._json({"ok": False, "error": str(e)}, 400)
            except Exception as e:   # noqa: BLE001
                log.exception("API-Fehler")
                self._json({"ok": False, "error": str(e)}, 500)

    return Handler


def start_web(bridge, ringlog, bind="0.0.0.0", port=8080):
    srv = ThreadingHTTPServer((bind, port), make_handler(bridge, ringlog))
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, name="web", daemon=True).start()
    log.info("Dashboard: http://%s:%d", "<pi-ip>" if bind == "0.0.0.0" else bind, port)
    return srv
