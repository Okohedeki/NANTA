"""
Add NANTA to Windows startup so it runs when the computer turns on.

Supports two modes:
  --exe    Uses the built executable (dist/NANTA/NANTA.exe)
  --python Uses python launcher.py directly (default, no rebuild needed)
"""

import os
import sys


def get_startup_folder():
    """Get the Windows Startup folder path."""
    return os.path.join(
        os.environ["APPDATA"],
        "Microsoft", "Windows", "Start Menu", "Programs", "Startup",
    )


def install(use_exe=False):
    here = os.path.dirname(os.path.abspath(__file__))
    startup_folder = get_startup_folder()
    bat_path = os.path.join(startup_folder, "NANTA.bat")

    if use_exe:
        exe_dir = os.path.join(here, "dist", "NANTA")
        exe_path = os.path.join(exe_dir, "NANTA.exe")

        if not os.path.exists(exe_path):
            print(f"ERROR: {exe_path} not found.")
            print("Run 'python build.py' first to create the executable.")
            sys.exit(1)

        bat_content = f"""@echo off
cd /d "{exe_dir}"
start "" "{exe_path}"
"""
    else:
        launcher_path = os.path.join(here, "launcher.py")
        bat_content = f"""@echo off
cd /d "{here}"
start "" pythonw "{launcher_path}"
"""

    with open(bat_path, "w") as f:
        f.write(bat_content)

    mode = "exe" if use_exe else "python"
    print(f"Startup script created ({mode} mode): {bat_path}")
    print(f"NANTA will now start automatically when you log in.")
    print()
    print(f"To remove, delete: {bat_path}")


def uninstall():
    startup_folder = get_startup_folder()
    bat_path = os.path.join(startup_folder, "NANTA.bat")
    if os.path.exists(bat_path):
        os.remove(bat_path)
        print(f"Removed: {bat_path}")
        print("NANTA will no longer start automatically.")
    else:
        print("NANTA is not in startup.")


if __name__ == "__main__":
    if "--remove" in sys.argv:
        uninstall()
    else:
        install(use_exe="--exe" in sys.argv)
