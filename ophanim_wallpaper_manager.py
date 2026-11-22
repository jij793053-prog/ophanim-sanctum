#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ophanim_wallpaper_manager.py
True Windows 10 / Windows 11 (including Win11 24H2 RaisedDesktop Progman build >= 26000)
dynamic desktop wallpaper controller for Ophanim Sanctum.

Safety & performance guarantees:
  1. Dedicated 64-bit `ctypes.WinDLL` bindings with explicit `argtypes`/`restype` everywhere
     (zero untyped `ctypes.windll.*` calls; safe against 64-bit handle truncation).
  2. All lifecycle/state transitions serialized under `_WALLPAPER_LOCK` (`threading.RLock`)
     with monotonic `_WALLPAPER_GEN` generation checks and atomic `os.replace` retry I/O.
  3. Spawned Chromium kiosk process is bound to a Win32 Job Object
     (`JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`) and verified on `SetParent`/`GetParent` so a
     failed attach or daemon crash can NEVER leave a trapped fullscreen `--kiosk` window.
  4. Zero `SPI_SETDESKWALLPAPER`, zero `SetParent(h, None)` before kill, and zero synchronous
     `RDW_UPDATENOW` on disable; desktop refresh is strictly asynchronous and guarded by
     `IsHungAppWindow(progman)`.
  5. `0x052C` (`0xD, 0x1` with `SMTO_ABORTIFHUNG`) and `ITaskbarList::DeleteTab` (paired
     `CoInitializeEx`/`CoUninitialize`) execute ONLY once on initial attach; periodic
     `ensure_wallpaper_pinned()` is a read-only diff check (zero Explorer/COM hammering).
  6. Replaces permanent global Python `WH_MOUSE_LL` with lifecycle-managed asynchronous
     Win32 Raw Input (`RIDEV_INPUTSINK` on a hidden `HWND_MESSAGE` window) that cleanly
     unregisters (`RIDEV_REMOVE`) and terminates its thread on disable/disconnect/shutdown.
  7. Runs `AccessibleObjectFromPoint` on a dedicated STA COM worker thread with <=150ms
     timeout + circuit-breaker, strictly gated to responsive `SysListView32` hits.
  8. Exposes `is_desktop_occluded()` so the daemon can pause 4K WebGL rendering to 0fps
     whenever fullscreen or maximized applications cover the desktop.
"""
from __future__ import annotations

import atexit
import ctypes
from ctypes import wintypes
import json
import logging
import os
from pathlib import Path
import shutil
import subprocess
import sys
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
SWP_ASYNCWINDOWPOS = 0x4000

SW_HIDE = 0
SW_SHOW = 5

WM_NULL = 0x0000
WM_DESTROY = 0x0002
WM_CLOSE = 0x0010
WM_QUIT = 0x0012
WM_INPUT = 0x00FF

SMTO_ABORTIFHUNG = 0x0002
GW_HWNDNEXT = 2

# RDW_INVALIDATE (0x0001) | RDW_ERASE (0x0004) | RDW_ALLCHILDREN (0x0080) — NO RDW_UPDATENOW!
RDW_ASYNC_REFRESH = 0x0085

COINIT_APARTMENTTHREADED = 0x2

# Win32 Job Object constants
JobObjectExtendedLimitInformation = 9
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
PROCESS_SET_QUOTA = 0x0100
PROCESS_TERMINATE = 0x0001
SYNCHRONIZE = 0x00100000

# Raw Input constants
RIDEV_REMOVE = 0x00000001
RIDEV_INPUTSINK = 0x00000100
RID_INPUT = 0x10000003
RIM_TYPEMOUSE = 0
RI_MOUSE_LEFT_BUTTON_DOWN = 0x0001
RI_MOUSE_LEFT_BUTTON_UP = 0x0002
RI_MOUSE_RIGHT_BUTTON_DOWN = 0x0004
RI_MOUSE_RIGHT_BUTTON_UP = 0x0008
RI_MOUSE_MIDDLE_BUTTON_DOWN = 0x0010
RI_MOUSE_MIDDLE_BUTTON_UP = 0x0020
RI_MOUSE_WHEEL = 0x0400

# SHQueryUserNotificationState values indicating fullscreen/presentation occlusion
QUNS_BUSY = 2
QUNS_RUNNING_D3D_FULL_SCREEN = 3
QUNS_PRESENTATION_MODE = 4

MONITOR_DEFAULTTOPRIMARY = 1

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)


# ============================================================================
# Explicit 64-bit Win32 Structures & Typed WinDLL Bindings
# ============================================================================

class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


class MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", RECT),
        ("rcWork", RECT),
        ("dwFlags", wintypes.DWORD),
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


class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_int64),
        ("PerJobUserTimeLimit", ctypes.c_int64),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]


class IO_COUNTERS(ctypes.Structure):
    _fields_ = [
        ("ReadOperationCount", ctypes.c_uint64),
        ("WriteOperationCount", ctypes.c_uint64),
        ("OtherOperationCount", ctypes.c_uint64),
        ("ReadTransferCount", ctypes.c_uint64),
        ("WriteTransferCount", ctypes.c_uint64),
        ("OtherTransferCount", ctypes.c_uint64),
    ]


class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
        ("IoInfo", IO_COUNTERS),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


class RAWINPUTDEVICE(ctypes.Structure):
    _fields_ = [
        ("usUsagePage", wintypes.USHORT),
        ("usUsage", wintypes.USHORT),
        ("dwFlags", wintypes.DWORD),
        ("hwndTarget", wintypes.HWND),
    ]


class RAWINPUTHEADER(ctypes.Structure):
    _fields_ = [
        ("dwType", wintypes.DWORD),
        ("dwSize", wintypes.DWORD),
        ("hDevice", wintypes.HANDLE),
        ("wParam", wintypes.WPARAM),
    ]


class _RAWMOUSE_BUTTONS_STRUCT(ctypes.Structure):
    _fields_ = [
        ("usButtonFlags", wintypes.USHORT),
        ("usButtonData", wintypes.USHORT),
    ]


class _RAWMOUSE_BUTTONS_UNION(ctypes.Union):
    _fields_ = [
        ("ulButtons", wintypes.ULONG),
        ("s", _RAWMOUSE_BUTTONS_STRUCT),
    ]


class RAWMOUSE(ctypes.Structure):
    _fields_ = [
        ("usFlags", wintypes.USHORT),
        ("buttons", _RAWMOUSE_BUTTONS_UNION),
        ("ulRawButtons", wintypes.ULONG),
        ("lLastX", wintypes.LONG),
        ("lLastY", wintypes.LONG),
        ("ulExtraInformation", wintypes.ULONG),
    ]


class RAWINPUT_MOUSE(ctypes.Structure):
    _fields_ = [
        ("header", RAWINPUTHEADER),
        ("mouse", RAWMOUSE),
    ]


WNDPROC_TYPE = ctypes.WINFUNCTYPE(
    ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM
)


class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.UINT),
        ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROC_TYPE),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
        ("hIconSm", wintypes.HICON),
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

    u32.IsWindowVisible.argtypes = [wintypes.HWND]
    u32.IsWindowVisible.restype = wintypes.BOOL

    u32.IsIconic.argtypes = [wintypes.HWND]
    u32.IsIconic.restype = wintypes.BOOL

    u32.IsZoomed.argtypes = [wintypes.HWND]
    u32.IsZoomed.restype = wintypes.BOOL

    u32.IsHungAppWindow.argtypes = [wintypes.HWND]
    u32.IsHungAppWindow.restype = wintypes.BOOL

    u32.GetParent.argtypes = [wintypes.HWND]
    u32.GetParent.restype = wintypes.HWND

    u32.SetParent.argtypes = [wintypes.HWND, wintypes.HWND]
    u32.SetParent.restype = wintypes.HWND

    u32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
    u32.GetWindow.restype = wintypes.HWND

    u32.EnableWindow.argtypes = [wintypes.HWND, wintypes.BOOL]
    u32.EnableWindow.restype = wintypes.BOOL

    u32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    u32.ShowWindow.restype = wintypes.BOOL

    u32.ShowWindowAsync.argtypes = [wintypes.HWND, ctypes.c_int]
    u32.ShowWindowAsync.restype = wintypes.BOOL

    u32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    u32.PostMessageW.restype = wintypes.BOOL

    u32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    u32.PostThreadMessageW.restype = wintypes.BOOL

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

    u32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    u32.GetWindowThreadProcessId.restype = wintypes.DWORD

    u32.GetCursorPos.argtypes = [ctypes.POINTER(POINT)]
    u32.GetCursorPos.restype = wintypes.BOOL

    u32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(RECT)]
    u32.GetWindowRect.restype = wintypes.BOOL

    u32.WindowFromPoint.argtypes = [POINT]
    u32.WindowFromPoint.restype = wintypes.HWND

    u32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
    u32.GetAncestor.restype = wintypes.HWND

    u32.GetForegroundWindow.argtypes = []
    u32.GetForegroundWindow.restype = wintypes.HWND

    u32.MonitorFromPoint.argtypes = [POINT, wintypes.DWORD]
    u32.MonitorFromPoint.restype = wintypes.HMONITOR

    u32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
    u32.MonitorFromWindow.restype = wintypes.HMONITOR

    u32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(MONITORINFO)]
    u32.GetMonitorInfoW.restype = wintypes.BOOL

    u32.GetAsyncKeyState.argtypes = [ctypes.c_int]
    u32.GetAsyncKeyState.restype = ctypes.c_short

    u32.GetSystemMetrics.argtypes = [ctypes.c_int]
    u32.GetSystemMetrics.restype = ctypes.c_int

    u32.SystemParametersInfoW.argtypes = [wintypes.UINT, wintypes.UINT, ctypes.c_void_p, wintypes.UINT]
    u32.SystemParametersInfoW.restype = wintypes.BOOL

    u32.EnumWindows.argtypes = [ctypes.c_void_p, wintypes.LPARAM]
    u32.EnumWindows.restype = wintypes.BOOL

    u32.EnumChildWindows.argtypes = [wintypes.HWND, ctypes.c_void_p, wintypes.LPARAM]
    u32.EnumChildWindows.restype = wintypes.BOOL

    if hasattr(u32, "SetProcessDpiAwarenessContext"):
        u32.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
        u32.SetProcessDpiAwarenessContext.restype = wintypes.BOOL
    if hasattr(u32, "SetProcessDPIAware"):
        u32.SetProcessDPIAware.argtypes = []
        u32.SetProcessDPIAware.restype = wintypes.BOOL
    if hasattr(u32, "GetDpiForSystem"):
        u32.GetDpiForSystem.argtypes = []
        u32.GetDpiForSystem.restype = wintypes.UINT

    # Raw Input & hidden HWND_MESSAGE window APIs
    u32.RegisterClassExW.argtypes = [ctypes.POINTER(WNDCLASSEXW)]
    u32.RegisterClassExW.restype = wintypes.ATOM

    u32.UnregisterClassW.argtypes = [wintypes.LPCWSTR, wintypes.HINSTANCE]
    u32.UnregisterClassW.restype = wintypes.BOOL

    u32.CreateWindowExW.argtypes = [
        wintypes.DWORD,
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        wintypes.DWORD,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.HWND,
        wintypes.HMENU,
        wintypes.HINSTANCE,
        ctypes.c_void_p,
    ]
    u32.CreateWindowExW.restype = wintypes.HWND

    u32.DestroyWindow.argtypes = [wintypes.HWND]
    u32.DestroyWindow.restype = wintypes.BOOL

    u32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    u32.DefWindowProcW.restype = ctypes.c_ssize_t

    u32.RegisterRawInputDevices.argtypes = [ctypes.POINTER(RAWINPUTDEVICE), wintypes.UINT, wintypes.UINT]
    u32.RegisterRawInputDevices.restype = wintypes.BOOL

    u32.GetRawInputData.argtypes = [
        ctypes.c_void_p,
        wintypes.UINT,
        ctypes.c_void_p,
        ctypes.POINTER(wintypes.UINT),
        wintypes.UINT,
    ]
    u32.GetRawInputData.restype = wintypes.UINT

    u32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
    u32.GetMessageW.restype = wintypes.BOOL

    u32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
    u32.TranslateMessage.restype = wintypes.BOOL

    u32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
    u32.DispatchMessageW.restype = ctypes.c_ssize_t

    u32.PostQuitMessage.argtypes = [ctypes.c_int]
    u32.PostQuitMessage.restype = None

    return u32


def _bind_win32_kernel32() -> Any:
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)

    k32.GetCurrentThreadId.argtypes = []
    k32.GetCurrentThreadId.restype = wintypes.DWORD

    k32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
    k32.GetModuleHandleW.restype = wintypes.HMODULE

    k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    k32.OpenProcess.restype = wintypes.HANDLE

    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    k32.CloseHandle.restype = wintypes.BOOL

    k32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    k32.WaitForSingleObject.restype = wintypes.DWORD

    k32.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    ]
    k32.QueryFullProcessImageNameW.restype = wintypes.BOOL

    k32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    k32.CreateJobObjectW.restype = wintypes.HANDLE

    k32.SetInformationJobObject.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
    k32.SetInformationJobObject.restype = wintypes.BOOL

    k32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    k32.AssignProcessToJobObject.restype = wintypes.BOOL

    k32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
    k32.TerminateJobObject.restype = wintypes.BOOL

    return k32


def _bind_win32_ole32() -> Any:
    if os.name != "nt":
        return None
    try:
        ole32 = ctypes.WinDLL("ole32")
        ole32.CoInitializeEx.argtypes = [ctypes.c_void_p, wintypes.DWORD]
        ole32.CoInitializeEx.restype = ctypes.c_long
        ole32.CoUninitialize.argtypes = []
        ole32.CoUninitialize.restype = None
        ole32.CoCreateInstance.argtypes = [
            ctypes.POINTER(_GUID),
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.POINTER(_GUID),
            ctypes.POINTER(ctypes.c_void_p),
        ]
        ole32.CoCreateInstance.restype = ctypes.c_long
        return ole32
    except Exception:
        return None


def _bind_win32_shell32() -> Any:
    if os.name != "nt":
        return None
    try:
        shell32 = ctypes.WinDLL("shell32")
        if hasattr(shell32, "SHQueryUserNotificationState"):
            shell32.SHQueryUserNotificationState.argtypes = [ctypes.POINTER(ctypes.c_int)]
            shell32.SHQueryUserNotificationState.restype = ctypes.c_long
        return shell32
    except Exception:
        return None


def _bind_win32_shcore() -> Any:
    if os.name != "nt":
        return None
    try:
        shcore = ctypes.WinDLL("shcore")
        if hasattr(shcore, "SetProcessDpiAwareness"):
            shcore.SetProcessDpiAwareness.argtypes = [ctypes.c_int]
            shcore.SetProcessDpiAwareness.restype = ctypes.c_long
        return shcore
    except Exception:
        return None


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
_K32 = _bind_win32_kernel32() if os.name == "nt" else None
_OLE32 = _bind_win32_ole32()
_SHELL32 = _bind_win32_shell32()
_SHCORE = _bind_win32_shcore()
_OLEACC, _OLEAUT32 = _bind_win32_accessibility()


# ============================================================================
# Serialized State, Generation Counter & Atomic File I/O
# ============================================================================

_WALLPAPER_LOCK = threading.RLock()
_WALLPAPER_GEN: int = 0
_MEM_STATE: dict[str, Any] | None = None
_ACTIVE_JOB_HANDLE: int = 0
_OWNED_BY_THIS_PROCESS: bool = False


def _atomic_write_text(dest: Path, text: str, retries: int = 5) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.parent / f".{dest.name}.{os.getpid()}.{threading.get_ident()}.{time.time_ns()}.tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            try:
                os.fsync(fh.fileno())
            except OSError:
                pass
        last_exc: Exception | None = None
        for attempt in range(max(1, retries)):
            try:
                os.replace(tmp, dest)
                return
            except PermissionError as exc:
                last_exc = exc
                time.sleep(0.02 * (attempt + 1))
            except OSError as exc:
                if getattr(exc, "winerror", 0) in (5, 32):
                    last_exc = exc
                    time.sleep(0.02 * (attempt + 1))
                else:
                    raise
        if last_exc is not None:
            raise last_exc
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def _load_state_from_disk() -> dict[str, Any]:
    if not WALLPAPER_STATE_PATH.is_file():
        return {}
    try:
        data = json.loads(WALLPAPER_STATE_PATH.read_text(encoding="utf-8", errors="replace"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _get_mem_state() -> dict[str, Any]:
    global _MEM_STATE
    with _WALLPAPER_LOCK:
        if _MEM_STATE is None:
            _MEM_STATE = _load_state_from_disk()
        return dict(_MEM_STATE)


def _save_state_raw(data: dict[str, Any]) -> None:
    global _MEM_STATE
    with _WALLPAPER_LOCK:
        _MEM_STATE = dict(data)
        try:
            _atomic_write_text(
                WALLPAPER_STATE_PATH,
                json.dumps(_MEM_STATE, ensure_ascii=False, indent=2) + "\n",
                retries=5,
            )
        except Exception as exc:
            logger.warning("Failed saving wallpaper state: %s", exc)


# ============================================================================
# Win32 Helpers, Job Object & Explorer Pre-flight Checks
# ============================================================================

def _is_win11_24h2_or_newer() -> bool:
    if os.name != "nt":
        return False
    try:
        return int(sys.getwindowsversion().build) >= 26000
    except Exception:
        return False


def _enable_dpi_awareness() -> None:
    if os.name != "nt":
        return
    try:
        if _U32 is not None and hasattr(_U32, "SetProcessDpiAwarenessContext"):
            if _U32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
                return
    except Exception:
        pass
    try:
        if _SHCORE is not None and hasattr(_SHCORE, "SetProcessDpiAwareness"):
            _SHCORE.SetProcessDpiAwareness(2)
            return
    except Exception:
        pass
    try:
        if _U32 is not None and hasattr(_U32, "SetProcessDPIAware"):
            _U32.SetProcessDPIAware()
    except Exception:
        pass


def _is_window_responsive(hwnd: int, timeout_ms: int = 250) -> bool:
    if os.name != "nt" or _U32 is None or not hwnd:
        return False
    try:
        if not _U32.IsWindow(hwnd):
            return False
        if _U32.IsHungAppWindow(hwnd):
            return False
        res = ctypes.c_size_t(0)
        ok = _U32.SendMessageTimeoutW(
            hwnd,
            WM_NULL,
            0,
            0,
            SMTO_ABORTIFHUNG,
            int(timeout_ms),
            ctypes.byref(res),
        )
        return bool(ok)
    except Exception:
        return False


def _win_class_fast(hwnd: int) -> str:
    if not hwnd or _U32 is None:
        return ""
    buf = ctypes.create_unicode_buffer(64)
    n = int(_U32.GetClassNameW(hwnd, buf, 64))
    return str(buf.value[:n]) if n > 0 else ""


def _get_hwnd_pid(hwnd: int) -> int:
    if os.name != "nt" or _U32 is None or not hwnd:
        return 0
    pid = wintypes.DWORD(0)
    try:
        _U32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return int(pid.value)
    except Exception:
        return 0


def _get_pid_exe_basename(pid: int) -> str:
    if os.name != "nt" or _K32 is None or pid <= 0:
        return ""
    hproc = _K32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
    if not hproc:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(1024)
        sz = wintypes.DWORD(1024)
        if _K32.QueryFullProcessImageNameW(hproc, 0, buf, ctypes.byref(sz)):
            return os.path.basename(buf.value or "").lower()
    except Exception:
        pass
    finally:
        _K32.CloseHandle(hproc)
    return ""


def _is_pid_alive(pid: int) -> bool:
    if os.name != "nt" or _K32 is None or pid <= 0:
        return False
    hproc = _K32.OpenProcess(SYNCHRONIZE, False, int(pid))
    if not hproc:
        return False
    try:
        # WAIT_TIMEOUT (0x102) => still running
        return int(_K32.WaitForSingleObject(hproc, 0)) == 0x00000102
    except Exception:
        return False
    finally:
        _K32.CloseHandle(hproc)


def _wait_pid_exit(pid: int, timeout_s: float = 2.0) -> bool:
    if os.name != "nt" or _K32 is None or pid <= 0:
        return True
    hproc = _K32.OpenProcess(SYNCHRONIZE, False, int(pid))
    if not hproc:
        return True
    try:
        rc = int(_K32.WaitForSingleObject(hproc, max(1, int(timeout_s * 1000))))
        return rc == 0
    except Exception:
        return False
    finally:
        _K32.CloseHandle(hproc)


def _is_verified_wallpaper_hwnd(hwnd: int, expected_pid: int = 0) -> bool:
    """Strictly verify `hwnd` is a genuine Ophanim Chromium wallpaper window (prevents recycled-HWND hijacking)."""
    if os.name != "nt" or _U32 is None or not hwnd or int(hwnd) <= 0:
        return False
    try:
        h = int(hwnd)
        if not _U32.IsWindow(h):
            return False
        if _win_class_fast(h) != "Chrome_WidgetWin_1":
            return False
        title_buf = ctypes.create_unicode_buffer(512)
        _U32.GetWindowTextW(h, title_buf, 512)
        title = (title_buf.value or "").strip()
        if "OPHANIM WALLPAPER" not in title.upper():
            return False
        win_pid = _get_hwnd_pid(h)
        if win_pid <= 0:
            return False
        if expected_pid > 0 and win_pid != int(expected_pid):
            return False
        exe_name = _get_pid_exe_basename(win_pid)
        if exe_name not in ("msedge.exe", "chrome.exe"):
            return False
        return True
    except Exception:
        return False


def _create_wallpaper_job() -> int:
    if os.name != "nt" or _K32 is None:
        return 0
    hjob = _K32.CreateJobObjectW(None, None)
    if not hjob:
        return 0
    info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
    info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    ok = _K32.SetInformationJobObject(
        hjob,
        JobObjectExtendedLimitInformation,
        ctypes.byref(info),
        ctypes.sizeof(info),
    )
    if not ok:
        _K32.CloseHandle(hjob)
        return 0
    return int(hjob)


def _assign_pid_to_job(job_handle: int, pid: int) -> bool:
    if os.name != "nt" or _K32 is None or not job_handle or pid <= 0:
        return False
    hproc = _K32.OpenProcess(PROCESS_SET_QUOTA | PROCESS_TERMINATE, False, int(pid))
    if not hproc:
        return False
    try:
        return bool(_K32.AssignProcessToJobObject(job_handle, hproc))
    finally:
        _K32.CloseHandle(hproc)


def _terminate_and_close_job() -> None:
    global _ACTIVE_JOB_HANDLE
    if os.name != "nt" or _K32 is None:
        _ACTIVE_JOB_HANDLE = 0
        return
    with _WALLPAPER_LOCK:
        jh = _ACTIVE_JOB_HANDLE
        _ACTIVE_JOB_HANDLE = 0
    if jh:
        try:
            _K32.TerminateJobObject(jh, 0)
        except Exception:
            pass
        try:
            _K32.CloseHandle(jh)
        except Exception:
            pass


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


def _hide_hwnd_from_taskbar(hwnd: int) -> bool:
    """Purge `hwnd` from Explorer Taskbar via COM `ITaskbarList::DeleteTab` (called ONLY once on initial attach)."""
    if os.name != "nt" or not hwnd or _U32 is None or _OLE32 is None:
        return False
    tray = _U32.FindWindowW("Shell_TrayWnd", None)
    if tray and _U32.IsHungAppWindow(tray):
        logger.debug("Skipping ITaskbarList::DeleteTab because Shell_TrayWnd is hung")
        return False

    p_tb = ctypes.c_void_p(0)
    should_uninit = False
    try:
        hr_init = int(_OLE32.CoInitializeEx(None, COINIT_APARTMENTTHREADED))
        should_uninit = hr_init in (0, 1)
        hr = int(
            _OLE32.CoCreateInstance(
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
        if should_uninit:
            try:
                _OLE32.CoUninitialize()
            except Exception:
                pass


def _read_current_system_wallpaper() -> str:
    if os.name != "nt" or _U32 is None:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(1024)
        if _U32.SystemParametersInfoW(SPI_GETDESKWALLPAPER, 1024, buf, 0):
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
    if os.name == "nt" and _U32 is not None:
        try:
            phys_w = int(_U32.GetSystemMetrics(0)) or 1920
            phys_h = int(_U32.GetSystemMetrics(1)) or 1080
            if hasattr(_U32, "GetDpiForSystem"):
                dpi = int(_U32.GetDpiForSystem())
                if dpi >= 96:
                    scale = dpi / 96.0
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
        _atomic_write_text(prefs_path, json.dumps(prefs, ensure_ascii=False), retries=5)
    except Exception as exc:
        logger.debug("Wallpaper Preferences atomic preset skipped: %s", exc)


def _find_wallpaper_hwnds(expected_pid: int = 0) -> list[int]:
    """Find any verified top-level or Progman/WorkerW-parented Chromium window titled 'OPHANIM WALLPAPER'."""
    if os.name != "nt" or _U32 is None:
        return []
    u32 = _U32
    found: list[int] = []
    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def _check_hwnd(h: int) -> None:
        if not h:
            return
        hv = int(h)
        if hv in found:
            return
        if _is_verified_wallpaper_hwnd(hv, expected_pid=expected_pid):
            found.append(hv)

    def _cb(hwnd: int, _lp: int) -> bool:
        _check_hwnd(hwnd)
        return True

    cb_fn = WNDENUMPROC(_cb)
    cb_ptr = ctypes.cast(cb_fn, ctypes.c_void_p)
    u32.EnumWindows(cb_ptr, 0)
    progman = u32.FindWindowW("Progman", None)
    if progman:
        u32.EnumChildWindows(progman, cb_ptr, 0)
    return found


def _taskkill_pid_tree(pid: int) -> None:
    if os.name != "nt" or pid <= 0:
        return
    try:
        subprocess.run(
            ["taskkill", "/PID", str(int(pid)), "/T", "/F"],
            timeout=3.0,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=_NO_WINDOW,
            check=False,
        )
    except Exception as exc:
        logger.debug("taskkill PID %s warning: %s", pid, exc)


def _kill_wallpaper_browser_processes(tracked_pids: list[int] | None = None, allow_wmi_fallback: bool = False) -> None:
    """Terminate tracked wallpaper browser Job Object & PID trees cleanly (fast, zero PowerShell WMI in steady path)."""
    if os.name != "nt":
        return

    # 1. Instant kernel-level termination via active Job Object
    _terminate_and_close_job()

    # 2. Terminate any explicit/discovered verified PIDs via taskkill /PID /T /F
    pids_clean: list[int] = []
    for p in (tracked_pids or []):
        pi = int(p or 0)
        if pi > 0 and pi not in pids_clean:
            pids_clean.append(pi)

    for pid in pids_clean:
        if _is_pid_alive(pid):
            _taskkill_pid_tree(pid)
            _wait_pid_exit(pid, timeout_s=1.5)

    # 3. Last-resort fallback ONLY if requested (e.g. stale orphan from previous daemon holding profile lockfile)
    if allow_wmi_fallback and (WALLPAPER_PROFILE_DIR / "lockfile").exists():
        try:
            ps_cmd = (
                "Get-CimInstance Win32_Process | Where-Object { "
                "($_.Name -eq 'msedge.exe' -or $_.Name -eq 'chrome.exe') -and "
                "$_.CommandLine -like '*ophanim_wallpaper_profile*' "
                "} | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
            )
            subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
                timeout=4.0,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=_NO_WINDOW,
                check=False,
            )
        except Exception as exc:
            logger.debug("kill wallpaper WMI fallback warning: %s", exc)


# ============================================================================
# Win11 24H2 / Classic WorkerW Attachment & Read-Only Keep-Alive
# ============================================================================

def _find_classic_workerw() -> int:
    if os.name != "nt" or _U32 is None:
        return 0
    u32 = _U32
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

    cb_fn = WNDENUMPROC(_find_worker_cb)
    u32.EnumWindows(ctypes.cast(cb_fn, ctypes.c_void_p), 0)
    return wallpaper_workerw


def _strict_set_parent(hwnd: int, target_parent: int) -> bool:
    if _U32 is None or not hwnd or not target_parent:
        return False
    ctypes.set_last_error(0)
    prev_parent = _U32.SetParent(hwnd, target_parent)
    err = ctypes.get_last_error()
    actual_parent = int(_U32.GetParent(hwnd) or 0)
    if not prev_parent and err != 0:
        return False
    if actual_parent != int(target_parent):
        return False
    return bool(_U32.IsWindow(hwnd))


def _apply_wallpaper_styles_and_zorder(
    hwnd: int,
    phys_w: int,
    phys_h: int,
    *,
    initial_attach: bool = False,
) -> tuple[bool, str]:
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
    if not _is_window_responsive(progman, timeout_ms=250):
        return False, "Windows 桌面管理器 (Progman) 未响应，已安全中止壁纸挂载"

    is_24h2 = _is_win11_24h2_or_newer()
    defview_in_progman = u32.FindWindowExW(progman, None, "SHELLDLL_DefView", None)
    workerw_in_progman = u32.FindWindowExW(progman, None, "WorkerW", None)

    # Send Progman 0x052C ONLY once on initial attach and ONLY when WorkerW doesn't already exist
    if initial_attach:
        need_spawn_worker = False
        if defview_in_progman:
            need_spawn_worker = not bool(workerw_in_progman)
        elif not is_24h2:
            need_spawn_worker = not bool(_find_classic_workerw())
        else:
            need_spawn_worker = not bool(workerw_in_progman)

        if need_spawn_worker:
            msg_res = ctypes.c_size_t(0)
            sent_ok = u32.SendMessageTimeoutW(
                progman, 0x052C, 0xD, 0x1, SMTO_ABORTIFHUNG, 500, ctypes.byref(msg_res)
            )
            if not sent_ok:
                return False, "Progman 0x052C 超时或无响应，已安全中止"
            defview_in_progman = u32.FindWindowExW(progman, None, "SHELLDLL_DefView", None)
            workerw_in_progman = u32.FindWindowExW(progman, None, "WorkerW", None)

    # On Win11 24H2+, NEVER fall back to classic SWP_NOZORDER if SHELLDLL_DefView is temporarily absent
    if is_24h2 and not defview_in_progman:
        if initial_attach:
            wait_end = time.monotonic() + 1.0
            while time.monotonic() < wait_end and not defview_in_progman:
                time.sleep(0.1)
                if not _is_window_responsive(progman, timeout_ms=200):
                    return False, "Progman 在等待 SHELLDLL_DefView 时失去响应"
                defview_in_progman = u32.FindWindowExW(progman, None, "SHELLDLL_DefView", None)
        if not defview_in_progman:
            return False, "Win11 24H2 SHELLDLL_DefView 暂不可用，已中止以防覆盖桌面图标"

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
        cur_parent = int(u32.GetParent(hwnd) or 0)
        cur_style = int(GetWindowLongPtrW(hwnd, GWL_STYLE)) & 0xFFFFFFFF
        new_style = (cur_style & ~strip_style) | child_flags
        SetWindowLongPtrW(hwnd, GWL_STYLE, _to_ptr_long(new_style))

        cur_ex = int(GetWindowLongPtrW(hwnd, GWL_EXSTYLE)) & 0xFFFFFFFF
        new_ex = (cur_ex & ~ex_strip) | ex_add
        SetWindowLongPtrW(hwnd, GWL_EXSTYLE, _to_ptr_long(new_ex))
        if initial_attach:
            u32.SetLayeredWindowAttributes(hwnd, 0, 255, LWA_ALPHA)
        u32.EnableWindow(hwnd, False)

        if cur_parent != int(progman):
            if not _strict_set_parent(hwnd, int(progman)):
                return False, "SetParent(Progman) 校验失败，已终止壁纸进程以防止全屏卡死"
            SetWindowLongPtrW(hwnd, GWL_STYLE, _to_ptr_long(new_style))
            SetWindowLongPtrW(hwnd, GWL_EXSTYLE, _to_ptr_long(new_ex))
            if initial_attach:
                u32.SetLayeredWindowAttributes(hwnd, 0, 255, LWA_ALPHA)
            u32.EnableWindow(hwnd, False)

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
        if initial_attach:
            _hide_hwnd_from_taskbar(hwnd)

        # Ensure `WorkerW` inside `Progman` sits BEHIND `hwnd` (asynchronously so we never block on Explorer!)
        workerw_in_progman = u32.FindWindowExW(progman, None, "WorkerW", None)
        if workerw_in_progman and int(workerw_in_progman) != int(hwnd):
            if int(u32.GetWindow(hwnd, GW_HWNDNEXT) or 0) != int(workerw_in_progman):
                u32.SetWindowPos(
                    workerw_in_progman,
                    hwnd,
                    0,
                    0,
                    0,
                    0,
                    SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_ASYNCWINDOWPOS,
                )
        return True, "win11_24h2_progman"

    # Classic Windows 10 / Windows 11 <=23H2 architecture
    wallpaper_workerw = _find_classic_workerw()
    target_parent = wallpaper_workerw or int(progman)
    if not _is_window_responsive(target_parent, timeout_ms=250):
        return False, "目标 WorkerW/Progman 未响应，已安全中止"

    cur_parent = int(u32.GetParent(hwnd) or 0)
    cur_style = int(GetWindowLongPtrW(hwnd, GWL_STYLE)) & 0xFFFFFFFF
    new_style = (cur_style & ~strip_style) | child_flags
    SetWindowLongPtrW(hwnd, GWL_STYLE, _to_ptr_long(new_style))

    cur_ex = int(GetWindowLongPtrW(hwnd, GWL_EXSTYLE)) & 0xFFFFFFFF
    new_ex = (cur_ex & ~ex_strip) | ex_add
    SetWindowLongPtrW(hwnd, GWL_EXSTYLE, _to_ptr_long(new_ex))
    if initial_attach:
        u32.SetLayeredWindowAttributes(hwnd, 0, 255, LWA_ALPHA)
    u32.EnableWindow(hwnd, False)

    if cur_parent != int(target_parent):
        if not _strict_set_parent(hwnd, int(target_parent)):
            return False, "SetParent(WorkerW) 校验失败，已终止壁纸进程以防止全屏卡死"
        SetWindowLongPtrW(hwnd, GWL_STYLE, _to_ptr_long(new_style))
        SetWindowLongPtrW(hwnd, GWL_EXSTYLE, _to_ptr_long(new_ex))
        u32.EnableWindow(hwnd, False)

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
    if initial_attach:
        _hide_hwnd_from_taskbar(hwnd)
    return True, "classic_workerw"


def _is_already_pinned_readonly(hwnd: int, phys_w: int, phys_h: int) -> bool:
    """Lightweight read-only check verifying parent, rect, styles, and Z-order behind SHELLDLL_DefView."""
    if os.name != "nt" or _U32 is None or not hwnd:
        return False
    u32 = _U32
    GetWindowLongPtrW = getattr(u32, "GetWindowLongPtrW", u32.GetWindowLongW)
    progman = u32.FindWindowW("Progman", None)
    if not progman:
        return False

    cur_parent = int(u32.GetParent(hwnd) or 0)
    cur_style = int(GetWindowLongPtrW(hwnd, GWL_STYLE)) & 0xFFFFFFFF
    if (cur_style & (WS_CHILD | WS_VISIBLE | WS_DISABLED)) != (WS_CHILD | WS_VISIBLE | WS_DISABLED):
        return False
    if cur_style & (WS_POPUP | WS_CAPTION):
        return False

    rc = RECT()
    if not u32.GetWindowRect(hwnd, ctypes.byref(rc)):
        return False
    if abs((rc.right - rc.left) - int(phys_w)) > 2 or abs((rc.bottom - rc.top) - int(phys_h)) > 2:
        return False
    if abs(rc.left) > 2 or abs(rc.top) > 2:
        return False

    defview_in_progman = u32.FindWindowExW(progman, None, "SHELLDLL_DefView", None)
    if defview_in_progman:
        if cur_parent != int(progman):
            return False
        if int(u32.GetWindow(defview_in_progman, GW_HWNDNEXT) or 0) != int(hwnd):
            return False
        workerw_in_progman = u32.FindWindowExW(progman, None, "WorkerW", None)
        if workerw_in_progman and int(workerw_in_progman) != int(hwnd):
            # Confirm workerw sits behind hwnd in Z-order
            cur = int(u32.GetWindow(hwnd, GW_HWNDNEXT) or 0)
            found_behind = False
            for _ in range(8):
                if not cur:
                    break
                if cur == int(workerw_in_progman):
                    found_behind = True
                    break
                cur = int(u32.GetWindow(cur, GW_HWNDNEXT) or 0)
            if not found_behind:
                return False
        return True

    if _is_win11_24h2_or_newer():
        # On 24H2 without DefView (mid Explorer restart), do not touch anything right now
        return True

    parent_cls = _win_class_fast(cur_parent)
    return cur_parent != 0 and parent_cls in ("WorkerW", "Progman")


def ensure_wallpaper_pinned() -> bool:
    """Lightweight periodic read-only health check — does nothing when already properly pinned."""
    if os.name != "nt" or _U32 is None:
        return False
    if not _WALLPAPER_LOCK.acquire(blocking=False):
        return True
    try:
        raw = _get_mem_state()
        if not raw.get("active"):
            return False

        saved_pid = int(raw.get("pid") or 0)
        hwnd = int(raw.get("hwnd") or 0)
        if not _is_verified_wallpaper_hwnd(hwnd, expected_pid=saved_pid):
            found_all = _find_wallpaper_hwnds(expected_pid=saved_pid)
            if not found_all and saved_pid > 0:
                found_all = _find_wallpaper_hwnds(expected_pid=0)
            if not found_all:
                raw["active"] = False
                raw["hwnd"] = 0
                raw["pid"] = 0
                _save_state_raw(raw)
                stop_input_observer()
                return False
            hwnd = found_all[0]
            raw["hwnd"] = hwnd
            raw["pid"] = _get_hwnd_pid(hwnd) or saved_pid
            _save_state_raw(raw)

        progman = _U32.FindWindowW("Progman", None)
        if not progman or _U32.IsHungAppWindow(progman):
            return False

        metrics = _get_primary_screen_metrics()
        if _is_already_pinned_readonly(hwnd, metrics["phys_w"], metrics["phys_h"]):
            return True

        ok, _ = _apply_wallpaper_styles_and_zorder(
            hwnd, metrics["phys_w"], metrics["phys_h"], initial_attach=False
        )
        return ok
    finally:
        _WALLPAPER_LOCK.release()


def get_wallpaper_status() -> dict[str, Any]:
    with _WALLPAPER_LOCK:
        raw = _get_mem_state()
        saved_h = int(raw.get("hwnd") or 0)
        saved_pid = int(raw.get("pid") or 0)
        verified_h = 0
        if saved_h and _is_verified_wallpaper_hwnd(saved_h, expected_pid=saved_pid):
            verified_h = saved_h
        elif raw.get("active"):
            found = _find_wallpaper_hwnds(expected_pid=saved_pid)
            if not found and saved_pid > 0:
                found = _find_wallpaper_hwnds(expected_pid=0)
            if found:
                verified_h = found[0]

        is_live = bool(verified_h) and bool(raw.get("active", False))
        if raw.get("active") and not verified_h:
            raw["active"] = False
            raw["hwnd"] = 0
            raw["pid"] = 0
            _save_state_raw(raw)
            stop_input_observer()
        return {
            "type": "ophanim_wallpaper_status",
            "ok": True,
            "active": is_live,
            "wallpaperMode": str(raw.get("wallpaperMode") or "agy_live"),
            "beamMode": str(raw.get("beamMode") or "tool_io"),
            "hwnd": verified_h if is_live else 0,
            "arch": str(raw.get("arch") or ""),
            "originalWallpaper": str(raw.get("originalWallpaperPath") or ""),
        }


def enable_live_wallpaper(
    host: str = "127.0.0.1",
    port: int = 18790,
    wallpaper_mode: str = "agy_live",
    beam_mode: str = "tool_io",
) -> dict[str, Any]:
    global _WALLPAPER_GEN, _ACTIVE_JOB_HANDLE, _OWNED_BY_THIS_PROCESS
    if os.name != "nt" or _U32 is None:
        return {"type": "ophanim_wallpaper_status", "ok": False, "active": False, "error": "仅支持 Windows 桌面环境"}

    with _WALLPAPER_LOCK:
        _WALLPAPER_GEN += 1
        my_gen = _WALLPAPER_GEN

        wp_mode = "ambient_eco" if wallpaper_mode == "ambient_eco" else "agy_live"
        eff_beam = (
            "ambient"
            if wp_mode == "ambient_eco"
            else (beam_mode if beam_mode in ("tool_io", "model_active", "ambient") else "tool_io")
        )

        # Pre-flight Progman health check BEFORE launching any kiosk browser!
        progman = _U32.FindWindowW("Progman", None)
        if not progman or not _is_window_responsive(progman, timeout_ms=250):
            return {
                "type": "ophanim_wallpaper_status",
                "ok": False,
                "active": False,
                "error": "Windows 桌面管理器 (Progman) 当前未响应，已安全取消壁纸启动",
            }
        if _is_win11_24h2_or_newer() and not _U32.FindWindowExW(progman, None, "SHELLDLL_DefView", None):
            return {
                "type": "ophanim_wallpaper_status",
                "ok": False,
                "active": False,
                "error": "Win11 24H2 桌面图标层 (SHELLDLL_DefView) 未就绪，请稍后重试",
            }

        prev_state = _get_mem_state()
        orig_wp = str(prev_state.get("originalWallpaperPath") or "").strip()
        if not prev_state.get("active") or not orig_wp or not Path(orig_wp).is_file():
            detected_wp = _read_current_system_wallpaper()
            if detected_wp:
                orig_wp = detected_wp

        # Clean up any previous wallpaper instance and confirm exit before writing Preferences
        _detach_and_close_existing_wallpaper(restore_static=False, allow_wmi_fallback=True)

        kind, browser_bin = _find_chromium_binary()
        if not browser_bin:
            return {
                "type": "ophanim_wallpaper_status",
                "ok": False,
                "active": False,
                "error": "未找到本地 Edge 或 Chrome 浏览器",
            }

        metrics = _get_primary_screen_metrics()
        WALLPAPER_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        WALLPAPER_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _preset_wallpaper_profile_prefs(metrics)

        eco_flag = "1" if wp_mode == "ambient_eco" else "0"
        target_url = (
            f"http://{host}:{port}/ophanim_sanctum.html"
            f"?ws=ws://{host}:{port}/ws&wallpaper=1&wpMode={wp_mode}&beamMode={eff_beam}&eco={eco_flag}&t={int(time.time())}"
        )

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

        job_handle = _create_wallpaper_job()
        _ACTIVE_JOB_HANDLE = job_handle
        try:
            proc = subprocess.Popen(
                args,
                cwd=str(PROJECT_DIR),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as exc:
            _terminate_and_close_job()
            return {
                "type": "ophanim_wallpaper_status",
                "ok": False,
                "active": False,
                "error": f"启动壁纸浏览器失败: {exc}",
            }

        if job_handle:
            _assign_pid_to_job(job_handle, proc.pid)

        # Wait up to 7.0s for the verified 'OPHANIM WALLPAPER' window to appear
        wp_hwnd = 0
        deadline = time.monotonic() + 7.0
        while time.monotonic() < deadline:
            found = _find_wallpaper_hwnds(expected_pid=proc.pid)
            if not found:
                found = _find_wallpaper_hwnds(expected_pid=0)
            if found:
                wp_hwnd = found[0]
                break
            time.sleep(0.06)

        if not wp_hwnd:
            _kill_wallpaper_browser_processes(tracked_pids=[proc.pid], allow_wmi_fallback=True)
            _save_state_raw({
                "active": False,
                "pid": 0,
                "hwnd": 0,
                "wallpaperMode": wp_mode,
                "beamMode": eff_beam,
                "originalWallpaperPath": orig_wp,
            })
            return {
                "type": "ophanim_wallpaper_status",
                "ok": False,
                "active": False,
                "error": "未能捕获壁纸渲染窗口句柄（请确认通过桌面 Ophanim_Sanctum.bat 启动）",
            }

        win_pid = _get_hwnd_pid(wp_hwnd) or proc.pid
        if job_handle and win_pid != proc.pid:
            _assign_pid_to_job(job_handle, win_pid)

        ok, arch = _apply_wallpaper_styles_and_zorder(
            wp_hwnd, metrics["phys_w"], metrics["phys_h"], initial_attach=True
        )
        if not ok:
            try:
                _U32.ShowWindowAsync(wp_hwnd, SW_HIDE)
            except Exception:
                pass
            _kill_wallpaper_browser_processes(tracked_pids=[win_pid, proc.pid], allow_wmi_fallback=True)
            _save_state_raw({
                "active": False,
                "pid": 0,
                "hwnd": 0,
                "wallpaperMode": wp_mode,
                "beamMode": eff_beam,
                "originalWallpaperPath": orig_wp,
            })
            return {"type": "ophanim_wallpaper_status", "ok": False, "active": False, "error": arch}

        new_state = {
            "active": True,
            "pid": win_pid,
            "launchPid": proc.pid,
            "hwnd": wp_hwnd,
            "arch": arch,
            "wallpaperMode": wp_mode,
            "beamMode": eff_beam,
            "originalWallpaperPath": orig_wp,
            "activatedAt": int(time.time()),
        }
        _save_state_raw(new_state)
        _OWNED_BY_THIS_PROCESS = True
        _PTR_CACHE["hwnd"] = wp_hwnd
        _PTR_CACHE["pid"] = win_pid
        _PTR_CACHE["phys_w"] = metrics["phys_w"]
        _PTR_CACHE["phys_h"] = metrics["phys_h"]
        _PTR_CACHE["last_hwnd_check_mono"] = time.monotonic()

        start_input_observer()

        # Chromium's kiosk startup may fire delayed SetWindowPos ~200-1500ms after first paint; re-pin only if drifted
        def _delayed_repin(h_target: int, pid_target: int, pw: int, ph: int, gen_id: int) -> None:
            for delay_s in (0.25, 0.65, 1.35, 2.4):
                time.sleep(delay_s)
                with _WALLPAPER_LOCK:
                    if gen_id != _WALLPAPER_GEN:
                        return
                    st_now = _get_mem_state()
                    if not st_now.get("active") or int(st_now.get("hwnd") or 0) != h_target:
                        return
                    if not _is_verified_wallpaper_hwnd(h_target, expected_pid=pid_target):
                        return
                    try:
                        if not _is_already_pinned_readonly(h_target, pw, ph):
                            _apply_wallpaper_styles_and_zorder(h_target, pw, ph, initial_attach=False)
                    except Exception:
                        return

        threading.Thread(
            target=_delayed_repin,
            args=(wp_hwnd, win_pid, metrics["phys_w"], metrics["phys_h"], my_gen),
            name="ophanim-wp-repin",
            daemon=True,
        ).start()

        logger.info(
            "Enabled Ophanim live wallpaper: hwnd=%s pid=%s arch=%s mode=%s beam=%s",
            wp_hwnd,
            win_pid,
            arch,
            wp_mode,
            eff_beam,
        )
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


def _detach_and_close_existing_wallpaper(
    restore_static: bool = True,
    allow_wmi_fallback: bool = False,
) -> str:
    """
    Safely hide & terminate verified wallpaper browser processes WITHOUT calling
    `SPI_SETDESKWALLPAPER`, `SetParent(h, None)`, or synchronous `RDW_UPDATENOW`.
    """
    if os.name != "nt" or _U32 is None:
        return ""
    u32 = _U32
    stop_input_observer()

    state = _get_mem_state()
    orig_wp = str(state.get("originalWallpaperPath") or "").strip()
    saved_h = int(state.get("hwnd") or 0)
    saved_pid = int(state.get("pid") or 0)
    launch_pid = int(state.get("launchPid") or 0)

    hwnds = _find_wallpaper_hwnds(expected_pid=0)
    if saved_h and saved_h not in hwnds and _is_verified_wallpaper_hwnd(saved_h, expected_pid=saved_pid):
        hwnds.append(saved_h)

    pids_to_kill: list[int] = []
    for p in (saved_pid, launch_pid):
        if p > 0 and p not in pids_to_kill:
            pids_to_kill.append(p)

    for h in hwnds:
        try:
            wp_pid = _get_hwnd_pid(h)
            if wp_pid > 0 and wp_pid not in pids_to_kill:
                pids_to_kill.append(wp_pid)
            # Hide asynchronously; NEVER call SetParent(h, None) before killing!
            u32.ShowWindowAsync(h, SW_HIDE)
        except Exception:
            pass

    _kill_wallpaper_browser_processes(tracked_pids=pids_to_kill, allow_wmi_fallback=allow_wmi_fallback)

    if restore_static:
        progman = u32.FindWindowW("Progman", None)
        if progman and not u32.IsHungAppWindow(progman):
            try:
                # Asynchronous invalidation ONLY (0x0085 = RDW_INVALIDATE|RDW_ERASE|RDW_ALLCHILDREN, NO RDW_UPDATENOW!)
                u32.RedrawWindow(progman, None, None, RDW_ASYNC_REFRESH)
                workerw = u32.FindWindowExW(progman, None, "WorkerW", None)
                if workerw and not u32.IsHungAppWindow(workerw):
                    u32.ShowWindowAsync(workerw, SW_SHOW)
                    u32.RedrawWindow(workerw, None, None, RDW_ASYNC_REFRESH)
            except Exception as exc:
                logger.debug("Async desktop refresh warning: %s", exc)

    return orig_wp


def disable_live_wallpaper() -> dict[str, Any]:
    global _WALLPAPER_GEN, _OWNED_BY_THIS_PROCESS
    if os.name != "nt":
        return {"type": "ophanim_wallpaper_status", "ok": False, "active": False}
    with _WALLPAPER_LOCK:
        _WALLPAPER_GEN += 1
        _OWNED_BY_THIS_PROCESS = False
        stop_input_observer()
        _PTR_CACHE["hwnd"] = 0
        _PTR_CACHE["pid"] = 0
        _PTR_CACHE["prev_btn"] = 0
        _PTR_CACHE["latched_on_icon"] = False

        prev = _get_mem_state()
        prev["active"] = False
        restored_path = _detach_and_close_existing_wallpaper(restore_static=True, allow_wmi_fallback=False)
        prev["hwnd"] = 0
        prev["pid"] = 0
        prev["launchPid"] = 0
        _save_state_raw(prev)
        logger.info("Disabled Ophanim live wallpaper; preserved static wallpaper=%r", restored_path)
        return {
            "type": "ophanim_wallpaper_status",
            "ok": True,
            "active": False,
            "wallpaperMode": str(prev.get("wallpaperMode") or "agy_live"),
            "beamMode": str(prev.get("beamMode") or "tool_io"),
            "hwnd": 0,
            "originalWallpaper": restored_path,
        }


def shutdown_wallpaper_runtime(*, only_if_owned: bool = False) -> None:
    """Cleanly terminate wallpaper browser Job Object, Raw Input observer, and STA COM worker on daemon exit."""
    global _WALLPAPER_GEN, _OWNED_BY_THIS_PROCESS
    with _WALLPAPER_LOCK:
        _WALLPAPER_GEN += 1
        stop_input_observer(timeout=1.5)
        _ICON_HIT_TESTER.stop()
        should_disable = bool(_OWNED_BY_THIS_PROCESS or _ACTIVE_JOB_HANDLE)
        if not only_if_owned and not should_disable:
            should_disable = bool(_get_mem_state().get("active"))
        if should_disable:
            try:
                disable_live_wallpaper()
            except Exception:
                _OWNED_BY_THIS_PROCESS = False
                _terminate_and_close_job()
        else:
            _terminate_and_close_job()


atexit.register(shutdown_wallpaper_runtime, only_if_owned=True)


# ============================================================================
# Safe Non-Blocking Desktop Icon Hit-Tester (Dedicated STA COM Thread + Timeout)
# ============================================================================

class _DesktopIconHitTester:
    """Dedicated STA COM worker executing `AccessibleObjectFromPoint` with <=150ms timeout & circuit-breaker."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._req_evt = threading.Event()
        self._res_evt = threading.Event()
        self._stop_evt = threading.Event()
        self._thread: threading.Thread | None = None
        self._busy: bool = False
        self._req_pt: tuple[int, int] = (0, 0)
        self._res_val: bool = False
        self._tripped_until: float = 0.0

    def _ensure_started(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_evt.clear()
        self._thread = threading.Thread(target=self._sta_loop, name="ophanim-sta-hit", daemon=True)
        self._thread.start()

    def _sta_loop(self) -> None:
        should_uninit = False
        if _OLE32 is not None:
            try:
                hr = int(_OLE32.CoInitializeEx(None, COINIT_APARTMENTTHREADED))
                should_uninit = hr in (0, 1)
            except Exception:
                pass
        try:
            while not self._stop_evt.is_set():
                if not self._req_evt.wait(timeout=0.5):
                    continue
                if self._stop_evt.is_set():
                    break
                px, py = self._req_pt
                self._req_evt.clear()
                hit = self._do_hit_test(POINT(px, py))
                self._res_val = hit
                self._busy = False
                self._res_evt.set()
        finally:
            if should_uninit and _OLE32 is not None:
                try:
                    _OLE32.CoUninitialize()
                except Exception:
                    pass

    @staticmethod
    def _do_hit_test(pt: POINT) -> bool:
        if _OLEACC is None or _OLEAUT32 is None:
            return False
        pacc = ctypes.c_void_p(0)
        var_child = VARIANT()
        try:
            hr = int(_OLEACC.AccessibleObjectFromPoint(pt, ctypes.byref(pacc), ctypes.byref(var_child)))
            return bool(hr == 0 and var_child.vt == 3 and int(var_child.u.lVal) > 0)
        except Exception:
            return False
        finally:
            if pacc.value:
                _release_com_unknown(int(pacc.value))
            try:
                _OLEAUT32.VariantClear(ctypes.byref(var_child))
            except Exception:
                pass

    def query(self, pt: POINT, hwnd_at: int, cls_at: str, timeout_s: float = 0.14) -> bool:
        if os.name != "nt" or _U32 is None or _OLEACC is None or _OLEAUT32 is None:
            return False
        if cls_at != "SysListView32":
            return False
        now = time.monotonic()
        if now < self._tripped_until:
            return True

        progman = _U32.FindWindowW("Progman", None)
        if progman and _U32.IsHungAppWindow(progman):
            self._tripped_until = now + 5.0
            return True
        if not _is_window_responsive(hwnd_at, timeout_ms=80):
            self._tripped_until = now + 5.0
            return True

        with self._lock:
            if self._busy:
                self._tripped_until = now + 5.0
                return True
            self._ensure_started()
            self._busy = True
            self._req_pt = (int(pt.x), int(pt.y))
            self._res_evt.clear()
            self._req_evt.set()
            if self._res_evt.wait(timeout=min(0.15, max(0.05, timeout_s))):
                return bool(self._res_val)
            self._tripped_until = time.monotonic() + 5.0
            return True

    def stop(self) -> None:
        self._stop_evt.set()
        self._req_evt.set()
        t = self._thread
        self._thread = None
        if t is not None and t.is_alive():
            t.join(timeout=0.6)


_ICON_HIT_TESTER = _DesktopIconHitTester()


def _is_point_on_desktop_icon(pt: POINT, hwnd_at: int = 0, cls_at: str = "") -> bool:
    """Return True iff `pt` hits an actual desktop shortcut item on SysListView32 (non-blocking STA COM)."""
    if not cls_at and hwnd_at:
        cls_at = _win_class_fast(hwnd_at)
    return _ICON_HIT_TESTER.query(pt, hwnd_at, cls_at, timeout_s=0.14)


# ============================================================================
# Asynchronous Win32 Raw Input Observer (Zero WH_MOUSE_LL, Clean Lifecycle)
# ============================================================================

_INPUT_LOCK = threading.Lock()
_WHEEL_ACCUM_STEPS: float = 0.0
_CLICK_PENDING: bool = False
_LDOWN_PT: tuple[int, int, float] | None = None

_RAWINPUT_CTRL_LOCK = threading.Lock()
_RAWINPUT_THREAD: threading.Thread | None = None
_RAWINPUT_HWND: int = 0
_RAWINPUT_TID: int = 0
_RAWINPUT_CLASS_NAME: str = ""
_RAWINPUT_WNDPROC_REF: Any = None
_RAWINPUT_READY_EVT: threading.Event | None = None


def is_input_observer_running() -> bool:
    with _RAWINPUT_CTRL_LOCK:
        return bool(_RAWINPUT_THREAD is not None and _RAWINPUT_THREAD.is_alive() and _RAWINPUT_HWND)


def start_input_observer() -> bool:
    """Start asynchronous Win32 Raw Input (`RIDEV_INPUTSINK`) on a hidden `HWND_MESSAGE` window."""
    global _RAWINPUT_THREAD, _RAWINPUT_READY_EVT
    if os.name != "nt" or _U32 is None or _K32 is None:
        return False
    with _RAWINPUT_CTRL_LOCK:
        if _RAWINPUT_THREAD is not None and _RAWINPUT_THREAD.is_alive():
            return bool(_RAWINPUT_HWND)
        ready_evt = threading.Event()
        _RAWINPUT_READY_EVT = ready_evt
        t = threading.Thread(
            target=_raw_input_worker,
            args=(ready_evt,),
            name="ophanim-wp-rawinput",
            daemon=True,
        )
        _RAWINPUT_THREAD = t
        t.start()
    ready_evt.wait(timeout=1.5)
    return is_input_observer_running()


def stop_input_observer(timeout: float = 2.0) -> None:
    """Unregister Raw Input (`RIDEV_REMOVE`), destroy hidden message window, and join thread cleanly."""
    global _RAWINPUT_THREAD, _RAWINPUT_HWND, _RAWINPUT_TID, _RAWINPUT_WNDPROC_REF
    if os.name != "nt" or _U32 is None:
        return
    with _RAWINPUT_CTRL_LOCK:
        t = _RAWINPUT_THREAD
        hwnd = _RAWINPUT_HWND
        tid = _RAWINPUT_TID

    if hwnd:
        try:
            _U32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
        except Exception:
            pass
    if tid:
        try:
            _U32.PostThreadMessageW(tid, WM_QUIT, 0, 0)
        except Exception:
            pass

    if t is not None and t.is_alive() and t is not threading.current_thread():
        t.join(timeout=max(0.2, float(timeout)))

    with _RAWINPUT_CTRL_LOCK:
        if _RAWINPUT_THREAD is t and (t is None or not t.is_alive()):
            _RAWINPUT_THREAD = None
            _RAWINPUT_HWND = 0
            _RAWINPUT_TID = 0
            _RAWINPUT_WNDPROC_REF = None

    with _INPUT_LOCK:
        global _WHEEL_ACCUM_STEPS, _CLICK_PENDING, _LDOWN_PT
        _WHEEL_ACCUM_STEPS = 0.0
        _CLICK_PENDING = False
        _LDOWN_PT = None


def _raw_input_worker(ready_evt: threading.Event) -> None:
    global _RAWINPUT_HWND, _RAWINPUT_TID, _RAWINPUT_CLASS_NAME, _RAWINPUT_WNDPROC_REF
    global _WHEEL_ACCUM_STEPS, _CLICK_PENDING, _LDOWN_PT

    u32 = _U32
    k32 = _K32
    if u32 is None or k32 is None:
        ready_evt.set()
        return

    hinst = k32.GetModuleHandleW(None)
    cls_name = f"OphanimRawInputSink_{os.getpid()}_{time.time_ns()}"
    registered_rid = False

    def _unregister_mouse_rid() -> None:
        nonlocal registered_rid
        if not registered_rid:
            return
        registered_rid = False
        rid_rem = RAWINPUTDEVICE(
            usUsagePage=0x01,
            usUsage=0x02,
            dwFlags=RIDEV_REMOVE,
            hwndTarget=None,
        )
        try:
            u32.RegisterRawInputDevices(ctypes.byref(rid_rem), 1, ctypes.sizeof(RAWINPUTDEVICE))
        except Exception:
            pass

    def _wnd_proc(hwnd: int, msg: int, wparam: int, lparam: int) -> int:
        global _WHEEL_ACCUM_STEPS, _CLICK_PENDING, _LDOWN_PT
        if msg == WM_INPUT and lparam:
            try:
                raw_buf = RAWINPUT_MOUSE()
                sz = wintypes.UINT(ctypes.sizeof(raw_buf))
                got = int(
                    u32.GetRawInputData(
                        ctypes.c_void_p(lparam),
                        RID_INPUT,
                        ctypes.byref(raw_buf),
                        ctypes.byref(sz),
                        ctypes.sizeof(RAWINPUTHEADER),
                    )
                )
                if got != 0xFFFFFFFF and raw_buf.header.dwType == RIM_TYPEMOUSE:
                    bflags = int(raw_buf.mouse.buttons.s.usButtonFlags)
                    bdata = int(raw_buf.mouse.buttons.s.usButtonData)

                    if bflags & RI_MOUSE_WHEEL:
                        if int(u32.GetAsyncKeyState(0x04)) & 0x8000:
                            raw_delta = ctypes.c_short(bdata).value
                            if raw_delta:
                                with _INPUT_LOCK:
                                    _WHEEL_ACCUM_STEPS = max(
                                        -12.0, min(12.0, _WHEEL_ACCUM_STEPS + (raw_delta / 120.0))
                                    )

                    swapped = bool(u32.GetSystemMetrics(23))
                    down_mask = RI_MOUSE_RIGHT_BUTTON_DOWN if swapped else RI_MOUSE_LEFT_BUTTON_DOWN
                    up_mask = RI_MOUSE_RIGHT_BUTTON_UP if swapped else RI_MOUSE_LEFT_BUTTON_UP

                    if bflags & down_mask:
                        pt = POINT()
                        if u32.GetCursorPos(ctypes.byref(pt)):
                            with _INPUT_LOCK:
                                _LDOWN_PT = (int(pt.x), int(pt.y), time.monotonic())
                    if bflags & up_mask:
                        pt = POINT()
                        if u32.GetCursorPos(ctypes.byref(pt)):
                            with _INPUT_LOCK:
                                if _LDOWN_PT is not None:
                                    dx = int(pt.x) - _LDOWN_PT[0]
                                    dy = int(pt.y) - _LDOWN_PT[1]
                                    dt_click = time.monotonic() - _LDOWN_PT[2]
                                    _LDOWN_PT = None
                                    if (dx * dx + dy * dy) <= 100 and dt_click <= 0.70:
                                        _CLICK_PENDING = True
            except Exception:
                pass
            return 0
        if msg == WM_CLOSE:
            _unregister_mouse_rid()
            u32.DestroyWindow(hwnd)
            return 0
        if msg == WM_DESTROY:
            _unregister_mouse_rid()
            u32.PostQuitMessage(0)
            return 0
        return int(u32.DefWindowProcW(hwnd, msg, wparam, lparam))

    wndproc_cb = WNDPROC_TYPE(_wnd_proc)
    wc = WNDCLASSEXW()
    wc.cbSize = ctypes.sizeof(WNDCLASSEXW)
    wc.lpfnWndProc = wndproc_cb
    wc.hInstance = hinst
    wc.lpszClassName = cls_name

    atom = u32.RegisterClassExW(ctypes.byref(wc))
    if not atom:
        ready_evt.set()
        return

    hwnd_msg = u32.CreateWindowExW(
        0,
        cls_name,
        "OphanimRawInputSink",
        0,
        0,
        0,
        0,
        0,
        wintypes.HWND(-3),  # HWND_MESSAGE
        None,
        hinst,
        None,
    )
    if not hwnd_msg:
        u32.UnregisterClassW(cls_name, hinst)
        ready_evt.set()
        return

    rid = RAWINPUTDEVICE(
        usUsagePage=0x01,  # Generic Desktop Controls
        usUsage=0x02,      # Mouse
        dwFlags=RIDEV_INPUTSINK,
        hwndTarget=hwnd_msg,
    )
    if not u32.RegisterRawInputDevices(ctypes.byref(rid), 1, ctypes.sizeof(RAWINPUTDEVICE)):
        u32.DestroyWindow(hwnd_msg)
        u32.UnregisterClassW(cls_name, hinst)
        ready_evt.set()
        return
    registered_rid = True

    tid = int(k32.GetCurrentThreadId())
    with _RAWINPUT_CTRL_LOCK:
        _RAWINPUT_HWND = int(hwnd_msg)
        _RAWINPUT_TID = tid
        _RAWINPUT_CLASS_NAME = cls_name
        _RAWINPUT_WNDPROC_REF = wndproc_cb

    ready_evt.set()

    msg = wintypes.MSG()
    try:
        while u32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            u32.TranslateMessage(ctypes.byref(msg))
            u32.DispatchMessageW(ctypes.byref(msg))
    finally:
        _unregister_mouse_rid()
        try:
            if u32.IsWindow(hwnd_msg):
                u32.DestroyWindow(hwnd_msg)
        except Exception:
            pass
        try:
            u32.UnregisterClassW(cls_name, hinst)
        except Exception:
            pass
        with _RAWINPUT_CTRL_LOCK:
            if _RAWINPUT_HWND == int(hwnd_msg):
                _RAWINPUT_HWND = 0
                _RAWINPUT_TID = 0
                _RAWINPUT_CLASS_NAME = ""
                _RAWINPUT_WNDPROC_REF = None


def _pop_input_events() -> tuple[float, bool]:
    global _WHEEL_ACCUM_STEPS, _CLICK_PENDING
    with _INPUT_LOCK:
        val = _WHEEL_ACCUM_STEPS
        clk = _CLICK_PENDING
        _WHEEL_ACCUM_STEPS = 0.0
        _CLICK_PENDING = False
    return val, clk


# ============================================================================
# Desktop Occlusion Detection & Pointer Sampling (Zero Disk Polling)
# ============================================================================

_PTR_CACHE: dict[str, Any] = {
    "last_hwnd_check_mono": 0.0,
    "hwnd": 0,
    "pid": 0,
    "phys_w": 1920,
    "phys_h": 1080,
    "prev_btn": 0,
    "latched_on_icon": False,
}

_DESKTOP_SHELL_CLASSES = {
    "Progman",
    "WorkerW",
    "Shell_TrayWnd",
    "Shell_SecondaryTrayWnd",
    "NotifyIconOverflowWindow",
}


def is_desktop_occluded() -> bool:
    """
    Return True when the primary Windows desktop is covered (>=95% of primary work area)
    by a fullscreen/D3D/presentation app or maximized/opaque foreground application window.
    """
    if os.name != "nt" or _U32 is None:
        return False

    # 1. Fast Shell check for fullscreen apps, D3D games, or presentation mode
    if _SHELL32 is not None and hasattr(_SHELL32, "SHQueryUserNotificationState"):
        try:
            state = ctypes.c_int(0)
            hr = int(_SHELL32.SHQueryUserNotificationState(ctypes.byref(state)))
            if hr == 0 and int(state.value) in (QUNS_BUSY, QUNS_RUNNING_D3D_FULL_SCREEN, QUNS_PRESENTATION_MODE):
                return True
        except Exception:
            pass

    # 2. Check foreground non-desktop, non-taskbar window coverage of primary work area
    try:
        u32 = _U32
        fg = int(u32.GetForegroundWindow() or 0)
        if not fg or not u32.IsWindowVisible(fg) or u32.IsIconic(fg):
            return False

        wp_hwnd = int(_PTR_CACHE.get("hwnd") or 0)
        if wp_hwnd and fg == wp_hwnd:
            return False

        cls = _win_class_fast(fg)
        if cls in _DESKTOP_SHELL_CLASSES:
            return False

        fg_rc = RECT()
        if not u32.GetWindowRect(fg, ctypes.byref(fg_rc)):
            return False

        hmon = u32.MonitorFromPoint(POINT(0, 0), MONITOR_DEFAULTTOPRIMARY)
        if not hmon:
            return False
        mi = MONITORINFO()
        mi.cbSize = ctypes.sizeof(MONITORINFO)
        if not u32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
            return False

        work = mi.rcWork
        work_w = max(1, int(work.right - work.left))
        work_h = max(1, int(work.bottom - work.top))
        inter_w = max(0, min(int(fg_rc.right), int(work.right)) - max(int(fg_rc.left), int(work.left)))
        inter_h = max(0, min(int(fg_rc.bottom), int(work.bottom)) - max(int(fg_rc.top), int(work.top)))
        coverage = float(inter_w * inter_h) / float(work_w * work_h)
        return coverage >= 0.95
    except Exception:
        return False


def sample_desktop_pointer() -> dict[str, Any] | None:
    """Sample live desktop cursor & button state purely from in-memory state + async Raw Input."""
    if os.name != "nt" or _U32 is None:
        return None
    u32 = _U32
    now_m = time.monotonic()

    wp_hwnd = int(_PTR_CACHE.get("hwnd") or 0)
    wp_pid = int(_PTR_CACHE.get("pid") or 0)
    if (now_m - float(_PTR_CACHE.get("last_hwnd_check_mono") or 0.0)) >= 2.0 or not wp_hwnd or not u32.IsWindow(wp_hwnd):
        _PTR_CACHE["last_hwnd_check_mono"] = now_m
        st = _get_mem_state()
        if not st.get("active"):
            _PTR_CACHE["hwnd"] = 0
            _PTR_CACHE["pid"] = 0
            _PTR_CACHE["prev_btn"] = 0
            _PTR_CACHE["latched_on_icon"] = False
            if is_input_observer_running():
                stop_input_observer(timeout=1.0)
            return None
        cand_h = int(st.get("hwnd") or 0)
        cand_pid = int(st.get("pid") or 0)
        if not _is_verified_wallpaper_hwnd(cand_h, expected_pid=cand_pid):
            found = _find_wallpaper_hwnds(expected_pid=cand_pid)
            if not found and cand_pid > 0:
                found = _find_wallpaper_hwnds(expected_pid=0)
            cand_h = found[0] if found else 0
            cand_pid = _get_hwnd_pid(cand_h) if cand_h else 0
        _PTR_CACHE["hwnd"] = cand_h
        _PTR_CACHE["pid"] = cand_pid
        wp_hwnd = cand_h
        wp_pid = cand_pid
        pw = int(u32.GetSystemMetrics(0)) or 1920
        ph = int(u32.GetSystemMetrics(1)) or 1080
        _PTR_CACHE["phys_w"] = pw
        _PTR_CACHE["phys_h"] = ph

    if not wp_hwnd:
        return None

    if not is_input_observer_running():
        start_input_observer()

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

    hwnd_at = int(u32.WindowFromPoint(pt) or 0)
    cls_at = ""
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
        _PTR_CACHE["latched_on_icon"] = (
            _is_point_on_desktop_icon(pt, hwnd_at, cls_at) if (on_desktop and cls_at == "SysListView32") else False
        )
        was_on_icon = bool(_PTR_CACHE["latched_on_icon"])
    elif not (btn & 1):
        _PTR_CACHE["latched_on_icon"] = False
    _PTR_CACHE["prev_btn"] = btn

    wheel_raw, click_raw = _pop_input_events()
    wheel_steps = round(wheel_raw, 3) if (on_desktop and (btn & 4) and abs(wheel_raw) > 0.01) else 0.0
    click_on_bg = False
    if click_raw and on_desktop:
        hit_icon_now = was_on_icon or (
            _is_point_on_desktop_icon(pt, hwnd_at, cls_at) if cls_at == "SysListView32" else False
        )
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
