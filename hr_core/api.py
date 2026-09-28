"""HR-System's HTTP API (phase 2) — a thin, strict translation of hr_core.service.HRService.

* Sessions: cookie `hr_sid` (HttpOnly, SameSite=Strict). The token is kept only as a SHA-256 hash on the server.
* Every mutation must be `Content-Type: application/json` (even with no body) and, when the browser sends an Origin, come from this
  server's own origin (no cross-site requests). Bodies are limited to 1 MB.
* Permissions are enforced by the service on every request; the answer to a missing right is 403, to a missing
  or ended session 401, to a stale version 409. Unexpected errors answer 500 without details (they are audited).
* The first administrator can be created only from the server machine itself, and only while no user exists.
Standard library only.
"""

import io
import json
import os
import re
import traceback
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .auth import AuthError
from .backup import BackupError
from .home import HomeError
from .registry import Conflict, RegistryError

MAX_BODY = 1 << 20
LOCAL = {"127.0.0.1", "::1"}


class HttpError(Exception):
    def __init__(self, status, code, message):
        super().__init__(message)
        self.status, self.code = status, code


def make_handler(service, product=None):
    """`product` (hr_core.app.Product) adds the screens, the attendance application behind the same sign-in, the
    settings and the product's own health; without it this is the phase-2 API alone (tests, the CLI server)."""
    routes = []
    attendance = product.attendance if product is not None else None
    base = attendance.engine.Handler if attendance is not None else BaseHTTPRequestHandler

    def route(method, pattern):
        def deco(fn):
            routes.append((method, re.compile("^" + pattern + "$"), fn))
            return fn
        return deco

    # -------------------------------------------------------------- sessions
    @route("POST", "/api/setup")
    def setup(h, body, user):
        if h.client_address[0] not in LOCAL:
            raise HttpError(403, "setup.local_only", "the first administrator can only be created on the server machine")
        service.bootstrap_admin(body.get("username", ""), body.get("display_name", ""), body.get("password", ""), h.ip)
        return 201, {"ok": True}

    @route("POST", "/api/login")
    def login(h, body, user):
        token, u = service.login(body.get("username"), body.get("password"), h.ip)
        h.set_cookie = f"hr_sid={token}; HttpOnly; SameSite=Strict; Path=/"
        return 200, service.me(u)

    @route("POST", "/api/logout")
    def logout(h, body, user):
        service.logout(h.token, user, h.ip)
        h.set_cookie = "hr_sid=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0"
        return 200, {"ok": True}

    @route("GET", "/api/me")
    def me(h, body, user):
        service.require(user, "self", h.ip)
        return 200, service.me(user)

    @route("POST", "/api/password")
    def password(h, body, user):
        service.change_own_password(user, body.get("old", ""), body.get("new", ""), h.ip)
        return 200, {"ok": True}

    # -------------------------------------------------------------- business data
    @route("GET", "/api/recycle")
    def recycle(h, body, user):
        return 200, service.recycle_bin(user, h.ip)

    @route("GET", "/api/(org_unit|job|position|employee|shift|work_calendar|shift_assignment|roster_override|skill|employee_skill)")
    def list_(h, body, user, entity):
        return 200, service.list(user, entity, h.query.get("deleted") == "1", h.ip)

    @route("PUT", "/api/(org_unit|job|position|employee|shift|work_calendar|shift_assignment|roster_override|skill|employee_skill)/([^/]+)")
    def put(h, body, user, entity, code):
        return 200, service.save(user, entity, code, body.get("fields") or {}, body.get("expected_ver"), h.ip)

    @route("DELETE", "/api/(org_unit|job|position|employee|shift|work_calendar|shift_assignment|roster_override|skill|employee_skill)/([^/]+)")
    def delete(h, body, user, entity, code):
        ver = h.query.get("ver")
        if not (ver or "").isdigit():
            raise HttpError(409, "ver.required", "send the version you are deleting (?ver=)")
        return 200, {"seq": service.delete(user, entity, code, int(ver), h.query.get("type"), h.ip)}

    @route("POST", "/api/(org_unit|job|position|employee|shift|work_calendar|shift_assignment|roster_override|skill|employee_skill)/([^/]+)/restore")
    def restore(h, body, user, entity, code):
        return 200, {"seq": service.restore(user, entity, code, body.get("type"), h.ip)}

    # -------------------------------------------------------------- the planned schedule (phase 3)
    @route("GET", "/api/schedule")
    def schedule(h, body, user):
        q = h.query
        return 200, service.schedule(user, q.get("from", ""), q.get("to", ""), q.get("employee") or None, h.ip)

    @route("GET", "/api/schedule/compare")
    def schedule_compare(h, body, user):
        rows = attendance.engine.current_rows() if attendance is not None else []
        return 200, service.compare(user, h.query.get("from", ""), h.query.get("to", ""), rows, h.ip)

    @route("POST", "/api/schedule/swap")
    def schedule_swap(h, body, user):
        return 200, {"seq": service.swap(user, body.get("date", ""), body.get("a", ""), body.get("b", ""), body.get("reason", ""), h.ip)}

    # -------------------------------------------------------------- accounts
    @route("GET", "/api/admin/users")
    def users(h, body, user):
        return 200, service.users(user, h.ip)

    @route("POST", "/api/admin/users")
    def create_user(h, body, user):
        return 201, {"seq": service.create_user(user, body.get("username", ""), body.get("display_name", ""), body.get("password", ""),
                                                body.get("profile", ""), body.get("extra_perms") or [], h.ip)}

    @route("PATCH", "/api/admin/users/([^/]+)")
    def update_user(h, body, user, username):
        return 200, {"seq": service.update_user(user, username, body.get("fields") or {}, body.get("expected_ver"), h.ip)}

    @route("POST", "/api/admin/users/([^/]+)/password")
    def reset_password(h, body, user, username):
        return 200, {"seq": service.reset_password(user, username, body.get("password", ""), h.ip)}

    @route("GET", "/api/admin/profiles")
    def profiles(h, body, user):
        return 200, service.profiles(user, h.ip)

    @route("PUT", "/api/admin/profiles/([^/]+)")
    def save_profile(h, body, user, code):
        return 200, {"seq": service.save_profile(user, code, body.get("name", code), body.get("perms") or [], body.get("expected_ver"), h.ip)}

    # -------------------------------------------------------------- audit, health, backups
    @route("GET", "/api/admin/audit")
    def audit(h, body, user):
        return 200, service.audit_entries(user, h.query.get("category"), min(int(h.query.get("limit", "200") or 200), 1000), h.ip)

    @route("GET", "/api/admin/health")
    def health(h, body, user):
        out = service.health(user, h.ip)
        if product is not None:
            out.update(product.health_extra())
        return 200, out

    # -------------------------------------------------------------- the product (phase 2.5)
    if product is not None:
        @route("GET", "/api/info")
        def info(h, body, user):
            return 200, product.info(h.client_address[0] in LOCAL)

        @route("GET", "/api/admin/settings")
        def settings(h, body, user):
            service.require(user, "admin.settings.manage", h.ip, "settings")
            return 200, product.settings()

        @route("PUT", "/api/admin/settings")
        def settings_put(h, body, user):
            service.require(user, "admin.settings.manage", h.ip, "settings")
            changes = {k: body[k] for k in ("autostart", "language", "backup_hours") if k in body}
            product.home.set(**changes)
            service.journal.audit("security", "settings.changed", user["code"], changes, h.ip)
            return 200, product.settings()

    @route("GET", "/api/admin/backups")
    def backups(h, body, user):
        return 200, service.backup_list(user, h.ip)

    @route("POST", "/api/admin/backups")
    def backup_create(h, body, user):
        return 201, service.backup_create(user, h.ip)

    @route("POST", "/api/admin/backups/([^/]+)/(verify|rehearse|restore)")
    def backup_action(h, body, user, name, action):
        fn = {"verify": service.backup_verify, "rehearse": service.backup_rehearse, "restore": service.backup_restore}[action]
        out = fn(user, name, h.ip)
        return 200, out if isinstance(out, dict) else {"seq": out}

    class Handler(base):
        server_version = "HR-System"
        sys_version = ""

        def log_message(self, *args):  # requests are audited by the service; no access log with tokens
            pass

        def _dispatch(self, method):
            self.set_cookie, self.ip = None, self.client_address[0]
            url = urlparse(self.path)
            self.query = {k: v[-1] for k, v in parse_qs(url.query).items()}
            cookie = SimpleCookie(self.headers.get("Cookie") or "")
            self.token = cookie["hr_sid"].value if "hr_sid" in cookie else None
            try:
                if method != "GET":
                    origin = self.headers.get("Origin")
                    if origin and urlparse(origin).netloc != self.headers.get("Host"):
                        raise HttpError(403, "origin.refused", "cross-site request refused")
                if product is not None and self._product(method, url):
                    return
                if method != "GET":
                    length = int(self.headers.get("Content-Length") or 0)
                    if length > MAX_BODY:
                        raise HttpError(413, "body.too_large", "request too large")
                    # every change must declare JSON, even with no body: a cross-site form cannot (CORS preflight)
                    if (self.headers.get("Content-Type") or "").split(";")[0].strip() != "application/json":
                        raise HttpError(415, "body.json_only", "send JSON (Content-Type: application/json)")
                    raw = self.rfile.read(length) if length else b""
                    body = json.loads(raw or b"{}")
                    if not isinstance(body, dict):
                        raise HttpError(400, "body.object", "the body must be a JSON object")
                else:
                    body = {}
                for m, rx, fn in routes:
                    match = rx.match(url.path)
                    if m == method and match:
                        user = service.session(self.token) if self.token else None
                        status, out = fn(self, body, user, *match.groups())
                        return self._send(status, out)
                raise HttpError(404, "not_found", "no such address")
            except HttpError as exc:
                self._send(exc.status, {"error": exc.code, "message": str(exc)})
            except AuthError as exc:
                self._send(exc.status, {"error": exc.code, "message": str(exc)})
            except Conflict as exc:
                self._send(409, {"error": exc.code, "message": str(exc)})
            except RegistryError as exc:
                self._send(404 if exc.code.endswith("not_found") else 400, {"error": exc.code, "message": str(exc)})
            except BackupError as exc:
                self._send(400, {"error": "backup", "message": str(exc)})
            except HomeError as exc:
                self._send(400, {"error": exc.code, "message": str(exc)})
            except (ValueError, KeyError, TypeError) as exc:
                try:  # usually a malformed request; recorded with its place so a server-side bug shows up too
                    where = traceback.extract_tb(exc.__traceback__)[-1]
                    service.journal.audit("system", "request.unreadable", "-", {"error": type(exc).__name__, "path": url.path,
                                          "where": f"{os.path.basename(where.filename)}:{where.lineno}"}, self.ip)
                except Exception:
                    pass
                self._send(400, {"error": "bad_request", "message": "the request could not be read"})
            except Exception as exc:
                try:
                    where = traceback.extract_tb(exc.__traceback__)[-1]  # file and line only: an exception text may hold data
                    service.journal.audit("system", "server.error", "-", {"error": type(exc).__name__, "path": url.path,
                                          "where": f"{os.path.basename(where.filename)}:{where.lineno}"}, self.ip)
                except Exception:
                    pass
                self._send(500, {"error": "server", "message": "internal error (recorded in the audit log)"})

        def _product(self, method, url):
            """The screens and the attendance application. True when this request was answered here."""
            from .web import send_asset, static_name
            if method == "GET":
                name = static_name(url.path)
                if name is not None:
                    if send_asset(self, name):
                        return True
                    raise HttpError(404, "not_found", "no such address")
                if url.path in ("/attendance", "/attendance/"):
                    user = service.session(self.token) if self.token else None
                    if user is None:  # a page, not an API: send the person to the sign-in screen
                        self.send_response(302)
                        self.send_header("Location", "/#/login?next=attendance")
                        self.end_headers()
                        return True
                    service.require(user, "hr.attendance.read", self.ip, "attendance")
                    body = attendance.dashboard()
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("X-Frame-Options", "SAMEORIGIN")
                    self.end_headers()
                    self.wfile.write(body)
                    return True
            right = attendance.route(method, url.path)
            if right is None:
                return False
            user = service.session(self.token) if self.token else None
            service.require(user, right, self.ip, f"attendance:{url.path}")
            if url.path in ("/api/upload", "/api/upload_multi") and self._needs_missing_excel(url):
                service.journal.audit("activity", "attendance.refused", user["code"], {"path": url.path, "reason": "excel.missing"}, self.ip)
                from .attendance import WITHOUT_EXCEL
                self._send(400, {"error": "attendance.needs_excel", "message": WITHOUT_EXCEL})
                return True
            self.engine_reply = None
            with attendance.lock:  # the locked engine answers its own address, as it always did
                (attendance.engine.Handler.do_GET if method == "GET" else attendance.engine.Handler.do_POST)(self)
            from .attendance import CHANGES
            if url.path in CHANGES:
                status, reply = self.engine_reply or (None, None)
                reply = reply if isinstance(reply, dict) else {}
                done = status == 200 and "error" not in reply and not reply.get("duplicate_upload")
                detail = {"path": url.path, "status": status}
                if done:
                    detail.update({k: reply[k] for k in ("run_id", "accepted_count", "rejected_count", "current_count") if k in reply})
                else:
                    detail["duplicate"] = bool(reply.get("duplicate_upload"))
                service.journal.audit("activity", CHANGES[url.path] if done else "attendance.refused", user["code"], detail, self.ip)
            return True

        def _needs_missing_excel(self, url):
            """Without Microsoft Excel the engine would wait minutes for Excel to open a protected or old-format
            workbook, holding the attendance lock (seen in Windows CI). Refuse such a file at once; the engine is
            unchanged and gets the same bytes otherwise."""
            from .attendance import excel_installed, needs_excel
            if excel_installed() is not False:
                return False
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0 or length > attendance.engine.MAX_UPLOAD:
                return False  # the engine refuses these itself, as before
            body = self.rfile.read(length)
            self.rfile = io.BytesIO(body)  # the engine reads the same bytes afterwards
            if url.path == "/api/upload":
                name = parse_qs(url.query).get("filename", ["upload.xlsx"])[0]
                return needs_excel(name, body)
            parts = attendance.engine.parse_multipart(body, self.headers.get("Content-Type", ""))
            return any(needs_excel(p.get("filename") or "", p.get("content") or b"") for p in parts.values())

        def send_json(self, payload, status=200):
            """The engine answers through this (engine.Handler.send_json); remember what it said, for the audit."""
            self.engine_reply = (status, payload)
            return attendance.engine.Handler.send_json(self, payload, status)

        def _send(self, status, payload):
            data = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            if self.set_cookie:
                self.send_header("Set-Cookie", self.set_cookie)
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            self._dispatch("GET")

        def do_POST(self):
            self._dispatch("POST")

        def do_PUT(self):
            self._dispatch("PUT")

        def do_PATCH(self):
            self._dispatch("PATCH")

        def do_DELETE(self):
            self._dispatch("DELETE")

    return Handler


def serve(service, host="127.0.0.1", port=8766):
    server = ThreadingHTTPServer((host, port), make_handler(service))
    server.daemon_threads = True
    return server
