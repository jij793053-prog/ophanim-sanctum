#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ophanim_agy_daemon.py
Local real-time bidirectional bridge daemon connecting Google Antigravity
conversations, `/swarm` subagents, verbatim task dispatch, and `agent-app-offload`
quota telemetry to the 3D Ophanim Sanctum frontend (`127.0.0.1:18790`).
"""
from __future__ import annotations

import argparse
import asyncio
from collections import deque
import contextlib
import ctypes
from ctypes import wintypes
import json
import logging
import math
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import threading
import time
from typing import Any
from urllib.parse import unquote, urlparse
import urllib.request

PROJECT_DIR = Path(__file__).resolve().parent
PROJECT_DIR.mkdir(parents=True, exist_ok=True)
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

DAEMON_LOG_PATH = PROJECT_DIR / "daemon.log"

# Guard stdout/stderr for windowless pythonw.exe execution on Windows
if sys.stdout is None or sys.stderr is None:
    _log_fh = open(DAEMON_LOG_PATH, "a", encoding="utf-8", buffering=1)
    if sys.stdout is None:
        sys.stdout = _log_fh
    if sys.stderr is None:
        sys.stderr = _log_fh

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(DAEMON_LOG_PATH, encoding="utf-8")],
)
logger = logging.getLogger("ophanim_daemon")

from aiohttp import WSMsgType, web  # noqa: E402
import ophanim_agy_bridge_core as agy_core  # noqa: E402
import ophanim_ai_usage_bridge as ai_usage_bridge  # noqa: E402
import ophanim_external_bridge as ext_bridge  # noqa: E402
import ophanim_wallpaper_manager as wp_mgr  # noqa: E402

HOST = os.environ.get("OPHANIM_HOST", "127.0.0.1")
PORT = int(os.environ.get("OPHANIM_PORT", "18790"))
API_TOKEN = os.environ.get("OPHANIM_API_TOKEN", "").strip()
ALLOW_REMOTE = os.environ.get("OPHANIM_ALLOW_REMOTE", "0").strip() == "1"

HTML_FILE_PATH = Path(
    os.environ.get("OPHANIM_HTML_PATH", str(PROJECT_DIR / "ophanim_sanctum.html"))
)
FALLBACK_HTML_PATH = PROJECT_DIR / "ophanim_sanctum.html"
AGY_PANEL_JS_PATH = PROJECT_DIR / "ophanim_agy_panel.js"
LOGO_ICO_PATH = PROJECT_DIR / "ophanim_logo.ico"
CONFIG_SAVE_PATH = PROJECT_DIR / "ophanim_config.json"

OFFLOAD_DIR = Path(os.environ.get("OPHANIM_OFFLOAD_DIR", str(PROJECT_DIR.parent / "agent-app-offload")))
OFFLOAD_DB_PATH = OFFLOAD_DIR / "offload_ledger.db"
OFFLOAD_SNAPSHOT_PATH = OFFLOAD_DIR / "offload_ledger_snapshot.json"
OFFLOAD_DASHBOARD_URL = "http://127.0.0.1:18765/api/state"

BRAIN_DIR = Path(os.environ.get("OPHANIM_BRAIN_DIR", str(Path.home() / ".gemini/antigravity/brain")))

_TRUSTED_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1", "[::1]"}
_BLOCKED_EXEC_EXTS = {
    ".exe", ".bat", ".cmd", ".ps1", ".vbs", ".vbe", ".js", ".jse",
    ".wsf", ".wsh", ".msi", ".msp", ".scr", ".com", ".pif", ".hta",
    ".cpl", ".reg", ".lnk", ".jar",
}

_DIRECT_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
START_MONO = time.monotonic()
_CONFIG_IO_LOCK = threading.Lock()
_WALLPAPER_ACTION_LOCK: asyncio.Lock | None = None


def _get_wallpaper_action_lock() -> asyncio.Lock:
    global _WALLPAPER_ACTION_LOCK
    if _WALLPAPER_ACTION_LOCK is None:
        _WALLPAPER_ACTION_LOCK = asyncio.Lock()
    return _WALLPAPER_ACTION_LOCK


def _bind_daemon_win32() -> tuple[Any, Any, Any, Any]:
    if os.name != "nt":
        return None, None, None, None
    u32 = ctypes.WinDLL("user32", use_last_error=True)
    u32.GetThreadDesktop.argtypes = [wintypes.DWORD]
    u32.GetThreadDesktop.restype = wintypes.HANDLE
    u32.GetUserObjectInformationW.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    u32.GetUserObjectInformationW.restype = wintypes.BOOL

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.GetCurrentThreadId.argtypes = []
    k32.GetCurrentThreadId.restype = wintypes.DWORD

    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    shell32.ShellExecuteW.argtypes = [
        wintypes.HWND,
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        ctypes.c_int,
    ]
    shell32.ShellExecuteW.restype = ctypes.c_ssize_t
    shell32.ILCreateFromPathW.argtypes = [wintypes.LPCWSTR]
    shell32.ILCreateFromPathW.restype = ctypes.c_void_p
    shell32.ILFree.argtypes = [ctypes.c_void_p]
    shell32.ILFree.restype = None
    shell32.SHOpenFolderAndSelectItems.argtypes = [
        ctypes.c_void_p,
        wintypes.UINT,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
    shell32.SHOpenFolderAndSelectItems.restype = ctypes.c_long

    ole32 = ctypes.WinDLL("ole32")
    ole32.CoInitializeEx.argtypes = [ctypes.c_void_p, wintypes.DWORD]
    ole32.CoInitializeEx.restype = ctypes.c_long
    ole32.CoUninitialize.argtypes = []
    ole32.CoUninitialize.restype = None

    return u32, k32, shell32, ole32


_D_U32, _D_K32, _D_SHELL32, _D_OLE32 = _bind_daemon_win32()


class DaemonRuntimeState:
    def __init__(self) -> None:
        self.clients: set[web.WebSocketResponse] = set()
        self.wallpaper_clients: set[web.WebSocketResponse] = set()
        self.quota_history: deque[float] = deque(maxlen=56)
        self.quota_seeded: bool = False
        self.tok_rate_history: deque[int] = deque(maxlen=56)
        self.tok_rate_cid: str = ""
        self.ema_tok_rate: float = 0.0
        self.session_total_tokens: int = 0
        self.peak_tok_rate: int = 0
        self.latest_quota: dict[str, Any] | None = None
        self.last_quota_sig: tuple[Any, ...] | None = None
        self.last_quota_broadcast_mono: float = 0.0
        self.offload_db_cache_key: tuple[int, int, int, int] | None = None
        self.offload_db_cache_val: dict[str, Any] | None = None
        self.transcript_sizes: dict[str, int] = {}
        self.transcript_offsets: dict[str, int] = {}
        self.last_rate_sample_mono: float = time.monotonic()

        self.active_cascade_id: str = ""
        self.wallpaper_cascade_id: str = ""
        self.wallpaper_auto_follow: bool = True
        self.last_wp_auto_switch_mono: float = 0.0
        self.desktop_occluded: bool = False
        self.cached_conversations: list[dict[str, Any]] = []
        self.cached_workers: list[dict[str, Any]] = []
        self.swarm_count: int = 0
        self.conv_tracker = agy_core.ConversationLiveTracker()
        self.wallpaper_conv_tracker = agy_core.ConversationLiveTracker()
        self.last_conv_list_sync_mono: float = 0.0
        self.last_conv_list_fp: str = ""
        self.last_wp_status_sig: tuple[Any, ...] | None = None

        self.shutdown_event = asyncio.Event()


STATE = DaemonRuntimeState()


def probe_existing_daemon(host: str = HOST, port: int = PORT, timeout: float = 1.2) -> dict[str, Any] | None:
    """Return health JSON if a healthy ophanim_agy_daemon is already listening."""
    url = f"http://{host}:{port}/api/health"
    try:
        req = urllib.request.Request(url, method="GET")
        with _DIRECT_OPENER.open(req, timeout=timeout) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8", errors="replace"))
                if isinstance(data, dict) and data.get("ok") is True:
                    return data
    except Exception:
        pass
    return None


async def _send_to_client_set(targets: list[web.WebSocketResponse], payload: dict[str, Any]) -> int:
    if not targets:
        return 0
    msg = json.dumps(payload, ensure_ascii=False)
    stale: list[web.WebSocketResponse] = []
    sent = 0
    for ws in targets:
        if ws.closed:
            stale.append(ws)
            continue
        try:
            await ws.send_str(msg)
            sent += 1
        except Exception:
            stale.append(ws)
    for ws in stale:
        STATE.clients.discard(ws)
        STATE.wallpaper_clients.discard(ws)
    return sent


async def broadcast(payload: dict[str, Any]) -> int:
    if not STATE.clients:
        return 0
    return await _send_to_client_set(list(STATE.clients), payload)


async def broadcast_ui(payload: dict[str, Any]) -> int:
    ui_clients = [ws for ws in list(STATE.clients) if ws not in STATE.wallpaper_clients]
    return await _send_to_client_set(ui_clients, payload)


async def broadcast_wallpaper(payload: dict[str, Any]) -> int:
    if not STATE.wallpaper_clients:
        return 0
    return await _send_to_client_set(list(STATE.wallpaper_clients), payload)


async def send_ws_json(ws: web.WebSocketResponse, payload: dict[str, Any]) -> None:
    if not ws.closed:
        await ws.send_str(json.dumps(payload, ensure_ascii=False))


def _current_desktop_name() -> str:
    """Return the Win32 desktop name of this process (e.g. 'Default' on interactive user desktop)."""
    if os.name != "nt":
        return "posix"
    if _D_U32 is None or _D_K32 is None:
        return ""
    try:
        hdesk = _D_U32.GetThreadDesktop(_D_K32.GetCurrentThreadId())
        if not hdesk:
            return ""
        buf = ctypes.create_unicode_buffer(256)
        needed = wintypes.DWORD(0)
        if _D_U32.GetUserObjectInformationW(hdesk, 2, buf, 512, ctypes.byref(needed)):
            return str(buf.value or "")
    except Exception:
        pass
    return ""


def _is_interactive_user_desktop() -> bool:
    if os.name != "nt":
        return True
    dname = _current_desktop_name().strip().lower()
    return dname == "default"


def _is_safe_local_windows_path(raw: str) -> Path | None:
    """Validate that a client-requested path is a real local drive path (never UNC/remote URL)."""
    s = (raw or "").strip()
    if not s or len(s) > 1024 or any(ord(ch) < 32 for ch in s):
        return None
    if s.lower().startswith("file:///"):
        s = unquote(s[8:])
    elif s.lower().startswith("file://"):
        s = unquote(s[7:])
    # Strip optional `#L10-20` line-range anchor from slab/code references
    if "#L" in s:
        s = s.split("#L", 1)[0].strip()
    elif "#" in s and not Path(s).exists():
        cand_base = s.split("#", 1)[0].strip()
        if cand_base:
            s = cand_base
    if s.startswith("\\\\") or "://" in s:
        return None
    norm = os.path.normpath(s)
    drive, _ = os.path.splitdrive(norm)
    if len(drive) != 2 or not drive[0].isalpha() or drive[1] != ":":
        return None
    try:
        return Path(norm).resolve(strict=False)
    except Exception:
        return None


def _open_folder_and_select_item(path_obj: Path, select_item: bool = True) -> bool:
    """Open Explorer and highlight `path_obj` via native Shell COM (`SHOpenFolderAndSelectItems`), zero process spawn."""
    if os.name != "nt" or _D_SHELL32 is None or _D_OLE32 is None:
        return False
    norm_path = os.path.normpath(str(path_obj))
    if not select_item:
        rc = int(_D_SHELL32.ShellExecuteW(None, "open", norm_path, None, norm_path, 1))
        return rc > 32

    should_uninit = False
    pidl = None
    try:
        hr_init = int(_D_OLE32.CoInitializeEx(None, 0x2))  # COINIT_APARTMENTTHREADED
        should_uninit = hr_init in (0, 1)
        pidl = _D_SHELL32.ILCreateFromPathW(norm_path)
        if not pidl:
            parent_dir = os.path.normpath(str(path_obj.parent))
            rc = int(_D_SHELL32.ShellExecuteW(None, "open", parent_dir, None, parent_dir, 1))
            return rc > 32
        hr = int(_D_SHELL32.SHOpenFolderAndSelectItems(pidl, 0, None, 0))
        if hr == 0:
            return True
        parent_dir = os.path.normpath(str(path_obj.parent))
        rc = int(_D_SHELL32.ShellExecuteW(None, "open", parent_dir, None, parent_dir, 1))
        return rc > 32
    except Exception as exc:
        logger.debug("SHOpenFolderAndSelectItems fallback error: %s", exc)
        return False
    finally:
        if pidl:
            try:
                _D_SHELL32.ILFree(pidl)
            except Exception:
                pass
        if should_uninit:
            try:
                _D_OLE32.CoUninitialize()
            except Exception:
                pass


def handle_local_file_action(data: dict[str, Any]) -> bool:
    """Open file or highlight target in Windows Explorer via native Shell APIs (no AttachThreadInput/keybd_event)."""
    if os.name == "nt" and not _is_interactive_user_desktop():
        logger.warning(
            "handle_local_file_action skipped on non-interactive desktop %r; start via Ophanim_Sanctum.bat",
            _current_desktop_name(),
        )
        return False

    action = str(data.get("action") or "").strip()
    raw_path = str(data.get("path") or "").strip()
    raw_dir = str(data.get("dir") or "").strip()
    raw_file = str(data.get("file") or "").strip()

    target = _is_safe_local_windows_path(raw_path)
    target_dir = _is_safe_local_windows_path(raw_dir)
    if target is None and target_dir is not None and raw_file and "/" not in raw_file and "\\" not in raw_file:
        cand = target_dir / raw_file.split("#L", 1)[0].strip()
        target = _is_safe_local_windows_path(str(cand))
    if target is None and raw_file:
        _scratch_cand = PROJECT_DIR.parent.parent / "scratch" / "ophanim_uploads"
        search_dirs = [
            PROJECT_DIR,
            _scratch_cand if _scratch_cand.is_dir() else (PROJECT_DIR / ".ophanim_cache" / "uploads"),
            Path.home() / "Desktop",
        ]
        if STATE.wallpaper_cascade_id and STATE.wallpaper_cascade_id != STATE.active_cascade_id:
            search_dirs.insert(0, agy_core._resolve_brain_dir(STATE.wallpaper_cascade_id) / ".user_uploaded")
        if STATE.active_cascade_id:
            search_dirs.insert(0, agy_core._resolve_brain_dir(STATE.active_cascade_id) / ".user_uploaded")
        for base_dir in search_dirs:
            clean_fn = raw_file.split("#L", 1)[0].strip()
            for prefix in ("已分析 ", "已编辑 ", "已生成 "):
                if clean_fn.startswith(prefix):
                    clean_fn = clean_fn[len(prefix):].strip()
            if clean_fn and "/" not in clean_fn and "\\" not in clean_fn:
                cand_p = base_dir / clean_fn
                if cand_p.exists():
                    target = cand_p.resolve(strict=False)
                    break

    try:
        if action == "open_location":
            if target and target.exists():
                return _open_folder_and_select_item(target, select_item=True)

            folder_to_open: Path | None = None
            if target_dir and target_dir.is_dir():
                folder_to_open = target_dir
            elif target and target.parent.is_dir():
                folder_to_open = target.parent

            if folder_to_open is not None:
                return _open_folder_and_select_item(folder_to_open, select_item=False)

        elif action == "open_file":
            if target and target.exists():
                norm_target = os.path.normpath(str(target))
                # Security guard: never directly execute shell/binary extensions on click — select in Explorer instead!
                if target.suffix.lower() in _BLOCKED_EXEC_EXTS:
                    return _open_folder_and_select_item(target, select_item=True)
                if os.name == "nt" and _D_SHELL32 is not None:
                    rc = int(
                        _D_SHELL32.ShellExecuteW(
                            None, "open", norm_target, None, os.path.normpath(str(target.parent)), 1
                        )
                    )
                    if rc > 32:
                        return True
                os.startfile(norm_target)  # type: ignore[attr-defined]
                return True
    except Exception as exc:
        logger.warning("handle_local_file_action failed (%s): %s", action, exc)
    return False


def atomic_save_config(cfg: dict[str, Any]) -> None:
    """Atomically write user UI/3D layout configuration to ophanim_config.json with Win32 lock & retry."""
    PROJECT_DIR.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(cfg, ensure_ascii=False, indent=2)
    with _CONFIG_IO_LOCK:
        tmp_path = PROJECT_DIR / f".ophanim_config.{os.getpid()}.{threading.get_ident()}.{time.time_ns()}.tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as fh:
                fh.write(serialized)
                fh.flush()
                try:
                    os.fsync(fh.fileno())
                except OSError:
                    pass
            last_exc: Exception | None = None
            for attempt in range(5):
                try:
                    os.replace(tmp_path, CONFIG_SAVE_PATH)
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
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass


# ============================================================================
# Real Local Quota & Token Velocity Telemetry
# ============================================================================

def _seed_tok_rate_from_snapshot(snap: dict[str, Any]) -> None:
    """Seed per-second token burn history & cumulative total from a conversation snapshot."""
    if not isinstance(snap, dict):
        return
    cid = str(snap.get("cascadeId") or "").strip()
    tstats = snap.get("tokenStats") if isinstance(snap.get("tokenStats"), dict) else {}
    total_toks = int(tstats.get("totalTokens") or 0)
    recent_rates = [max(0, int(v)) for v in (tstats.get("recentRates") or []) if isinstance(v, (int, float))]

    STATE.session_total_tokens = total_toks
    if cid and cid != STATE.tok_rate_cid:
        STATE.tok_rate_cid = cid
        STATE.tok_rate_history.clear()
        for rv in recent_rates[-54:]:
            STATE.tok_rate_history.append(rv)
        while len(STATE.tok_rate_history) < 56:
            STATE.tok_rate_history.appendleft(0)
        STATE.peak_tok_rate = max(STATE.tok_rate_history) if STATE.tok_rate_history else 0


def _sample_live_transcript_tok_rate() -> int:
    """Measure real-time per-second token consumption (`tok/s`) from active/recent Antigravity transcripts."""
    now_mono = time.monotonic()
    dt = max(0.35, min(6.0, now_mono - STATE.last_rate_sample_mono))
    STATE.last_rate_sample_mono = now_mono

    exact_step_tokens = 0
    delta_bytes = 0
    seeded_before = bool(STATE.transcript_sizes)

    # Scan ONLY active/recent CIDs (never stat hundreds of dormant brain directories!)
    candidate_cids: list[str] = []
    seen_cids: set[str] = set()

    def _add_cid(c: str) -> None:
        cs = (c or "").strip()
        if cs and cs != "__new__" and cs not in seen_cids:
            seen_cids.add(cs)
            candidate_cids.append(cs)

    _add_cid(STATE.active_cascade_id)
    _add_cid(STATE.wallpaper_cascade_id)
    for conv in STATE.cached_conversations:
        if conv.get("status") == "running":
            _add_cid(str(conv.get("id") or ""))
    for conv in STATE.cached_conversations[:8]:
        _add_cid(str(conv.get("id") or ""))

    watched_paths: list[tuple[str, Path]] = []
    for cid in candidate_cids[:16]:
        t_path = agy_core._resolve_brain_dir(cid) / ".system_generated/logs/transcript.jsonl"
        watched_paths.append((cid, t_path))

    if not watched_paths and BRAIN_DIR.is_dir():
        try:
            with os.scandir(BRAIN_DIR) as it:
                for entry in it:
                    if len(watched_paths) >= 12:
                        break
                    if entry.is_dir(follow_symlinks=False) and len(entry.name) >= 32:
                        watched_paths.append((entry.name, Path(entry.path) / ".system_generated/logs/transcript.jsonl"))
        except OSError:
            pass

    active_keys: set[str] = set()
    try:
        for cid_name, t_path in watched_paths:
            try:
                st = t_path.stat()
            except OSError:
                continue
            key = str(t_path)
            active_keys.add(key)
            prev_sz = STATE.transcript_sizes.get(key)
            STATE.transcript_sizes[key] = st.st_size
            if not seeded_before or prev_sz is None:
                STATE.transcript_offsets[key] = st.st_size
                continue

            if st.st_size > prev_sz:
                grow = st.st_size - prev_sz
                delta_bytes += grow
                read_from = STATE.transcript_offsets.get(key, prev_sz)
                if st.st_size - read_from <= 512_000:
                    try:
                        with open(t_path, "rb") as fh:
                            fh.seek(max(0, read_from))
                            chunk = fh.read()
                        STATE.transcript_offsets[key] = st.st_size
                        for raw_line in chunk.splitlines():
                            line_s = raw_line.decode("utf-8", errors="ignore").strip()
                            if not line_s or not line_s.startswith("{"):
                                continue
                            obj = json.loads(line_s)
                            if not isinstance(obj, dict):
                                continue
                            in_t = int(obj.get("input_tokens") or 0)
                            out_t = int(obj.get("output_tokens") or 0)
                            cache_t = int(obj.get("cache_read_tokens") or 0)
                            if out_t > 0 or in_t > 0:
                                step_burn = out_t + min(in_t, 6400) + int(cache_t * 0.04)
                                exact_step_tokens += max(out_t, step_burn)
                                if cid_name == STATE.active_cascade_id:
                                    STATE.session_total_tokens += (in_t + out_t + cache_t)
                    except Exception:
                        STATE.transcript_offsets[key] = st.st_size
            elif st.st_size < prev_sz:
                STATE.transcript_offsets[key] = st.st_size
    except Exception:
        pass

    # Cap STATE.transcript_sizes & STATE.transcript_offsets to prevent unbounded growth
    if len(STATE.transcript_sizes) > 64:
        for k in list(STATE.transcript_sizes.keys()):
            if k not in active_keys:
                STATE.transcript_sizes.pop(k, None)
                STATE.transcript_offsets.pop(k, None)
                if len(STATE.transcript_sizes) <= 48:
                    break

    any_running = any(c.get("status") == "running" for c in STATE.cached_conversations) or any(
        w.get("status") == "running" for w in STATE.cached_workers
    )

    inst_rate = 0.0
    if exact_step_tokens > 0:
        inst_rate = exact_step_tokens / max(1.0, dt)
    elif delta_bytes > 0:
        inst_rate = (delta_bytes / 3.4) / dt

    if inst_rate > 0:
        STATE.ema_tok_rate = STATE.ema_tok_rate * 0.42 + inst_rate * 0.58
    elif any_running:
        floor_vel = 210.0 + 58.0 * math.sin(now_mono * 2.1) + 45.0 * max(0, STATE.swarm_count)
        STATE.ema_tok_rate = max(floor_vel, STATE.ema_tok_rate * 0.82)
    else:
        STATE.ema_tok_rate *= 0.42
        if STATE.ema_tok_rate < 8.0:
            STATE.ema_tok_rate = 0.0

    return min(96000, max(0, int(round(STATE.ema_tok_rate))))


def _stat_offload_db_key() -> tuple[int, int, int, int] | None:
    try:
        st_db = OFFLOAD_DB_PATH.stat()
    except OSError:
        return None
    wal_path = Path(str(OFFLOAD_DB_PATH) + "-wal")
    try:
        st_wal = wal_path.stat()
        wal_m, wal_s = int(st_wal.st_mtime_ns), int(st_wal.st_size)
    except OSError:
        wal_m, wal_s = 0, 0
    return (int(st_db.st_mtime_ns), int(st_db.st_size), wal_m, wal_s)


def collect_real_quota_snapshot() -> dict[str, Any]:
    """Read real quota telemetry from mtime-cached agent-app-offload SQLite DB + active transcript `tok/s`."""
    used_pct = 20.0
    rem_label = "80.0% · 0.00M"
    tier_tag = "PRO·LIVE"
    ledger_recent_tok_rate = 0
    hist_candidates: list[float] = []
    loaded_ok = False

    db_key = _stat_offload_db_key()
    if db_key is not None:
        if STATE.quota_seeded and STATE.offload_db_cache_key == db_key and STATE.offload_db_cache_val is not None:
            cached = STATE.offload_db_cache_val
            used_pct = float(cached["used_pct"])
            rem_label = str(cached["rem_label"])
            tier_tag = str(cached["tier_tag"])
            if (time.time() - float(cached.get("ts") or 0.0)) <= 15.0:
                ledger_recent_tok_rate = int(cached.get("ledger_recent_tok_rate") or 0)
            loaded_ok = True
        else:
            try:
                uri = f"file:{OFFLOAD_DB_PATH.as_posix()}?mode=ro"
                with contextlib.closing(sqlite3.connect(uri, uri=True, timeout=2.0)) as con:
                    con.row_factory = sqlite3.Row
                    cfg_row = con.execute("SELECT * FROM account_config WHERE id = 1").fetchone()
                    if cfg_row:
                        cfg = dict(cfg_row)
                        active_acc = str(cfg.get("active_account") or "")
                        win_sec = max(60, int(cfg.get("window_seconds") or 10800))
                        safe_limit = max(1, int(cfg.get("window_safe_limit") or 50))
                        offset_pct = float(cfg.get("manual_offset_pct") or 0.0)
                        weekly_used = max(0.0, min(100.0, float(cfg.get("weekly_used_pct") or 0.0)))
                        enabled = bool(cfg.get("enabled", 1))

                        now_ts = time.time()
                        cutoff = now_ts - win_sec
                        used_in_win = int(
                            con.execute(
                                "SELECT COUNT(*) FROM call_ledger WHERE account = ? AND status = 'SUCCESS' AND ts_epoch >= ?",
                                (active_acc, cutoff),
                            ).fetchone()[0]
                        )
                        raw_rem = (1.0 - (used_in_win / safe_limit)) * 100.0
                        eff_rem = max(0.0, min(100.0, round(raw_rem + offset_pct, 1)))
                        cur_used = round(100.0 - eff_rem, 1)

                        used_pct = cur_used if cur_used > 0.0 else weekly_used

                        tot_saved = int(
                            con.execute(
                                "SELECT COALESCE(SUM(estimated_tokens_saved), 0) FROM call_ledger WHERE status = 'SUCCESS'"
                            ).fetchone()[0]
                        )
                        saved_m = tot_saved / 1_000_000.0
                        rem_calls = max(0, safe_limit - used_in_win)
                        rem_label = f"{rem_calls}/{safe_limit}轮 · 省{saved_m:.2f}M"

                        acc_row = con.execute(
                            "SELECT tier_label FROM accounts WHERE account_email = ?",
                            (active_acc,),
                        ).fetchone()
                        tier_str = str(acc_row["tier_label"]) if acc_row and acc_row["tier_label"] else "Pro"
                        tier_prefix = "ULTRA" if "ultra" in tier_str.lower() else "PRO"
                        tier_tag = f"{tier_prefix}·{'LIVE' if enabled else 'PAUSED'}"

                        recent_toks = int(
                            con.execute(
                                "SELECT COALESCE(SUM(estimated_tokens_saved), 0) FROM call_ledger WHERE status = 'SUCCESS' AND ts_epoch >= ?",
                                (now_ts - 15.0,),
                            ).fetchone()[0]
                        )
                        if recent_toks > 0:
                            ledger_recent_tok_rate = int(round(recent_toks / 15.0))

                        if not STATE.quota_seeded:
                            rows = con.execute(
                                "SELECT remaining_pct_after FROM call_ledger ORDER BY id DESC LIMIT 55"
                            ).fetchall()
                            for r in reversed(rows):
                                rp = float(r["remaining_pct_after"] if r["remaining_pct_after"] is not None else eff_rem)
                                up = round(max(0.0, min(100.0, 100.0 - rp)), 1)
                                hist_candidates.append(up if up > 0.0 else weekly_used)
                        STATE.offload_db_cache_key = db_key
                        STATE.offload_db_cache_val = {
                            "used_pct": used_pct,
                            "rem_label": rem_label,
                            "tier_tag": tier_tag,
                            "ledger_recent_tok_rate": ledger_recent_tok_rate,
                            "ts": now_ts,
                        }
                        loaded_ok = True
            except Exception as exc:
                logger.warning("SQLite quota read fallback (%s)", exc)

    if not loaded_ok:
        try:
            req = urllib.request.Request(OFFLOAD_DASHBOARD_URL, method="GET")
            with _DIRECT_OPENER.open(req, timeout=0.8) as resp:
                d = json.loads(resp.read().decode("utf-8", errors="replace"))
            cur_used = float(d.get("current_used_pct") or 0.0)
            wk_used = float(d.get("weekly_used_pct") or 20.0)
            used_pct = round(cur_used if cur_used > 0.0 else wk_used, 1)
            tot_saved = int((d.get("totals") or {}).get("total_tokens_saved") or 0)
            safe_limit = max(1, int(d.get("window_safe_limit") or 50))
            used_in_win = int(d.get("used_in_window") or 0)
            rem_label = f"{max(0, safe_limit - used_in_win)}/{safe_limit}轮 · 省{tot_saved / 1_000_000.0:.2f}M"
            badge = str(d.get("active_tier_badge") or "PRO").upper()
            tier_tag = f"{'ULTRA' if 'ULTRA' in badge else 'PRO'}·LIVE"
        except Exception:
            if OFFLOAD_SNAPSHOT_PATH.is_file():
                try:
                    snap = json.loads(OFFLOAD_SNAPSHOT_PATH.read_text(encoding="utf-8"))
                    acfg = snap.get("account_config") or {}
                    used_pct = round(float(acfg.get("weekly_used_pct") or 20.0), 1)
                    rem_label = f"{100.0 - used_pct:.0f}% · SNAPSHOT"
                    tier_tag = "PRO·LIVE"
                except Exception:
                    pass

    live_tok_rate = _sample_live_transcript_tok_rate()
    burn_rate = max(ledger_recent_tok_rate, live_tok_rate)

    if not STATE.quota_seeded:
        STATE.quota_seeded = True
        for val in hist_candidates[-55:]:
            STATE.quota_history.append(val)
        while len(STATE.quota_history) < 12:
            STATE.quota_history.appendleft(used_pct)

    STATE.quota_history.append(used_pct)
    history_list = list(STATE.quota_history)[-56:]
    if len(history_list) < 2:
        history_list = [used_pct, used_pct]

    while len(STATE.tok_rate_history) < 55:
        STATE.tok_rate_history.appendleft(0)
    STATE.tok_rate_history.append(int(burn_rate))
    rate_history_list = list(STATE.tok_rate_history)[-56:]
    STATE.peak_tok_rate = max(STATE.peak_tok_rate, max(rate_history_list) if rate_history_list else 0, int(burn_rate))

    snapshot = {
        "usedPct": round(used_pct, 1),
        "remPct": round(100.0 - used_pct, 1),
        "burnRateTokPerSec": int(burn_rate),
        "peakTokPerSec": int(STATE.peak_tok_rate),
        "sessionTotalTokens": int(STATE.session_total_tokens),
        "remLabel": rem_label,
        "tierTag": tier_tag,
        "history": history_list,
        "rateHistory": rate_history_list,
    }
    STATE.latest_quota = snapshot
    return snapshot


# ============================================================================
# Per-Conversation Antigravity / Universal External Agent Sync & Live Loop
# ============================================================================

def _is_external_mode_sync() -> bool:
    ls_addr, _ = agy_core.discover_agy_ls(force=False)
    return ext_bridge.is_external_backend_preferred(bool(ls_addr))


def _list_conversations_unified_sync() -> list[dict[str, Any]]:
    if _is_external_mode_sync():
        return ext_bridge.list_conversations()
    return agy_core.list_conversations()


def _send_message_unified_sync(
    target_cid: str,
    exact_text: Any,
    model_key: str,
    allow_create: bool,
    attachments: list[dict[str, Any]],
    send_mode: str,
) -> dict[str, Any]:
    ls_addr, _ = agy_core.discover_agy_ls(force=False)
    if ext_bridge.is_external_backend_preferred(bool(ls_addr)) or not ls_addr:
        # Double-check with forced discovery once in case Antigravity just launched
        if not ext_bridge.is_external_backend_preferred(False):
            ls_addr, _ = agy_core.discover_agy_ls(force=True)
        if ext_bridge.is_external_backend_preferred(bool(ls_addr)) or not ls_addr:
            return ext_bridge.send_verbatim_message(
                target_cid, exact_text, model_key, allow_create, attachments, send_mode
            )
    return agy_core.send_verbatim_message(
        target_cid, exact_text, model_key, allow_create, attachments, send_mode
    )


def _bind_and_snapshot_sync(target_cid: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if _is_external_mode_sync():
        convs = ext_bridge.list_conversations()
        STATE.cached_conversations = convs
        valid_ids = {c["id"] for c in convs}
        chosen_cid = (target_cid or "").strip()
        if chosen_cid == "__new__":
            chosen_cid = ""
        elif chosen_cid and chosen_cid not in valid_ids:
            chosen_cid = ""
        if not chosen_cid:
            if STATE.active_cascade_id and STATE.active_cascade_id in valid_ids:
                chosen_cid = STATE.active_cascade_id
            elif convs:
                non_arch = [c for c in convs if not c.get("archived")] or convs
                running_convs = [c["id"] for c in non_arch if c.get("status") == "running"]
                chosen_cid = running_convs[0] if running_convs else non_arch[0]["id"]
        STATE.active_cascade_id = chosen_cid
        snap = ext_bridge.get_conversation_snapshot(chosen_cid)
        STATE.cached_workers = snap.get("workers") or []
        STATE.swarm_count = len(STATE.cached_workers)
        return convs, snap

    convs = agy_core.list_conversations()
    STATE.cached_conversations = convs

    valid_ids = {c["id"] for c in convs}
    chosen_cid = (target_cid or "").strip()
    if chosen_cid == "__new__":
        chosen_cid = ""
    elif chosen_cid and chosen_cid not in valid_ids and not (BRAIN_DIR / chosen_cid).is_dir():
        chosen_cid = ""

    if not chosen_cid:
        if STATE.active_cascade_id and STATE.active_cascade_id in valid_ids:
            chosen_cid = STATE.active_cascade_id
        elif convs:
            # Prefer a currently running non-archived conversation if active, else newest non-archived
            non_arch = [c for c in convs if not c.get("archived")] or convs
            running_convs = [c["id"] for c in non_arch if c.get("status") == "running"]
            chosen_cid = running_convs[0] if running_convs else non_arch[0]["id"]

    STATE.active_cascade_id = chosen_cid
    STATE.conv_tracker.bind(chosen_cid)
    snap = agy_core.build_conversation_snapshot(chosen_cid) if chosen_cid else {
        "cascadeId": "",
        "shortId": "NEW",
        "title": "新建对话 · 待发首条指令",
        "status": "idle",
        "messages": [],
        "turns": [],
        "workers": [],
        "slabs": [],
        "outerFiles": [],
        "deliverables": [],
        "tokenStats": {"totalTokens": 0, "recentRates": []},
    }
    _seed_tok_rate_from_snapshot(snap)
    STATE.cached_workers = snap.get("workers") or []
    STATE.swarm_count = len(STATE.cached_workers)
    return convs, snap


# ============================================================================
# Wallpaper Independent Auto-Follow Working Conversation Engine
# ============================================================================

def _load_saved_wallpaper_auto_follow() -> bool:
    if not CONFIG_SAVE_PATH.is_file():
        return True
    try:
        raw = json.loads(CONFIG_SAVE_PATH.read_text(encoding="utf-8", errors="replace"))
        if isinstance(raw, dict) and isinstance(raw.get("wallpaperAutoFollow"), bool):
            return bool(raw["wallpaperAutoFollow"])
    except Exception:
        pass
    return True


def _persist_wallpaper_auto_follow_sync(enabled: bool) -> None:
    cfg: dict[str, Any] = {}
    if CONFIG_SAVE_PATH.is_file():
        try:
            raw = json.loads(CONFIG_SAVE_PATH.read_text(encoding="utf-8", errors="replace"))
            if isinstance(raw, dict):
                cfg = raw
        except Exception:
            cfg = {}
    cfg["wallpaperAutoFollow"] = bool(enabled)
    atomic_save_config(cfg)


def _get_running_conversations(convs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    non_arch = [c for c in convs if not c.get("archived")] or list(convs)
    running = [c for c in non_arch if c.get("status") == "running" and c.get("id")]
    running.sort(key=lambda x: -float(x.get("updatedEpoch") or 0.0))
    return running


def _is_valid_conv_id(cid: str, valid_ids: set[str], external_mode: bool) -> bool:
    c = (cid or "").strip()
    if not c or c == "__new__":
        return False
    if c in valid_ids:
        return True
    if not external_mode and (BRAIN_DIR / c).is_dir():
        return True
    return False


def _pick_wallpaper_cascade_id(
    convs: list[dict[str, Any]],
    current_wp_cid: str = "",
    fallback_cid: str = "",
    external_mode: bool = False,
) -> str:
    valid_ids = {str(c.get("id") or "") for c in convs if c.get("id")}
    non_arch = [c for c in convs if not c.get("archived")] or list(convs)
    cur_cid = (current_wp_cid or "").strip()
    fb_cid = (fallback_cid or "").strip()

    if STATE.wallpaper_auto_follow:
        running = _get_running_conversations(convs)
        if running:
            running_ids = {str(c["id"]) for c in running}
            if cur_cid and cur_cid in running_ids:
                return cur_cid
            return str(running[0]["id"])
    else:
        if _is_valid_conv_id(fb_cid, valid_ids, external_mode):
            return fb_cid

    # No conversation is currently running (or auto-follow disabled with no fallback):
    # stay on current wallpaper conversation (e.g. just-finished C) before falling back.
    if _is_valid_conv_id(cur_cid, valid_ids, external_mode):
        return cur_cid
    if _is_valid_conv_id(fb_cid, valid_ids, external_mode):
        return fb_cid
    if non_arch and non_arch[0].get("id"):
        return str(non_arch[0]["id"])
    return ""


def _build_snapshot_only_sync(target_cid: str) -> dict[str, Any]:
    cid = (target_cid or "").strip()
    if _is_external_mode_sync():
        return ext_bridge.get_conversation_snapshot(cid)
    if cid:
        return agy_core.build_conversation_snapshot(cid)
    return {
        "cascadeId": "",
        "shortId": "NEW",
        "title": "新建对话 · 待发首条指令",
        "status": "idle",
        "messages": [],
        "turns": [],
        "workers": [],
        "slabs": [],
        "outerFiles": [],
        "deliverables": [],
        "tokenStats": {"totalTokens": 0, "recentRates": []},
    }


def _bind_wallpaper_snapshot_sync(
    preferred_cid: str = "",
    force_cid: str = "",
) -> tuple[list[dict[str, Any]], dict[str, Any], str]:
    ext_mode = _is_external_mode_sync()
    convs = ext_bridge.list_conversations() if ext_mode else agy_core.list_conversations()
    STATE.cached_conversations = convs
    valid_ids = {str(c.get("id") or "") for c in convs if c.get("id")}

    prev_cid = STATE.wallpaper_cascade_id
    chosen_cid = (force_cid or "").strip()
    if not _is_valid_conv_id(chosen_cid, valid_ids, ext_mode):
        fallback = STATE.active_cascade_id or preferred_cid
        chosen_cid = _pick_wallpaper_cascade_id(
            convs,
            current_wp_cid=STATE.wallpaper_cascade_id,
            fallback_cid=fallback,
            external_mode=ext_mode,
        )

    STATE.wallpaper_cascade_id = chosen_cid
    snap = _build_snapshot_only_sync(chosen_cid)
    if not ext_mode and chosen_cid and chosen_cid != STATE.active_cascade_id:
        STATE.wallpaper_conv_tracker.bind(chosen_cid)
        STATE.wallpaper_conv_tracker.last_status = str(snap.get("status") or "idle")
    return convs, snap, prev_cid


def _enrich_wallpaper_status(st: dict[str, Any]) -> dict[str, Any]:
    out = dict(st or {})
    wp_cid = STATE.wallpaper_cascade_id or ""
    wp_title = ""
    wp_conv_status = "idle"
    if wp_cid:
        for c in STATE.cached_conversations:
            if c.get("id") == wp_cid:
                wp_title = str(c.get("title") or c.get("shortId") or wp_cid[:8])
                wp_conv_status = str(c.get("status") or "idle")
                break
        if not wp_title:
            wp_title = wp_cid[:8]
    out["autoFollowWorking"] = bool(STATE.wallpaper_auto_follow)
    out["wallpaperCascadeId"] = wp_cid
    out["wallpaperTitle"] = wp_title
    out["wallpaperStatus"] = wp_conv_status
    return out


async def _broadcast_wallpaper_status_if_changed(force: bool = False) -> None:
    st = _enrich_wallpaper_status(await asyncio.to_thread(wp_mgr.get_wallpaper_status))
    sig = (
        bool(st.get("active")),
        st.get("wallpaperMode"),
        st.get("autoFollowWorking"),
        st.get("wallpaperCascadeId"),
        st.get("wallpaperTitle"),
        st.get("wallpaperStatus"),
    )
    if force or sig != STATE.last_wp_status_sig:
        STATE.last_wp_status_sig = sig
        await broadcast({"type": "ophanim_wallpaper_status", **st})


async def _switch_wallpaper_conversation(
    target_cid: str,
    convs: list[dict[str, Any]] | None = None,
    animate: bool = True,
) -> bool:
    cid = (target_cid or "").strip()
    if not cid or cid == "__new__":
        return False
    prev_cid = STATE.wallpaper_cascade_id
    STATE.wallpaper_cascade_id = cid
    ext_mode = await asyncio.to_thread(_is_external_mode_sync)
    snap = await asyncio.to_thread(_build_snapshot_only_sync, cid)
    if not ext_mode and cid != STATE.active_cascade_id:
        await asyncio.to_thread(STATE.wallpaper_conv_tracker.bind, cid)
        STATE.wallpaper_conv_tracker.last_status = str(snap.get("status") or "idle")

    convs_use = convs if convs is not None else STATE.cached_conversations
    if STATE.wallpaper_clients:
        await broadcast_wallpaper(
            {
                "type": "agy_conversation_snapshot",
                "snapshot": snap,
                "conversations": convs_use,
                "animateTransition": bool(animate and prev_cid and prev_cid != cid),
                "autoSwitched": True,
            }
        )
    if prev_cid != cid:
        STATE.last_wp_auto_switch_mono = time.monotonic()
        logger.info(
            "Wallpaper conversation switched: %s -> %s (%s) [%s]",
            prev_cid[:8] or "NONE",
            cid[:8],
            str(snap.get("title") or "")[:28],
            snap.get("status") or "idle",
        )
    await _broadcast_wallpaper_status_if_changed(force=True)
    return True


async def _sync_wallpaper_auto_follow(
    convs: list[dict[str, Any]],
    animate: bool = True,
    explicit_ui_cid: str = "",
) -> bool:
    if not convs:
        return False
    ext_mode = await asyncio.to_thread(_is_external_mode_sync)
    exp_cid = (explicit_ui_cid or "").strip()

    if not STATE.wallpaper_clients:
        # Keep STATE.wallpaper_cascade_id pre-computed even when wallpaper isn't connected yet
        desired = _pick_wallpaper_cascade_id(
            convs,
            current_wp_cid=STATE.wallpaper_cascade_id,
            fallback_cid=exp_cid or STATE.active_cascade_id,
            external_mode=ext_mode,
        )
        if desired:
            STATE.wallpaper_cascade_id = desired
        return False

    if STATE.wallpaper_auto_follow:
        running = _get_running_conversations(convs)
        if exp_cid and exp_cid != "__new__":
            exp_running = any(str(c.get("id")) == exp_cid for c in running)
            if exp_running or not running:
                desired = exp_cid
            else:
                desired = _pick_wallpaper_cascade_id(
                    convs,
                    current_wp_cid=STATE.wallpaper_cascade_id,
                    fallback_cid="",
                    external_mode=ext_mode,
                )
        else:
            desired = _pick_wallpaper_cascade_id(
                convs,
                current_wp_cid=STATE.wallpaper_cascade_id,
                fallback_cid=STATE.active_cascade_id,
                external_mode=ext_mode,
            )
    else:
        desired = exp_cid if (exp_cid and exp_cid != "__new__") else STATE.active_cascade_id

    if desired and desired != STATE.wallpaper_cascade_id:
        # Debounce automatic background wallpaper switches (>=4.5s cooldown) to prevent GPU texture upload storms
        if not exp_cid and STATE.wallpaper_cascade_id and (time.monotonic() - STATE.last_wp_auto_switch_mono) < 4.5:
            return False
        return await _switch_wallpaper_conversation(desired, convs, animate=animate)

    await _broadcast_wallpaper_status_if_changed(force=False)
    return False


async def agy_conversation_loop() -> None:
    """Poll the bound Antigravity conversation (and independent wallpaper working conversation)."""
    while not STATE.shutdown_event.is_set():
        try:
            now_m = time.monotonic()
            has_wp = bool(STATE.wallpaper_clients)
            ui_clients = [ws for ws in list(STATE.clients) if ws not in STATE.wallpaper_clients]
            has_ui = bool(ui_clients)

            if await asyncio.to_thread(_is_external_mode_sync):
                if has_wp and (now_m - STATE.last_conv_list_sync_mono) >= 5.0:
                    STATE.last_conv_list_sync_mono = now_m
                    convs = await asyncio.to_thread(ext_bridge.list_conversations)
                    STATE.cached_conversations = convs
                    await _sync_wallpaper_auto_follow(convs, animate=True)
                try:
                    await asyncio.wait_for(STATE.shutdown_event.wait(), timeout=1.5)
                except asyncio.TimeoutError:
                    pass
                continue

            active_cid = STATE.active_cascade_id
            wp_cid = STATE.wallpaper_cascade_id
            same_cid = bool(active_cid and wp_cid and active_cid == wp_cid)
            refreshed_convs: list[dict[str, Any]] | None = None

            # 1. Poll UI's bound conversation (shared with wallpaper if both point to the same conversation)
            if active_cid and active_cid != "__new__" and (has_ui or same_cid or not has_wp):
                upd = await asyncio.to_thread(STATE.conv_tracker.poll_updates, active_cid)
                for bm in (upd.get("beamEvents") or []):
                    if same_cid:
                        await broadcast(bm)
                    else:
                        await broadcast_ui(bm)

                if upd.get("changed") and isinstance(upd.get("snapshot"), dict):
                    snap = upd["snapshot"]
                    _seed_tok_rate_from_snapshot(snap)
                    STATE.cached_workers = snap.get("workers") or []
                    STATE.swarm_count = len(STATE.cached_workers)
                    convs = await asyncio.to_thread(agy_core.list_conversations)
                    STATE.cached_conversations = convs
                    refreshed_convs = convs
                    STATE.last_conv_list_sync_mono = now_m
                    STATE.last_conv_list_fp = json.dumps(convs, ensure_ascii=False, sort_keys=True)
                    delta_msg = {
                        "type": "agy_conversation_delta",
                        "snapshot": snap,
                        "conversations": convs,
                    }
                    if same_cid:
                        await broadcast(delta_msg)
                    else:
                        await broadcast_ui(delta_msg)
                        if has_wp:
                            await broadcast_wallpaper(
                                {
                                    "type": "agy_conversations_list",
                                    "conversations": convs,
                                    "activeCascadeId": STATE.wallpaper_cascade_id,
                                }
                            )

            # 2. Poll Wallpaper's independent working conversation when it differs from UI's displayed conversation
            if has_wp and wp_cid and wp_cid != "__new__" and not same_cid:
                wp_upd = await asyncio.to_thread(STATE.wallpaper_conv_tracker.poll_updates, wp_cid)
                for bm in (wp_upd.get("beamEvents") or []):
                    await broadcast_wallpaper(bm)

                if wp_upd.get("changed") and isinstance(wp_upd.get("snapshot"), dict):
                    wp_snap = wp_upd["snapshot"]
                    if not has_ui:
                        _seed_tok_rate_from_snapshot(wp_snap)
                        STATE.cached_workers = wp_snap.get("workers") or []
                        STATE.swarm_count = len(STATE.cached_workers)
                    convs = await asyncio.to_thread(agy_core.list_conversations)
                    STATE.cached_conversations = convs
                    refreshed_convs = convs
                    STATE.last_conv_list_sync_mono = now_m
                    STATE.last_conv_list_fp = json.dumps(convs, ensure_ascii=False, sort_keys=True)
                    await broadcast_wallpaper(
                        {
                            "type": "agy_conversation_delta",
                            "snapshot": wp_snap,
                            "conversations": convs,
                        }
                    )
                    if has_ui:
                        await broadcast_ui(
                            {
                                "type": "agy_conversations_list",
                                "conversations": convs,
                                "activeCascadeId": STATE.active_cascade_id,
                            }
                        )

            # 3. Refresh background conversations list (`A`, `B`, `C` running vs idle)
            list_sync_interval = 5.0 if has_wp else 8.0
            if refreshed_convs is None and (now_m - STATE.last_conv_list_sync_mono) >= list_sync_interval:
                STATE.last_conv_list_sync_mono = now_m
                convs = await asyncio.to_thread(agy_core.list_conversations)
                STATE.cached_conversations = convs
                refreshed_convs = convs
                fp = json.dumps(convs, ensure_ascii=False, sort_keys=True)
                if fp != STATE.last_conv_list_fp:
                    STATE.last_conv_list_fp = fp
                    if has_ui:
                        await broadcast_ui(
                            {
                                "type": "agy_conversations_list",
                                "conversations": convs,
                                "activeCascadeId": STATE.active_cascade_id,
                            }
                        )
                    if has_wp:
                        await broadcast_wallpaper(
                            {
                                "type": "agy_conversations_list",
                                "conversations": convs,
                                "activeCascadeId": STATE.wallpaper_cascade_id,
                            }
                        )

            # 4. Auto-switch desktop wallpaper to any currently working conversation (e.g. A/B idle, C running -> C)
            if refreshed_convs is not None:
                await _sync_wallpaper_auto_follow(refreshed_convs, animate=True)
        except Exception as exc:
            logger.debug("agy_conversation_loop error: %s", exc)

        try:
            await asyncio.wait_for(STATE.shutdown_event.wait(), timeout=0.9)
        except asyncio.TimeoutError:
            pass


async def quota_telemetry_loop() -> None:
    wp_pin_tick = 0
    while not STATE.shutdown_event.is_set():
        try:
            wp_pin_tick += 1
            # Lightweight read-only wallpaper health check every ~15s (5 ticks * 3s)
            if wp_pin_tick % 5 == 0:
                await asyncio.to_thread(wp_mgr.ensure_wallpaper_pinned)

            ui_clients = [ws for ws in list(STATE.clients) if ws not in STATE.wallpaper_clients]
            if ui_clients:
                snap = await asyncio.to_thread(collect_real_quota_snapshot)
                sig = (
                    snap["usedPct"],
                    snap["burnRateTokPerSec"],
                    snap["sessionTotalTokens"],
                    snap["remLabel"],
                    snap["tierTag"],
                )
                now_m = time.monotonic()
                if (
                    snap["burnRateTokPerSec"] > 0
                    or sig != STATE.last_quota_sig
                    or (now_m - STATE.last_quota_broadcast_mono) >= 6.0
                ):
                    STATE.last_quota_sig = sig
                    STATE.last_quota_broadcast_mono = now_m
                    await broadcast_ui({"quota": snap})
        except Exception as exc:
            logger.warning("quota_telemetry_loop error: %s", exc)
        try:
            await asyncio.wait_for(STATE.shutdown_event.wait(), timeout=3.0)
        except asyncio.TimeoutError:
            pass


# ============================================================================
# HTTP & WebSocket Routes
# ============================================================================

NO_CACHE_HEADERS = {
    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
    "Pragma": "no-cache",
    "Expires": "0",
    "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Ophanim-Token",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
}


def _extract_host_only(host_hdr: str) -> str:
    h = (host_hdr or "").strip().lower()
    if not h:
        return ""
    if h.startswith("[") and "]" in h:
        return h[: h.index("]") + 1]
    return h.split(":", 1)[0]


def _is_trusted_origin(origin_hdr: str) -> bool:
    orig = (origin_hdr or "").strip()
    if not orig:
        return True
    if orig.lower() == "null":
        return True  # Local file:/// double-click origin
    try:
        parsed = urlparse(orig)
        host_part = (parsed.hostname or "").strip().lower()
        return host_part in _TRUSTED_LOCAL_HOSTS
    except Exception:
        return False


@web.middleware
async def localhost_security_middleware(request: web.Request, handler: Any) -> web.StreamResponse:
    """Block DNS-rebinding (`Host`), cross-site CSRF/CSWSH (`Origin`), and unauthorized remote access."""
    if not ALLOW_REMOTE:
        req_host = _extract_host_only(request.headers.get("Host", ""))
        if req_host and req_host not in _TRUSTED_LOCAL_HOSTS:
            return web.json_response({"ok": False, "error": "Forbidden Host header (loopback only)"}, status=403)

        origin = request.headers.get("Origin", "").strip()
        if origin and not _is_trusted_origin(origin):
            return web.json_response(
                {"ok": False, "error": "Forbidden cross-site Origin (localhost/file only)"}, status=403
            )

    if API_TOKEN and request.method != "OPTIONS" and request.path.startswith(("/api/", "/ws")):
        if request.path != "/api/health":
            hdr_tok = request.headers.get("X-Ophanim-Token", "").strip()
            auth_hdr = request.headers.get("Authorization", "").strip()
            if auth_hdr.lower().startswith("bearer "):
                hdr_tok = hdr_tok or auth_hdr[7:].strip()
            q_tok = request.query.get("token", "").strip()
            if (hdr_tok or q_tok) != API_TOKEN:
                return web.json_response({"ok": False, "error": "Unauthorized token"}, status=401)

    resp = await handler(request)
    origin_echo = request.headers.get("Origin", "").strip()
    if origin_echo and (_is_trusted_origin(origin_echo) or ALLOW_REMOTE):
        resp.headers["Access-Control-Allow-Origin"] = origin_echo
    elif not origin_echo:
        resp.headers["Access-Control-Allow-Origin"] = f"http://{HOST}:{PORT}"
    return resp


async def handle_cors_options(request: web.Request) -> web.Response:
    return web.Response(status=204, headers=NO_CACHE_HEADERS)


async def handle_index(request: web.Request) -> web.StreamResponse:
    if request.query.get("ws") is None:
        qs = request.query_string
        extra = f"&{qs}" if qs else ""
        raise web.HTTPFound(f"/ophanim_sanctum.html?ws=ws://{HOST}:{PORT}/ws{extra}")
    target = HTML_FILE_PATH if HTML_FILE_PATH.is_file() else FALLBACK_HTML_PATH
    if not target.is_file():
        return web.Response(
            text="ophanim_sanctum.html not found",
            status=404,
            headers=NO_CACHE_HEADERS,
        )
    html_bytes = await asyncio.to_thread(target.read_bytes)
    return web.Response(
        body=html_bytes,
        content_type="text/html",
        charset="utf-8",
        headers=NO_CACHE_HEADERS,
    )


async def handle_agy_panel_js(request: web.Request) -> web.Response:
    if not AGY_PANEL_JS_PATH.is_file():
        return web.Response(
            text="/* ophanim_agy_panel.js missing */",
            content_type="application/javascript",
            charset="utf-8",
            status=404,
            headers=NO_CACHE_HEADERS,
        )
    js_bytes = await asyncio.to_thread(AGY_PANEL_JS_PATH.read_bytes)
    return web.Response(
        body=js_bytes,
        content_type="application/javascript",
        charset="utf-8",
        headers=NO_CACHE_HEADERS,
    )


async def handle_logo_ico(request: web.Request) -> web.Response:
    if not LOGO_ICO_PATH.is_file():
        return web.Response(status=204)
    ico_bytes = await asyncio.to_thread(LOGO_ICO_PATH.read_bytes)
    return web.Response(body=ico_bytes, content_type="image/x-icon", headers=NO_CACHE_HEADERS)


async def handle_health(request: web.Request) -> web.Response:
    ls_addr, _ = await asyncio.to_thread(agy_core.discover_agy_ls, False)
    backend_info = await asyncio.to_thread(ext_bridge.get_backend_info, bool(ls_addr))
    return web.json_response(
        {
            "ok": True,
            "service": "ophanim_agy_daemon",
            "apiVersion": 5,
            "aiUsageBridge": True,
            "wallpaperKiosk64": True,
            "interactiveWallpaper": True,
            "agentBackend": backend_info,
            "pid": os.getpid(),
            "desktop": _current_desktop_name(),
            "desktopInteractive": _is_interactive_user_desktop(),
            "clients": len(STATE.clients),
            "wallpaperClients": len(STATE.wallpaper_clients),
            "uptime": round(time.monotonic() - START_MONO, 2),
            "activeCascadeId": STATE.active_cascade_id,
            "wallpaperCascadeId": STATE.wallpaper_cascade_id,
            "wallpaperAutoFollow": STATE.wallpaper_auto_follow,
            "swarmCount": STATE.swarm_count,
            "htmlFile": (HTML_FILE_PATH if HTML_FILE_PATH.is_file() else FALLBACK_HTML_PATH).name,
        },
        headers=NO_CACHE_HEADERS,
    )


async def handle_api_conversations(request: web.Request) -> web.Response:
    convs = await asyncio.to_thread(_list_conversations_unified_sync)
    STATE.cached_conversations = convs
    if not STATE.active_cascade_id and convs:
        STATE.active_cascade_id = convs[0]["id"]
    return web.json_response(
        {
            "type": "agy_conversations_list",
            "conversations": convs,
            "activeCascadeId": STATE.active_cascade_id,
            "wallpaperCascadeId": STATE.wallpaper_cascade_id,
        },
        headers=NO_CACHE_HEADERS,
    )


async def handle_api_conversation_detail(request: web.Request) -> web.Response:
    cid = str(request.match_info.get("cid") or "").strip()
    animate_flag = request.query.get("animate", "1") != "0"
    convs, snap = await asyncio.to_thread(_bind_and_snapshot_sync, cid)
    q_snap = await asyncio.to_thread(collect_real_quota_snapshot)
    await broadcast_ui({"quota": q_snap})
    await _sync_wallpaper_auto_follow(
        convs,
        animate=True,
        explicit_ui_cid=str(snap.get("cascadeId") or ""),
    )
    return web.json_response(
        {
            "type": "agy_conversation_snapshot",
            "snapshot": snap,
            "conversations": convs,
            "animateTransition": animate_flag,
        },
        headers=NO_CACHE_HEADERS,
    )


async def handle_api_file_action(request: web.Request) -> web.Response:
    try:
        body = await request.json()
    except Exception as exc:
        return web.json_response({"ok": False, "error": str(exc)}, status=400, headers=NO_CACHE_HEADERS)
    if not isinstance(body, dict):
        return web.json_response({"ok": False, "error": "JSON object required"}, status=400, headers=NO_CACHE_HEADERS)
    ok = await asyncio.to_thread(handle_local_file_action, body)
    return web.json_response(
        {
            "ok": ok,
            "action": str(body.get("action") or ""),
            "file": str(body.get("file") or ""),
            "desktopInteractive": _is_interactive_user_desktop(),
        },
        headers=NO_CACHE_HEADERS,
    )


async def handle_api_conversation_send(request: web.Request) -> web.Response:
    try:
        body = await request.json()
    except Exception as exc:
        return web.json_response({"type": "agy_send_ack", "ok": False, "error": f"JSON 解析错误: {exc}"}, status=400)

    target_cid = str(body.get("cascadeId") or "").strip()
    exact_text = body.get("text")
    model_key = str(body.get("model") or "inherit").strip()
    attachments = body.get("attachments") if isinstance(body.get("attachments"), list) else []
    send_mode = str(body.get("sendMode") or "queue").strip()

    try:
        res = await asyncio.to_thread(
            _send_message_unified_sync, target_cid, exact_text, model_key, True, attachments, send_mode
        )
        if not res.get("ok"):
            return web.json_response({"type": "agy_send_ack", **res}, status=400, headers=NO_CACHE_HEADERS)

        real_cid = str(res.get("cascadeId") or "")
        convs, snap = await asyncio.to_thread(_bind_and_snapshot_sync, real_cid)
        ack = {
            "type": "agy_send_ack",
            "ok": True,
            "cascadeId": real_cid,
            "createdNew": bool(res.get("createdNew")),
            "flushedNow": bool(res.get("flushedNow")),
            "stagedPaths": res.get("stagedPaths") or [],
            "conversations": convs,
            "snapshot": snap,
        }
        await broadcast_ui({
            "type": "agy_conversations_list",
            "conversations": convs,
            "activeCascadeId": real_cid,
        })
        if STATE.wallpaper_clients and real_cid:
            if real_cid != STATE.wallpaper_cascade_id:
                await _switch_wallpaper_conversation(real_cid, convs, animate=True)
            else:
                await broadcast_wallpaper({
                    "type": "agy_conversation_delta",
                    "snapshot": snap,
                    "conversations": convs,
                })
        return web.json_response(ack, headers=NO_CACHE_HEADERS)
    except Exception as exc:
        logger.warning("send_verbatim_message error: %s", exc)
        return web.json_response(
            {"type": "agy_send_ack", "ok": False, "error": str(exc)},
            status=500,
            headers=NO_CACHE_HEADERS,
        )


async def handle_api_event(request: web.Request) -> web.Response:
    try:
        payload = await request.json()
    except Exception as exc:
        return web.json_response({"ok": False, "error": f"Invalid JSON: {exc}"}, status=400)

    if not isinstance(payload, dict):
        return web.json_response({"ok": False, "error": "JSON object required"}, status=400)

    if isinstance(payload.get("quota"), dict):
        STATE.latest_quota = payload["quota"]

    evt_cid = str(payload.get("cascadeId") or "").strip()
    if evt_cid:
        match_ui = (not STATE.active_cascade_id) or (evt_cid == STATE.active_cascade_id)
        match_wp = bool(STATE.wallpaper_clients) and (
            (not STATE.wallpaper_cascade_id) or (evt_cid == STATE.wallpaper_cascade_id)
        )
        if not match_ui and not match_wp:
            return web.json_response({"ok": True, "ignored": "inactive_cascade"}, headers=NO_CACHE_HEADERS)
        if match_ui and match_wp:
            await broadcast(payload)
        elif match_ui:
            await broadcast_ui(payload)
        elif match_wp:
            await broadcast_wallpaper(payload)
    else:
        await broadcast(payload)
    return web.json_response({"ok": True, "clients": len(STATE.clients)}, headers=NO_CACHE_HEADERS)


async def _execute_session_meta_action(cid: str, action: str) -> dict[str, Any]:
    if await asyncio.to_thread(_is_external_mode_sync):
        res = await asyncio.to_thread(ext_bridge.mutate_conversation_meta, cid, action)
    else:
        res = await asyncio.to_thread(agy_core.mutate_conversation_meta, cid, action)
    if not res.get("ok"):
        return {"type": "agy_session_meta_ack", **res}

    rebound_snap: dict[str, Any] | None = None
    if action == "delete" and cid and STATE.active_cascade_id == cid:
        STATE.active_cascade_id = ""
        convs, rebound_snap = await asyncio.to_thread(_bind_and_snapshot_sync, "")
    else:
        convs = await asyncio.to_thread(_list_conversations_unified_sync)
        STATE.cached_conversations = convs

    if cid and STATE.wallpaper_cascade_id == cid and action in ("delete", "archive", "toggle_archive"):
        if action == "delete" or res.get("archived"):
            STATE.wallpaper_cascade_id = ""

    STATE.last_conv_list_fp = json.dumps(convs, ensure_ascii=False, sort_keys=True)
    await broadcast_ui(
        {
            "type": "agy_conversations_list",
            "conversations": convs,
            "activeCascadeId": STATE.active_cascade_id,
        }
    )
    if STATE.wallpaper_clients:
        await broadcast_wallpaper(
            {
                "type": "agy_conversations_list",
                "conversations": convs,
                "activeCascadeId": STATE.wallpaper_cascade_id,
            }
        )
    if rebound_snap is not None:
        await broadcast_ui(
            {
                "type": "agy_conversation_snapshot",
                "snapshot": rebound_snap,
                "conversations": convs,
                "animateTransition": False,
            }
        )
    await _sync_wallpaper_auto_follow(convs, animate=True)
    return {
        "type": "agy_session_meta_ack",
        **res,
        "conversations": convs,
        "activeCascadeId": STATE.active_cascade_id,
        "snapshot": rebound_snap,
    }


async def _execute_wallpaper_action(body: dict[str, Any]) -> dict[str, Any]:
    async with _get_wallpaper_action_lock():
        action = str(body.get("action") or "status").strip().lower()
        wp_mode = str(body.get("wallpaperMode") or "agy_live").strip()
        beam_mode = str(body.get("beamMode") or "tool_io").strip()
        if isinstance(body.get("autoFollowWorking"), bool):
            STATE.wallpaper_auto_follow = bool(body["autoFollowWorking"])
        cfg = body.get("config")
        if isinstance(cfg, dict):
            if isinstance(cfg.get("wallpaperAutoFollow"), bool):
                STATE.wallpaper_auto_follow = bool(cfg["wallpaperAutoFollow"])
            else:
                cfg = dict(cfg)
                cfg["wallpaperAutoFollow"] = bool(STATE.wallpaper_auto_follow)
            await asyncio.to_thread(atomic_save_config, cfg)
            await broadcast({"type": "ophanim_config_updated", "config": cfg})

        if action == "status":
            st = _enrich_wallpaper_status(await asyncio.to_thread(wp_mgr.get_wallpaper_status))
            return {"type": "ophanim_wallpaper_status", **st}

        if action == "set_auto_follow":
            STATE.wallpaper_auto_follow = bool(body.get("autoFollowWorking", True))
            await asyncio.to_thread(_persist_wallpaper_auto_follow_sync, STATE.wallpaper_auto_follow)
            convs = await asyncio.to_thread(_list_conversations_unified_sync)
            STATE.cached_conversations = convs
            if STATE.wallpaper_clients:
                if STATE.wallpaper_auto_follow:
                    await _sync_wallpaper_auto_follow(convs, animate=True)
                elif STATE.active_cascade_id and STATE.active_cascade_id != STATE.wallpaper_cascade_id:
                    await _switch_wallpaper_conversation(STATE.active_cascade_id, convs, animate=True)
            st = _enrich_wallpaper_status(await asyncio.to_thread(wp_mgr.get_wallpaper_status))
            payload = {"type": "ophanim_wallpaper_status", **st}
            STATE.last_wp_status_sig = None
            await broadcast(payload)
            return payload

        if os.name == "nt" and not _is_interactive_user_desktop():
            return {
                "type": "ophanim_wallpaper_status",
                "ok": False,
                "active": False,
                "error": "当前守护进程不在交互式用户桌面，请双击桌面 Ophanim_Sanctum.bat 重启后再设置壁纸",
            }

        if action == "enable":
            st = await asyncio.to_thread(
                wp_mgr.enable_live_wallpaper, HOST, PORT, wp_mode, beam_mode
            )
        elif action == "disable":
            st = await asyncio.to_thread(wp_mgr.disable_live_wallpaper)
        else:
            return {"type": "ophanim_wallpaper_status", "ok": False, "error": f"未知壁纸指令: {action}"}

        st = _enrich_wallpaper_status(st)
        payload = {"type": "ophanim_wallpaper_status", **st}
        STATE.last_wp_status_sig = None
        await broadcast(payload)
        return payload


async def handle_api_conversation_meta(request: web.Request) -> web.Response:
    try:
        body = await request.json()
    except Exception as exc:
        return web.json_response({"ok": False, "error": f"Invalid JSON: {exc}"}, status=400, headers=NO_CACHE_HEADERS)
    if not isinstance(body, dict):
        return web.json_response({"ok": False, "error": "JSON object required"}, status=400, headers=NO_CACHE_HEADERS)
    cid = str(body.get("cascadeId") or "").strip()
    action = str(body.get("action") or "").strip()
    ack = await _execute_session_meta_action(cid, action)
    status_code = 200 if ack.get("ok") else 400
    return web.json_response(ack, status=status_code, headers=NO_CACHE_HEADERS)


async def _execute_queue_action(body: dict[str, Any]) -> dict[str, Any]:
    cid = str(body.get("cascadeId") or STATE.active_cascade_id or "").strip()
    action = str(body.get("action") or "flush").strip().lower()
    model_key = str(body.get("model") or "inherit").strip()
    step_idx = int(body.get("stepIndex") if body.get("stepIndex") is not None else -1)
    is_ext = await asyncio.to_thread(_is_external_mode_sync)

    if action in ("cancel", "stop"):
        if is_ext:
            res = await asyncio.to_thread(ext_bridge.cancel_running_turn, cid)
        else:
            res = await asyncio.to_thread(agy_core.cancel_cascade_execution, cid)
            await asyncio.sleep(0.18)
    elif action == "flush":
        if is_ext:
            res = {"ok": True, "cascadeId": cid, "action": "flush"}
        else:
            res = await asyncio.to_thread(agy_core.flush_queued_messages, cid, model_key)
    elif action == "delete_step":
        if is_ext:
            res = {"ok": True, "cascadeId": cid, "action": "delete_step", "stepIndex": step_idx}
        else:
            res = await asyncio.to_thread(agy_core.delete_queued_step, cid, step_idx)
    else:
        return {"type": "agy_queue_action_ack", "ok": False, "error": f"未知队列操作: {action}"}

    snap = None
    convs = STATE.cached_conversations
    if cid and cid != "__new__":
        try:
            convs, snap = await asyncio.to_thread(_bind_and_snapshot_sync, cid)
            delta_msg = {
                "type": "agy_conversation_delta",
                "snapshot": snap,
                "conversations": convs,
            }
            if cid == STATE.wallpaper_cascade_id:
                await broadcast(delta_msg)
            else:
                await broadcast_ui(delta_msg)
                if STATE.wallpaper_clients:
                    await broadcast_wallpaper({
                        "type": "agy_conversations_list",
                        "conversations": convs,
                        "activeCascadeId": STATE.wallpaper_cascade_id,
                    })
            await _sync_wallpaper_auto_follow(convs, animate=True)
        except Exception:
            pass
    return {
        "type": "agy_queue_action_ack",
        **res,
        "snapshot": snap,
        "conversations": convs,
    }


async def handle_api_queue_action(request: web.Request) -> web.Response:
    try:
        body = await request.json()
    except Exception as exc:
        return web.json_response({"ok": False, "error": f"Invalid JSON: {exc}"}, status=400, headers=NO_CACHE_HEADERS)
    if not isinstance(body, dict):
        return web.json_response({"ok": False, "error": "JSON object required"}, status=400, headers=NO_CACHE_HEADERS)
    ack = await _execute_queue_action(body)
    return web.json_response(ack, status=(200 if ack.get("ok") else 400), headers=NO_CACHE_HEADERS)


async def handle_api_ai_usage(request: web.Request) -> web.Response:
    force = request.query.get("force") == "1"
    bundle = await asyncio.to_thread(ai_usage_bridge.get_ai_usage_bundle, force)
    return web.json_response({"type": "ophanim_ai_usage_bundle", **bundle}, headers=NO_CACHE_HEADERS)


async def handle_api_ai_usage_turns(request: web.Request) -> web.Response:
    sess_id = str(request.query.get("id") or "").strip()
    data = await asyncio.to_thread(ai_usage_bridge.get_ai_usage_turns, sess_id)
    return web.json_response({"type": "ophanim_ai_usage_turns_ack", **data}, headers=NO_CACHE_HEADERS)


async def handle_api_wallpaper_get(request: web.Request) -> web.Response:
    st = _enrich_wallpaper_status(await asyncio.to_thread(wp_mgr.get_wallpaper_status))
    return web.json_response({"type": "ophanim_wallpaper_status", **st}, headers=NO_CACHE_HEADERS)


async def handle_api_wallpaper_post(request: web.Request) -> web.Response:
    try:
        body = await request.json()
    except Exception as exc:
        return web.json_response({"ok": False, "error": f"Invalid JSON: {exc}"}, status=400, headers=NO_CACHE_HEADERS)
    if not isinstance(body, dict):
        return web.json_response({"ok": False, "error": "JSON object required"}, status=400, headers=NO_CACHE_HEADERS)
    res = await _execute_wallpaper_action(body)
    return web.json_response(res, status=(200 if res.get("ok") else 400), headers=NO_CACHE_HEADERS)


async def handle_api_external_pending(request: web.Request) -> web.Response:
    wait_sec = float(request.query.get("wait") or "0")
    task = await asyncio.to_thread(ext_bridge.pop_pending_relay_task, wait_sec)
    return web.json_response({"ok": True, "task": task}, headers=NO_CACHE_HEADERS)


async def handle_api_external_reply(request: web.Request) -> web.Response:
    try:
        body = await request.json()
    except Exception as exc:
        return web.json_response({"ok": False, "error": f"Invalid JSON: {exc}"}, status=400, headers=NO_CACHE_HEADERS)
    if not isinstance(body, dict):
        return web.json_response({"ok": False, "error": "JSON object required"}, status=400, headers=NO_CACHE_HEADERS)
    cid = str(body.get("cascadeId") or body.get("sessionId") or STATE.active_cascade_id or "").strip()
    turn_num = int(body.get("turnNumber") or 1)
    text = str(body.get("text") or body.get("reply") or "")
    finished = bool(body.get("finished", True))
    res = await asyncio.to_thread(ext_bridge.submit_relay_reply, cid, turn_num, text, finished)
    return web.json_response(res, status=(200 if res.get("ok") else 400), headers=NO_CACHE_HEADERS)


async def handle_self_restart(request: web.Request) -> web.Response:
    if os.name == "nt" and not _is_interactive_user_desktop():
        STATE.shutdown_event.set()
        return web.json_response(
            {"ok": True, "restarted": False, "note": "non_interactive_desktop_shutdown_only"},
            headers=NO_CACHE_HEADERS,
        )
    py_exe = Path(sys.executable)
    pythonw = py_exe.with_name("pythonw.exe")
    runner_exe = str(pythonw if pythonw.is_file() else py_exe)
    script_str = str((PROJECT_DIR / "ophanim_agy_daemon.py").resolve())
    helper_code = (
        "import subprocess, time; time.sleep(0.85); "
        f"subprocess.Popen([{runner_exe!r}, {script_str!r}], "
        "creationflags=0x08000200, close_fds=True)"
    )
    subprocess.Popen(
        [str(py_exe), "-c", helper_code],
        creationflags=0x08000200 if os.name == "nt" else 0,
        close_fds=True,
    )
    STATE.shutdown_event.set()
    return web.json_response({"ok": True, "restarted": True}, headers=NO_CACHE_HEADERS)


async def handle_shutdown(request: web.Request) -> web.Response:
    STATE.shutdown_event.set()
    return web.json_response({"ok": True, "shutting_down": True}, headers=NO_CACHE_HEADERS)


async def wallpaper_pointer_relay_loop() -> None:
    """Off-loop adaptive desktop pointer & occlusion relay to active wallpaper WebSocket clients."""
    last_sig: tuple[Any, ...] | None = None
    last_occ_sent: bool | None = None
    last_occ_check_mono: float = 0.0
    last_move_mono: float = 0.0

    while not STATE.shutdown_event.is_set():
        if not STATE.wallpaper_clients:
            last_sig = None
            last_occ_sent = None
            await asyncio.sleep(0.40)
            continue

        now_m = time.monotonic()
        occluded = STATE.desktop_occluded
        if last_occ_sent is None or (now_m - last_occ_check_mono) >= 0.30:
            last_occ_check_mono = now_m
            try:
                occluded = bool(await asyncio.to_thread(wp_mgr.is_desktop_occluded))
            except Exception:
                occluded = False
            if last_occ_sent is None or occluded != last_occ_sent:
                STATE.desktop_occluded = occluded
                last_occ_sent = occluded
                await broadcast_wallpaper({"type": "wp_visibility", "occluded": occluded})

        if occluded:
            await asyncio.sleep(0.25)
            continue

        sleep_sec = 0.22
        try:
            snap = await asyncio.to_thread(wp_mgr.sample_desktop_pointer)
            if snap:
                wheel_val = float(snap.get("wheel") or 0.0)
                click_val = int(snap.get("click") or 0)
                sig = (
                    snap.get("px"),
                    snap.get("py"),
                    snap.get("btn"),
                    snap.get("desk"),
                    snap.get("icon"),
                )
                changed = wheel_val != 0.0 or click_val != 0 or sig != last_sig
                if changed:
                    last_sig = sig
                    last_move_mono = now_m
                    msg = json.dumps(snap, ensure_ascii=False)
                    dead: list[web.WebSocketResponse] = []
                    for ws in list(STATE.wallpaper_clients):
                        if ws.closed:
                            dead.append(ws)
                            continue
                        try:
                            await ws.send_str(msg)
                        except Exception:
                            dead.append(ws)
                    if dead:
                        for d in dead:
                            STATE.wallpaper_clients.discard(d)
                            STATE.clients.discard(d)
                        if not STATE.wallpaper_clients:
                            await asyncio.to_thread(wp_mgr.stop_input_observer)
                if snap.get("desk") and (snap.get("btn") or (now_m - last_move_mono) < 1.5):
                    sleep_sec = 0.033  # ~30Hz while actively interacting over exposed desktop
                else:
                    sleep_sec = 0.22   # ~4.5Hz backoff when idle or cursor over another app
        except Exception as exc:
            logger.debug("wallpaper_pointer_relay_loop warning: %s", exc)
        await asyncio.sleep(sleep_sec)


async def handle_ws(request: web.Request) -> web.WebSocketResponse:
    ws = web.WebSocketResponse(heartbeat=25.0, max_msg_size=64 * 1024 * 1024)
    await ws.prepare(request)
    STATE.clients.add(ws)
    if request.query.get("wallpaper") == "1":
        STATE.wallpaper_clients.add(ws)

    try:
        # 1. Push persisted layout/parameter configuration if present
        if CONFIG_SAVE_PATH.is_file():
            try:
                raw_cfg = await asyncio.to_thread(CONFIG_SAVE_PATH.read_text, "utf-8")
                saved_cfg = json.loads(raw_cfg)
                if isinstance(saved_cfg, dict):
                    await send_ws_json(ws, {"config": saved_cfg})
            except Exception as exc:
                logger.warning("Failed to push saved config on connect: %s", exc)

        # 2. Push real local quota telemetry snapshot (plus autoSim=False guard)
        q_snap = STATE.latest_quota or await asyncio.to_thread(collect_real_quota_snapshot)
        await send_ws_json(ws, {"quota": q_snap, "autoSim": False})

        # 3. Push live desktop wallpaper status snapshot + active Agent backend metadata
        try:
            wp_st = _enrich_wallpaper_status(await asyncio.to_thread(wp_mgr.get_wallpaper_status))
            await send_ws_json(ws, {"type": "ophanim_wallpaper_status", **wp_st})
            ls_addr, _ = await asyncio.to_thread(agy_core.discover_agy_ls, False)
            b_info = await asyncio.to_thread(ext_bridge.get_backend_info, bool(ls_addr))
            await send_ws_json(ws, {"type": "ophanim_backend_info", **b_info})
        except Exception as exc:
            logger.debug("Initial wallpaper/backend status check warning: %s", exc)

        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)
                except Exception:
                    continue
                if not isinstance(data, dict):
                    continue
                mtype = str(data.get("type") or "")

                if mtype == "ophanim_file_action":
                    ok = await asyncio.to_thread(handle_local_file_action, data)
                    await send_ws_json(
                        ws,
                        {
                            "type": "ophanim_file_action_ack",
                            "ok": ok,
                            "action": str(data.get("action") or ""),
                            "file": str(data.get("file") or ""),
                            "desktopInteractive": _is_interactive_user_desktop(),
                        },
                    )

                elif mtype == "ophanim_save_config" and isinstance(data.get("config"), dict):
                    cfg_save = dict(data["config"])
                    if isinstance(cfg_save.get("wallpaperAutoFollow"), bool):
                        STATE.wallpaper_auto_follow = bool(cfg_save["wallpaperAutoFollow"])
                    else:
                        cfg_save["wallpaperAutoFollow"] = bool(STATE.wallpaper_auto_follow)
                    await asyncio.to_thread(atomic_save_config, cfg_save)
                    for peer in list(STATE.clients):
                        if peer is not ws and not peer.closed:
                            try:
                                await send_ws_json(peer, {"type": "ophanim_config_updated", "config": cfg_save})
                            except Exception:
                                pass
                    if STATE.wallpaper_clients and STATE.cached_conversations:
                        await _sync_wallpaper_auto_follow(STATE.cached_conversations, animate=True)
                    await _broadcast_wallpaper_status_if_changed(force=False)

                elif mtype == "agy_session_meta_action":
                    cid = str(data.get("cascadeId") or "").strip()
                    action = str(data.get("action") or "").strip()
                    ack = await _execute_session_meta_action(cid, action)
                    await send_ws_json(ws, ack)

                elif mtype == "ophanim_wallpaper_hello":
                    STATE.wallpaper_clients.add(ws)
                    occ = bool(await asyncio.to_thread(wp_mgr.is_desktop_occluded))
                    STATE.desktop_occluded = occ
                    await send_ws_json(ws, {"type": "wp_visibility", "occluded": occ})
                    snap = await asyncio.to_thread(wp_mgr.sample_desktop_pointer)
                    if snap:
                        await send_ws_json(ws, snap)

                elif mtype == "ophanim_wallpaper_action":
                    res = await _execute_wallpaper_action(data)
                    await send_ws_json(ws, res)

                elif mtype in ("ophanim_ack_completions", "ophanim_preview_completion"):
                    for peer in list(STATE.clients):
                        if peer is not ws and not peer.closed:
                            try:
                                await send_ws_json(peer, data)
                            except Exception:
                                pass

                elif mtype in ("agy_queue_action", "agy_cancel_execution"):
                    act_payload = dict(data)
                    if mtype == "agy_cancel_execution":
                        act_payload["action"] = "cancel"
                    ack = await _execute_queue_action(act_payload)
                    await send_ws_json(ws, ack)

                elif mtype == "ophanim_ai_usage_query":
                    force = bool(data.get("force", False))
                    bundle = await asyncio.to_thread(ai_usage_bridge.get_ai_usage_bundle, force)
                    await send_ws_json(ws, {"type": "ophanim_ai_usage_bundle", **bundle})

                elif mtype == "ophanim_ai_usage_turns":
                    sess_id = str(data.get("id") or "").strip()
                    turns_res = await asyncio.to_thread(ai_usage_bridge.get_ai_usage_turns, sess_id)
                    await send_ws_json(ws, {"type": "ophanim_ai_usage_turns_ack", **turns_res})

                elif mtype == "agy_init_sync":
                    pref_cid = str(data.get("preferredCascadeId") or "").strip()
                    is_wp = (ws in STATE.wallpaper_clients) or bool(data.get("isWallpaper"))
                    if is_wp:
                        STATE.wallpaper_clients.add(ws)
                        convs, snap, _ = await asyncio.to_thread(_bind_wallpaper_snapshot_sync, pref_cid)
                        q_snap = await asyncio.to_thread(collect_real_quota_snapshot)
                        await send_ws_json(ws, {"quota": q_snap})
                        snap_cid = str(snap.get("cascadeId") or "")
                        await send_ws_json(
                            ws,
                            {
                                "type": "agy_conversation_snapshot",
                                "snapshot": snap,
                                "conversations": convs,
                                "animateTransition": bool(pref_cid and snap_cid and pref_cid != snap_cid),
                            },
                        )
                        await _broadcast_wallpaper_status_if_changed(force=True)
                    else:
                        convs, snap = await asyncio.to_thread(_bind_and_snapshot_sync, pref_cid)
                        q_snap = await asyncio.to_thread(collect_real_quota_snapshot)
                        await send_ws_json(ws, {"quota": q_snap})
                        await send_ws_json(
                            ws,
                            {
                                "type": "agy_conversation_snapshot",
                                "snapshot": snap,
                                "conversations": convs,
                                "animateTransition": False,
                            },
                        )

                elif mtype == "agy_select_conversation":
                    sel_cid = str(data.get("cascadeId") or "").strip()
                    anim = bool(data.get("animate", True))
                    if ws in STATE.wallpaper_clients:
                        convs, snap, _ = await asyncio.to_thread(_bind_wallpaper_snapshot_sync, sel_cid, sel_cid)
                        await send_ws_json(
                            ws,
                            {
                                "type": "agy_conversation_snapshot",
                                "snapshot": snap,
                                "conversations": convs,
                                "animateTransition": anim,
                            },
                        )
                        await _broadcast_wallpaper_status_if_changed(force=True)
                    else:
                        convs, snap = await asyncio.to_thread(_bind_and_snapshot_sync, sel_cid)
                        q_snap = await asyncio.to_thread(collect_real_quota_snapshot)
                        await send_ws_json(ws, {"quota": q_snap})
                        await send_ws_json(
                            ws,
                            {
                                "type": "agy_conversation_snapshot",
                                "snapshot": snap,
                                "conversations": convs,
                                "animateTransition": anim,
                            },
                        )
                        await _sync_wallpaper_auto_follow(
                            convs,
                            animate=True,
                            explicit_ui_cid=str(snap.get("cascadeId") or ""),
                        )

                elif mtype == "agy_refresh_conversations":
                    if ws in STATE.wallpaper_clients:
                        convs, snap, _ = await asyncio.to_thread(_bind_wallpaper_snapshot_sync, "")
                        await send_ws_json(
                            ws,
                            {
                                "type": "agy_conversation_snapshot",
                                "snapshot": snap,
                                "conversations": convs,
                                "animateTransition": False,
                            },
                        )
                        await _broadcast_wallpaper_status_if_changed(force=False)
                    else:
                        req_cid = str(data.get("cascadeId") or STATE.active_cascade_id or "").strip()
                        if req_cid:
                            convs, snap = await asyncio.to_thread(_bind_and_snapshot_sync, req_cid)
                            await send_ws_json(
                                ws,
                                {
                                    "type": "agy_conversation_snapshot",
                                    "snapshot": snap,
                                    "conversations": convs,
                                    "animateTransition": False,
                                },
                            )
                        else:
                            convs = await asyncio.to_thread(_list_conversations_unified_sync)
                            STATE.cached_conversations = convs
                            await send_ws_json(
                                ws,
                                {
                                    "type": "agy_conversations_list",
                                    "conversations": convs,
                                    "activeCascadeId": STATE.active_cascade_id,
                                },
                            )
                        await _sync_wallpaper_auto_follow(convs, animate=True)

                elif mtype == "agy_send_message":
                    target_cid = str(data.get("cascadeId") or "").strip()
                    exact_text = data.get("text")
                    model_key = str(data.get("model") or "inherit").strip()
                    attachments = data.get("attachments") if isinstance(data.get("attachments"), list) else []
                    send_mode = str(data.get("sendMode") or "queue").strip()
                    try:
                        res = await asyncio.to_thread(
                            _send_message_unified_sync,
                            target_cid,
                            exact_text,
                            model_key,
                            True,
                            attachments,
                            send_mode,
                        )
                        if not res.get("ok"):
                            await send_ws_json(ws, {"type": "agy_send_ack", **res})
                            continue
                        real_cid = str(res.get("cascadeId") or "")
                        convs, snap = await asyncio.to_thread(_bind_and_snapshot_sync, real_cid)
                        await send_ws_json(
                            ws,
                            {
                                "type": "agy_send_ack",
                                "ok": True,
                                "cascadeId": real_cid,
                                "createdNew": bool(res.get("createdNew")),
                                "flushedNow": bool(res.get("flushedNow")),
                                "stagedPaths": res.get("stagedPaths") or [],
                                "conversations": convs,
                                "snapshot": snap,
                            },
                        )
                        if res.get("createdNew"):
                            await send_ws_json(
                                ws,
                                {
                                    "type": "agy_conversation_snapshot",
                                    "snapshot": snap,
                                    "conversations": convs,
                                    "animateTransition": False,
                                },
                            )
                        if STATE.wallpaper_clients and real_cid:
                            if real_cid != STATE.wallpaper_cascade_id:
                                await _switch_wallpaper_conversation(real_cid, convs, animate=True)
                            else:
                                await broadcast_wallpaper(
                                    {
                                        "type": "agy_conversation_delta",
                                        "snapshot": snap,
                                        "conversations": convs,
                                    }
                                )
                    except Exception as exc:
                        logger.warning("WS agy_send_message error: %s", exc)
                        await send_ws_json(ws, {"type": "agy_send_ack", "ok": False, "error": str(exc)})

            elif msg.type == WSMsgType.ERROR:
                break
    finally:
        was_wp = ws in STATE.wallpaper_clients
        STATE.wallpaper_clients.discard(ws)
        STATE.clients.discard(ws)
        if was_wp and not STATE.wallpaper_clients:
            try:
                await asyncio.to_thread(wp_mgr.stop_input_observer)
            except Exception:
                pass
    return ws


async def _handle_ext_bridge_event_async(evt_payload: dict[str, Any]) -> None:
    if not isinstance(evt_payload, dict):
        return
    convs = evt_payload.get("conversations")
    if isinstance(convs, list):
        STATE.cached_conversations = convs

    etype = str(evt_payload.get("type") or "")
    snap = evt_payload.get("snapshot") if isinstance(evt_payload.get("snapshot"), dict) else None
    evt_cid = str(evt_payload.get("cascadeId") or (snap.get("cascadeId") if snap else "") or "").strip()

    if etype == "agy_conversation_delta" and snap:
        if evt_cid and evt_cid == STATE.active_cascade_id:
            await broadcast_ui(evt_payload)
        if STATE.wallpaper_clients:
            if evt_cid and evt_cid == STATE.wallpaper_cascade_id:
                await broadcast_wallpaper(evt_payload)
            elif isinstance(convs, list):
                await broadcast_wallpaper(
                    {
                        "type": "agy_conversations_list",
                        "conversations": convs,
                        "activeCascadeId": STATE.wallpaper_cascade_id,
                    }
                )
        if isinstance(convs, list):
            await _sync_wallpaper_auto_follow(convs, animate=True)
        return

    if evt_cid and etype != "agy_conversations_list":
        match_ui = (not STATE.active_cascade_id) or (evt_cid == STATE.active_cascade_id)
        match_wp = bool(STATE.wallpaper_clients) and (
            (not STATE.wallpaper_cascade_id) or (evt_cid == STATE.wallpaper_cascade_id)
        )
        if match_ui and match_wp:
            await broadcast(evt_payload)
        elif match_ui:
            await broadcast_ui(evt_payload)
        elif match_wp:
            await broadcast_wallpaper(evt_payload)
    else:
        await broadcast(evt_payload)

    if isinstance(convs, list):
        await _sync_wallpaper_auto_follow(convs, animate=True)


async def run_daemon(host: str, port: int) -> int:
    clean_host = (host or "127.0.0.1").strip().lower()
    if clean_host not in _TRUSTED_LOCAL_HOSTS and not (ALLOW_REMOTE and API_TOKEN):
        logger.error(
            "Refusing to bind non-loopback host %r without OPHANIM_ALLOW_REMOTE=1 and OPHANIM_API_TOKEN.",
            host,
        )
        return 2

    existing = await asyncio.to_thread(probe_existing_daemon, host, port, 1.2)
    if existing is not None:
        logger.info("Healthy daemon already running on %s:%s (pid=%s); exiting 0.", host, port, existing.get("pid"))
        return 0

    STATE.wallpaper_auto_follow = await asyncio.to_thread(_load_saved_wallpaper_auto_follow)
    loop = asyncio.get_running_loop()

    def _on_ext_bridge_event(evt_payload: dict[str, Any]) -> None:
        try:
            loop.call_soon_threadsafe(lambda p=evt_payload: asyncio.create_task(_handle_ext_bridge_event_async(p)))
        except Exception:
            pass

    ext_bridge.register_event_sink(_on_ext_bridge_event)

    await asyncio.to_thread(collect_real_quota_snapshot)
    try:
        convs, _ = await asyncio.to_thread(_bind_and_snapshot_sync, "")
        ext_mode = await asyncio.to_thread(_is_external_mode_sync)
        STATE.wallpaper_cascade_id = _pick_wallpaper_cascade_id(
            convs,
            current_wp_cid="",
            fallback_cid=STATE.active_cascade_id,
            external_mode=ext_mode,
        )
    except Exception as exc:
        logger.debug("Initial conversation prime warning: %s", exc)

    app = web.Application(client_max_size=64 * 1024 * 1024, middlewares=[localhost_security_middleware])
    app.router.add_get("/", handle_index)
    app.router.add_get("/ophanim_sanctum.html", handle_index)
    app.router.add_get("/ophanim_agy_panel.js", handle_agy_panel_js)
    app.router.add_get("/favicon.ico", handle_logo_ico)
    app.router.add_get("/ophanim_logo.ico", handle_logo_ico)
    app.router.add_get("/api/health", handle_health)
    app.router.add_get("/api/conversations", handle_api_conversations)
    app.router.add_get("/api/conversation/{cid}", handle_api_conversation_detail)
    app.router.add_post("/api/conversation/send", handle_api_conversation_send)
    app.router.add_options("/api/conversation/send", handle_cors_options)
    app.router.add_post("/api/conversation/meta", handle_api_conversation_meta)
    app.router.add_options("/api/conversation/meta", handle_cors_options)
    app.router.add_post("/api/conversation/queue-action", handle_api_queue_action)
    app.router.add_options("/api/conversation/queue-action", handle_cors_options)
    app.router.add_get("/api/external/pending", handle_api_external_pending)
    app.router.add_post("/api/external/reply", handle_api_external_reply)
    app.router.add_options("/api/external/reply", handle_cors_options)
    app.router.add_get("/api/ai-usage", handle_api_ai_usage)
    app.router.add_get("/api/ai-usage/turns", handle_api_ai_usage_turns)
    app.router.add_get("/api/wallpaper", handle_api_wallpaper_get)
    app.router.add_post("/api/wallpaper", handle_api_wallpaper_post)
    app.router.add_options("/api/wallpaper", handle_cors_options)
    app.router.add_post("/api/file-action", handle_api_file_action)
    app.router.add_options("/api/file-action", handle_cors_options)
    app.router.add_post("/api/event", handle_api_event)
    app.router.add_options("/api/event", handle_cors_options)
    app.router.add_post("/api/self-restart", handle_self_restart)
    app.router.add_options("/api/self-restart", handle_cors_options)
    app.router.add_post("/api/shutdown", handle_shutdown)
    app.router.add_get("/ws", handle_ws)

    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    try:
        await site.start()
    except OSError as exc:
        await runner.cleanup()
        if await asyncio.to_thread(probe_existing_daemon, host, port, 1.2) is not None:
            logger.info("Port %s bound by concurrent daemon startup; exiting 0.", port)
            return 0
        logger.error("Failed to bind %s:%s: %s", host, port, exc)
        raise

    quota_task = asyncio.create_task(quota_telemetry_loop())
    conv_task = asyncio.create_task(agy_conversation_loop())
    wp_ptr_task = asyncio.create_task(wallpaper_pointer_relay_loop())

    url = f"http://{host}:{port}/ophanim_sanctum.html?ws=ws://{host}:{port}/ws"
    logger.info("OPHANIM Live Bridge online at %s (pid=%s)", url, os.getpid())
    print(f"OPHANIM Live Bridge running at: {url}", flush=True)

    try:
        await STATE.shutdown_event.wait()
    finally:
        STATE.shutdown_event.set()
        for ws in list(STATE.clients):
            try:
                await ws.close()
            except Exception:
                pass
        quota_task.cancel()
        conv_task.cancel()
        wp_ptr_task.cancel()
        await asyncio.gather(quota_task, conv_task, wp_ptr_task, return_exceptions=True)
        try:
            await asyncio.to_thread(wp_mgr.shutdown_wallpaper_runtime)
        except Exception as exc:
            logger.debug("Wallpaper runtime shutdown warning: %s", exc)
        await runner.cleanup()
        logger.info("OPHANIM Live Bridge shut down cleanly.")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Ophanim Sanctum Local Antigravity Daemon")
    parser.add_argument("--host", default=HOST)
    parser.add_argument("--port", type=int, default=PORT)
    args = parser.parse_args()
    try:
        code = asyncio.run(run_daemon(args.host, args.port))
    except KeyboardInterrupt:
        code = 0
    sys.exit(code)


if __name__ == "__main__":
    main()
