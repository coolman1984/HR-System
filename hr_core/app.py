"""HR-System as one product: one server, one port, one sign-in (phase 2.5, ADR-HR-005).

    product = Product(Home())          # %ProgramData%\\HR-System when installed, HR_HOME otherwise
    server = product.serve()           # setup mode until the installation belongs to a company
    server.serve_forever()

Opening an installation, in order: put back a lost attendance history from the newest verified backup; bring the
data to this program's data version (hr_core/upgrade.py: verified pre-update backup first); bind the locked
attendance engine to the data folder; verify the journal and the audit; only then promote the installer that came
with this version to the recovery folder and start the automatic backups, and (when a GMES address is set in the
settings) the link that publishes HR's workforce truth to manufacturing (hr_core/eco_link.py).
Standard library only.
"""

import os
import threading
from http.server import ThreadingHTTPServer

from . import signing, upgrade
from .attendance import FILE as ATTENDANCE_FILE, Attendance
from .backup import recover_lost_attachment
from .home import Home, HomeError
from .registry import RegistryError
from .service import HRService
from .version import DATA_VERSION, PRODUCT, VERSION


class Product:
    def __init__(self, home=None):
        self.home = home or Home()
        self.attendance = Attendance(self.home.data)
        self.service = None
        self.server = None
        self.link = None  # hr_core/eco_link.EcoLink once the data is open; its thread runs only with a GMES address
        self.report = {}
        self.error = None  # set when the data cannot be opened (e.g. a failed update): the screens show it
        self.lock = threading.Lock()

    # ------------------------------------------------------------------ opening
    def open(self, link=True):
        """`link=False`: maintenance tools (hr_main.py tool ...) open the data without publishing anything."""
        company = self.home.company()
        if not company:
            raise HomeError("company.missing", "this installation does not belong to a company yet")
        recovered = None
        if not os.path.isfile(self.attendance.path) and os.path.isfile(os.path.join(self.home.data, "hr_journal.db")):
            recovered = recover_lost_attachment(self.home.data, [self.home.backups], ATTENDANCE_FILE)

        def open_service():
            return HRService(self.home.data, company["id"], company["code"], company["name"], backup_dir=self.home.backups,
                             attachments=[(ATTENDANCE_FILE, self.attendance.path, self.attendance.lock)])

        self.service, self.report["upgrade"] = upgrade.prepare(self.home, open_service)
        if recovered:
            self.service.journal.audit("system", "attendance.recovered", "system", {"from_backup": recovered})
        self.report["attendance_recovered_from"] = recovered
        self.attendance.engine  # bind the locked engine to this data folder now, not on the first request
        health = self.service.health()
        if health["journal"]["ok"] and health["audit"]["ok"]:
            self.report["recovery"] = upgrade.promote_installer(self.home)
            if self.report["recovery"]:
                self.service.journal.audit("system", "recovery.installer", "system", self.report["recovery"])
        self.service.backups.start(float(self.home.config().get("backup_hours", 6)))
        from .eco_link import EcoLink
        self.link = EcoLink(self.home, company["id"], self.attendance, self.service.journal)
        if link:
            self.report["eco_link"] = self.link.start()
        return self.service

    def install(self, company, admin, ip=None):
        """First run: the company identity (from its owner application, or a local provisional one) and the first
        administrator. Checked before anything is written; if the program stops in between, the next attempt
        continues (the identity, once written, is kept and only the administrator is still asked for)."""
        from .auth import USERNAME, _policy
        with self.lock:
            if self.error:
                raise HomeError("setup.blocked", self.error["message"])
            # everything about the administrator is checked BEFORE the company identity is written: the identity
            # can never be changed afterwards, so a refusal must leave nothing behind
            _policy(admin.get("password") or "")
            username = (admin.get("username") or "").strip().lower()
            if not USERNAME.match(username):
                raise HomeError("setup.admin", "user names are 3-50 lower-case letters, digits, dot, dash or underscore")
            if len((admin.get("display_name") or username).strip()) > 100:
                raise HomeError("setup.admin", "the name is too long")
            if not self.home.company():
                self.home.check_company(company.get("source"), company.get("code"), company.get("name"), company.get("id"), company.get("owner_app"))
            if not self.home.company():
                self.home.set_company(company.get("source"), company.get("code"), company.get("name"), company.get("id"), company.get("owner_app"))
            if self.service is None:
                self.open()
            if self.service.auth.has_users():
                raise HomeError("setup.done", "this installation is already set up")
            self.service.bootstrap_admin(username, (admin.get("display_name") or username).strip(), admin["password"], ip)
            if self.server is not None:
                from .api import make_handler
                self.server.RequestHandlerClass = make_handler(self.service, self)

    def demo_skip_allowed(self):
        """The "development stage: skip" button exists only on an empty installation started for a presentation (HR_DEMO_SKIP=1)."""
        return os.environ.get("HR_DEMO_SKIP") == "1" and not self.home.company() and self.service is None and self.error is None

    def skip_to_demo(self, ip=None):
        """Presentation only: builds the demo company (tools/make_demo.py: synthetic people, attendance, leave, overtime, payroll set-up) beside this
        empty installation, moves it in and opens it, so the audience goes from the set-up screen straight into a working application
        (sign in: admin / 123). Refused on any installation that already belongs to a company."""
        import shutil
        import subprocess
        import sys
        from .home import Home
        with self.lock:
            if not self.demo_skip_allowed():
                raise HomeError("setup.skip_refused", "skipping the set-up is only offered on an empty installation started for a presentation")
            repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            build = self.home.path + ".demo-build"
            shutil.rmtree(build, ignore_errors=True)
            env = {**os.environ, "OPENBLAS_NUM_THREADS": "1"}
            env.pop("HR_DEMO_SKIP", None)
            done = subprocess.run([sys.executable, os.path.join(repo, "tools", "make_demo.py"), build], cwd=repo, env=env, capture_output=True, text=True, timeout=600)
            if done.returncode != 0:
                shutil.rmtree(build, ignore_errors=True)
                raise HomeError("setup.skip_failed", "the demo company could not be built: " + (done.stderr or done.stdout)[-300:])
            for name in os.listdir(build):
                target = os.path.join(self.home.path, name)
                if os.path.isdir(target):
                    shutil.rmtree(target)
                elif os.path.exists(target):
                    os.remove(target)
                shutil.move(os.path.join(build, name), target)
            shutil.rmtree(build, ignore_errors=True)
            self.home = Home(self.home.path)
            self.attendance = Attendance(self.home.data)
            self.open()
            if self.server is not None:
                from .api import make_handler
                self.server.RequestHandlerClass = make_handler(self.service, self)

    # ------------------------------------------------------------------ information
    def info(self, local=False):
        """Public: what the sign-in page needs (no personal data, no secrets)."""
        company = self.home.company() or {}
        cfg = self.home.config()
        users = self.service.auth.has_users() if self.service else False
        return {"product": PRODUCT, "version": VERSION, "setup_needed": not (company and users), "local": bool(local), "demo_skip": bool(local and self.demo_skip_allowed()),
                "error": self.error,
                "language": cfg.get("language", "en"),
                "company": {k: company.get(k) for k in ("code", "name", "source", "provisional")} if company else None}

    def health_extra(self):
        company = self.home.company() or {}
        return {"product": {"version": VERSION, "data_version": upgrade.read_version(self.home.data), "program_data_version": DATA_VERSION,
                            "home": self.home.path, "signing_backend": signing.BACKEND},
                "company": {k: company.get(k) for k in ("id", "code", "name", "source", "owner_app", "provisional", "set_at")},
                "attendance": self.attendance.status(),
                "recovery": upgrade.known_good(self.home),
                "startup": self.report}

    def settings(self):
        cfg = self.home.config()
        return {k: cfg[k] for k in ("autostart", "language", "backup_hours")}

    # ------------------------------------------------------------------ serving
    def serve(self, host=None, port=None):
        from .api import make_handler
        from .web import make_setup_handler
        cfg = self.home.config()
        if self.home.company() and self.service is None and self.error is None:
            try:
                self.open()
            except (upgrade.UpgradeError, HomeError, RegistryError, RuntimeError) as exc:
                # the data is left as it is; the screens explain what happened and what to do
                self.error = {"code": getattr(exc, "code", "open.failed"), "message": str(exc)}
                with open(os.path.join(self.home.logs, "startup-error.txt"), "a", encoding="utf-8") as fh:
                    fh.write(f"{self.error['code']}: {self.error['message']}\n")
        ready = self.service is not None and self.service.auth.has_users()
        handler = make_handler(self.service, self) if ready else make_setup_handler(self)
        self.server = ThreadingHTTPServer((host or cfg["host"], int(port if port is not None else cfg["port"])), handler)
        self.server.daemon_threads = True
        return self.server

    def close(self):
        if self.link is not None:
            self.link.stop()
            self.link = None
        if self.service is not None:
            self.service.close()
            self.service = None
