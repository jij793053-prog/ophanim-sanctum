# -*- coding: utf-8 -*-
"""Windowless launcher for Ophanim Sanctum Toy & Interactive Wallpaper Edition."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import urllib.request
import webbrowser

ROOT = Path(__file__).resolve().parent
DAEMON_PY = ROOT / "ophanim_toy_daemon.py"
CACHE_DIR = ROOT / ".ophanim_cache"
PROFILE_DIR = CACHE_DIR / "toy_app_profile"
HOST = "127.0.0.1"
PORT = 18791
APP_URL = f"http://{HOST}:{PORT}/ophanim_toy_sanctum.html?ws=ws://{HOST}:{PORT}/ws"
HEALTH_URL = f"http://{HOST}:{PORT}/api/health"
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
_NO_WIN = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)


def _is_ready() -> bool:
    try:
        with _OPENER.open(HEALTH_URL, timeout=0.6) as resp:
            return resp.status == 200
    except Exception:
        return False


def _find_edge_or_chrome() -> str | None:
    candidates = [
        Path(os.environ.get("PROGRAMFILES(X86)", "C:/Program Files (x86)")) / "Microsoft/Edge/Application/msedge.exe",
        Path(os.environ.get("PROGRAMFILES", "C:/Program Files")) / "Microsoft/Edge/Application/msedge.exe",
        Path(os.environ.get("PROGRAMFILES", "C:/Program Files")) / "Google/Chrome/Application/chrome.exe",
        shutil.which("msedge"),
        shutil.which("chrome"),
    ]
    for c in candidates:
        if c and Path(c).is_file():
            return str(c)
    return None


def main() -> None:
    if not _is_ready():
        py_exe = Path(sys.executable)
        pyw = py_exe.with_name("pythonw.exe")
        runner = str(pyw if pyw.is_file() else py_exe)
        subprocess.Popen(
            [runner, str(DAEMON_PY)],
            cwd=str(ROOT),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=_NO_WIN,
        )
        for _ in range(30):
            if _is_ready():
                break
            time.sleep(0.2)

    target = APP_URL if _is_ready() else (ROOT / "ophanim_toy_sanctum.html").as_uri()
    browser = _find_edge_or_chrome()
    if browser:
        PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        subprocess.Popen(
            [
                browser,
                f"--user-data-dir={PROFILE_DIR}",
                f"--app={target}",
                "--window-size=1560,940",
                "--no-first-run",
                "--no-default-browser-check",
            ],
            cwd=str(ROOT),
        )
    else:
        webbrowser.open(target)


if __name__ == "__main__":
    main()
