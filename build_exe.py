"""Builds build/AntennaCalc.exe (single file, windowed) with PyInstaller.

    python build_exe.py            # build
    python build_exe.py --shortcut # build and put a shortcut on the Desktop
"""
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.join(ROOT, "build")


def main():
    os.makedirs(BUILD, exist_ok=True)
    work = os.path.join(ROOT, "build_tmp")
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile", "--noconsole",
           "--name", "AntennaCalc", "--icon", os.path.join(ROOT, "icon.ico"),
           "--distpath", BUILD, "--workpath", work, "--specpath", work,
           "--add-data", f"{os.path.join(ROOT, 'icon.ico')};.",
           "--collect-submodules", "antennacalc",
           "--exclude-module", "matplotlib", "--exclude-module", "pytest", "--exclude-module", "tkinter",
           "--exclude-module", "PySide6.QtWebEngineCore", "--exclude-module", "PySide6.QtWebEngineWidgets",
           "--exclude-module", "PySide6.Qt3DCore", "--exclude-module", "PySide6.QtQuick",
           os.path.join(ROOT, "main.py")]
    env = dict(os.environ)
    env["PYTHONPATH"] = ROOT
    subprocess.check_call(cmd, env=env, cwd=ROOT)
    shutil.rmtree(work, ignore_errors=True)
    print("built", os.path.join(BUILD, "AntennaCalc.exe"))
    if "--shortcut" in sys.argv:
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        lnk = os.path.join(desktop, "AntennaCalc.lnk")
        ps = (f"$s=(New-Object -ComObject WScript.Shell).CreateShortcut('{lnk}');"
              f"$s.TargetPath='{os.path.join(BUILD, 'AntennaCalc.exe')}';$s.WorkingDirectory='{BUILD}';"
              f"$s.IconLocation='{os.path.join(ROOT, 'icon.ico')}';$s.Description='AntennaCalc';$s.Save()")
        subprocess.check_call(["powershell", "-NoProfile", "-Command", ps])
        print("shortcut", lnk)


if __name__ == "__main__":
    main()
