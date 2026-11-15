#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ophanim_wallpaper_manager.py
True Windows 10 / Windows 11 (including Win11 24H2 RaisedDesktop Progman build >= 26000)
dynamic desktop wallpaper controller for Ophanim Sanctum.

Key Win11 24H2 guarantees:
  1. Explicit 64-bit `ctypes` `argtypes`/`restype` on all `user32` calls (`SetWindowLongPtrW`,
     `GetWindowLongPtrW`, `SetParent`, `SetWindowPos`, `EnableWindow`, `SetLayeredWindowAttributes`)
     to prevent signed/unsigned 32-bit `OverflowError` on `~WS_POPUP`.
  2. Launches Edge/Chrome in true chromeless `--kiosk "<url>" --edge-kiosk-type=fullscreen` mode
     (zero `--app` titlebar, zero min/max/close buttons, zero draggable frame).
  3. Embeds `hwnd` inside `Progman` (Win11 24H2 RaisedDesktop) sandwiched strictly AFTER
     `SHELLDLL_DefView` (so desktop icons & rubber-band selection stay interactive on top) and
     BEFORE `WorkerW` (hiding the static wallpaper while running), with `WS_DISABLED` +
     `WS_EX_TRANSPARENT | WS_EX_NOPARENTNOTIFY | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW | WS_EX_LAYERED`
     so desktop clicks pass cleanly to `SHELLDLL_DefView` and NEVER drag or focus the wallpaper.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import json
import logging
import os
from pathlib import Path
import shutil
import subprocess
import threading
import time
from typing import Any
import winreg

logger = logging.getLogger("ophanim_wallpaper")

PROJECT_DIR = Path(__file__).resolve().parent
_PARENT_CACHE_CAND = PROJECT_DIR.parent.parent / "cache"
CACHE_ROOT = Path(
    os.environ.get(
        "OPHANIM_CACHE_DIR",
        str(_PARENT_CACHE_CAND if _PARENT_CACHE_CAND.is_dir() else (PROJECT_DIR / ".ophanim_cache")),
    )
)
WALLPAPER_PROFILE_DIR = CACHE_ROOT / "ophanim_wallpaper_profile"
WALLPAPER_CACHE_DIR = CACHE_ROOT / "ophanim_wallpaper_cache"
WALLPAPER_STATE_PATH = PROJECT_DIR / "ophanim_wallpaper_state.json"

SPI_GETDESKWALLPAPER = 0x0073
SPI_SETDESKWALLPAPER = 0x0014
SPIF_UPDATEINIFILE = 0x0001
SPIF_SENDWININICHANGE = 0x0002

GWL_STYLE = -16
GWL_EXSTYLE = -20
WS_CHILD = 0x40000000
WS_POPUP = 0x80000000
WS_VISIBLE = 0x10000000
WS_DISABLED = 0x08000000
WS_CLIPSIBLINGS = 0x04000000
WS_CLIPCHILDREN = 0x02000000
WS_CAPTION = 0x00C00000
WS_BORDER = 0x00800000
WS_DLGFRAME = 0x00400000
WS_THICKFRAME = 0x00040000
WS_MINIMIZEBOX = 0x00020000
WS_MAXIMIZEBOX = 0x00010000
WS_SYSMENU = 0x00080000

WS_EX_NOPARENTNOTIFY = 0x00000004
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_WINDOWEDGE = 0x00000100
WS_EX_CLIENTEDGE = 0x00000200
WS_EX_APPWINDOW = 0x00040000
WS_EX_LAYERED = 0x00080000
WS_EX_NOACTIVATE = 0x08000000
LWA_ALPHA = 0x00000002

SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_FRAMECHANGED = 0x0020
SWP_SHOWWINDOW = 0x0040
WM_CLOSE = 0x0010

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


class _VARIANT_UNION(ctypes.Union):
    _fields_ = [
        ("lVal", ctypes.c_long),
        ("llVal", ctypes.c_longlong),
        ("_pad", ctypes.c_void_p * 2),
    ]


class VARIANT(ctypes.Structure):
    _fields_ = [
        ("vt", ctypes.c_ushort),
        ("wReserved1", ctypes.c_ushort),
        ("wReserved2", ctypes.c_ushort),
        ("wReserved3", ctypes.c_ushort),
        ("u", _VARIANT_UNION),
    ]


class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]


_CLSID_TASKBAR_LIST = _GUID(
    0x56FDF344,
    0xFD6D,
    0x11D0,
    (ctypes.c_ubyte * 8)(0x95, 0x8A, 0x00, 0x60, 0x97, 0xC9, 0xA0, 0x90),
)
_IID_ITASKBAR_LIST = _GUID(
    0x56FDF342,
    0xFD6D,
    0x11D0,
    (ctypes.c_ubyte * 8)(0x95, 0x8A, 0x00, 0x60, 0x97, 0xC9, 0xA0, 0x90),
)


def _hide_hwnd_from_taskbar(hwnd: int) -> bool:
    """Explicitly purge `hwnd` from Windows 10/11 Explorer Taskbar via COM `ITaskbarList::DeleteTab`."""
    if os.name != "nt" or not hwnd:
        return False
    p_tb = ctypes.c_void_p(0)
    try:
        ole32 = ctypes.WinDLL("ole32")
        ole32.CoInitialize.argtypes = [ctypes.c_void_p]
        ole32.CoInitialize.restype = ctypes.c_long
        ole32.CoCreateInstance.argtypes = [
            ctypes.POINTER(_GUID),
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.POINTER(_GUID),
            ctypes.POINTER(ctypes.c_void_p),
        ]
        ole32.CoCreateInstance.restype = ctypes.c_long

        ole32.CoInitialize(None)
        hr = int(
            ole32.CoCreateInstance(
                ctypes.byref(_CLSID_TASKBAR_LIST),
                None,
                1,  # CLSCTX_INPROC_SERVER
                ctypes.byref(_IID_ITASKBAR_LIST),
                ctypes.byref(p_tb),
            )
        )
        if hr != 0 or not p_tb.value:
            return False
        vtbl = ctypes.c_void_p.from_address(p_tb.value).value
        if not vtbl:
            return False
        ptr_sz = ctypes.sizeof(ctypes.c_void_p)
        hr_init_addr = ctypes.c_void_p.from_address(vtbl + 3 * ptr_sz).value
        del_tab_addr = ctypes.c_void_p.from_address(vtbl + 5 * ptr_sz).value
        if not hr_init_addr or not del_tab_addr:
            return False
        hr_init_fn = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p)(hr_init_addr)
        del_tab_fn = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, wintypes.HWND)(del_tab_addr)
        if int(hr_init_fn(p_tb.value)) == 0:
            return int(del_tab_fn(p_tb.value, wintypes.HWND(hwnd))) == 0
        return False
    except Exception:
        return False
    finally:
        if p_tb.value:
            _release_com_unknown(int(p_tb.value))


def _to_ptr_long(val: int) -> int:
    """Convert any 32-bit bitwise window style mask safely to signed pointer-sized integer (`LONG_PTR`)."""
    return ctypes.c_ssize_t(int(val) & 0xFFFFFFFF).value


def _bind_win32_user32() -> Any:
    """Configure explicit 64-bit Win32 `argtypes` & `restype` on a dedicated `WinDLL('user32')` handle."""
    u32 = ctypes.WinDLL("user32", use_last_error=True)

    u32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
    u32.FindWindowW.restype = wintypes.HWND

    u32.FindWindowExW.argtypes = [wintypes.HWND, wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR]
    u32.FindWindowExW.restype = wintypes.HWND

    u32.IsWindow.argtypes = [wintypes.HWND]
    u32.IsWindow.restype = wintypes.BOOL

    u32.GetParent.argtypes = [wintypes.HWND]
    u32.GetParent.restype = wintypes.HWND

    u32.SetParent.argtypes = [wintypes.HWND, wintypes.HWND]
    u32.SetParent.restype = wintypes.HWND

    u32.EnableWindow.argtypes = [wintypes.HWND, wintypes.BOOL]
    u32.EnableWindow.restype = wintypes.BOOL

    u32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    u32.ShowWindow.restype = wintypes.BOOL

    u32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    u32.PostMessageW.restype = wintypes.BOOL

    u32.SendMessageTimeoutW.argtypes = [
        wintypes.HWND,
        wintypes.UINT,
        wintypes.WPARAM,
        wintypes.LPARAM,
        wintypes.UINT,
        wintypes.UINT,
        ctypes.POINTER(ctypes.c_size_t),
    ]
    u32.SendMessageTimeoutW.restype = ctypes.c_ssize_t

    get_long = getattr(u32, "GetWindowLongPtrW", u32.GetWindowLongW)
    get_long.argtypes = [wintypes.HWND, ctypes.c_int]
    get_long.restype = ctypes.c_ssize_t

    set_long = getattr(u32, "SetWindowLongPtrW", u32.SetWindowLongW)
    set_long.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
    set_long.restype = ctypes.c_ssize_t

    u32.SetLayeredWindowAttributes.argtypes = [wintypes.HWND, wintypes.COLORREF, wintypes.BYTE, wintypes.DWORD]
    u32.SetLayeredWindowAttributes.restype = wintypes.BOOL

    u32.ScreenToClient.argtypes = [wintypes.HWND, ctypes.POINTER(POINT)]
    u32.ScreenToClient.restype = wintypes.BOOL

    u32.SetWindowPos.argtypes = [
        wintypes.HWND,
        wintypes.HWND,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.UINT,
    ]
    u32.SetWindowPos.restype = wintypes.BOOL

    u32.RedrawWindow.argtypes = [wintypes.HWND, ctypes.c_void_p, wintypes.HANDLE, wintypes.UINT]
    u32.RedrawWindow.restype = wintypes.BOOL

    u32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    u32.GetClassNameW.restype = ctypes.c_int

    u32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    u32.GetWindowTextW.restype = ctypes.c_int

    u32.GetCursorPos.argtypes = [ctypes.POINTER(POINT)]
    u32.GetCursorPos.restype = wintypes.BOOL

    u32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(RECT)]
    u32.GetWindowRect.restype = wintypes.BOOL

    u32.WindowFromPoint.argtypes = [POINT]
    u32.WindowFromPoint.restype = wintypes.HWND

    u32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
    u32.GetAncestor.restype = wintypes.HWND

    u32.GetAsyncKeyState.argtypes = [ctypes.c_int]
    u32.GetAsyncKeyState.restype = ctypes.c_short

    u32.GetSystemMetrics.argtypes = [ctypes.c_int]
    u32.GetSystemMetrics.restype = ctypes.c_int

    u32.SetWindowsHookExW.argtypes = [ctypes.c_int, ctypes.c_void_p, wintypes.HINSTANCE, wintypes.DWORD]
    u32.SetWindowsHookExW.restype = wintypes.HANDLE

    u32.CallNextHookEx.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
    u32.CallNextHookEx.restype = ctypes.c_ssize_t

    u32.UnhookWindowsHookEx.argtypes = [wintypes.HANDLE]
    u32.UnhookWindowsHookEx.restype = wintypes.BOOL

    u32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
    u32.GetMessageW.restype = wintypes.BOOL

    return u32


def _bind_win32_accessibility() -> tuple[Any, Any]:
    if os.name != "nt":
        return None, None
    try:
        oleacc = ctypes.WinDLL("oleacc")
        oleacc.AccessibleObjectFromPoint.argtypes = [
            POINT,
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.POINTER(VARIANT),
        ]
        oleacc.AccessibleObjectFromPoint.restype = ctypes.c_long

        oleaut32 = ctypes.WinDLL("oleaut32")
        oleaut32.VariantClear.argtypes = [ctypes.POINTER(VARIANT)]
        oleaut32.VariantClear.restype = ctypes.c_long
        return oleacc, oleaut32
    except Exception:
        return None, None


_U32 = _bind_win32_user32() if os.name == "nt" else None
_OLEACC, _OLEAUT32 = _bind_win32_accessibility()


def _enable_dpi_awareness() -> None:
    if os.name != "nt":
        return
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        return
    except Exception:
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass


def _read_current_system_wallpaper() -> str:
    if os.name != "nt":
        return ""
    try:
        buf = ctypes.create_unicode_buffer(1024)
        if ctypes.windll.user32.SystemParametersInfoW(SPI_GETDESKWALLPAPER, 1024, buf, 0):
            val = (buf.value or "").strip()
            if val and Path(val).is_file():
                return val
    except Exception:
        pass
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Control Panel\Desktop") as k:
            val, _ = winreg.QueryValueEx(k, "WallPaper")
            val_s = str(val or "").strip()
            if val_s and Path(val_s).is_file():
                return val_s
    except Exception:
        pass
    return ""


def _load_state_raw() -> dict[str, Any]:
    if not WALLPAPER_STATE_PATH.is_file():
        return {}
    try:
        data = json.loads(WALLPAPER_STATE_PATH.read_text(encoding="utf-8", errors="replace"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_state_raw(data: dict[str, Any]) -> None:
    PROJECT_DIR.mkdir(parents=True, exist_ok=True)
    tmp = PROJECT_DIR / f".ophanim_wp_state.{os.getpid()}.{time.time_ns()}.tmp"
    try:
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, WALLPAPER_STATE_PATH)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def _find_chromium_binary() -> tuple[str, str | None]:
    edge_candidates = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        os.path.expandvars(r"%LocalAppData%\Microsoft\Edge\Application\msedge.exe"),
        shutil.which("msedge") or "",
    ]
    for c in edge_candidates:
        if c and Path(c).is_file():
            return "edge", c
    chrome_candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
        shutil.which("chrome") or "",
    ]
    for c in chrome_candidates:
        if c and Path(c).is_file():
            return "chrome", c
    return "", None


def _get_primary_screen_metrics() -> dict[str, Any]:
    _enable_dpi_awareness()
    phys_w, phys_h = 1920, 1080
    scale = 1.0
    if os.name == "nt":
        try:
            u32 = ctypes.windll.user32
            phys_w = int(u32.GetSystemMetrics(0)) or 1920
            phys_h = int(u32.GetSystemMetrics(1)) or 1080
            try:
                dpi = int(u32.GetDpiForSystem())
                if dpi >= 96:
                    scale = dpi / 96.0
            except Exception:
                pass
        except Exception:
            pass
    dip_w = max(800, int(round(phys_w / scale)))
    dip_h = max(600, int(round(phys_h / scale)))
    return {
        "scale": scale,
        "phys_w": phys_w,
        "phys_h": phys_h,
        "dip_w": dip_w,
        "dip_h": dip_h,
    }


def _preset_wallpaper_profile_prefs(metrics: dict[str, Any]) -> None:
    default_dir = WALLPAPER_PROFILE_DIR / "Default"
    default_dir.mkdir(parents=True, exist_ok=True)
    prefs_path = default_dir / "Preferences"
    prefs: dict[str, Any] = {}
    if prefs_path.is_file():
        try:
            loaded = json.loads(prefs_path.read_text(encoding="utf-8", errors="replace"))
            if isinstance(loaded, dict):
                prefs = loaded
        except Exception:
            prefs = {}
    browser_sec = prefs.get("browser")
    if not isinstance(browser_sec, dict):
        browser_sec = {}
        prefs["browser"] = browser_sec
    placement = {
        "left": 0,
        "top": 0,
        "right": int(metrics["dip_w"]),
        "bottom": int(metrics["dip_h"]),
        "maximized": False,
        "minimized": False,
        "work_area_left": 0,
        "work_area_top": 0,
        "work_area_right": int(metrics["dip_w"]),
        "work_area_bottom": int(metrics["dip_h"]),
    }
    browser_sec["window_placement"] = dict(placement)
    browser_sec["has_seen_welcome_page"] = True
    prefs["profile"] = prefs.get("profile") if isinstance(prefs.get("profile"), dict) else {}
    prefs["profile"]["exit_type"] = "Normal"
    prefs["profile"]["exited_cleanly"] = True
    try:
        prefs_path.write_text(json.dumps(prefs, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def _find_wallpaper_hwnds() -> list[int]:
    """Find any top-level or Progman/WorkerW-parented Chromium window titled 'OPHANIM WALLPAPER'."""
    if os.name != "nt" or _U32 is None:
        return []
    u32 = _U32
    found: list[int] = []
    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    title_buf = ctypes.create_unicode_buffer(512)
    cls_buf = ctypes.create_unicode_buffer(128)

    def _check_hwnd(h: int) -> None:
        if not h:
            return
        u32.GetClassNameW(h, cls_buf, 128)
        if cls_buf.value != "Chrome_WidgetWin_1":
            return
        u32.GetWindowTextW(h, title_buf, 512)
        t = (title_buf.value or "").strip()
        if "OPHANIM WALLPAPER" in t.upper():
            hv = int(h)
            if hv not in found:
                found.append(hv)

    def _cb(hwnd: int, _lp: int) -> bool:
        _check_hwnd(hwnd)
        return True

    cb_fn = WNDENUMPROC(_cb)
    ctypes.windll.user32.EnumWindows(cb_fn, 0)
    progman = u32.FindWindowW("Progman", None)
    if progman:
        ctypes.windll.user32.EnumChildWindows(progman, cb_fn, 0)
    return found


def _kill_wallpaper_browser_processes() -> None:
    """Terminate ONLY Chromium processes running with `--user-data-dir=...ophanim_wallpaper_profile`."""
    if os.name != "nt":
        return
    try:
        ps_cmd = (
            "Get-CimInstance Win32_Process | Where-Object { "
            "($_.Name -eq 'msedge.exe' -or $_.Name -eq 'chrome.exe') -and "
            "$_.CommandLine -like '*ophanim_wallpaper_profile*' "
            "} | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
        )
        subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
            timeout=5.0,
            capture_output=True,
            creationflags=_NO_WINDOW,
            check=False,
        )
    except Exception as exc:
        logger.debug("kill wallpaper processes warning: %s", exc)


def _apply_wallpaper_styles_and_zorder(hwnd: int, phys_w: int, phys_h: int) -> tuple[bool, str]:
    """
    Embed `hwnd` behind Windows desktop icons (`SHELLDLL_DefView`), supporting BOTH:
      1. Windows 11 24H2+ (`build >= 26000` RaisedDesktop, where `SHELLDLL_DefView` & `WorkerW`
         are direct children inside `Progman`).
      2. Windows 10 / Windows 11 <=23H2 (classic top-level `WorkerW` sibling behind `SHELLDLL_DefView`).
    """
    if os.name != "nt" or _U32 is None:
        return False, "仅支持 Windows"
    _enable_dpi_awareness()
    u32 = _U32
    GetWindowLongPtrW = getattr(u32, "GetWindowLongPtrW", u32.GetWindowLongW)
    SetWindowLongPtrW = getattr(u32, "SetWindowLongPtrW", u32.SetWindowLongW)

    if not u32.IsWindow(hwnd):
        return False, "壁纸窗口句柄已失效"

    progman = u32.FindWindowW("Progman", None)
    if not progman:
        return False, "未找到 Windows Progman 桌面句柄"

    # Trigger Progman 0x052C to ensure WorkerW wallpaper layer exists
    msg_res = ctypes.c_size_t(0)
    u32.SendMessageTimeoutW(progman, 0x052C, 0xD, 0x1, 0, 1000, ctypes.byref(msg_res))
    u32.SendMessageTimeoutW(progman, 0x052C, 0, 0, 0, 1000, ctypes.byref(msg_res))

    defview_in_progman = u32.FindWindowExW(progman, None, "SHELLDLL_DefView", None)

    strip_style = (
        WS_POPUP
        | WS_CAPTION
        | WS_BORDER
        | WS_DLGFRAME
        | WS_THICKFRAME
        | WS_MINIMIZEBOX
        | WS_MAXIMIZEBOX
        | WS_SYSMENU
    )
    child_flags = WS_CHILD | WS_VISIBLE | WS_CLIPSIBLINGS | WS_CLIPCHILDREN | WS_DISABLED
    ex_strip = WS_EX_APPWINDOW | WS_EX_WINDOWEDGE | WS_EX_CLIENTEDGE
    ex_add = WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE | WS_EX_TRANSPARENT | WS_EX_NOPARENTNOTIFY | WS_EX_LAYERED

    if defview_in_progman:
        # Windows 11 24H2+ RaisedDesktop architecture (`SHELLDLL_DefView` + `WorkerW` inside `Progman`)
        cur_parent = u32.GetParent(hwnd)
        cur_style = int(GetWindowLongPtrW(hwnd, GWL_STYLE)) & 0xFFFFFFFF
        new_style = (cur_style & ~strip_style) | child_flags
        SetWindowLongPtrW(hwnd, GWL_STYLE, _to_ptr_long(new_style))

        cur_ex = int(GetWindowLongPtrW(hwnd, GWL_EXSTYLE)) & 0xFFFFFFFF
        new_ex = (cur_ex & ~ex_strip) | ex_add
        SetWindowLongPtrW(hwnd, GWL_EXSTYLE, _to_ptr_long(new_ex))
        u32.SetLayeredWindowAttributes(hwnd, 0, 255, LWA_ALPHA)
        u32.EnableWindow(hwnd, False)
        _hide_hwnd_from_taskbar(hwnd)

        if int(cur_parent or 0) != int(progman):
            u32.SetParent(hwnd, progman)
            # Re-assert WS_CHILD & click-through styles after Chromium's WM_STYLECHANGED reaction
            SetWindowLongPtrW(hwnd, GWL_STYLE, _to_ptr_long(new_style))
            SetWindowLongPtrW(hwnd, GWL_EXSTYLE, _to_ptr_long(new_ex))
            u32.SetLayeredWindowAttributes(hwnd, 0, 255, LWA_ALPHA)
            u32.EnableWindow(hwnd, False)
            _hide_hwnd_from_taskbar(hwnd)

        pt = POINT(0, 0)
        u32.ScreenToClient(progman, ctypes.byref(pt))

        # Place `hwnd` immediately AFTER `SHELLDLL_DefView` (behind desktop icons!)
        u32.SetWindowPos(
            hwnd,
            defview_in_progman,
            int(pt.x),
            int(pt.y),
            int(phys_w),
            int(phys_h),
            SWP_NOACTIVATE | SWP_FRAMECHANGED | SWP_SHOWWINDOW,
        )
        _hide_hwnd_from_taskbar(hwnd)

        # Ensure `WorkerW` inside `Progman` sits BEHIND `hwnd` so static wallpaper doesn't cover WebGL
        workerw_in_progman = u32.FindWindowExW(progman, None, "WorkerW", None)
        if workerw_in_progman and int(workerw_in_progman) != int(hwnd):
            u32.SetWindowPos(
                workerw_in_progman,
                hwnd,
                0,
                0,
                0,
                0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE,
            )
        return True, "win11_24h2_progman"

    # Classic Windows 10 / Windows 11 <=23H2 architecture
    wallpaper_workerw = 0
    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def _find_worker_cb(top_h: int, _lp: int) -> bool:
        nonlocal wallpaper_workerw
        dv = u32.FindWindowExW(top_h, None, "SHELLDLL_DefView", None)
        if dv:
            w = u32.FindWindowExW(None, top_h, "WorkerW", None)
            if w:
                wallpaper_workerw = int(w)
                return False
        return True

    ctypes.windll.user32.EnumWindows(WNDENUMPROC(_find_worker_cb), 0)
    target_parent = wallpaper_workerw or progman

    cur_parent = u32.GetParent(hwnd)
    cur_style = int(GetWindowLongPtrW(hwnd, GWL_STYLE)) & 0xFFFFFFFF
    new_style = (cur_style & ~strip_style) | child_flags
    SetWindowLongPtrW(hwnd, GWL_STYLE, _to_ptr_long(new_style))

    cur_ex = int(GetWindowLongPtrW(hwnd, GWL_EXSTYLE)) & 0xFFFFFFFF
    new_ex = (cur_ex & ~ex_strip) | ex_add
    SetWindowLongPtrW(hwnd, GWL_EXSTYLE, _to_ptr_long(new_ex))
    u32.SetLayeredWindowAttributes(hwnd, 0, 255, LWA_ALPHA)
    u32.EnableWindow(hwnd, False)
    _hide_hwnd_from_taskbar(hwnd)

    if int(cur_parent or 0) != int(target_parent):
        u32.SetParent(hwnd, target_parent)
        SetWindowLongPtrW(hwnd, GWL_STYLE, _to_ptr_long(new_style))
        SetWindowLongPtrW(hwnd, GWL_EXSTYLE, _to_ptr_long(new_ex))
        u32.EnableWindow(hwnd, False)
        _hide_hwnd_from_taskbar(hwnd)

    pt = POINT(0, 0)
    u32.ScreenToClient(target_parent, ctypes.byref(pt))
    u32.SetWindowPos(
        hwnd,
        0,
        int(pt.x),
        int(pt.y),
        int(phys_w),
        int(phys_h),
        SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED | SWP_SHOWWINDOW,
    )
    _hide_hwnd_from_taskbar(hwnd)
    return True, "classic_workerw"


def ensure_wallpaper_pinned() -> bool:
    """Keep-alive check called periodically by daemon so Chromium fullscreen/focus never breaks out of Progman."""
    if os.name != "nt" or _U32 is None:
        return False
    raw = _load_state_raw()
    if not raw.get("active"):
        return False
    found_all = _find_wallpaper_hwnds()
    for h_cand in found_all:
        _hide_hwnd_from_taskbar(h_cand)
    hwnd = int(raw.get("hwnd") or 0)
    if not hwnd or not _U32.IsWindow(hwnd):
        if not found_all:
            return False
        hwnd = found_all[0]
        raw["hwnd"] = hwnd
        _save_state_raw(raw)
    metrics = _get_primary_screen_metrics()
    ok, _ = _apply_wallpaper_styles_and_zorder(hwnd, metrics["phys_w"], metrics["phys_h"])
    return ok


def get_wallpaper_status() -> dict[str, Any]:
    raw = _load_state_raw()
    hwnds = _find_wallpaper_hwnds()
    saved_h = int(raw.get("hwnd") or 0)
    if saved_h and _U32 is not None and _U32.IsWindow(saved_h) and saved_h not in hwnds:
        hwnds.insert(0, saved_h)
    is_live = len(hwnds) > 0 and bool(raw.get("active", True))
    if raw.get("active") and not hwnds:
        raw["active"] = False
        _save_state_raw(raw)
    return {
        "type": "ophanim_wallpaper_status",
        "ok": True,
        "active": is_live,
        "wallpaperMode": str(raw.get("wallpaperMode") or "agy_live"),
        "beamMode": str(raw.get("beamMode") or "tool_io"),
        "hwnd": hwnds[0] if hwnds else 0,
        "arch": str(raw.get("arch") or ""),
        "originalWallpaper": str(raw.get("originalWallpaperPath") or ""),
    }


def enable_live_wallpaper(
    host: str = "127.0.0.1",
    port: int = 18790,
    wallpaper_mode: str = "agy_live",
    beam_mode: str = "tool_io",
) -> dict[str, Any]:
    if os.name != "nt" or _U32 is None:
        return {"type": "ophanim_wallpaper_status", "ok": False, "active": False, "error": "仅支持 Windows 桌面环境"}

    wp_mode = "ambient_eco" if wallpaper_mode == "ambient_eco" else "agy_live"
    eff_beam = (
        "ambient"
        if wp_mode == "ambient_eco"
        else (beam_mode if beam_mode in ("tool_io", "model_active", "ambient") else "tool_io")
    )

    prev_state = _load_state_raw()
    orig_wp = str(prev_state.get("originalWallpaperPath") or "").strip()
    if not prev_state.get("active") or not orig_wp or not Path(orig_wp).is_file():
        detected_wp = _read_current_system_wallpaper()
        if detected_wp:
            orig_wp = detected_wp

    # Clean up any previous wallpaper instance before spawning fresh configuration
    _detach_and_close_existing_wallpaper(restore_static=False)

    kind, browser_bin = _find_chromium_binary()
    if not browser_bin:
        return {"type": "ophanim_wallpaper_status", "ok": False, "active": False, "error": "未找到本地 Edge 或 Chrome 浏览器"}

    metrics = _get_primary_screen_metrics()
    WALLPAPER_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    WALLPAPER_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _preset_wallpaper_profile_prefs(metrics)

    eco_flag = "1" if wp_mode == "ambient_eco" else "0"
    target_url = (
        f"http://{host}:{port}/ophanim_sanctum.html"
        f"?ws=ws://{host}:{port}/ws&wallpaper=1&wpMode={wp_mode}&beamMode={eff_beam}&eco={eco_flag}&t={int(time.time())}"
    )

    # Launch in true borderless Kiosk fullscreen (NO `--app` titlebar or min/max/close buttons!)
    args = [
        browser_bin,
        f"--user-data-dir={WALLPAPER_PROFILE_DIR}",
        f"--disk-cache-dir={WALLPAPER_CACHE_DIR}",
        "--window-position=0,0",
        f"--window-size={metrics['dip_w']},{metrics['dip_h']}",
        "--kiosk",
        target_url,
    ]
    if kind == "edge":
        args.append("--edge-kiosk-type=fullscreen")
    args.extend([
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-extensions",
        "--disable-sync",
        "--disable-infobars",
        "--disable-session-crashed-bubble",
        "--autoplay-policy=no-user-gesture-required",
        "--disable-background-timer-throttling",
        "--disable-renderer-backgrounding",
        "--disable-backgrounding-occluded-windows",
        "--disable-features=CalculateNativeWinOcclusion,Translate,msEdgeSidebarV2",
    ])

    proc = subprocess.Popen(
        args,
        cwd=str(PROJECT_DIR),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # Wait up to 7.0s for the 'OPHANIM WALLPAPER' window to appear
    wp_hwnd = 0
    deadline = time.monotonic() + 7.0
    while time.monotonic() < deadline:
        found = _find_wallpaper_hwnds()
        if found:
            wp_hwnd = found[0]
            break
        time.sleep(0.06)

    if not wp_hwnd:
        _kill_wallpaper_browser_processes()
        return {
            "type": "ophanim_wallpaper_status",
            "ok": False,
            "active": False,
            "error": "未能捕获壁纸渲染窗口句柄（请确认通过桌面 Ophanim_Sanctum.bat 启动）",
        }

    ok, arch = _apply_wallpaper_styles_and_zorder(wp_hwnd, metrics["phys_w"], metrics["phys_h"])
    if not ok:
        _kill_wallpaper_browser_processes()
        return {"type": "ophanim_wallpaper_status", "ok": False, "active": False, "error": arch}

    new_state = {
        "active": True,
        "pid": proc.pid,
        "hwnd": wp_hwnd,
        "arch": arch,
        "wallpaperMode": wp_mode,
        "beamMode": eff_beam,
        "originalWallpaperPath": orig_wp,
        "activatedAt": int(time.time()),
    }
    _save_state_raw(new_state)

    # Chromium's kiosk startup may fire delayed SetWindowPos ~200-1500ms after first paint; re-pin smoothly
    def _delayed_repin(h_target: int, pw: int, ph: int) -> None:
        for delay_s in (0.25, 0.65, 1.35, 2.4):
            time.sleep(delay_s)
            st_now = _load_state_raw()
            if not st_now.get("active") or int(st_now.get("hwnd") or 0) != h_target:
                return
            try:
                _apply_wallpaper_styles_and_zorder(h_target, pw, ph)
            except Exception:
                return

    threading.Thread(
        target=_delayed_repin,
        args=(wp_hwnd, metrics["phys_w"], metrics["phys_h"]),
        daemon=True,
    ).start()

    logger.info("Enabled Ophanim live wallpaper: hwnd=%s arch=%s mode=%s beam=%s", wp_hwnd, arch, wp_mode, eff_beam)
    return {
        "type": "ophanim_wallpaper_status",
        "ok": True,
        "active": True,
        "wallpaperMode": wp_mode,
        "beamMode": eff_beam,
        "hwnd": wp_hwnd,
        "arch": arch,
        "originalWallpaper": orig_wp,
    }


def _detach_and_close_existing_wallpaper(restore_static: bool = True) -> str:
    if os.name != "nt" or _U32 is None:
        return ""
    u32 = _U32
    state = _load_state_raw()
    orig_wp = str(state.get("originalWallpaperPath") or "").strip()

    hwnds = _find_wallpaper_hwnds()
    saved_h = int(state.get("hwnd") or 0)
    if saved_h and saved_h not in hwnds and u32.IsWindow(saved_h):
        hwnds.append(saved_h)

    for h in hwnds:
        try:
            u32.ShowWindow(h, 0)
            u32.SetParent(h, None)
            u32.PostMessageW(h, WM_CLOSE, 0, 0)
        except Exception:
            pass

    _kill_wallpaper_browser_processes()

    if restore_static:
        if not orig_wp or not Path(orig_wp).is_file():
            orig_wp = _read_current_system_wallpaper()
        if orig_wp and Path(orig_wp).is_file():
            try:
                ctypes.windll.user32.SystemParametersInfoW(
                    SPI_SETDESKWALLPAPER,
                    0,
                    orig_wp,
                    SPIF_UPDATEINIFILE | SPIF_SENDWININICHANGE,
                )
            except Exception as exc:
                logger.warning("Restore SPI_SETDESKWALLPAPER warning: %s", exc)
        progman = u32.FindWindowW("Progman", None)
        if progman:
            u32.RedrawWindow(progman, None, None, 0x0585)
            workerw = u32.FindWindowExW(progman, None, "WorkerW", None)
            if workerw:
                u32.ShowWindow(workerw, 5)
                u32.RedrawWindow(workerw, None, None, 0x0585)

    return orig_wp


def disable_live_wallpaper() -> dict[str, Any]:
    if os.name != "nt":
        return {"type": "ophanim_wallpaper_status", "ok": False, "active": False}
    prev = _load_state_raw()
    prev["active"] = False
    _save_state_raw(prev)
    restored_path = _detach_and_close_existing_wallpaper(restore_static=True)
    prev["hwnd"] = 0
    prev["pid"] = 0
    _save_state_raw(prev)
    logger.info("Disabled Ophanim live wallpaper; restored original wallpaper=%r", restored_path)
    return {
        "type": "ophanim_wallpaper_status",
        "ok": True,
        "active": False,
        "wallpaperMode": str(prev.get("wallpaperMode") or "agy_live"),
        "beamMode": str(prev.get("beamMode") or "tool_io"),
        "hwnd": 0,
        "originalWallpaper": restored_path,
    }


_PTR_CACHE: dict[str, Any] = {
    "last_hwnd_check_mono": 0.0,
    "hwnd": 0,
    "phys_w": 1920,
    "phys_h": 1080,
    "prev_btn": 0,
    "latched_on_icon": False,
}


def _release_com_unknown(ptr_val: int) -> None:
    """Call IUnknown::Release (vtable slot 2) safely on a raw COM interface pointer."""
    if not ptr_val:
        return
    try:
        vtbl_ptr = ctypes.c_void_p.from_address(ptr_val).value
        if not vtbl_ptr:
            return
        release_addr = ctypes.c_void_p.from_address(vtbl_ptr + 2 * ctypes.sizeof(ctypes.c_void_p)).value
        if not release_addr:
            return
        release_fn = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(release_addr)
        release_fn(ptr_val)
    except Exception:
        pass


def _is_point_on_desktop_icon(pt: POINT) -> bool:
    """Return True iff `pt` hits an actual desktop shortcut item on SysListView32 (not empty desktop background)."""
    if os.name != "nt" or _OLEACC is None or _OLEAUT32 is None:
        return False
    pacc = ctypes.c_void_p(0)
    var_child = VARIANT()
    try:
        hr = int(_OLEACC.AccessibleObjectFromPoint(pt, ctypes.byref(pacc), ctypes.byref(var_child)))
        is_icon = bool(hr == 0 and var_child.vt == 3 and int(var_child.u.lVal) > 0)
        return is_icon
    except Exception:
        return False
    finally:
        if pacc.value:
            _release_com_unknown(int(pacc.value))
        try:
            _OLEAUT32.VariantClear(ctypes.byref(var_child))
        except Exception:
            pass


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("pt", POINT),
        ("mouseData", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


_WHEEL_LOCK = threading.Lock()
_WHEEL_ACCUM_STEPS: float = 0.0
_CLICK_PENDING: bool = False
_LDOWN_PT: tuple[int, int, float] | None = None
_WHEEL_HOOK_STARTED = False
_WHEEL_HOOK_PROC_REF: Any = None


def _ensure_mid_wheel_observer() -> None:
    """Start a passive 64-bit WH_MOUSE_LL observer once for Middle+Wheel zoom and crisp desktop clicks."""
    global _WHEEL_HOOK_STARTED, _WHEEL_HOOK_PROC_REF
    if _WHEEL_HOOK_STARTED or os.name != "nt" or _U32 is None:
        return
    with _WHEEL_LOCK:
        if _WHEEL_HOOK_STARTED:
            return
        _WHEEL_HOOK_STARTED = True

    def _hook_worker() -> None:
        global _WHEEL_ACCUM_STEPS, _CLICK_PENDING, _LDOWN_PT, _WHEEL_HOOK_PROC_REF
        u32 = _U32
        if u32 is None:
            return
        HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)

        def _ll_mouse_cb(n_code: int, w_param: int, l_param: int) -> int:
            global _WHEEL_ACCUM_STEPS, _CLICK_PENDING, _LDOWN_PT
            try:
                if n_code >= 0 and l_param:
                    if w_param == 0x020A:  # WM_MOUSEWHEEL
                        if int(u32.GetAsyncKeyState(0x04)) & 0x8000:
                            info = ctypes.cast(l_param, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
                            raw_delta = ctypes.c_short((int(info.mouseData) >> 16) & 0xFFFF).value
                            if raw_delta:
                                with _WHEEL_LOCK:
                                    _WHEEL_ACCUM_STEPS = max(-12.0, min(12.0, _WHEEL_ACCUM_STEPS + (raw_delta / 120.0)))
                    elif w_param == 0x0201:  # WM_LBUTTONDOWN
                        info = ctypes.cast(l_param, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
                        with _WHEEL_LOCK:
                            _LDOWN_PT = (int(info.pt.x), int(info.pt.y), time.monotonic())
                    elif w_param == 0x0202:  # WM_LBUTTONUP
                        info = ctypes.cast(l_param, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
                        with _WHEEL_LOCK:
                            if _LDOWN_PT is not None:
                                dx = int(info.pt.x) - _LDOWN_PT[0]
                                dy = int(info.pt.y) - _LDOWN_PT[1]
                                dt_click = time.monotonic() - _LDOWN_PT[2]
                                _LDOWN_PT = None
                                if (dx * dx + dy * dy) <= 100 and dt_click <= 0.70:
                                    _CLICK_PENDING = True
            except Exception:
                pass
            return int(u32.CallNextHookEx(None, n_code, w_param, l_param))

        cb_ref = HOOKPROC(_ll_mouse_cb)
        _WHEEL_HOOK_PROC_REF = cb_ref
        hhook = u32.SetWindowsHookExW(14, ctypes.cast(cb_ref, ctypes.c_void_p), None, 0)
        if not hhook:
            return
        msg = wintypes.MSG()
        try:
            while u32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                pass
        finally:
            u32.UnhookWindowsHookEx(hhook)

    threading.Thread(target=_hook_worker, name="ophanim-wp-wheel", daemon=True).start()


def _pop_hook_events() -> tuple[float, bool]:
    global _WHEEL_ACCUM_STEPS, _CLICK_PENDING
    with _WHEEL_LOCK:
        val = _WHEEL_ACCUM_STEPS
        clk = _CLICK_PENDING
        _WHEEL_ACCUM_STEPS = 0.0
        _CLICK_PENDING = False
    return val, clk


def _win_class_fast(hwnd: int) -> str:
    if not hwnd or _U32 is None:
        return ""
    buf = ctypes.create_unicode_buffer(64)
    n = int(_U32.GetClassNameW(hwnd, buf, 64))
    return str(buf.value[:n]) if n > 0 else ""


def sample_desktop_pointer() -> dict[str, Any] | None:
    """Sample live desktop cursor & button state without hooks or focus theft (~60Hz when wallpaper is active)."""
    if os.name != "nt" or _U32 is None:
        return None
    u32 = _U32
    now_m = time.monotonic()

    wp_hwnd = int(_PTR_CACHE.get("hwnd") or 0)
    if (now_m - float(_PTR_CACHE.get("last_hwnd_check_mono") or 0.0)) >= 0.45 or not wp_hwnd or not u32.IsWindow(wp_hwnd):
        _PTR_CACHE["last_hwnd_check_mono"] = now_m
        st = _load_state_raw()
        if not st.get("active"):
            _PTR_CACHE["hwnd"] = 0
            _PTR_CACHE["prev_btn"] = 0
            _PTR_CACHE["latched_on_icon"] = False
            return None
        cand_h = int(st.get("hwnd") or 0)
        if not cand_h or not u32.IsWindow(cand_h):
            found = _find_wallpaper_hwnds()
            cand_h = found[0] if found else 0
        _PTR_CACHE["hwnd"] = cand_h
        wp_hwnd = cand_h
        pw = int(u32.GetSystemMetrics(0)) or 1920
        ph = int(u32.GetSystemMetrics(1)) or 1080
        _PTR_CACHE["phys_w"] = pw
        _PTR_CACHE["phys_h"] = ph

    if not wp_hwnd:
        return None

    _ensure_mid_wheel_observer()

    pt = POINT()
    if not u32.GetCursorPos(ctypes.byref(pt)):
        return None

    rc = RECT()
    if u32.GetWindowRect(wp_hwnd, ctypes.byref(rc)) and (rc.right - rc.left) >= 200 and (rc.bottom - rc.top) >= 200:
        w = float(rc.right - rc.left)
        h = float(rc.bottom - rc.top)
        nx = (float(pt.x - rc.left)) / w
        ny = (float(pt.y - rc.top)) / h
    else:
        pw = float(_PTR_CACHE.get("phys_w") or 1920)
        ph = float(_PTR_CACHE.get("phys_h") or 1080)
        nx = float(pt.x) / pw
        ny = float(pt.y) / ph

    nx = 0.0 if nx < 0.0 else (1.0 if nx > 1.0 else nx)
    ny = 0.0 if ny < 0.0 else (1.0 if ny > 1.0 else ny)

    # Determine whether the cursor is directly over the exposed Windows Desktop (not covered by an app window/menu/taskbar)
    hwnd_at = int(u32.WindowFromPoint(pt) or 0)
    on_desktop = False
    if hwnd_at:
        cls_at = _win_class_fast(hwnd_at)
        root = int(u32.GetAncestor(hwnd_at, 2) or hwnd_at)
        cls_root = _win_class_fast(root)
        if cls_root == "Progman":
            on_desktop = True
        elif cls_root == "WorkerW" and cls_at in ("SysListView32", "SHELLDLL_DefView", "WorkerW"):
            if u32.FindWindowExW(root, None, "SHELLDLL_DefView", None):
                on_desktop = True

    swapped = bool(u32.GetSystemMetrics(23))
    vk_left = 0x02 if swapped else 0x01
    vk_right = 0x01 if swapped else 0x02
    vk_mid = 0x04

    btn = 0
    if int(u32.GetAsyncKeyState(vk_left)) & 0x8000:
        btn |= 1
    if int(u32.GetAsyncKeyState(vk_right)) & 0x8000:
        btn |= 2
    if int(u32.GetAsyncKeyState(vk_mid)) & 0x8000:
        btn |= 4

    prev_btn = int(_PTR_CACHE.get("prev_btn") or 0)
    was_on_icon = bool(_PTR_CACHE.get("latched_on_icon"))
    if (btn & 1) and not (prev_btn & 1):
        _PTR_CACHE["latched_on_icon"] = _is_point_on_desktop_icon(pt) if on_desktop else False
        was_on_icon = bool(_PTR_CACHE["latched_on_icon"])
    elif not (btn & 1):
        _PTR_CACHE["latched_on_icon"] = False
    _PTR_CACHE["prev_btn"] = btn

    wheel_raw, click_raw = _pop_hook_events()
    wheel_steps = round(wheel_raw, 3) if (on_desktop and (btn & 4) and abs(wheel_raw) > 0.01) else 0.0
    click_on_bg = False
    if click_raw and on_desktop:
        hit_icon_now = was_on_icon or _is_point_on_desktop_icon(pt)
        click_on_bg = not hit_icon_now

    return {
        "type": "wp_ptr",
        "nx": round(nx, 5),
        "ny": round(ny, 5),
        "px": int(pt.x),
        "py": int(pt.y),
        "btn": btn,
        "desk": on_desktop,
        "icon": bool(_PTR_CACHE["latched_on_icon"]),
        "wheel": wheel_steps,
        "click": 1 if click_on_bg else 0,
    }
