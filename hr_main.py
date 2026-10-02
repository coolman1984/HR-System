"""HR-System — the one entry point of the installed product (HR-System.exe, built by tools/build_windows.py).

  HR-System.exe                 start the server and open it in the browser
  HR-System.exe --background    start without opening the browser (Windows start-up); does nothing when the setting
                                "start with Windows" is off
  HR-System.exe --no-browser    start without opening Chrome, regardless of the Windows start-up setting
  HR-System.exe tool <command>  maintenance from a command window: status, backup, backups, rehearse <name>, health,
                                data-version, recovery

The installed program keeps everything it writes in %ProgramData%\\HR-System (HR_HOME overrides), so updating or
removing the program never touches the data. A second start while the server runs only opens the browser.
Standard library only.
"""

import json
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
for vendored in (os.path.join(HERE, "vendor"), os.path.join(HERE, "vendor.zip")):  # openpyxl, in a source checkout
    if os.path.exists(vendored) and vendored not in sys.path:
        sys.path.insert(1, vendored)


def _running(port):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/info", timeout=2) as r:
            return json.load(r).get("product") == "HR-System"
    except Exception:
        return False


def _open_chrome(url):
    """Use the owner's interactive-desktop helper; never a default browser handler."""
    launchers = (
        r"D:\WORK\Software Development\GitHub\AI CREW\Mandatory To Use Skills\windows-chrome-launcher\scripts\open_chrome.py",
        os.path.join(os.environ.get("USERPROFILE", os.path.expanduser("~")), ".codex", "skills",
                     "windows-chrome-launcher", "scripts", "open_chrome.py"),
    )
    launcher = next((path for path in launchers if os.path.isfile(path)), None)
    # A frozen executable is HR-System.exe, not a Python interpreter.
    if getattr(sys, "frozen", False):
        python = shutil.which("python")
        py_launcher = shutil.which("py") if not python else None
        command = [python] if python else ([py_launcher, "-3"] if py_launcher else [])
    else:
        command = [sys.executable] if sys.executable else []
    if launcher and command:
        try:
            result = subprocess.run(command + [launcher, url], timeout=20, check=False,
                                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if result.returncode == 0:
                return True
        except (OSError, subprocess.TimeoutExpired):
            pass
    print(f"Open this URL in Google Chrome: {url} (Chrome launcher unavailable)", flush=True)
    return False


def tool(home, argv):
    from hr_core import upgrade
    from hr_core.app import Product
    cmd = argv[0] if argv else "status"
    if cmd == "data-version":
        print(json.dumps({"data_version": upgrade.read_version(home.data)}))
        return 0
    if cmd == "recovery":
        print(json.dumps(upgrade.known_good(home), indent=1))
        return 0
    product = Product(home)
    try:
        svc = product.open(link=False)  # a maintenance command never publishes
        if cmd in ("status", "health"):
            h = svc.health()
            h.update(product.health_extra())
            print(json.dumps(h, indent=1, default=str))
            return 0 if h["journal"]["ok"] and h["audit"]["ok"] else 1
        if cmd == "backup":
            made = svc.backups.create("local-tool", "manual")
            made["rehearsal"] = svc.backups.rehearse(made["path"], "local-tool")
            print(json.dumps({"name": made["name"], "rehearsal": made["rehearsal"]}, indent=1))
            return 0 if made["rehearsal"]["ok"] else 1
        if cmd == "backups":
            print(json.dumps(svc.backups.list(), indent=1))
            return 0
        if cmd == "rehearse" and len(argv) > 1:
            r = svc.backups.rehearse(svc.backups.path_of(argv[1]), "local-tool")
            print(json.dumps(r, indent=1))
            return 0 if r["ok"] else 1
        print(__doc__)
        return 2
    finally:
        product.close()


def main(argv):
    if sys.stdout is None:  # started without a console window
        sys.stdout = open(os.devnull, "w")
    if sys.stderr is None:
        sys.stderr = sys.stdout
    from hr_core.app import Product
    from hr_core.home import Home
    home = Home()
    if argv[:1] == ["tool"]:
        return tool(home, argv[1:])
    cfg = home.config()
    background = "--background" in argv
    no_browser = background or "--no-browser" in argv
    if background and not cfg.get("autostart", True):
        return 0  # the person switched "start with Windows" off in the settings
    port = int(argv[argv.index("--port") + 1]) if "--port" in argv else int(cfg["port"])
    url = f"http://127.0.0.1:{port}/"
    if _running(port):
        if not no_browser:
            _open_chrome(url)
        return 0
    product = Product(home)
    server = product.serve(port=port)
    print(f"HR-System {url} (data: {home.path})" + (f"\nNOT READY: {product.error['message']}" if product.error else ""), flush=True)
    if not no_browser:
        threading.Thread(target=lambda: (time.sleep(0.8), _open_chrome(url)), daemon=True).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        product.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
