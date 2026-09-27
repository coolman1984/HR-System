"""Builds the Windows installer HR-System-Setup-<version>.exe (run on Windows; CI does it on every pull request).

Steps: pack the screens into hr_core/_assets.py, draw the icon, unpack the vendored Excel library, compile hr_main.py
and everything it imports into HR-System.exe with Nuitka (Python translated to C, its own Python runtime and the
`cryptography` library inside, no readable program source), check the program folder, then wrap it with Inno Setup.
Reference: BAMS tools/build_windows.py (same approach, written again for HR-System; docs/HR_DELIVERY.md ADR-HR-004).

    python -m pip install "nuitka>=2.4,<3" ordered-set zstandard cryptography      (and Inno Setup 6)
    python tools/build_windows.py
"""
import glob
import os
import shutil
import subprocess
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD = os.path.join(ROOT, "build")
DIST = os.path.join(BUILD, "hr_main.dist")
sys.path.insert(0, ROOT)
from hr_core.version import COPYRIGHT, DEVELOPER, PRODUCT, VERSION  # noqa: E402

# the locked attendance application reads these next to its own module; CUSTOM_RULES.py is its documented, optional
# customisation hook (read as a file by the engine), so it is the one .py a customer may see
DATA_FILES = ["PROJECT.json", "dashboard.html", "department_packs.json", "excel_com.ps1", "CUSTOM_RULES.py"]
ALLOWED_PY = {"CUSTOM_RULES.py"}


def run(cmd, env=None):
    print(">", " ".join(cmd), flush=True)
    subprocess.check_call(cmd, cwd=ROOT, env=env)


def iscc():
    for p in [shutil.which("iscc"), r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe", r"C:\Program Files\Inno Setup 6\ISCC.exe"]:
        if p and os.path.exists(p):
            return p
    sys.exit("Inno Setup 6 (ISCC.exe) was not found.")


def main():
    shutil.rmtree(BUILD, ignore_errors=True)
    os.makedirs(BUILD)
    assets = os.path.join(ROOT, "hr_core", "_assets.py")
    run([sys.executable, "tools/make_assets.py", assets])
    run([sys.executable, "tools/make_icon.py", os.path.join(BUILD, "hr.ico")])
    vendor = os.path.join(BUILD, "vendor")
    with zipfile.ZipFile(os.path.join(ROOT, "vendor.zip")) as z:  # openpyxl exactly as the application ships it
        z.extractall(vendor)
    env = dict(os.environ, PYTHONPATH=vendor)
    v4 = ".".join((VERSION.split(".") + ["0", "0", "0"])[:4])
    try:
        run([sys.executable, "-m", "nuitka", "--standalone", "--assume-yes-for-downloads", "--windows-console-mode=attach",
             f"--output-dir={BUILD}", "--output-filename=HR-System.exe", f"--windows-icon-from-ico={os.path.join(BUILD, 'hr.ico')}",
             f"--company-name={DEVELOPER}", f"--product-name={PRODUCT}", f"--file-description={PRODUCT}", f"--file-version={v4}",
             f"--product-version={v4}", f"--copyright={COPYRIGHT}",
             "--include-package=hr_core", "--include-module=hr_core._assets", "--include-module=engine", "--include-module=calculation_engine",
             "--include-module=eco_publisher", "--include-module=eco_contract", "--include-package=openpyxl", "--include-package=et_xmlfile",
             "--include-package=cryptography", "--nofollow-import-to=tkinter,unittest,pydoc,test",
             *[f"--include-data-files={f}={f}" for f in DATA_FILES], "hr_main.py"], env=env)
    finally:  # never leave the packed screens next to the source: a checkout would serve them instead of the files
        if os.path.exists(assets):
            os.remove(assets)
    assert os.path.exists(os.path.join(DIST, "HR-System.exe")), "HR-System.exe was not built"
    leaks = [os.path.relpath(p, DIST) for p in glob.glob(os.path.join(DIST, "**", "*.py"), recursive=True)
             if os.path.relpath(p, DIST) not in ALLOWED_PY]
    assert not leaks, f"program source in the program folder: {leaks}"
    pages = [p for p in glob.glob(os.path.join(DIST, "**", "*.js"), recursive=True)]
    assert not pages, f"screen files in the program folder (they belong inside the program): {pages}"
    run([iscc(), f"/DAppVersion={VERSION}", f"/DAppPublisher={DEVELOPER}", f"/DAppCopyright={COPYRIGHT}", os.path.join("installer", "hr-system.iss")])
    made = glob.glob(os.path.join(ROOT, "dist", f"HR-System-Setup-{VERSION}.exe"))
    assert made, "the installer was not written"
    print("Done:", made[0])


if __name__ == "__main__":
    main()
