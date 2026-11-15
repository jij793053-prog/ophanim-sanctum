# -*- coding: utf-8 -*-
"""Ophanim Sanctum standalone windowless desktop launcher & daemon auto-starter.

- Runs completely windowless under `pythonw.exe` (never opens a CMD console).
- Auto-starts `ophanim_agy_daemon.py` on `127.0.0.1:18790` if not already listening.
- Opens Ophanim Sanctum in a dedicated chromeless Edge `--app` window (isolated profile
  under `CACHE_ROOT/ophanim_app_profile`, zero address/tab/bookmarks bar,
  full 120fps hardware WebGL, zero default-profile cache pollution), with Chrome / pywebview fallbacks.
- Supports `--daemon-only` / `--headless-check` for automated health & auto-start verification.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import urllib.request

SANCTUM_DIR = Path(__file__).resolve().parent
DAEMON_SCRIPT = SANCTUM_DIR / "ophanim_agy_daemon.py"
LAUNCHER_LOG = SANCTUM_DIR / "launcher.log"
DAEMON_BOOT_LOG = SANCTUM_DIR / "daemon_boot.log"

_PARENT_CACHE_CAND = SANCTUM_DIR.parent.parent / "cache"
CACHE_ROOT = Path(
    os.environ.get(
        "OPHANIM_CACHE_DIR",
        str(_PARENT_CACHE_CAND if _PARENT_CACHE_CAND.is_dir() else (SANCTUM_DIR / ".ophanim_cache")),
    )
)
APP_PROFILE_DIR = CACHE_ROOT / "ophanim_app_profile"
APP_CACHE_DIR = CACHE_ROOT / "ophanim_app_cache"
WEBVIEW_STORAGE_DIR = CACHE_ROOT / "ophanim_webview"

HOST = "127.0.0.1"
PORT = 18790
HEALTH_URL = f"http://{HOST}:{PORT}/api/health"
WALLPAPER_API_URL = f"http://{HOST}:{PORT}/api/wallpaper"
SHUTDOWN_URL = f"http://{HOST}:{PORT}/api/shutdown"
APP_URL = f"http://{HOST}:{PORT}/ophanim_sanctum.html?ws=ws://{HOST}:{PORT}/ws"

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
_NEW_GROUP = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
_DIRECT_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _log(msg: str) -> None:
    try:
        SANCTUM_DIR.mkdir(parents=True, exist_ok=True)
        if LAUNCHER_LOG.is_file() and LAUNCHER_LOG.stat().st_size > 524_288:
            tail = LAUNCHER_LOG.read_bytes()[-262_144:]
            LAUNCHER_LOG.write_bytes(tail)
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        with LAUNCHER_LOG.open("a", encoding="utf-8") as fh:
            fh.write(f"[{ts}] {msg}\n")
    except Exception:
        pass


def _current_desktop_name() -> str:
    if os.name != "nt":
        return "posix"
    try:
        import ctypes

        u32 = ctypes.windll.user32
        k32 = ctypes.windll.kernel32
        hdesk = u32.GetThreadDesktop(k32.GetCurrentThreadId())
        if not hdesk:
            return ""
        buf = ctypes.create_unicode_buffer(256)
        needed = ctypes.c_ulong(0)
        if u32.GetUserObjectInformationW(hdesk, 2, buf, 512, ctypes.byref(needed)):
            return str(buf.value or "")
    except Exception:
        pass
    return ""


def _probe_daemon_health(timeout: float = 0.5) -> dict | None:
    try:
        req = urllib.request.Request(HEALTH_URL, method="GET")
        with _DIRECT_OPENER.open(req, timeout=timeout) as resp:
            if 200 <= getattr(resp, "status", 200) < 300:
                data = json.loads(resp.read().decode("utf-8", errors="replace"))
                if isinstance(data, dict) and data.get("ok") is True:
                    return data
    except Exception:
        pass
    return None


def _is_daemon_ready(timeout: float = 0.5) -> bool:
    if _probe_daemon_health(timeout=timeout) is not None:
        return True
    try:
        req = urllib.request.Request(APP_URL, method="GET")
        with _DIRECT_OPENER.open(req, timeout=timeout) as resp:
            if 200 <= getattr(resp, "status", 200) < 400:
                return True
    except Exception:
        pass
    return False


def _candidate_python_exes() -> list[Path]:
    uv_py_root = Path(os.environ.get("APPDATA", "")) / "uv/python"
    uv_candidates: list[Path] = sorted(uv_py_root.glob("cpython-*/python.exe"), reverse=True) if uv_py_root.is_dir() else []
    raw_candidates: list[str | Path | None] = [
        SANCTUM_DIR / ".venv/Scripts/python.exe",
        sys.executable,
        shutil.which("python"),
        shutil.which("pythonw"),
        *uv_candidates,
    ]
    seen: set[str] = set()
    out: list[Path] = []
    for item in raw_candidates:
        if not item:
            continue
        p = Path(item)
        if p.name.lower() == "pythonw.exe":
            sib = p.with_name("python.exe")
            if sib.is_file():
                p = sib
        if not p.is_file():
            continue
        norm = os.path.normcase(str(p.resolve()))
        if norm not in seen:
            seen.add(norm)
            out.append(p)
    return out


def _to_windowless_exe(py_exe: Path) -> str:
    pyw = py_exe.with_name("pythonw.exe")
    return str(pyw if pyw.is_file() else py_exe)


def _resolve_daemon_pythonw() -> str:
    candidates = _candidate_python_exes()
    for py_exe in candidates:
        try:
            proc = subprocess.run(
                [str(py_exe), "-c", "import aiohttp, watchdog"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=2.5,
                creationflags=_NO_WINDOW,
                check=False,
            )
            if proc.returncode == 0:
                chosen = _to_windowless_exe(py_exe)
                _log(f"Selected daemon runtime with aiohttp+watchdog: {chosen}")
                return chosen
        except Exception:
            continue
    fallback = _to_windowless_exe(candidates[0]) if candidates else (shutil.which("pythonw") or sys.executable)
    _log(f"Fallback daemon runtime: {fallback}")
    return str(fallback)


def _has_upgraded_apis(timeout: float = 0.5) -> bool:
    health = _probe_daemon_health(timeout=timeout)
    if (
        not isinstance(health, dict)
        or not health.get("aiUsageBridge")
        or not health.get("wallpaperKiosk64")
        or not health.get("interactiveWallpaper")
    ):
        return False
    try:
        req = urllib.request.Request(WALLPAPER_API_URL, method="GET")
        with _DIRECT_OPENER.open(req, timeout=timeout) as resp:
            if 200 <= getattr(resp, "status", 200) < 300:
                data = json.loads(resp.read().decode("utf-8", errors="replace"))
                return isinstance(data, dict) and data.get("type") == "ophanim_wallpaper_status"
    except Exception:
        pass
    return False


def ensure_daemon_running(wait_seconds: float = 6.5) -> bool:
    my_desktop = _current_desktop_name().strip().lower()
    health = _probe_daemon_health(timeout=0.55)
    if health is not None:
        # Ensure daemon is BOTH running on interactive 'Default' desktop AND running latest API build
        need_replace = (my_desktop == "default" and health.get("desktopInteractive") is not True) or (
            not _has_upgraded_apis(timeout=0.55)
        )
        if need_replace:
            _log(
                f"Replacing stale/non-interactive daemon (pid={health.get('pid')}, desktop={health.get('desktop')!r}) "
                "with upgraded Default-desktop daemon"
            )
            try:
                req = urllib.request.Request(SHUTDOWN_URL, data=b"{}", method="POST")
                with _DIRECT_OPENER.open(req, timeout=1.2):
                    pass
            except Exception:
                pass
            shut_deadline = time.monotonic() + 2.5
            while time.monotonic() < shut_deadline:
                if not _is_daemon_ready(timeout=0.25):
                    break
                time.sleep(0.12)
        else:
            _log(f"Daemon already online at 127.0.0.1:18790 (desktop={health.get('desktop')!r})")
            return True
    elif _is_daemon_ready():
        _log("Daemon already online at 127.0.0.1:18790")
        return True

    if not DAEMON_SCRIPT.is_file():
        _log(f"ERROR: Daemon script missing at {DAEMON_SCRIPT.as_posix()}")
        return False

    daemon_pyw = _resolve_daemon_pythonw()
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env.setdefault("OPHANIM_HTML_PATH", str(SANCTUM_DIR / "ophanim_sanctum.html"))

    SANCTUM_DIR.mkdir(parents=True, exist_ok=True)
    try:
        boot_fh = DAEMON_BOOT_LOG.open("ab")
        proc = subprocess.Popen(
            [daemon_pyw, str(DAEMON_SCRIPT)],
            cwd=str(SANCTUM_DIR),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=boot_fh,
            stderr=boot_fh,
            close_fds=True,
            creationflags=_NO_WINDOW | _NEW_GROUP,
        )
        boot_fh.close()
        _log(f"Spawned ophanim_agy_daemon.py (pid={proc.pid}) via {daemon_pyw}")
    except Exception as exc:
        _log(f"ERROR spawning daemon: {exc}")
        return False

    deadline = time.monotonic() + max(1.0, float(wait_seconds))
    while time.monotonic() < deadline:
        if _is_daemon_ready(timeout=0.45):
            _log("Daemon became ready on 127.0.0.1:18790")
            return True
        time.sleep(0.2)

    _log("WARNING: Timed out waiting for 127.0.0.1:18790 readiness")
    return _is_daemon_ready(timeout=0.5)


def _find_app_browser() -> tuple[str, str]:
    candidates = [
        ("edge", "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"),
        ("edge", "C:/Program Files/Microsoft/Edge/Application/msedge.exe"),
        ("edge", shutil.which("msedge") or ""),
        ("chrome", "C:/Program Files/Google/Chrome/Application/chrome.exe"),
        ("chrome", "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe"),
        ("chrome", shutil.which("chrome") or ""),
    ]
    for kind, raw in candidates:
        if raw and Path(raw).is_file():
            return kind, str(Path(raw))
    return "", ""


def _compute_centered_window_metrics(
    target_dip_w: int = 1560, target_dip_h: int = 940
) -> dict[str, int | float]:
    """Compute BOTH logical DIP coordinates (for Chromium `--window-position`/`Preferences`)
    AND physical pixel coordinates (for Win32 `SetWindowPos`) so 125%/150%/200% 4K scaling
    always lands dead-center instead of drifting to the bottom-right!
    """
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        try:
            user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        except Exception:
            try:
                user32.SetProcessDPIAware()
            except Exception:
                pass

        rect = wintypes.RECT()
        if user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0):
            phys_left = int(rect.left)
            phys_top = int(rect.top)
            phys_avail_w = max(800, int(rect.right - rect.left))
            phys_avail_h = max(600, int(rect.bottom - rect.top))

            dpi = 96
            try:
                shcore = ctypes.windll.shcore
                pt = wintypes.POINT(phys_left + phys_avail_w // 2, phys_top + phys_avail_h // 2)
                hmon = user32.MonitorFromPoint(pt, 2)
                dx = ctypes.c_uint(96)
                dy = ctypes.c_uint(96)
                if hmon and shcore.GetDpiForMonitor(hmon, 0, ctypes.byref(dx), ctypes.byref(dy)) == 0:
                    dpi = max(96, int(dx.value))
                else:
                    dpi = max(96, int(user32.GetDpiForSystem()))
            except Exception:
                try:
                    dpi = max(96, int(user32.GetDpiForSystem()))
                except Exception:
                    dpi = 96

            scale = max(1.0, float(dpi) / 96.0)
            dip_left = int(round(phys_left / scale))
            dip_top = int(round(phys_top / scale))
            dip_avail_w = max(800, int(round(phys_avail_w / scale)))
            dip_avail_h = max(600, int(round(phys_avail_h / scale)))

            dip_w = min(target_dip_w, int(dip_avail_w * 0.84))
            dip_h = min(target_dip_h, int(dip_avail_h * 0.86))
            dip_x = int(dip_left + (dip_avail_w - dip_w) // 2)
            dip_y = int(dip_top + (dip_avail_h - dip_h) // 2)

            phys_w = min(int(phys_avail_w * 0.92), int(round(dip_w * scale)))
            phys_h = min(int(phys_avail_h * 0.92), int(round(dip_h * scale)))
            phys_x = int(phys_left + (phys_avail_w - phys_w) // 2)
            phys_y = int(phys_top + (phys_avail_h - phys_h) // 2)

            return {
                "scale": scale,
                "dip_x": dip_x,
                "dip_y": dip_y,
                "dip_w": dip_w,
                "dip_h": dip_h,
                "dip_work_left": dip_left,
                "dip_work_top": dip_top,
                "dip_work_right": dip_left + dip_avail_w,
                "dip_work_bottom": dip_top + dip_avail_h,
                "phys_x": phys_x,
                "phys_y": phys_y,
                "phys_w": phys_w,
                "phys_h": phys_h,
            }
    except Exception:
        pass
    return {
        "scale": 1.0,
        "dip_x": 160,
        "dip_y": 70,
        "dip_w": target_dip_w,
        "dip_h": target_dip_h,
        "dip_work_left": 0,
        "dip_work_top": 0,
        "dip_work_right": target_dip_w + 320,
        "dip_work_bottom": target_dip_h + 140,
        "phys_x": 160,
        "phys_y": 70,
        "phys_w": target_dip_w,
        "phys_h": target_dip_h,
    }


def _preset_chromium_centered_prefs(profile_dir: Path, m: dict[str, int | float]) -> None:
    """Update Chromium Default/Preferences in logical DIPs so `--app` opens dead-center."""
    prefs_file = profile_dir / "Default" / "Preferences"
    try:
        prefs_file.parent.mkdir(parents=True, exist_ok=True)
        data: dict = {}
        if prefs_file.is_file():
            data = json.loads(prefs_file.read_text(encoding="utf-8", errors="replace"))
        x = int(m["dip_x"])
        y = int(m["dip_y"])
        w = int(m["dip_w"])
        h = int(m["dip_h"])
        placement = {
            "bottom": y + h,
            "left": x,
            "maximized": False,
            "right": x + w,
            "top": y,
            "work_area_bottom": int(m["dip_work_bottom"]),
            "work_area_left": int(m["dip_work_left"]),
            "work_area_right": int(m["dip_work_right"]),
            "work_area_top": int(m["dip_work_top"]),
        }
        browser_sec = data.setdefault("browser", {})
        if isinstance(browser_sec, dict):
            browser_sec["window_placement"] = dict(placement)
            app_wp = browser_sec.setdefault("app_window_placement", {})
            if isinstance(app_wp, dict):
                for k in list(app_wp.keys()):
                    app_wp[k] = dict(placement)
                app_wp[f"_127.0.0.1_{PORT}"] = dict(placement)
        prefs_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except Exception as exc:
        _log(f"Preferences center preset skipped: {exc}")


def _get_hwnd_exe_basename(hwnd: int) -> str:
    """Return lowercase executable filename (e.g. 'msedge.exe') owning `hwnd`."""
    if os.name != "nt":
        return ""
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        pid = wintypes.DWORD(0)
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if not pid.value:
            return ""
        hproc = kernel32.OpenProcess(0x1000, False, pid.value)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not hproc:
            return ""
        try:
            ebuf = ctypes.create_unicode_buffer(1024)
            sz = wintypes.DWORD(1024)
            if kernel32.QueryFullProcessImageNameW(hproc, 0, ebuf, ctypes.byref(sz)):
                return os.path.basename(ebuf.value or "").lower()
        finally:
            kernel32.CloseHandle(hproc)
    except Exception:
        pass
    return ""


def _snapshot_non_ophanim_browser_hwnds() -> set[int]:
    """Record existing `Chrome_WidgetWin_1` HWNDs before launching so we NEVER resize existing tabs or IDEs."""
    existing: set[int] = set()
    if os.name != "nt":
        return existing
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        def _cb(hwnd: int, _lparam: int) -> bool:
            if not user32.IsWindowVisible(hwnd):
                return True
            cls_buf = ctypes.create_unicode_buffer(128)
            user32.GetClassNameW(hwnd, cls_buf, 128)
            if cls_buf.value != "Chrome_WidgetWin_1":
                return True
            exe_name = _get_hwnd_exe_basename(int(hwnd))
            ln = user32.GetWindowTextLengthW(hwnd)
            title = ""
            if ln > 0:
                t_buf = ctypes.create_unicode_buffer(ln + 2)
                user32.GetWindowTextW(hwnd, t_buf, ln + 2)
                title = (t_buf.value or "").strip()
            # Keep an already-open standalone OPHANIM UI `--app` window eligible for re-centering,
            # while locking out ALL other windows (Antigravity IDE, regular browser windows, etc.)!
            if exe_name in ("msedge.exe", "chrome.exe") and title == "OPHANIM UI":
                return True
            existing.add(int(hwnd))
            return True

        user32.EnumWindows(WNDENUMPROC(_cb), 0)
    except Exception:
        pass
    return existing


def _center_spawned_ophanim_window_win32(
    phys_x: int, phys_y: int, phys_w: int, phys_h: int, pre_hwnds: set[int], wait_sec: float = 2.8
) -> None:
    """Center ONLY the standalone `msedge.exe`/`chrome.exe` `OPHANIM UI` `--app` window in physical pixels.
    NEVER touches `Antigravity.exe`, `Code.exe`, `electron.exe`, or regular browser windows!
    """
    if os.name != "nt":
        return
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        deadline = time.monotonic() + wait_sec

        while time.monotonic() < deadline:
            matched_hwnds: list[tuple[int, str, str]] = []

            def _cb(hwnd: int, _lparam: int) -> bool:
                h_int = int(hwnd)
                if h_int in pre_hwnds or not user32.IsWindowVisible(hwnd):
                    return True
                cls_buf = ctypes.create_unicode_buffer(128)
                user32.GetClassNameW(hwnd, cls_buf, 128)
                if cls_buf.value != "Chrome_WidgetWin_1":
                    return True
                exe_name = _get_hwnd_exe_basename(h_int)
                # STRICT PROCESS GUARD: ONLY standalone Edge/Chrome browser, NEVER Antigravity/Electron!
                if exe_name not in ("msedge.exe", "chrome.exe"):
                    return True
                ln = user32.GetWindowTextLengthW(hwnd)
                if ln <= 0:
                    return True
                t_buf = ctypes.create_unicode_buffer(ln + 2)
                user32.GetWindowTextW(hwnd, t_buf, ln + 2)
                raw_title = (t_buf.value or "").strip()
                low_title = raw_title.lower()
                if "antigravity" in low_title or "ophanim wallpaper" in low_title:
                    return True
                if (
                    raw_title == "OPHANIM UI"
                    or "127.0.0.1:18790" in low_title
                    or "ophanim_sanctum.html" in low_title
                ):
                    matched_hwnds.append((h_int, exe_name, raw_title))
                return True

            user32.EnumWindows(WNDENUMPROC(_cb), 0)
            if matched_hwnds:
                hwnd_target, exe_target, title_target = matched_hwnds[0]
                if user32.IsZoomed(hwnd_target) or user32.IsIconic(hwnd_target):
                    user32.ShowWindow(hwnd_target, 9)  # SW_RESTORE
                user32.SetWindowPos(hwnd_target, 0, phys_x, phys_y, phys_w, phys_h, 0x0040)  # SWP_SHOWWINDOW
                user32.SetForegroundWindow(hwnd_target)
                _log(
                    f"Centered standalone {exe_target} window {title_target!r} (hwnd={hwnd_target}) "
                    f"to phys=({phys_x}, {phys_y}, {phys_w}x{phys_h})"
                )
                return
            time.sleep(0.10)
    except Exception as exc:
        _log(f"Win32 center window pass skipped: {exc}")


def launch_standalone_window(force_pywebview: bool = False) -> str:
    APP_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    APP_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    m = _compute_centered_window_metrics(1560, 940)
    dip_x, dip_y, dip_w, dip_h = int(m["dip_x"]), int(m["dip_y"]), int(m["dip_w"]), int(m["dip_h"])
    phys_x, phys_y, phys_w, phys_h = int(m["phys_x"]), int(m["phys_y"]), int(m["phys_w"]), int(m["phys_h"])

    if not force_pywebview:
        kind, browser_exe = _find_app_browser()
        if browser_exe:
            _preset_chromium_centered_prefs(APP_PROFILE_DIR, m)
            pre_hwnds = _snapshot_non_ophanim_browser_hwnds()
            cmd = [
                browser_exe,
                f"--app={APP_URL}",
                f"--user-data-dir={APP_PROFILE_DIR.as_posix()}",
                f"--disk-cache-dir={APP_CACHE_DIR.as_posix()}",
                f"--window-size={dip_w},{dip_h}",
                f"--window-position={dip_x},{dip_y}",
                "--force-dark-mode",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-features=Translate,EdgeSidebar,msEdgeSidebarV2",
            ]
            proc = subprocess.Popen(
                cmd,
                cwd=str(SANCTUM_DIR),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
                creationflags=_NO_WINDOW | _NEW_GROUP,
            )
            _log(
                f"Launched standalone {kind} --app window (pid={proc.pid}, scale={m['scale']:.2f}) "
                f"dip=({dip_x},{dip_y},{dip_w}x{dip_h}) phys=({phys_x},{phys_y},{phys_w}x{phys_h}) -> {APP_URL}"
            )
            _center_spawned_ophanim_window_win32(phys_x, phys_y, phys_w, phys_h, pre_hwnds)
            return f"{kind}_app"

    try:
        import webview  # type: ignore

        WEBVIEW_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        _log(f"Launching pywebview native window -> {APP_URL}")
        webview.create_window(
            "OPHANIM UI",
            APP_URL,
            x=dip_x,
            y=dip_y,
            width=dip_w,
            height=dip_h,
            background_color="#050608",
        )
        webview.start(private_mode=False, storage_path=str(WEBVIEW_STORAGE_DIR))
        return "pywebview"
    except Exception as exc:
        _log(f"pywebview fallback unavailable ({exc}); using os.startfile")
        os.startfile(APP_URL)
        return "startfile"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ophanim Sanctum Desktop App Launcher")
    parser.add_argument(
        "--daemon-only",
        action="store_true",
        help="Ensure background daemon on 127.0.0.1:18790 is running without opening GUI window",
    )
    parser.add_argument(
        "--headless-check",
        action="store_true",
        help="Alias for --daemon-only with JSON health output for automated verification",
    )
    parser.add_argument(
        "--pywebview",
        action="store_true",
        help="Force pywebview container instead of Edge/Chrome --app mode",
    )
    parser.add_argument(
        "--wait",
        type=float,
        default=6.5,
        help="Max seconds to wait for daemon startup (default: 6.5)",
    )
    args = parser.parse_args(argv)

    ready = ensure_daemon_running(wait_seconds=args.wait)
    if args.daemon_only or args.headless_check:
        if sys.stdout is not None:
            try:
                sys.stdout.write(
                    json.dumps({"ok": ready, "host": HOST, "port": PORT, "url": APP_URL}) + "\n"
                )
                sys.stdout.flush()
            except Exception:
                pass
        return 0 if ready else 1

    mode = launch_standalone_window(force_pywebview=args.pywebview)
    _log(f"Launcher completed (daemon_ready={ready}, window_mode={mode})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
