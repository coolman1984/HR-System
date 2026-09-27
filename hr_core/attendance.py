"""The migrated attendance application inside the one HR-System server (phase 2.5, ADR-HR-005).

The attendance engine (engine.py, calculation_engine.py, dashboard.html, PROJECT.json) stays locked and unchanged:
its own request handler answers its own addresses, called by the HR-System server after the session and the right
were checked. None of its addresses collides with the HR API (TEST_HR_DELIVERY.py proves it), so one server, one
port and one sign-in serve both.

Its data (history.db, last_result.json, uploads/) lives in the same data folder. It is not a fold of the journal,
so backups copy history.db while this module's lock is held (no upload is half in the copy), and a lost history.db
comes back from the newest verified backup (hr_core/backup.recover_lost_attachment).
Standard library only.
"""

import os
import sys
import threading

FILE = "history.db"
READ, UPLOAD = "hr.attendance.read", "hr.attendance.upload"
# the engine's own addresses (dashboard.html calls them as they are) and the right each one needs
ROUTES = {
    ("GET", "/api/state"): READ, ("GET", "/api/runs"): READ, ("GET", "/api/rejected.csv"): READ,
    ("POST", "/api/query"): READ, ("POST", "/api/history"): READ, ("POST", "/api/export"): READ,
    ("POST", "/api/upload"): UPLOAD, ("POST", "/api/upload_multi"): UPLOAD, ("POST", "/api/rollback"): UPLOAD,
}
CHANGES = {"/api/upload": "attendance.uploaded", "/api/upload_multi": "attendance.uploaded", "/api/rollback": "attendance.rolled_back"}


def excel_installed():
    """Microsoft Excel on this PC? Only protected workbooks need it (the engine asks Excel to open them); ordinary
    workbooks are read without it. True / False on Windows, None elsewhere (not applicable)."""
    if os.name != "nt":
        return None
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r"Excel.Application\CLSID"):
            return True
    except OSError:
        return False


NEEDS_EXCEL = (".xls", ".xlsb")  # binary workbooks: the engine always opens them with Microsoft Excel


def needs_excel(filename, content):
    """Would the engine have to ask Microsoft Excel to open this file? Binary workbooks always; an .xlsx/.xlsm that is
    not a readable zip package (a protected or damaged workbook) too. CSV and ordinary .xlsx never."""
    name = (filename or "").lower()
    if name.endswith(NEEDS_EXCEL):
        return True
    if name.endswith((".xlsx", ".xlsm")):
        return not content.startswith(b"PK\x03\x04")
    return False


WITHOUT_EXCEL = ("This file needs Microsoft Excel to be opened (a protected, damaged or old-format workbook), and Excel is "
                 "not installed on this computer. Save it as an ordinary .xlsx workbook, or upload it on a computer with Excel.")


class Attendance:
    def __init__(self, data_dir):
        self.data_dir = os.path.abspath(data_dir)
        self.path = os.path.join(self.data_dir, FILE)
        self.lock = threading.RLock()  # one upload at a time, and never during a backup copy
        self._engine = None

    @property
    def engine(self):
        """The locked engine, bound to this data folder. It reads its folder once, when first imported."""
        if self._engine is None:
            loaded = sys.modules.get("engine")
            if loaded is not None and os.path.abspath(str(loaded.DATA_DIR)) != self.data_dir:
                raise RuntimeError(f"the attendance engine is already bound to {loaded.DATA_DIR}")
            os.environ["EXCEL_APP_DATA_DIR"] = self.data_dir
            import engine
            engine.init_db()
            self._engine = engine
        return self._engine

    def route(self, method, path):
        return ROUTES.get((method, path))

    def dashboard(self):
        with open(os.path.join(os.path.dirname(os.path.abspath(self.engine.__file__)), "dashboard.html"), "rb") as fh:
            return fh.read()

    def status(self):
        return {"history_file": os.path.isfile(self.path), "excel_desktop": excel_installed()}
