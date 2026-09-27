"""The screens of HR-System and the first-run setup (phase 2.5).

The screens are static files in hr_core/web/ (one page, plain JavaScript, English and Arabic dictionaries). The
installed program carries them inside the compiled program (tools/make_assets.py writes hr_core/_assets.py at build
time), so no readable page files sit in the program folder; a source checkout reads the files directly.

Until the installation belongs to a company, the server runs in SETUP mode: it serves the screens, the public
product information and one setup call, allowed only from the server machine itself.
Standard library only.
"""

import json
import mimetypes
import os
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse

HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
LOCAL = {"127.0.0.1", "::1"}
TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
         ".json": "application/json; charset=utf-8", ".svg": "image/svg+xml"}
# the screens only need these; anything that could run code from another site is refused
SECURITY_HEADERS = {"X-Content-Type-Options": "nosniff", "X-Frame-Options": "SAMEORIGIN", "Referrer-Policy": "no-referrer",
                    "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
                                               "img-src 'self' data:; connect-src 'self'; frame-ancestors 'self'"}


def _packed():
    try:
        from . import _assets  # written by tools/make_assets.py for the installed program
        return _assets.FILES
    except ImportError:
        return None


def asset_names():
    packed = _packed()
    if packed is not None:
        return sorted(packed)
    out = []
    for root, _, files in os.walk(HERE):
        out += [os.path.relpath(os.path.join(root, f), HERE).replace(os.sep, "/") for f in files]
    return sorted(out)


def asset(name):
    """The bytes of one screen file, or None. Only names that exist are served (no path from the request is opened)."""
    packed = _packed()
    if packed is not None:
        return packed.get(name)
    if name not in asset_names():
        return None
    with open(os.path.join(HERE, *name.split("/")), "rb") as fh:
        return fh.read()


def send_asset(h, name):
    body = asset(name)
    if body is None:
        return False
    h.send_response(200)
    h.send_header("Content-Type", TYPES.get(os.path.splitext(name)[1], mimetypes.guess_type(name)[0] or "application/octet-stream"))
    h.send_header("Content-Length", str(len(body)))
    h.send_header("Cache-Control", "no-cache")
    for k, v in SECURITY_HEADERS.items():
        h.send_header(k, v)
    h.end_headers()
    h.wfile.write(body)
    return True


def static_name(path):
    """/ → index.html; /ui/<file> → <file>. Anything else is not a screen file."""
    if path in ("/", "/index.html"):
        return "index.html"
    if path.startswith("/ui/"):
        return path[len("/ui/"):]
    return None


def make_setup_handler(product):
    """The server before the installation belongs to a company: screens, product information, and the setup call."""

    class SetupHandler(BaseHTTPRequestHandler):
        server_version = "HR-System"
        sys_version = ""

        def log_message(self, *args):
            pass

        def _json(self, status, payload):
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            path = urlparse(self.path).path
            name = static_name(path)
            if name and send_asset(self, name):
                return
            if path == "/api/info":
                return self._json(200, product.info(self.client_address[0] in LOCAL))
            if path.startswith("/api/"):
                return self._json(503, {"error": "setup.required", "message": "this installation is not set up yet"})
            self.send_response(302)
            self.send_header("Location", "/")
            self.end_headers()

        def do_POST(self):
            path = urlparse(self.path).path
            if path != "/api/setup/install":
                return self._json(503, {"error": "setup.required", "message": "this installation is not set up yet"})
            if self.client_address[0] not in LOCAL:
                return self._json(403, {"error": "setup.local_only", "message": "set up HR-System on the server machine itself"})
            origin = self.headers.get("Origin")
            if origin and urlparse(origin).netloc != self.headers.get("Host"):
                return self._json(403, {"error": "origin.refused", "message": "cross-site request refused"})
            if (self.headers.get("Content-Type") or "").split(";")[0].strip() != "application/json":
                return self._json(415, {"error": "body.json_only", "message": "send JSON"})
            try:
                length = min(int(self.headers.get("Content-Length") or 0), 1 << 16)
                body = json.loads(self.rfile.read(length) or b"{}")
                company, admin = body.get("company") or {}, body.get("admin") or {}
                product.install(company, admin, self.client_address[0])
            except Exception as exc:  # a refusal names its reason; nothing is half-installed (see Product.install)
                code = getattr(exc, "code", "setup.failed")
                return self._json(400, {"error": code, "message": str(exc)})
            return self._json(201, {"ok": True})

    return SetupHandler
