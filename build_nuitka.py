"""Nuitka build configuration for Shocking-VRChat."""
# Run with: python -m nuitka --help  (to see all options)
# Or simply: python build_nuitka.py

import subprocess
import sys
import os

def build():
    cmd = [
        sys.executable, "-m", "nuitka",
        "--standalone",
        "--onefile",
        "--output-dir=dist_nuitka",
        "--output-filename=shocking_vrchat.exe",

        # Windows-specific
        "--windows-console-mode=attach",
        "--windows-icon-from-ico=",  # No icon (remove this line or provide .ico)

        # Include data files
        "--include-data-dir=static=static",
        "--include-data-dir=templates=templates",
        "--include-data-dir=wave_presets=wave_presets",

        # Include our package modules
        "--include-package=srv",
        "--include-package=pulse_to_hex",

        # Include dependencies that Nuitka may miss
        "--include-module=uvicorn.logging",
        "--include-module=uvicorn.loops.auto",
        "--include-module=uvicorn.protocols.http.auto",
        "--include-module=uvicorn.protocols.websockets.auto",
        "--include-module=uvicorn.lifespan.on",
        "--include-module=multipart.multipart",
        "--include-module=pydantic",
        "--include-module=pydantic_core",
        "--include-module=annotated_types",
        "--include-module=websockets.asyncio.server",
        "--include-module=pythonosc.osc_server",
        "--include-module=pythonosc.dispatcher",
        "--include-module=pythonosc.udp_client",

        # Exclude unnecessary modules
        "--nofollow-import-to=pytest",
        "--nofollow-import-to=unittest",
        "--nofollow-import-to=setuptools",
        "--nofollow-import-to=pip",
        "--nofollow-import-to=tkinter",
        "--nofollow-import-to=numpy",

        # Compilation options
        "--jobs=4",
        "--lto=yes",
        "--remove-output",

        # Entry point
        "shocking_vrchat.py",
    ]

    # Remove empty icon flag if no icon
    cmd = [c for c in cmd if c != "--windows-icon-from-ico="]

    print(f"Running Nuitka build...")
    print(f"Command: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=os.path.dirname(os.path.abspath(__file__)))
    sys.exit(result.returncode)

if __name__ == "__main__":
    build()
