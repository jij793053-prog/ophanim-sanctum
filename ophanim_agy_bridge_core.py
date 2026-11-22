#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ophanim_agy_bridge_core.py
Real-time bidirectional bridge between Ophanim Sanctum (`ophanim_agy_daemon.py`)
and local Google Antigravity IDE (`LanguageServerService` Connect-RPC +
`~/.gemini/antigravity/brain/<cid>` transcripts & `/swarm` metadata).
Zero mock data, zero unrelated background file noise.
"""
from __future__ import annotations

import base64
from collections import OrderedDict
import copy
from datetime import datetime, timezone
import json
import logging
import mimetypes
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import threading
import time
from typing import Any
import urllib.error
import urllib.request
import uuid

logger = logging.getLogger("ophanim_agy_bridge")

PROJECT_DIR = Path(__file__).resolve().parent
BRAIN_DIR = Path(os.environ.get("OPHANIM_BRAIN_DIR", str(Path.home() / ".gemini/antigravity/brain")))
DESKTOP_CONV_DIR = Path(os.environ.get("OPHANIM_DESKTOP_CONV_DIR", str(Path.home() / ".gemini/antigravity/conversations")))
DAEMON_HUB_DIR = Path(os.environ.get("OPHANIM_DAEMON_DIR", str(Path.home() / ".gemini/antigravity/daemon")))
CLI_BRAIN_DIR = Path(os.environ.get("OPHANIM_CLI_BRAIN_DIR", str(Path.home() / ".gemini/antigravity-cli/brain")))
CLI_CONV_DIR = Path(os.environ.get("OPHANIM_CLI_CONV_DIR", str(Path.home() / ".gemini/antigravity-cli/conversations")))
DESKTOP_ANN_DIR = Path.home() / ".gemini/antigravity/annotations"
CLI_ANN_DIR = Path.home() / ".gemini/antigravity-cli/annotations"
HERMES_BRIDGE_DIR = Path(os.environ.get("OPHANIM_HERMES_DIR", str(PROJECT_DIR.parent / "hermes-agy-bridge")))
AGY_ENV_FILE = HERMES_BRIDGE_DIR / "agy_env.json"
CASCADE_TEMPLATE_FILE = HERMES_BRIDGE_DIR / "cascade_config_template.json"
_LS_RPC_FAIL_UNTIL: float = 0.0
_OPHANIM_CLI_PROCS: dict[str, subprocess.Popen] = {}
_OPHANIM_CLI_ALIAS: dict[str, str] = {}
_OPHANIM_CLI_LOCK = threading.Lock()
_SCRATCH_ROOT_CAND = PROJECT_DIR.parent.parent / "scratch"
UPLOAD_STAGE_DIR = Path(
    os.environ.get(
        "OPHANIM_UPLOAD_DIR",
        str((_SCRATCH_ROOT_CAND if _SCRATCH_ROOT_CAND.is_dir() else (PROJECT_DIR / ".ophanim_cache")) / "ophanim_uploads"),
    )
)
SESSION_META_FILE = PROJECT_DIR / "ophanim_session_meta.json"

_DIRECT_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)

MODEL_CATALOG_PB: dict[str, dict[str, str]] = {
    "inherit": {"label": "跟随会话当前模型 (默认)", "pb": ""},
    "gemini-4-neon-xhigh": {"label": "Gemini 4 Neon (XHigh)", "pb": "MODEL_PLACEHOLDER_M535"},
    "gemini-4-neon-high": {"label": "Gemini 4 Neon (High)", "pb": "MODEL_PLACEHOLDER_M532"},
    "gemini-4-neon-medium": {"label": "Gemini 4 Neon (Medium)", "pb": "MODEL_PLACEHOLDER_M533"},
    "gemini-4-neon-low": {"label": "Gemini 4 Neon (Low)", "pb": "MODEL_PLACEHOLDER_M534"},
    "gemini-4-hydrogen-xhigh": {"label": "Gemini 4 Hydrogen (XHigh)", "pb": "MODEL_PLACEHOLDER_M528"},
    "gemini-4-hydrogen-high": {"label": "Gemini 4 Hydrogen (High)", "pb": "MODEL_PLACEHOLDER_M525"},
    "gemini-4-hydrogen-medium": {"label": "Gemini 4 Hydrogen (Medium)", "pb": "MODEL_PLACEHOLDER_M526"},
    "gemini-4-hydrogen-low": {"label": "Gemini 4 Hydrogen (Low)", "pb": "MODEL_PLACEHOLDER_M527"},
    "gemini-4-carbon-high": {"label": "Gemini 4 Carbon (High)", "pb": "MODEL_PLACEHOLDER_M427"},
    "gemini-4-carbon-medium": {"label": "Gemini 4 Carbon (Medium)", "pb": "MODEL_PLACEHOLDER_M437"},
    "gemini-4-carbon-low": {"label": "Gemini 4 Carbon (Low)", "pb": "MODEL_PLACEHOLDER_M438"},
    "gemini-4-argon-high": {"label": "Gemini 4 Argon (High)", "pb": "MODEL_PLACEHOLDER_M417"},
    "gemini-4-argon-medium": {"label": "Gemini 4 Argon (Medium)", "pb": "MODEL_PLACEHOLDER_M418"},
    "claude-opus-5-5-high": {"label": "Claude Opus 5.5 (High)", "pb": "MODEL_PLACEHOLDER_M402"},
    "claude-sonnet-5-5-high": {"label": "Claude Sonnet 5.5 (High)", "pb": "MODEL_PLACEHOLDER_M405"},
    "gemini-3.8-flash-high": {"label": "Gemini 3.8 Flash (High)", "pb": "MODEL_PLACEHOLDER_M318"},
}

NOISE_DIR_FRAGMENTS = (
    ".gemini/antigravity/builtin",
    ".gemini/antigravity/mcp",
    ".system_generated",
    "__pycache__",
    "node_modules",
    "ophanim_app_profile",
    "ophanim_app_cache",
    "qq_images",
    "qq_videos",
    "qq_group_files_sandbox",
)

NOISE_FILE_PREFIXES = (
    "_chk",
    "_probe",
    "_verify",
    ".ophanim_config",
    "app_offload_dm_",
    "qq_",
)

NOISE_FILENAMES = {
    "qq_group_memory.json",
    "qq_group_names.json",
    "qq_user_profiles.json",
    "qq_image_desc_cache.json",
    "qq_video_desc_cache.json",
    "qq_memes_catalog.json",
    "qq_memes_rejected.json",
    "qq_poke_state.json",
    "qq_bot_config.json",
    "hermes_foreman_state.json",
    "usage_stats.json",
    "ophanim_config.json",
    "ophanim_session_meta.json",
    "ophanim_wallpaper_state.json",
    "offload_ledger.db",
    "offload_ledger.db-wal",
    "offload_ledger.db-shm",
    "offload_ledger_snapshot.json",
    "daemon.log",
    "daemon_boot.log",
    "launcher.log",
    "agy_env.json",
    "cascade_config_template.json",
}

STRICT_DELIVERABLE_EXTS = {
    ".pdf", ".docx", ".xlsx", ".pptx", ".zip", ".7z",
    ".exe", ".msi", ".apk", ".bat", ".cmd",
    ".png", ".jpg", ".jpeg", ".webp", ".mp4",
}

LINKED_DELIVERABLE_EXTS = STRICT_DELIVERABLE_EXTS | {
    ".html", ".htm", ".md", ".py", ".pyw", ".js", ".ts", ".csv", ".json",
}

DELIVERABLE_FOLDER_NAMES = {"deliverables", "output", "dist", "release", "out", "desktop"}

TEXT_PREVIEW_EXTS = {
    ".py", ".pyw", ".js", ".mjs", ".cjs", ".ts", ".jsx", ".tsx",
    ".html", ".htm", ".css", ".scss", ".json", ".md", ".txt",
    ".c", ".cpp", ".h", ".hpp", ".rs", ".go", ".java",
    ".yaml", ".yml", ".toml", ".ini", ".cfg", ".sh", ".bat", ".cmd", ".ps1", ".sql", ".csv", ".xml",
}

_LS_CACHE_LOCK = threading.Lock()
_LS_CACHE: dict[str, Any] = {"addr": "", "token": "", "ts": 0.0, "port_ts": 0.0, "neg_until": 0.0}
_CASCADE_CFG_CACHE: dict[str, Any] = {"cfg": None, "ts": 0.0}


def format_size(num_bytes: int) -> str:
    if num_bytes >= 1024 * 1024:
        return f"{num_bytes / (1024 * 1024):.2f} MB"
    if num_bytes >= 1024:
        return f"{num_bytes / 1024:.1f} KB"
    return f"{num_bytes} B"


def read_preview(path: Path, max_lines: int = 68, max_bytes: int = 24576) -> str:
    try:
        with open(path, "rb") as fh:
            raw = fh.read(max_bytes)
        if b"\x00" in raw[:512]:
            st = path.stat()
            return (
                f"=== BINARY ARTIFACT ===\n"
                f"File: {path.name}\n"
                f"Size: {format_size(st.st_size)}\n"
                f"Path: {os.path.normpath(str(path))}"
            )
        text = raw.decode("utf-8", errors="replace")
        return "\n".join(text.splitlines()[:max_lines])
    except Exception as exc:
        return f"# Unable to preview: {path.name}\n# {exc}"


def _is_port_alive(addr: str) -> bool:
    if not addr or ":" not in addr:
        return False
    try:
        port = int(addr.rsplit(":", 1)[-1])
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.25)
            return s.connect_ex(("127.0.0.1", port)) == 0
    except Exception:
        return False


def _probe_hub_json_ls() -> tuple[str, str]:
    """Fast pure-Python check of ~/.gemini/antigravity/daemon/hub_*.json before spawning PowerShell."""
    if not DAEMON_HUB_DIR.is_dir():
        return "", ""
    try:
        entries: list[tuple[float, str]] = []
        with os.scandir(DAEMON_HUB_DIR) as it:
            for e in it:
                if e.name.startswith("hub_") and e.name.endswith(".json") and e.is_file(follow_symlinks=False):
                    try:
                        entries.append((e.stat(follow_symlinks=False).st_mtime, e.path))
                    except OSError:
                        pass
        entries.sort(reverse=True)
        for _, fpath in entries[:4]:
            try:
                raw = json.loads(Path(fpath).read_text(encoding="utf-8", errors="replace"))
                if not isinstance(raw, dict):
                    continue
                port = int(raw.get("httpPort") or raw.get("port") or raw.get("connectPort") or 0)
                tok = str(raw.get("csrfToken") or raw.get("csrf_token") or "").strip()
                if port > 0:
                    cand_addr = f"localhost:{port}"
                    if _is_port_alive(cand_addr):
                        return cand_addr, tok
            except Exception:
                continue
    except OSError:
        pass
    return "", ""


def discover_agy_ls(force: bool = False) -> tuple[str, str]:
    now = time.monotonic()
    with _LS_CACHE_LOCK:
        cached_addr = str(_LS_CACHE["addr"] or "")
        cached_tok = str(_LS_CACHE["token"] or "")
        cached_ts = float(_LS_CACHE["ts"])
        cached_port_ts = float(_LS_CACHE["port_ts"])
        neg_until = float(_LS_CACHE["neg_until"])

    if not force:
        if cached_addr and (now - cached_ts) < 10.0:
            if (now - cached_port_ts) < 5.0:
                return cached_addr, cached_tok
            if _is_port_alive(cached_addr):
                with _LS_CACHE_LOCK:
                    _LS_CACHE["port_ts"] = now
                return cached_addr, cached_tok
        elif not cached_addr and now < neg_until:
            # 30s negative cache prevents PowerShell Get-CimInstance storms when IDE LS isn't running
            return "", ""

    with _LS_CACHE_LOCK:
        now = time.monotonic()
        if not force and not _LS_CACHE["addr"] and now < float(_LS_CACHE["neg_until"]):
            return "", ""

        addr = ""
        token = ""
        saved_env: dict[str, Any] = {}
        if AGY_ENV_FILE.is_file():
            try:
                saved_env = json.loads(AGY_ENV_FILE.read_text(encoding="utf-8", errors="replace"))
                if isinstance(saved_env, dict):
                    addr = (
                        str(saved_env.get("ANTIGRAVITY_LS_ADDRESS") or "")
                        .strip()
                        .replace("http://", "")
                        .replace("https://", "")
                        .rstrip("/")
                    )
                    token = str(saved_env.get("ANTIGRAVITY_CSRF_TOKEN") or "").strip()
            except Exception:
                saved_env = {}

        if not force and addr and _is_port_alive(addr):
            _LS_CACHE.update({"addr": addr, "token": token, "ts": now, "port_ts": now, "neg_until": 0.0})
            return addr, token

        hub_addr, hub_tok = _probe_hub_json_ls()
        if hub_addr:
            _LS_CACHE.update(
                {"addr": hub_addr, "token": hub_tok or token, "ts": now, "port_ts": now, "neg_until": 0.0}
            )
            return hub_addr, hub_tok or token

        found_addr = ""
        found_tok = token
        try:
            ps_cmd = (
                "$proc = Get-CimInstance Win32_Process | Where-Object { $_.Name -match 'language_server' } | Select-Object -First 1; "
                "if ($proc) { "
                "  $ports = @(Get-NetTCPConnection -OwningProcess $proc.ProcessId -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty LocalPort); "
                "  Write-Output ('PID=' + $proc.ProcessId + '|PORTS=' + ($ports -join ',') + '|CMD=' + $proc.CommandLine) "
                "}"
            )
            out = subprocess.check_output(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
                timeout=4.5,
                text=True,
                errors="ignore",
                creationflags=_NO_WINDOW,
            ).strip()
            if "PID=" in out:
                m_tok = re.search(r"--csrf_token[=\s]+([0-9a-fA-F\-]{16,})", out)
                m_ports = re.search(r"\|PORTS=([0-9,]+)\|", out)
                cand_tok = m_tok.group(1).strip() if m_tok else token
                cand_ports = [int(p) for p in (m_ports.group(1).split(",") if m_ports else []) if p.isdigit()]
                chosen_port = 0
                for cp in sorted(cand_ports):
                    try:
                        req = urllib.request.Request(
                            f"http://127.0.0.1:{cp}/exa.language_server_pb.LanguageServerService/GetUserStatus",
                            data=b"{}",
                            headers={
                                "Content-Type": "application/json",
                                "Connect-Protocol-Version": "1",
                                "x-codeium-csrf-token": cand_tok,
                                "X-Csrf-Token": cand_tok,
                            },
                            method="POST",
                        )
                        with _DIRECT_OPENER.open(req, timeout=1.2) as r:
                            if r.status == 200:
                                chosen_port = cp
                                break
                    except Exception:
                        continue
                if not chosen_port and cand_ports:
                    chosen_port = sorted(cand_ports)[0]
                if chosen_port:
                    found_addr = f"localhost:{chosen_port}"
                    found_tok = cand_tok
                    if isinstance(saved_env, dict) and AGY_ENV_FILE.parent.is_dir():
                        try:
                            saved_env["ANTIGRAVITY_LS_ADDRESS"] = found_addr
                            if found_tok:
                                saved_env["ANTIGRAVITY_CSRF_TOKEN"] = found_tok
                            AGY_ENV_FILE.write_text(
                                json.dumps(saved_env, ensure_ascii=False, indent=2) + "\n",
                                encoding="utf-8",
                            )
                        except Exception:
                            pass
        except Exception as exc:
            logger.debug("LS discovery error: %s", exc)

        if found_addr:
            _LS_CACHE.update({"addr": found_addr, "token": found_tok, "ts": now, "port_ts": now, "neg_until": 0.0})
            return found_addr, found_tok

        _LS_CACHE.update({"addr": "", "token": "", "ts": now, "port_ts": now, "neg_until": now + 30.0})
        return "", ""


def agy_rpc(method: str, payload: dict[str, Any], timeout: float = 8.0) -> dict[str, Any]:
    global _LS_RPC_FAIL_UNTIL
    if time.time() < _LS_RPC_FAIL_UNTIL:
        raise RuntimeError("桌面端 Antigravity LS 处于 44.9.1+ 401 冷却期（已自动切换至官方 agy CLI 通道）")
    for attempt in range(2):
        addr, tok = discover_agy_ls(force=(attempt > 0))
        if not addr:
            _LS_RPC_FAIL_UNTIL = time.time() + 120.0
            raise RuntimeError("未检测到运行中的本地 Antigravity Language Server")
        host_part = addr.replace("localhost:", "127.0.0.1:")
        url = f"http://{host_part}/exa.language_server_pb.LanguageServerService/{method}"
        headers = {
            "Content-Type": "application/json",
            "Connect-Protocol-Version": "1",
        }
        if tok:
            headers["x-codeium-csrf-token"] = tok
            headers["X-Csrf-Token"] = tok
        req = urllib.request.Request(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with _DIRECT_OPENER.open(req, timeout=min(timeout, 2.5 if attempt == 0 else timeout)) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                return json.loads(raw) if raw.strip() else {}
        except urllib.error.HTTPError as he:
            if he.code in (401, 403):
                _LS_RPC_FAIL_UNTIL = time.time() + 120.0
                body = ""
                try:
                    body = he.read().decode("utf-8", errors="replace")[:240]
                except Exception:
                    pass
                raise RuntimeError(f"Antigravity RPC {method} HTTP {he.code}: {body}") from he
            if attempt == 0 and he.code in (502, 503):
                continue
            body = ""
            try:
                body = he.read().decode("utf-8", errors="replace")[:240]
            except Exception:
                pass
            raise RuntimeError(f"Antigravity RPC {method} HTTP {he.code}: {body}") from he
        except Exception as exc:
            if attempt == 0:
                continue
            _LS_RPC_FAIL_UNTIL = time.time() + 60.0
            raise RuntimeError(f"Antigravity RPC {method} 调用失败: {exc}") from exc
    return {}


def _resolve_brain_dir(cid: str) -> Path:
    clean = str(cid or "").strip()
    if clean:
        cli_d = CLI_BRAIN_DIR / clean
        if (cli_d / ".system_generated/logs/transcript.jsonl").is_file() or cli_d.is_dir():
            return cli_d
    return BRAIN_DIR / clean


def _read_pbtxt_title(cid: str) -> str:
    clean = str(cid or "").strip()
    if not clean:
        return ""
    for ann_dir in (CLI_ANN_DIR, DESKTOP_ANN_DIR):
        p = ann_dir / f"{clean}.pbtxt"
        if p.is_file():
            try:
                raw = p.read_text(encoding="utf-8", errors="replace")
                m = re.search(r'title:\s*"((?:[^"\\]|\\.)*)"', raw)
                if m:
                    t = m.group(1).replace('\\"', '"').replace("\\\\", "\\").replace("\\n", " ").strip()
                    if t:
                        return t[:54]
            except Exception:
                pass
    return ""


def _is_cli_proc_running(cid: str) -> bool:
    with _OPHANIM_CLI_LOCK:
        p = _OPHANIM_CLI_PROCS.get(str(cid or "").strip())
    return bool(p is not None and p.poll() is None)


def _find_agy_cli_bin() -> str:
    env_bin = os.environ.get("OPHANIM_AGY_BIN", "").strip()
    if env_bin and Path(env_bin).is_file():
        return str(Path(env_bin))
    which_bin = shutil.which("agy") or shutil.which("agy.exe")
    if which_bin:
        return str(which_bin)
    candidates: list[Path] = [
        PROJECT_DIR.parent.parent / "bin" / "agy.exe",
        PROJECT_DIR / "bin" / "agy.exe",
        Path.home() / ".antigravity" / "bin" / "agy.exe",
    ]
    local_app = os.environ.get("LOCALAPPDATA", "").strip()
    if local_app:
        candidates.append(Path(local_app) / "agy" / "bin" / "agy.exe")
    for cand in candidates:
        if cand.is_file():
            return str(cand)
    return ""


def _resolve_agy_cli_cwd() -> str:
    env_cwd = os.environ.get("OPHANIM_AGY_CWD", "").strip()
    if env_cwd and Path(env_cwd).is_dir():
        return str(Path(env_cwd))
    workspace_root = PROJECT_DIR.parent.parent
    if (workspace_root / "projects").is_dir():
        return str(workspace_root)
    if PROJECT_DIR.is_dir():
        return str(PROJECT_DIR)
    return str(Path.home())


def _build_cli_env_oph() -> dict[str, str]:
    env = dict(os.environ)
    for port in (7890, 10809, 10808):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.15):
                px = f"http://127.0.0.1:{port}"
                env["HTTP_PROXY"] = px
                env["HTTPS_PROXY"] = px
                env["ALL_PROXY"] = px
                break
        except OSError:
            continue
    env["NO_PROXY"] = "127.0.0.1,localhost,::1"
    return env


def _parse_iso_epoch(iso_str: str, fallback: float = 0.0) -> float:
    s = (iso_str or "").strip()
    if not s:
        return fallback
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        s = re.sub(r"\.(\d{6})\d+([+-]\d\d:\d\d)$", r".\1\2", s)
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except Exception:
        return fallback


def _unwrap_arg_val(val: Any) -> Any:
    if isinstance(val, str):
        s = val.strip()
        if len(s) >= 2 and s.startswith('"') and s.endswith('"'):
            try:
                return json.loads(s)
            except Exception:
                return s.strip('"')
        if (s.startswith("{") and s.endswith("}")) or (s.startswith("[") and s.endswith("]")):
            try:
                return json.loads(s)
            except Exception:
                return s
        return s
    return val


def _unwrap_arg_str(val: Any) -> str:
    unwrapped = _unwrap_arg_val(val)
    return "" if unwrapped is None else str(unwrapped).strip()


def _normalize_local_path(raw: str) -> Path | None:
    s = (raw or "").strip()
    if not s:
        return None
    if s.startswith("file:///"):
        s = urllib.request.unquote(s[len("file:///"):])
    elif s.startswith("file://"):
        s = urllib.request.unquote(s[len("file://"):])
    if "#" in s and re.search(r"#L\d+", s):
        s = s.split("#", 1)[0]
    s = s.strip().strip('"').strip("'")
    if not s or len(s) > 1024 or "://" in s or s.startswith("\\\\"):
        return None
    norm = os.path.normpath(s)
    drive, _ = os.path.splitdrive(norm)
    if len(drive) != 2 or not drive[0].isalpha() or drive[1] != ":":
        return None
    try:
        return Path(norm)
    except Exception:
        return None


def _is_noise_file(p: Path) -> bool:
    posix_lower = p.as_posix().lower()
    for frag in NOISE_DIR_FRAGMENTS:
        if frag in posix_lower:
            return True
    name_lower = p.name.lower()
    if name_lower in NOISE_FILENAMES:
        return True
    if any(name_lower.startswith(pref) for pref in NOISE_FILE_PREFIXES):
        return True
    if name_lower.endswith((".tmp", ".pyc", ".pyo", ".log", ".db", ".db-wal", ".db-shm", ".swp")):
        return True
    return False


def _is_core_file(p: Path) -> tuple[bool, str]:
    nl = p.name.lower()
    ext = p.suffix.lower()
    if "daemon" in nl and ext == ".py":
        return True, "DAEMON_PY"
    if "bridge" in nl and ext in {".py", ".js", ".ts"}:
        return True, "AGY_BRIDGE"
    if "server" in nl and ext in {".py", ".js", ".ts"}:
        return True, "CORE_SRV"
    if "executor" in nl and ext == ".py":
        return True, "SYS_EXEC"
    if "launcher" in nl and ext in {".py", ".pyw", ".bat"}:
        return True, "LAUNCHER"
    if ext == ".bat":
        return True, "WIN_ENTRY"
    if nl in {"main.py", "app.py", "index.js", "index.ts", "ophanim_sanctum.html", "ophanim_agy_panel.js"}:
        return True, "CORE_UI" if ext in {".html", ".js"} else "MAIN_CORE"
    return False, ""


def _is_deliverable_candidate(p: Path, explicitly_linked: bool = False) -> bool:
    if _is_noise_file(p) or not p.is_file():
        return False
    posix_low = p.as_posix().lower()
    if "/antigravity/scratch/" in posix_low and not explicitly_linked:
        return False
    ext = p.suffix.lower()
    if ext in STRICT_DELIVERABLE_EXTS:
        return True
    parent_names = {pt.lower() for pt in p.parts[:-1]}
    if (parent_names & DELIVERABLE_FOLDER_NAMES) and ext in LINKED_DELIVERABLE_EXTS:
        return True
    if explicitly_linked and ext in LINKED_DELIVERABLE_EXTS:
        return True
    return False


def _clean_user_text(raw: str) -> str:
    txt = str(raw or "")
    if not txt.strip():
        return ""
    if "<CONTEXT_SUMMARY>" in txt and "<USER_REQUEST>" not in txt:
        return ""
    m_req = re.search(r"<USER_REQUEST>\s*([\s\S]*?)\s*</USER_REQUEST>", txt)
    if m_req:
        txt = m_req.group(1)
    else:
        txt = re.sub(r"<CONTEXT_SUMMARY>[\s\S]*?</CONTEXT_SUMMARY>", "", txt)
        txt = re.sub(r"<ADDITIONAL_METADATA>[\s\S]*?</ADDITIONAL_METADATA>", "", txt)
        txt = re.sub(r"<USER_SETTINGS_CHANGE>[\s\S]*?</USER_SETTINGS_CHANGE>", "", txt)

    if "【当前用户指令与要求】" in txt:
        after = txt.split("【当前用户指令与要求】", 1)[1]
        after = re.split(r"\n+请你直接基于当前对话的上下文", after, maxsplit=1)[0]
        clean_q = after.strip()
        if clean_q:
            return f"[QQ桥接] {clean_q}"
    return txt.strip()


def _clean_assistant_text(raw: str) -> str:
    txt = str(raw or "").strip()
    if not txt:
        return ""
    lines = [
        ln for ln in txt.splitlines()
        if not ln.strip().startswith("[防长对话漂移锚点]")
        and not ln.strip().startswith("> [路由：")
        and not ln.strip().startswith("[路由：")
    ]
    return "\n".join(lines).strip()


def _extract_first_user_title(cid: str) -> str:
    pb_t = _read_pbtxt_title(cid)
    if pb_t:
        return pb_t
    t_path = _resolve_brain_dir(cid) / ".system_generated/logs/transcript.jsonl"
    if not t_path.is_file():
        return ""
    try:
        with open(t_path, "r", encoding="utf-8", errors="replace") as fh:
            for idx, line in enumerate(fh):
                if idx > 40:
                    break
                if '"USER_INPUT"' not in line:
                    continue
                obj = json.loads(line)
                if obj.get("type") == "USER_INPUT":
                    cleaned = _clean_user_text(str(obj.get("content") or ""))
                    if cleaned:
                        cleaned = re.sub(r"@\[[^\]]+\]", "", cleaned)
                        cleaned = re.sub(r"\s+", " ", cleaned).strip()
                        return cleaned[:40]
    except Exception:
        pass
    return ""


def _read_swarm_child_ids(cid: str) -> list[tuple[str, dict[str, Any]]]:
    mem_path = _resolve_brain_dir(cid) / ".system_generated/swarm/members.json"
    if not mem_path.is_file():
        return []
    try:
        data = json.loads(mem_path.read_text(encoding="utf-8", errors="replace"))
        members = data.get("members") or {}
        out: list[tuple[str, dict[str, Any]]] = []
        for name, info in members.items():
            if not isinstance(info, dict) or info.get("role") == "coordinator":
                continue
            out.append((str(name), info))
        return out
    except Exception:
        return []


def _fetch_all_summaries_safe() -> dict[str, dict[str, Any]]:
    try:
        resp = agy_rpc("GetAllCascadeTrajectories", {}, timeout=5.0)
        s = resp.get("trajectorySummaries")
        if isinstance(s, dict):
            return s
    except Exception as exc:
        logger.debug("GetAllCascadeTrajectories fallback: %s", exc)
    return {}


_SESSION_META_LOCK = threading.Lock()
_SESSION_META_CACHE: dict[str, Any] = {
    "exists": False,
    "mtime_ns": -1,
    "size": -1,
    "data": {"pinned": set(), "archived": set(), "deleted": set()},
}


def load_session_meta() -> dict[str, set[str]]:
    """Load persisted pinned / archived / deleted conversation ID sets (mtime-cached)."""
    exists = False
    mtime_ns = -1
    size = -1
    try:
        st = SESSION_META_FILE.stat()
        exists = True
        mtime_ns = int(st.st_mtime_ns)
        size = int(st.st_size)
    except OSError:
        exists = False

    with _SESSION_META_LOCK:
        if (
            _SESSION_META_CACHE["exists"] == exists
            and _SESSION_META_CACHE["mtime_ns"] == mtime_ns
            and _SESSION_META_CACHE["size"] == size
        ):
            cached = _SESSION_META_CACHE["data"]
            return {
                "pinned": set(cached["pinned"]),
                "archived": set(cached["archived"]),
                "deleted": set(cached["deleted"]),
            }

        out: dict[str, set[str]] = {"pinned": set(), "archived": set(), "deleted": set()}
        if exists:
            try:
                raw = json.loads(SESSION_META_FILE.read_text(encoding="utf-8", errors="replace"))
                if isinstance(raw, dict):
                    for k in ("pinned", "archived", "deleted"):
                        vals = raw.get(k)
                        if isinstance(vals, list):
                            out[k] = {str(v).strip() for v in vals if str(v).strip()}
            except Exception as exc:
                logger.debug("load_session_meta error: %s", exc)
        _SESSION_META_CACHE.update(
            {
                "exists": exists,
                "mtime_ns": mtime_ns,
                "size": size,
                "data": {
                    "pinned": set(out["pinned"]),
                    "archived": set(out["archived"]),
                    "deleted": set(out["deleted"]),
                },
            }
        )
        return out


def save_session_meta(meta: dict[str, set[str]]) -> None:
    """Atomically persist pinned / archived / deleted conversation ID sets."""
    SESSION_META_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "pinned": sorted(meta.get("pinned", set())),
        "archived": sorted(meta.get("archived", set())),
        "deleted": sorted(meta.get("deleted", set())),
        "updatedAt": int(time.time()),
    }
    serialized = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    with _SESSION_META_LOCK:
        tmp = SESSION_META_FILE.parent / f".ophanim_session_meta.{os.getpid()}.{time.time_ns()}.tmp"
        try:
            tmp.write_text(serialized, encoding="utf-8")
            for attempt in range(5):
                try:
                    os.replace(tmp, SESSION_META_FILE)
                    break
                except PermissionError:
                    if attempt == 4:
                        raise
                    time.sleep(0.02 * (attempt + 1))
            try:
                st = SESSION_META_FILE.stat()
                _SESSION_META_CACHE.update(
                    {
                        "exists": True,
                        "mtime_ns": int(st.st_mtime_ns),
                        "size": int(st.st_size),
                        "data": {
                            "pinned": set(meta.get("pinned", set())),
                            "archived": set(meta.get("archived", set())),
                            "deleted": set(meta.get("deleted", set())),
                        },
                    }
                )
            except OSError:
                _SESSION_META_CACHE["mtime_ns"] = -1
        finally:
            if tmp.exists():
                try:
                    tmp.unlink()
                except OSError:
                    pass


def mutate_conversation_meta(cascade_id: str, action: str) -> dict[str, Any]:
    """Pin, unpin, archive, unarchive, or delete a conversation."""
    cid = str(cascade_id or "").strip()
    act = str(action or "").strip().lower()
    if not cid or cid == "__new__":
        return {"ok": False, "error": "无效的会话 ID"}

    meta = load_session_meta()
    if act == "pin":
        meta["pinned"].add(cid)
        meta["archived"].discard(cid)
    elif act == "unpin":
        meta["pinned"].discard(cid)
    elif act == "toggle_pin":
        if cid in meta["pinned"]:
            meta["pinned"].discard(cid)
        else:
            meta["pinned"].add(cid)
            meta["archived"].discard(cid)
    elif act == "archive":
        meta["archived"].add(cid)
        meta["pinned"].discard(cid)
    elif act == "unarchive":
        meta["archived"].discard(cid)
    elif act == "toggle_archive":
        if cid in meta["archived"]:
            meta["archived"].discard(cid)
        else:
            meta["archived"].add(cid)
            meta["pinned"].discard(cid)
    elif act == "delete":
        meta["deleted"].add(cid)
        meta["pinned"].discard(cid)
        meta["archived"].discard(cid)
        for rpc_name in ("DeleteCascadeTrajectory", "DeleteTrajectory"):
            try:
                agy_rpc(rpc_name, {"cascadeId": cid}, timeout=2.5)
                break
            except Exception:
                continue
    else:
        return {"ok": False, "error": f"未知操作: {act}"}

    save_session_meta(meta)
    return {
        "ok": True,
        "cascadeId": cid,
        "action": act,
        "pinned": cid in meta["pinned"],
        "archived": cid in meta["archived"],
        "deleted": cid in meta["deleted"],
    }


_CONV_CACHE_LOCK = threading.Lock()
_LAST_DONE_META_CACHE: OrderedDict[str, tuple[int, int, str, dict[str, Any] | None]] = OrderedDict()
_LAST_DONE_META_MAX = 500
_CONV_META_CACHE: OrderedDict[str, dict[str, Any]] = OrderedDict()
_CONV_META_MAX = 2500
_FLAT_CONV_MTIMES: dict[str, int] = {}
_DORMANT_SWEEP_CURSOR: int = 0


def _peek_last_completed_turn_meta(
    t_path: Path,
    conv_status: str,
    *,
    mtime_ns: int | None = None,
    size: int | None = None,
) -> dict[str, Any] | None:
    """Fast LRU-bounded mtime_ns-cached check for the latest genuinely completed turn."""
    key = str(t_path)
    if mtime_ns is None or size is None:
        try:
            st = t_path.stat()
            mtime_ns = int(st.st_mtime_ns)
            size = int(st.st_size)
        except OSError:
            return None

    with _CONV_CACHE_LOCK:
        cached = _LAST_DONE_META_CACHE.get(key)
        if cached and cached[0] == mtime_ns and cached[1] == size and cached[2] == conv_status:
            _LAST_DONE_META_CACHE.move_to_end(key)
            return cached[3]

    meta_out: dict[str, Any] | None = None
    try:
        msgs, _, _, _ = _extract_file_touches_from_transcript(t_path)
        turns = _build_numbered_turns(msgs, conv_status)
        for tr in reversed(turns):
            if tr.get("hasFinalReply") and str(tr.get("assistantText") or "").strip():
                a_txt = str(tr.get("assistantText") or "").strip()
                meta_out = {
                    "turnNumber": int(tr["turnNumber"]),
                    "userTitle": str(tr.get("userTitle") or f"第 {tr['turnNumber']} 轮"),
                    "snippet": re.sub(r"\s+", " ", a_txt)[:84],
                    "time": str(tr.get("time") or ""),
                }
                break
    except Exception:
        meta_out = None

    with _CONV_CACHE_LOCK:
        _LAST_DONE_META_CACHE[key] = (mtime_ns, size, conv_status, meta_out)
        _LAST_DONE_META_CACHE.move_to_end(key)
        while len(_LAST_DONE_META_CACHE) > _LAST_DONE_META_MAX:
            _LAST_DONE_META_CACHE.popitem(last=False)
    return meta_out


def _scan_flat_conv_dirty_cids() -> set[str]:
    """Zero-extra-syscall `os.scandir` over flat `.db`/`.pb` conversation dirs to catch revived old chats."""
    dirty: set[str] = set()
    for flat_dir, suffix in ((CLI_CONV_DIR, ".db"), (DESKTOP_CONV_DIR, ".pb")):
        if not flat_dir.is_dir():
            continue
        try:
            with os.scandir(flat_dir) as it:
                for entry in it:
                    nm = entry.name
                    if not nm.endswith(suffix):
                        continue
                    cid = nm[:-len(suffix)]
                    if len(cid) < 32:
                        continue
                    try:
                        m_ns = int(entry.stat(follow_symlinks=False).st_mtime_ns)
                    except OSError:
                        continue
                    prev_m = _FLAT_CONV_MTIMES.get(cid)
                    if prev_m != m_ns:
                        _FLAT_CONV_MTIMES[cid] = m_ns
                        if prev_m is not None:
                            dirty.add(cid)
        except OSError:
            pass
    return dirty


def _stat_cid_entry(cid: str, brain_dir_str: str, rec: dict[str, Any] | None) -> dict[str, Any]:
    """Stat transcript.jsonl & members.json for `cid`, refreshing cached child_ids only when members.json changes."""
    t_path_str = os.path.join(brain_dir_str, ".system_generated", "logs", "transcript.jsonl")
    m_path_str = os.path.join(brain_dir_str, ".system_generated", "swarm", "members.json")

    if rec is None:
        rec = {
            "brain_dir": brain_dir_str,
            "t_path": t_path_str,
            "t_exists": False,
            "t_mtime_ns": 0,
            "t_mtime": 0.0,
            "t_size": 0,
            "hydrated_mtime_ns": -1,
            "hydrated_size": -1,
            "title": "",
            "pbtxt_mtime_ns": -1,
            "step_count": 0,
            "members_mtime_ns": -1,
            "child_ids": [],
        }
    elif rec.get("brain_dir") != brain_dir_str:
        rec["brain_dir"] = brain_dir_str
        rec["t_path"] = t_path_str
        rec["hydrated_mtime_ns"] = -1
        rec["hydrated_size"] = -1
        rec["members_mtime_ns"] = -1

    try:
        st = os.stat(t_path_str)
        rec["t_exists"] = True
        rec["t_mtime_ns"] = int(st.st_mtime_ns)
        rec["t_mtime"] = float(st.st_mtime)
        rec["t_size"] = int(st.st_size)
    except OSError:
        rec["t_exists"] = False
        rec["t_mtime_ns"] = 0
        rec["t_mtime"] = 0.0
        rec["t_size"] = 0

    try:
        mst = os.stat(m_path_str)
        m_ns = int(mst.st_mtime_ns)
        if m_ns != int(rec.get("members_mtime_ns", -1)):
            cids_list: list[str] = []
            try:
                data = json.loads(Path(m_path_str).read_text(encoding="utf-8", errors="replace"))
                members = data.get("members") or {}
                for _, info in members.items():
                    if not isinstance(info, dict) or info.get("role") == "coordinator":
                        continue
                    w_cid = str(info.get("conversation_id") or "").strip()
                    if w_cid and w_cid != cid:
                        cids_list.append(w_cid)
            except Exception:
                pass
            rec["members_mtime_ns"] = m_ns
            rec["child_ids"] = cids_list
    except OSError:
        rec["members_mtime_ns"] = -1
        if rec.get("child_ids"):
            rec["child_ids"] = []

    return rec


def _hydrate_cid_title_and_steps(cid: str, rec: dict[str, Any], need_title: bool, need_steps: bool) -> None:
    """Read title / pbtxt / line count ONLY when transcript `(mtime_ns, size)` or pbtxt changed."""
    t_exists = bool(rec.get("t_exists"))
    t_mtime_ns = int(rec.get("t_mtime_ns") or 0)
    t_size = int(rec.get("t_size") or 0)

    # Check pbtxt title mtime if needed
    pb_title = ""
    pb_m_ns = -1
    if need_title:
        for ann_dir in (CLI_ANN_DIR, DESKTOP_ANN_DIR):
            p = ann_dir / f"{cid}.pbtxt"
            try:
                pst = os.stat(p)
                pb_m_ns = int(pst.st_mtime_ns)
                if pb_m_ns != int(rec.get("pbtxt_mtime_ns", -1)) or not rec.get("title"):
                    raw = p.read_text(encoding="utf-8", errors="replace")
                    m = re.search(r'title:\s*"((?:[^"\\]|\\.)*)"', raw)
                    if m:
                        t = m.group(1).replace('\\"', '"').replace("\\\\", "\\").replace("\\n", " ").strip()
                        if t:
                            pb_title = t[:54]
                    rec["pbtxt_mtime_ns"] = pb_m_ns
                    if pb_title:
                        rec["title"] = pb_title
                break
            except OSError:
                continue

    up_to_date = (
        int(rec.get("hydrated_mtime_ns", -1)) == t_mtime_ns
        and int(rec.get("hydrated_size", -1)) == t_size
    )
    if up_to_date and (not need_title or rec.get("title")) and (not need_steps or rec.get("step_count", 0) >= 0):
        return

    if not t_exists:
        rec["hydrated_mtime_ns"] = t_mtime_ns
        rec["hydrated_size"] = t_size
        rec["step_count"] = 0
        return

    t_path_str = str(rec.get("t_path") or "")
    try:
        need_extract_title = need_title and not pb_title and (not rec.get("title") or not up_to_date)
        extracted_title = ""
        line_cnt = 0
        with open(t_path_str, "rb") as fh:
            for idx, raw_b in enumerate(fh):
                line_cnt += 1
                if need_extract_title and not extracted_title and idx <= 40 and b'"USER_INPUT"' in raw_b:
                    try:
                        obj = json.loads(raw_b.decode("utf-8", errors="replace"))
                        if obj.get("type") == "USER_INPUT":
                            cleaned = _clean_user_text(str(obj.get("content") or ""))
                            if cleaned:
                                cleaned = re.sub(r"@\[[^\]]+\]", "", cleaned)
                                cleaned = re.sub(r"\s+", " ", cleaned).strip()
                                extracted_title = cleaned[:40]
                    except Exception:
                        pass
        rec["step_count"] = line_cnt
        if extracted_title and not pb_title:
            rec["title"] = extracted_title
        rec["hydrated_mtime_ns"] = t_mtime_ns
        rec["hydrated_size"] = t_size
    except Exception:
        pass


def list_conversations(limit: int = 48, include_archived: bool = True) -> list[dict[str, Any]]:
    global _DORMANT_SWEEP_CURSOR
    meta_sets = load_session_meta()
    pinned_ids = meta_sets["pinned"]
    archived_ids = meta_sets["archived"]
    deleted_ids = meta_sets["deleted"]

    summaries = _fetch_all_summaries_safe()
    child_cids: set[str] = set()
    children_by_parent: dict[str, set[str]] = {}

    for cid, info in summaries.items():
        if not isinstance(info, dict):
            continue
        meta = info.get("trajectoryMetadata") or {}
        parent_id = str(meta.get("parentConversationId") or "").strip()
        if parent_id:
            child_cids.add(cid)
            children_by_parent.setdefault(parent_id, set()).add(cid)

    # 1. Fast os.scandir() discovery of all brain dirs (CLI takes precedence over desktop if both exist)
    cid_to_dir: dict[str, str] = {}
    for scan_dir in (BRAIN_DIR, CLI_BRAIN_DIR):
        if not scan_dir.is_dir():
            continue
        try:
            with os.scandir(scan_dir) as it:
                for entry in it:
                    nm = entry.name
                    if len(nm) >= 32 and nm != "tempmediaStorage" and entry.is_dir(follow_symlinks=False):
                        cid_to_dir[nm] = entry.path
        except OSError:
            pass

    all_candidate_cids = set(summaries.keys()) | set(cid_to_dir.keys())

    with _OPHANIM_CLI_LOCK:
        running_cli_cids = {k for k, p in _OPHANIM_CLI_PROCS.items() if p is not None and p.poll() is None}

    # 2. Detect revived old conversations via flat .db/.pb dir scandir (zero extra syscalls)
    dirty_flat_cids = _scan_flat_conv_dirty_cids()

    with _CONV_CACHE_LOCK:
        # Remove deleted/gone dirs from cache
        for cached_cid in list(_CONV_META_CACHE.keys()):
            if cached_cid not in all_candidate_cids:
                _CONV_META_CACHE.pop(cached_cid, None)

        # Decide which CIDs need fresh os.stat(transcript.jsonl) this call:
        # - Any brand new CID not yet in cache
        # - Any CID touched in flat conv dirs, pinned, CLI-running, or present in LS summaries
        # - Top (limit + 16) most recent cached CIDs
        # - Plus a small rotating slice (32) of dormant CIDs so even untracked edits get picked up with <0.5ms cost
        cached_sorted = sorted(
            _CONV_META_CACHE.items(),
            key=lambda kv: float(kv[1].get("t_mtime") or 0.0),
            reverse=True,
        )
        hot_limit = max(limit + 16, 64)
        hot_cids: set[str] = {k for k, _ in cached_sorted[:hot_limit]}
        hot_cids.update(pinned_ids)
        hot_cids.update(running_cli_cids)
        hot_cids.update(dirty_flat_cids)
        hot_cids.update(summaries.keys())

        dormant_keys = [k for k, _ in cached_sorted[hot_limit:]]
        if dormant_keys:
            start_i = _DORMANT_SWEEP_CURSOR % len(dormant_keys)
            batch_n = min(32, len(dormant_keys))
            for off in range(batch_n):
                hot_cids.add(dormant_keys[(start_i + off) % len(dormant_keys)])
            _DORMANT_SWEEP_CURSOR = (start_i + batch_n) % len(dormant_keys)

        for cid in all_candidate_cids:
            bdir = cid_to_dir.get(cid)
            if not bdir:
                continue
            existing_rec = _CONV_META_CACHE.get(cid)
            if existing_rec is None or cid in hot_cids or existing_rec.get("brain_dir") != bdir:
                rec = _stat_cid_entry(cid, bdir, existing_rec)
                _CONV_META_CACHE[cid] = rec
                _CONV_META_CACHE.move_to_end(cid)
            else:
                rec = existing_rec

            for w_cid in rec.get("child_ids") or ():
                child_cids.add(w_cid)
                children_by_parent.setdefault(cid, set()).add(w_cid)

        while len(_CONV_META_CACHE) > _CONV_META_MAX:
            _CONV_META_CACHE.popitem(last=False)

        # 3. Cheap sort BEFORE hydrating title/stepCount/lastCompletedTurn!
        prelim: list[tuple[int, int, float, str, dict[str, Any], dict[str, Any] | None, str, str, str]] = []
        for cid in all_candidate_cids:
            if cid in child_cids or cid in deleted_ids or cid == "tempmediaStorage":
                continue
            is_archived = cid in archived_ids
            if is_archived and not include_archived:
                continue
            info = summaries.get(cid) if isinstance(summaries.get(cid), dict) else {}
            rec = _CONV_META_CACHE.get(cid)
            if not info and (rec is None or not rec.get("t_exists")):
                continue

            is_cli_run = cid in running_cli_cids
            status_raw = str(
                info.get("status") or ("CASCADE_RUN_STATUS_RUNNING" if is_cli_run else "CASCADE_RUN_STATUS_IDLE")
            )
            status = "running" if ("RUNNING" in status_raw or is_cli_run) else "idle"

            t_mtime = float(rec.get("t_mtime") or 0.0) if rec else 0.0
            updated_str = str(info.get("lastModifiedTime") or info.get("createdTime") or "")
            updated_epoch = max(_parse_iso_epoch(updated_str, t_mtime), t_mtime)
            is_pinned = cid in pinned_ids
            prelim.append((
                1 if is_archived else 0,
                0 if is_pinned else 1,
                -updated_epoch,
                cid,
                info,
                rec,
                status,
                status_raw,
                updated_str,
            ))

        prelim.sort(key=lambda x: (x[0], x[1], x[2]))

        # Keep top `limit` plus any running conversations (even if beyond limit)
        selected = prelim[:limit]
        selected_ids = {item[3] for item in selected}
        for item in prelim[limit:]:
            if item[6] == "running" and item[3] not in selected_ids:
                selected.append(item)

        # 4. Hydrate ONLY the selected top `limit` + running CIDs (zero reads when cached!)
        results: list[dict[str, Any]] = []
        for idx_sel, (arch_ord, pin_ord, neg_ep, cid, info, rec, status, status_raw, updated_str) in enumerate(selected):
            updated_epoch = -neg_ep
            if not updated_str and updated_epoch > 0:
                updated_str = datetime.fromtimestamp(updated_epoch, tz=timezone.utc).isoformat()

            annotations = info.get("annotations") if isinstance(info.get("annotations"), dict) else {}
            title = str(annotations.get("title") or info.get("summary") or "").strip()
            step_count = int(info.get("stepCount") or 0)

            if rec is not None:
                _hydrate_cid_title_and_steps(
                    cid,
                    rec,
                    need_title=(not title),
                    need_steps=(step_count == 0),
                )
                if not title:
                    title = str(rec.get("title") or "")
                if step_count == 0:
                    step_count = int(rec.get("step_count") or 0)

            if not title:
                title = f"对话 {cid[:8]}"

            cached_children = len(rec.get("child_ids") or ()) if rec else 0
            subagent_total = max(len(children_by_parent.get(cid, set())), cached_children)

            last_done_meta = None
            if rec is not None and rec.get("t_exists") and (status == "running" or idx_sel < 16):
                # Release lock while parsing transcript on cache miss
                t_path_obj = Path(str(rec["t_path"]))
                t_m_ns = int(rec.get("t_mtime_ns") or 0)
                t_sz = int(rec.get("t_size") or 0)
                cached_done = _LAST_DONE_META_CACHE.get(str(t_path_obj))
                if cached_done and cached_done[0] == t_m_ns and cached_done[1] == t_sz and cached_done[2] == status:
                    _LAST_DONE_META_CACHE.move_to_end(str(t_path_obj))
                    last_done_meta = cached_done[3]
                else:
                    # Will hydrate right below outside lock if needed
                    last_done_meta = ("__NEEDS_PEEK__", t_path_obj, status, t_m_ns, t_sz)

            results.append({
                "id": cid,
                "shortId": cid[:8],
                "title": title[:54],
                "status": status,
                "statusRaw": status_raw,
                "stepCount": step_count,
                "subagentCount": subagent_total,
                "pinned": pin_ord == 0,
                "archived": arch_ord == 1,
                "updatedAt": updated_str,
                "updatedEpoch": round(updated_epoch, 3),
                "lastCompletedTurn": last_done_meta,
            })

    # Complete any cold _peek_last_completed_turn_meta misses outside _CONV_CACHE_LOCK
    for item in results:
        lct = item.get("lastCompletedTurn")
        if isinstance(lct, tuple) and lct and lct[0] == "__NEEDS_PEEK__":
            _, t_path_obj, st_str, t_m_ns, t_sz = lct
            item["lastCompletedTurn"] = _peek_last_completed_turn_meta(
                t_path_obj, st_str, mtime_ns=t_m_ns, size=t_sz
            )

    return results[:limit]


def _prettify_model_name(raw_model: str) -> str:
    s = (raw_model or "").strip()
    if not s:
        return "Gemini-4-Carbon"
    if s in MODEL_CATALOG_PB and s != "inherit":
        return MODEL_CATALOG_PB[s]["label"]
    return s.replace("gemini-", "Gemini-").replace("claude-", "Claude-").title()[:28]


def read_line_range_preview(
    path: Path,
    start_line: int | None = None,
    end_line: int | None = None,
    max_lines: int = 76,
    max_bytes: int = 196608,
) -> str:
    """Read an exact #L<start>-<end> slice (with line numbers) or file preview."""
    if not start_line and not end_line:
        return read_preview(path, max_lines=max_lines)
    try:
        with open(path, "rb") as fh:
            raw = fh.read(max_bytes)
        if b"\x00" in raw[:512]:
            return read_preview(path, max_lines=max_lines)
        all_lines = raw.decode("utf-8", errors="replace").splitlines()
        total = len(all_lines)
        s_idx = max(1, int(start_line or 1))
        e_idx = min(total, int(end_line or (s_idx + max_lines - 1)))
        if e_idx < s_idx:
            e_idx = min(total, s_idx + max_lines - 1)
        sliced = all_lines[s_idx - 1 : min(e_idx, s_idx - 1 + max_lines)]
        header = f"// {path.name}  #L{s_idx}-{e_idx}  (共 {total} 行)"
        numbered = [f"{s_idx + idx:>4d} | {ln}" for idx, ln in enumerate(sliced)]
        if e_idx - s_idx + 1 > max_lines:
            numbered.append(f" ... | (后续省略 {e_idx - s_idx + 1 - max_lines} 行)")
        return "\n".join([header, ""] + numbered)
    except Exception:
        return read_preview(path, max_lines=max_lines)


def _extract_system_incoming_message(raw_content: str) -> tuple[str, str]:
    """Extract real @coordinator / subagent incoming message from SYSTEM_MESSAGE."""
    txt = str(raw_content or "").strip()
    if not txt:
        return "", ""
    m_sys = re.search(r"<SYSTEM_MESSAGE>\s*([\s\S]*?)\s*</SYSTEM_MESSAGE>", txt)
    body = m_sys.group(1).strip() if m_sys else txt
    m_msg = re.match(
        r"^\[Message\]\s*timestamp=\S+\s+sender=(\S+)\s+priority=\S+\s+content=([\s\S]*)$",
        body,
    )
    if m_msg:
        sender_id = m_msg.group(1).strip()
        msg_body = m_msg.group(2).strip()
    else:
        sender_id = ""
        msg_body = body

    if not msg_body:
        return "", ""
    if msg_body.startswith("[swarm] new board message") or msg_body.startswith("[monitor] tick:"):
        return "", ""
    if "Your assignment" in msg_body or msg_body.startswith("@"):
        return "来自 @coordinator 的消息", msg_body
    if "/" in sender_id and "task-" in sender_id:
        return "", ""
    return "来自 @coordinator 的消息", msg_body


def _build_worker_detail(
    worker_cid: str,
    worker_name: str,
    brief_short: str,
    full_brief: str = "",
    board_posts: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """
    Build rich Antigravity sub-agent conversation messages (for the middle main view)
    AND compact technical tool trace (for the bottom row).
    """
    conv_messages: list[dict[str, str]] = []
    recent_actions: list[str] = []
    seen_texts: set[str] = set()

    def _add_conv_msg(role: str, sender: str, text: str, ts: str = "") -> None:
        cleaned = str(text or "").strip()
        if not cleaned:
            return
        dedup_key = f"{role}:{cleaned[:180]}"
        if dedup_key in seen_texts:
            return
        seen_texts.add(dedup_key)
        conv_messages.append({
            "role": role,
            "sender": sender,
            "text": cleaned,
            "time": ts,
        })

    if worker_cid:
        w_bdir = _resolve_brain_dir(worker_cid)
        full_t_path = w_bdir / ".system_generated/logs/transcript_full.jsonl"
        compact_t_path = w_bdir / ".system_generated/logs/transcript.jsonl"
        chosen_t = full_t_path if full_t_path.is_file() else compact_t_path
        if chosen_t.is_file():
            try:
                with open(chosen_t, "r", encoding="utf-8", errors="replace") as fh:
                    for raw in fh:
                        if not raw.strip():
                            continue
                        try:
                            st = json.loads(raw)
                        except Exception:
                            continue
                        stype = str(st.get("type") or "")
                        created_at = str(st.get("created_at") or "")
                        raw_c = str(st.get("content") or "")

                        if stype == "SYSTEM_MESSAGE":
                            sender_lbl, msg_body = _extract_system_incoming_message(raw_c)
                            if msg_body:
                                _add_conv_msg("coordinator", sender_lbl, msg_body, created_at)
                        elif stype == "USER_INPUT":
                            cu = _clean_user_text(raw_c)
                            if cu:
                                _add_conv_msg("coordinator", "来自主控智能体的任务指令", cu, created_at)
                        elif stype == "PLANNER_RESPONSE":
                            for tc in (st.get("tool_calls") or []):
                                if not isinstance(tc, dict):
                                    continue
                                tname = str(tc.get("name") or "")
                                targs = tc.get("args") if isinstance(tc.get("args"), dict) else {}
                                if tname == "post_message":
                                    pm_txt = _unwrap_arg_str(targs.get("text"))
                                    if pm_txt:
                                        _add_conv_msg(
                                            "worker",
                                            f"@{worker_name} · 看板汇报",
                                            pm_txt,
                                            created_at,
                                        )
                                elif tname == "send_message":
                                    sm_txt = _unwrap_arg_str(targs.get("Message"))
                                    if sm_txt:
                                        _add_conv_msg(
                                            "worker",
                                            f"@{worker_name} · 回传消息",
                                            sm_txt,
                                            created_at,
                                        )
                                tgt = (
                                    _unwrap_arg_str(targs.get("Path"))
                                    or _unwrap_arg_str(targs.get("toolSummary"))
                                    or _unwrap_arg_str(targs.get("CommandLine"))[:52]
                                    or _unwrap_arg_str(targs.get("text"))[:52]
                                )
                                if tname:
                                    recent_actions.append(f"{tname}({tgt})" if tgt else f"{tname}()")

                            c_txt = _clean_assistant_text(raw_c)
                            if c_txt:
                                _add_conv_msg("worker", f"@{worker_name} · 执行回执", c_txt, created_at)
            except Exception:
                pass

    if full_brief and not any(m["role"] == "coordinator" for m in conv_messages):
        _add_conv_msg("coordinator", "来自 @coordinator 的消息", full_brief, "")

    for bp in (board_posts or []):
        _add_conv_msg("worker", f"@{worker_name} · 看板汇报", bp.get("text", ""), bp.get("time", ""))

    if not conv_messages:
        _add_conv_msg("coordinator", "来自 @coordinator 的消息", full_brief or brief_short, "")

    trace_header = f"Sub-Agent: @{worker_name}  ·  ID: {worker_cid or 'N/A'}"
    trace_tools = recent_actions[-14:]
    trace_lines = [
        "=== ANTIGRAVITY SUB-AGENT REAL TRACE ===",
        f"Sub-Agent Handle : {worker_name}",
        f"Conversation ID  : {worker_cid or 'N/A'}",
    ]
    if trace_tools:
        trace_lines.append("Recent Tool Executions:")
        trace_lines.extend(f"  • {act}" for act in trace_tools)

    full_copy_parts = []
    for m in conv_messages:
        full_copy_parts.append(f"[{m['sender']}]\n{m['text']}")
    full_copy_parts.append("\n".join(trace_lines))

    return {
        "messages": conv_messages,
        "traceHeader": trace_header,
        "traceTools": trace_tools,
        "traceText": "\n".join(trace_lines),
        "code": "\n\n".join(full_copy_parts),
    }


def _extract_user_attachments_from_step(step: dict[str, Any], raw_content: str) -> list[dict[str, str]]:
    atts: list[dict[str, str]] = []
    seen_u: set[str] = set()
    for med in (step.get("media") or []):
        if not isinstance(med, dict):
            continue
        uri = str(med.get("uri") or "").strip()
        mime = str(med.get("mime_type") or med.get("mimeType") or "image/png")
        p_obj = _normalize_local_path(uri)
        nm = p_obj.name if p_obj else (Path(uri).name if uri else "image.png")
        key = uri or nm
        if key in seen_u:
            continue
        seen_u.add(key)
        atts.append({
            "name": nm,
            "kind": "image" if mime.startswith("image/") else "file",
            "path": os.path.normpath(str(p_obj)) if p_obj else uri,
        })
    for m_att in re.finditer(r"\[Attachment:\s*([^\s\]]+)\s*\(([^)]+)\)\]", raw_content):
        mime_s = m_att.group(1)
        p_raw = m_att.group(2).strip()
        p_obj = _normalize_local_path(p_raw)
        nm = p_obj.name if p_obj else Path(p_raw).name
        key = os.path.normpath(str(p_obj)) if p_obj else p_raw
        if key in seen_u:
            continue
        seen_u.add(key)
        atts.append({
            "name": nm,
            "kind": "image" if mime_s.startswith("image/") else "file",
            "path": key,
        })
    return atts


def _summarize_turn_title(user_text: str, attachments: list[dict[str, str]], turn_num: int) -> str:
    txt = re.sub(r"\s+", " ", (user_text or "").strip())
    if txt:
        return txt[:68] + ("…" if len(txt) > 68 else "")
    if attachments:
        names = ", ".join(a["name"] for a in attachments[:2])
        return f"[拖入附件] {names}"
    return f"第 {turn_num} 轮指令"


def _load_full_transcript_contents(t_path: Path) -> dict[int, str]:
    """Load untruncated `content` strings by `step_index` from sibling `transcript_full.jsonl`."""
    full_path = t_path.with_name("transcript_full.jsonl")
    out: dict[int, str] = {}
    if not full_path.is_file():
        return out
    try:
        with open(full_path, "r", encoding="utf-8", errors="replace") as fh:
            for raw_line in fh:
                if not raw_line.strip():
                    continue
                try:
                    st = json.loads(raw_line)
                except Exception:
                    continue
                sidx = st.get("step_index")
                if isinstance(sidx, int) and st.get("content"):
                    out[sidx] = str(st["content"])
    except Exception as exc:
        logger.debug("transcript_full read warning (%s): %s", full_path, exc)
    return out


def _extract_file_touches_from_transcript(
    t_path: Path,
    base_turn_idx: int | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str, dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    file_events: list[dict[str, Any]] = []
    detected_model = ""
    cur_turn = base_turn_idx if base_turn_idx is not None else -1
    token_stats: dict[str, Any] = {
        "inputTokens": 0,
        "outputTokens": 0,
        "cacheReadTokens": 0,
        "stepSamples": [],
    }

    if not t_path.is_file():
        return messages, file_events, detected_model, token_stats

    full_contents_cache: dict[int, str] | None = None
    prev_step_epoch = 0.0
    try:
        with open(t_path, "r", encoding="utf-8", errors="replace") as fh:
            for raw_line in fh:
                if not raw_line.strip():
                    continue
                try:
                    step = json.loads(raw_line)
                except Exception:
                    continue
                stype = str(step.get("type") or "")
                sidx = int(step.get("step_index") or 0)
                s_status = str(step.get("status") or "DONE").upper()
                created_at = str(step.get("created_at") or "")
                step_epoch = _parse_iso_epoch(created_at, 0.0)
                raw_content = str(step.get("content") or "")
                trunc_fields = step.get("truncated_fields")
                is_content_truncated = (
                    (isinstance(trunc_fields, list) and "content" in trunc_fields)
                    or ("<truncated " in raw_content)
                )
                if is_content_truncated:
                    if full_contents_cache is None:
                        full_contents_cache = _load_full_transcript_contents(t_path)
                    if sidx in full_contents_cache:
                        raw_content = full_contents_cache[sidx]

                if "<USER_SETTINGS_CHANGE>" in raw_content:
                    m_mod = re.search(r"Model Selection` from [^\n]+? to ([^\.\n]+)", raw_content)
                    if m_mod:
                        detected_model = m_mod.group(1).strip()

                if stype == "USER_INPUT":
                    clean_u = _clean_user_text(raw_content)
                    u_atts = _extract_user_attachments_from_step(step, raw_content)
                    if clean_u or u_atts:
                        if base_turn_idx is None:
                            cur_turn += 1
                        messages.append({
                            "role": "user",
                            "text": clean_u,
                            "attachments": u_atts,
                            "time": created_at,
                            "stepIndex": sidx,
                            "turnIdx": max(0, cur_turn),
                        })
                elif stype == "PLANNER_RESPONSE":
                    in_tok = int(step.get("input_tokens") or 0)
                    out_tok = int(step.get("output_tokens") or 0)
                    cache_tok = int(step.get("cache_read_tokens") or 0)
                    if in_tok > 0 or out_tok > 0 or cache_tok > 0:
                        token_stats["inputTokens"] += in_tok
                        token_stats["outputTokens"] += out_tok
                        token_stats["cacheReadTokens"] += cache_tok
                        dt_s = (
                            max(1.2, min(25.0, step_epoch - prev_step_epoch))
                            if (step_epoch > 0 and prev_step_epoch > 0 and step_epoch >= prev_step_epoch)
                            else 4.0
                        )
                        eff_tok = in_tok + out_tok + int(cache_tok * 0.20)
                        rate_tok_s = max(18, int(round(eff_tok / dt_s)))
                        token_stats["stepSamples"].append({
                            "epoch": step_epoch,
                            "tokens": in_tok + out_tok + cache_tok,
                            "rate": min(36000, rate_tok_s),
                        })
                    if step_epoch > 0:
                        prev_step_epoch = step_epoch

                    eff_turn = max(0, cur_turn)
                    tool_chips: list[dict[str, str]] = []
                    for tc in (step.get("tool_calls") or []):
                        if not isinstance(tc, dict):
                            continue
                        tname = str(tc.get("name") or "")
                        targs = tc.get("args") if isinstance(tc.get("args"), dict) else {}
                        short_target = ""

                        if tname in {"read_file", "write_file", "edit_file"}:
                            raw_p = _unwrap_arg_str(targs.get("Path"))
                            p_obj = _normalize_local_path(raw_p)
                            s_ln_raw = _unwrap_arg_str(targs.get("StartLine"))
                            e_ln_raw = _unwrap_arg_str(targs.get("EndLine"))
                            s_ln = int(s_ln_raw) if s_ln_raw.isdigit() else None
                            e_ln = int(e_ln_raw) if e_ln_raw.isdigit() else None
                            line_tag = ""
                            if s_ln and e_ln:
                                line_tag = f"#L{s_ln}-{e_ln}"
                            elif s_ln:
                                line_tag = f"#L{s_ln}+"
                            short_target = (f"{p_obj.name} {line_tag}".strip() if p_obj else raw_p[-36:])
                            if p_obj and not _is_noise_file(p_obj):
                                op_kind = "read" if tname == "read_file" else "write"
                                sub_op = "analyze" if tname == "read_file" else ("edit" if tname == "edit_file" else "create")
                                code_snip = ""
                                if op_kind == "write":
                                    raw_code_arg = _unwrap_arg_str(targs.get("Replacement") if tname == "edit_file" else targs.get("Content"))
                                    if raw_code_arg:
                                        code_snip = "\n".join(raw_code_arg.splitlines()[:42])
                                file_events.append({
                                    "op": op_kind,
                                    "subOp": sub_op,
                                    "path": p_obj,
                                    "startLine": s_ln,
                                    "endLine": e_ln,
                                    "lineTag": line_tag,
                                    "codeSnippet": code_snip,
                                    "turnIdx": eff_turn,
                                    "linked": False,
                                    "stepIndex": sidx,
                                })
                        elif tname == "call_mcp_tool":
                            mcp_tool = _unwrap_arg_str(targs.get("ToolName"))
                            short_target = mcp_tool
                            mcp_args = _unwrap_arg_val(targs.get("Arguments"))
                            if isinstance(mcp_args, dict) and mcp_tool == "offload_task_to_app":
                                tfp = _unwrap_arg_str(mcp_args.get("target_file_path"))
                                p_obj = _normalize_local_path(tfp)
                                if p_obj:
                                    short_target = f"offload → {p_obj.name}"
                                    if not _is_noise_file(p_obj):
                                        file_events.append({
                                            "op": "write",
                                            "subOp": "create",
                                            "path": p_obj,
                                            "startLine": None,
                                            "endLine": None,
                                            "lineTag": "",
                                            "turnIdx": eff_turn,
                                            "linked": False,
                                            "stepIndex": sidx,
                                        })
                        elif tname == "run_command":
                            short_target = (
                                _unwrap_arg_str(targs.get("toolSummary"))
                                or _unwrap_arg_str(targs.get("CommandLine"))[:42]
                            )
                        elif tname == "swarm":
                            act = _unwrap_arg_str(targs.get("action"))
                            wnm = _unwrap_arg_str(targs.get("name"))
                            short_target = f"{act} {wnm}".strip()
                        elif tname == "invoke_subagent":
                            short_target = (
                                _unwrap_arg_str(targs.get("Role"))
                                or _unwrap_arg_str(targs.get("TypeName"))
                            )

                        if tname:
                            tool_chips.append({"name": tname, "target": short_target[:48]})

                    clean_a = _clean_assistant_text(raw_content)
                    if clean_a:
                        for m_link in re.finditer(r"file:///([^\)\s\"'>]+)", clean_a):
                            p_lnk = _normalize_local_path("file:///" + m_link.group(1))
                            if p_lnk and not _is_noise_file(p_lnk):
                                file_events.append({
                                    "op": "link",
                                    "subOp": "link",
                                    "path": p_lnk,
                                    "startLine": None,
                                    "endLine": None,
                                    "lineTag": "",
                                    "turnIdx": eff_turn,
                                    "linked": True,
                                    "stepIndex": sidx,
                                })

                    if clean_a or tool_chips:
                        messages.append({
                            "role": "assistant",
                            "text": clean_a,
                            "tools": tool_chips,
                            "time": created_at,
                            "stepIndex": sidx,
                            "turnIdx": eff_turn,
                            "isFinalStep": bool(clean_a and not tool_chips and s_status == "DONE"),
                        })
                elif step_epoch > 0:
                    prev_step_epoch = step_epoch
    except Exception as exc:
        logger.debug("Transcript parse error (%s): %s", t_path, exc)

    return messages, file_events, detected_model, token_stats


def _clean_swarm_brief(raw_text: str, worker_name: str) -> str:
    txt = re.sub(rf"^@{re.escape(worker_name)}\b\s*", "", (raw_text or "").strip())
    for line in txt.splitlines():
        s = re.sub(r"[`*_#>]+", "", line).strip(" -:\t")
        if len(s) >= 4:
            return s[:38]
    return f"Sub-agent @{worker_name}"[:38]


def _build_numbered_turns(messages: list[dict[str, Any]], conv_status: str) -> list[dict[str, Any]]:
    """Group raw user + assistant steps into clean numbered collapsible turns (1..N) with strict completion & queue states."""
    turns_map: dict[int, dict[str, Any]] = {}
    ordered_tids: list[int] = []

    for m in messages:
        t_idx = int(m.get("turnIdx") or 0)
        role = m.get("role")
        if role == "user":
            if t_idx not in turns_map:
                turns_map[t_idx] = {
                    "userTexts": [],
                    "attachments": [],
                    "assistantTexts": [],
                    "toolCount": 0,
                    "hasFinalStep": False,
                    "userStepIndex": int(m.get("stepIndex") if m.get("stepIndex") is not None else -1),
                    "time": str(m.get("time") or ""),
                }
                ordered_tids.append(t_idx)
            elif turns_map[t_idx]["userStepIndex"] < 0 and m.get("stepIndex") is not None:
                turns_map[t_idx]["userStepIndex"] = int(m["stepIndex"])
            u_txt = str(m.get("text") or "").strip()
            if u_txt and u_txt not in turns_map[t_idx]["userTexts"]:
                turns_map[t_idx]["userTexts"].append(u_txt)
            for att in (m.get("attachments") or []):
                if att not in turns_map[t_idx]["attachments"]:
                    turns_map[t_idx]["attachments"].append(att)
            if m.get("time"):
                turns_map[t_idx]["time"] = str(m["time"])
        elif role == "assistant":
            if t_idx not in turns_map:
                turns_map[t_idx] = {
                    "userTexts": [],
                    "attachments": [],
                    "assistantTexts": [],
                    "toolCount": 0,
                    "hasFinalStep": False,
                    "userStepIndex": -1,
                    "time": str(m.get("time") or ""),
                }
                ordered_tids.append(t_idx)
            turns_map[t_idx]["toolCount"] += len(m.get("tools") or [])
            if m.get("isFinalStep"):
                turns_map[t_idx]["hasFinalStep"] = True
            a_txt = str(m.get("text") or "").strip()
            if a_txt and (not turns_map[t_idx]["assistantTexts"] or turns_map[t_idx]["assistantTexts"][-1] != a_txt):
                turns_map[t_idx]["assistantTexts"].append(a_txt)
            if m.get("time"):
                turns_map[t_idx]["time"] = str(m["time"])

    total_t = len(ordered_tids)
    last_completed_pos = -1
    for pos, t_idx in enumerate(ordered_tids):
        rec = turns_map[t_idx]
        a_check = "\n\n".join(rec["assistantTexts"]).strip()
        if a_check and (rec["hasFinalStep"] or conv_status != "running"):
            last_completed_pos = pos

    active_pos = -1
    if conv_status == "running" and total_t > 0 and last_completed_pos < total_t - 1:
        for pos in range(last_completed_pos + 1, total_t):
            rec = turns_map[ordered_tids[pos]]
            if rec["toolCount"] > 0 or rec["assistantTexts"]:
                active_pos = pos
                break
        if active_pos < 0:
            active_pos = last_completed_pos + 1

    turns: list[dict[str, Any]] = []
    for pos, t_idx in enumerate(ordered_tids):
        rec = turns_map[t_idx]
        turn_num = pos + 1
        u_full = "\n\n".join(rec["userTexts"]).strip()
        a_full = "\n\n".join(rec["assistantTexts"]).strip()
        has_final_reply = bool(a_full) and (bool(rec["hasFinalStep"]) or conv_status != "running")

        if has_final_reply:
            t_status = "done"
        elif conv_status == "running" and pos > last_completed_pos:
            if pos == active_pos:
                t_status = "running"
            elif pos > active_pos:
                t_status = "queued"
            else:
                t_status = "ingested"
        elif pos < last_completed_pos:
            t_status = "merged"
        else:
            t_status = "pending"

        turns.append({
            "turnNumber": turn_num,
            "userTitle": _summarize_turn_title(u_full, rec["attachments"], turn_num),
            "userText": u_full,
            "attachments": rec["attachments"],
            "assistantText": a_full,
            "toolCount": int(rec["toolCount"]),
            "time": rec["time"],
            "status": t_status,
            "hasFinalReply": has_final_reply,
            "userStepIndex": int(rec["userStepIndex"]),
        })
    return turns


def build_conversation_snapshot(
    cid: str,
    summaries: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    cid = str(cid or "").strip()
    if summaries is None:
        summaries = _fetch_all_summaries_safe()
    info = summaries.get(cid) if isinstance(summaries.get(cid), dict) else {}
    status_raw = str(info.get("status") or ("CASCADE_RUN_STATUS_RUNNING" if _is_cli_proc_running(cid) else "CASCADE_RUN_STATUS_IDLE"))
    status = "running" if ("RUNNING" in status_raw or _is_cli_proc_running(cid)) else "idle"

    annotations = info.get("annotations") if isinstance(info.get("annotations"), dict) else {}
    title = str(annotations.get("title") or info.get("summary") or "").strip()
    if not title:
        title = _extract_first_user_title(cid) or (f"新对话 {cid[:8]}" if cid else "新建对话")

    cid_brain_dir = _resolve_brain_dir(cid)
    main_t_path = cid_brain_dir / ".system_generated/logs/transcript.jsonl"
    messages, all_file_events, detected_model, main_tok_stats = _extract_file_touches_from_transcript(main_t_path)

    if not messages and cid:
        try:
            traj_resp = agy_rpc("GetCascadeTrajectory", {"cascadeId": cid}, timeout=5.0)
            status_raw = str(traj_resp.get("status") or status_raw)
            status = "running" if "RUNNING" in status_raw else "idle"
            steps = ((traj_resp.get("trajectory") or {}).get("steps") or [])
            turn_i = -1
            for idx_s, st in enumerate(steps):
                if not isinstance(st, dict):
                    continue
                st_type = str(st.get("type") or "")
                if "USER_INPUT" in st_type:
                    u_items = ((st.get("userInput") or {}).get("items") or [])
                    u_txt = "\n".join(str(it.get("text") or "") for it in u_items if isinstance(it, dict))
                    clean_u = _clean_user_text(u_txt)
                    if clean_u:
                        turn_i += 1
                        messages.append({
                            "role": "user",
                            "text": clean_u,
                            "attachments": [],
                            "time": "",
                            "stepIndex": idx_s,
                            "turnIdx": max(0, turn_i),
                        })
                elif st.get("plannerResponse"):
                    pr = st["plannerResponse"]
                    a_txt = _clean_assistant_text(str(pr.get("modifiedResponse") or pr.get("response") or ""))
                    t_chips = [
                        {"name": str(tc.get("name") or ""), "target": ""}
                        for tc in (pr.get("toolCalls") or [])
                        if isinstance(tc, dict) and tc.get("name")
                    ]
                    if a_txt or t_chips:
                        messages.append({
                            "role": "assistant",
                            "text": a_txt,
                            "tools": t_chips,
                            "time": "",
                            "stepIndex": idx_s,
                            "turnIdx": max(0, turn_i),
                            "isFinalStep": bool(a_txt and not t_chips),
                        })
        except Exception:
            pass

    turns = _build_numbered_turns(messages, status)
    max_user_turn = max((m.get("turnIdx", 0) for m in messages if m.get("role") == "user"), default=0)

    workers: list[dict[str, Any]] = []
    seen_worker_cids: set[str] = set()

    swarm_dir = cid_brain_dir / ".system_generated/swarm"
    briefs_by_name: dict[str, str] = {}
    full_briefs_by_name: dict[str, str] = {}
    board_posts_by_name: dict[str, list[dict[str, str]]] = {}
    board_file = swarm_dir / "board.jsonl"
    if board_file.is_file():
        try:
            for bline in board_file.read_text(encoding="utf-8", errors="replace").splitlines():
                if not bline.strip():
                    continue
                bmsg = json.loads(bline)
                btxt = str(bmsg.get("text") or "").strip()
                btime = str(bmsg.get("time") or "")
                bagent = str(bmsg.get("agent") or "")
                if bmsg.get("kind") == "brief":
                    m_lead = re.match(r"^@([a-zA-Z0-9_\-]+)\b", btxt)
                    if m_lead:
                        wn = m_lead.group(1)
                        briefs_by_name[wn] = _clean_swarm_brief(btxt, wn)
                        full_briefs_by_name[wn] = btxt
                elif bagent and bagent != "coordinator" and btxt:
                    board_posts_by_name.setdefault(bagent, []).append({"text": btxt, "time": btime})
        except Exception:
            pass

    for w_name, w_info in _read_swarm_child_ids(cid):
        w_cid = str(w_info.get("conversation_id") or "").strip()
        if w_cid:
            seen_worker_cids.add(w_cid)
        child_sum = summaries.get(w_cid) if isinstance(summaries.get(w_cid), dict) else {}
        child_running = "RUNNING" in str(child_sum.get("status") or "")
        if w_info.get("killed") or str(w_info.get("phase") or "").upper() == "KILLED":
            w_state = "DONE"
        elif child_running or w_info.get("wake_mode") == "working":
            w_state = "WORK"
        else:
            w_state = "WAIT"

        raw_m = str(w_info.get("applied_model") or w_info.get("model") or "")
        if raw_m and not detected_model:
            detected_model = raw_m
        brief_txt = briefs_by_name.get(w_name) or _extract_first_user_title(w_cid) or f"Swarm worker @{w_name}"
        detail = _build_worker_detail(
            w_cid,
            w_name,
            brief_txt,
            full_brief=full_briefs_by_name.get(w_name, ""),
            board_posts=board_posts_by_name.get(w_name, []),
        )
        workers.append({
            "id": w_name.upper().replace("-", "_")[:14],
            "handle": w_name,
            "conversationId": w_cid,
            "model": _prettify_model_name(raw_m),
            "dept": f"{w_name.upper()[:9]}·{w_state}",
            "status": w_state,
            "task": brief_txt[:36],
            "messages": detail["messages"],
            "traceHeader": detail["traceHeader"],
            "traceTools": detail["traceTools"],
            "traceText": detail["traceText"],
            "code": detail["code"],
        })

    child_entries: list[tuple[str, dict[str, Any]]] = []
    for cand_cid, cand_info in summaries.items():
        if cand_cid in seen_worker_cids or not isinstance(cand_info, dict):
            continue
        p_id = str((cand_info.get("trajectoryMetadata") or {}).get("parentConversationId") or "").strip()
        if p_id == cid:
            child_entries.append((cand_cid, cand_info))

    child_entries.sort(key=lambda item: _parse_iso_epoch(str(item[1].get("createdTime") or ""), 0.0))
    for idx_c, (c_cid, c_info) in enumerate(child_entries):
        seen_worker_cids.add(c_cid)
        c_running = "RUNNING" in str(c_info.get("status") or "")
        c_state = "WORK" if c_running else "DONE"
        c_title = (
            str(((c_info.get("annotations") or {}).get("title")) or c_info.get("summary") or "").strip()
            or _extract_first_user_title(c_cid)
            or f"Sub-Agent #{idx_c + 1}"
        )
        short_handle = f"SUB_{idx_c + 1:02d}"
        detail = _build_worker_detail(c_cid, short_handle.lower(), c_title)
        workers.append({
            "id": short_handle,
            "handle": short_handle.lower(),
            "conversationId": c_cid,
            "model": _prettify_model_name(detected_model),
            "dept": f"{short_handle}·{c_state}",
            "status": c_state,
            "task": c_title[:36],
            "messages": detail["messages"],
            "traceHeader": detail["traceHeader"],
            "traceTools": detail["traceTools"],
            "traceText": detail["traceText"],
            "code": detail["code"],
        })

    combined_step_samples = list(main_tok_stats["stepSamples"])
    tot_in_tok = int(main_tok_stats["inputTokens"])
    tot_out_tok = int(main_tok_stats["outputTokens"])
    tot_cache_tok = int(main_tok_stats["cacheReadTokens"])

    for w_cid in seen_worker_cids:
        wt_path = _resolve_brain_dir(w_cid) / ".system_generated/logs/transcript.jsonl"
        if wt_path.is_file():
            child_turn = max_user_turn if (
                main_t_path.is_file() and abs(wt_path.stat().st_mtime - main_t_path.stat().st_mtime) < 180.0
            ) else 0
            _, w_fevents, _, w_tok_stats = _extract_file_touches_from_transcript(wt_path, base_turn_idx=child_turn)
            all_file_events.extend(w_fevents)
            tot_in_tok += int(w_tok_stats["inputTokens"])
            tot_out_tok += int(w_tok_stats["outputTokens"])
            tot_cache_tok += int(w_tok_stats["cacheReadTokens"])
            combined_step_samples.extend(w_tok_stats["stepSamples"])

    combined_step_samples.sort(key=lambda s: float(s.get("epoch") or 0.0))

    # Determine directories where this conversation ACTUALLY produced/edited files (`op == "write"`).
    # This strictly prevents read-only glimpses of foreign files (e.g. `MOSS提示词工作台.bat` on Desktop)
    # from ever polluting either the Outermost Ring OR the Thinking Slabs!
    written_file_keys: set[str] = set()
    written_dirs: set[str] = set()
    for ev in all_file_events:
        if ev["op"] == "write":
            p_w: Path = ev["path"]
            if p_w.is_file() and not _is_noise_file(p_w):
                nk_w = os.path.normcase(os.path.normpath(str(p_w)))
                written_file_keys.add(nk_w)
                parent_norm = os.path.normcase(os.path.normpath(str(p_w.parent)))
                # Do not treat shared Desktop / Downloads as a blanket project root for unrelated files!
                if not parent_norm.endswith(("\\desktop", "\\downloads")):
                    written_dirs.add(parent_norm)

    def _belongs_to_conversation_scope(ev_item: dict[str, Any]) -> bool:
        p_cand: Path = ev_item["path"]
        nk_cand = os.path.normcase(os.path.normpath(str(p_cand)))
        if nk_cand in written_file_keys:
            return True
        if not written_dirs:
            return int(ev_item.get("turnIdx") or 0) >= max(0, max_user_turn - 1)
        cand_dir = os.path.normcase(os.path.normpath(str(p_cand.parent)))
        for wd in written_dirs:
            if cand_dir == wd or cand_dir.startswith(wd + os.sep):
                return True
        return False

    # 1) Outermost Ring (`outer_files`): Accumulates real produced code blocks (`op == "write"`) across recent turns!
    #    - Starts EMPTY (`[]`) at conversation start when no code has been produced yet.
    #    - Packs contiguously as work progresses, capped at the LATEST 15 code blocks (`OUTER_RING_CAPACITY = 15`)
    #      so at full capacity all 15 original-size bevel screens seamlessly fill 360° with zero gaps!
    OUTER_RING_CAPACITY = 15
    write_candidates = [
        ev for ev in all_file_events
        if ev["op"] == "write"
        and ev["path"].is_file()
        and not _is_noise_file(ev["path"])
        and ev["path"].suffix.lower() in TEXT_PREVIEW_EXTS
        and "/antigravity/scratch/" not in ev["path"].as_posix().lower()
    ]
    write_candidates.sort(
        key=lambda e: (-int(e.get("turnIdx") or 0), -int(e.get("stepIndex") or 0))
    )

    outer_files: list[dict[str, Any]] = []
    seen_outer_blocks: set[tuple[str, str]] = set()
    for ev in write_candidates:
        if len(outer_files) >= OUTER_RING_CAPACITY:
            break
        p_obj = ev["path"]
        norm_p = os.path.normpath(str(p_obj))
        norm_k = os.path.normcase(norm_p)
        snip = str(ev.get("codeSnippet") or "").strip()
        if not snip:
            snip = read_preview(p_obj, 42)
        block_sig = (norm_k, snip[:180])
        if block_sig in seen_outer_blocks:
            continue
        seen_outer_blocks.add(block_sig)

        _, core_role = _is_core_file(p_obj)
        base_role = core_role or ((p_obj.suffix.lstrip(".").upper() or "MOD") + "_OUT")
        t_num = int(ev.get("turnIdx") or 0)
        role_lbl = f"{base_role}·R{t_num}" if t_num > 0 else base_role
        outer_files.append({
            "file": p_obj.name,
            "fullPath": norm_p,
            "role": role_lbl,
            "code": snip,
        })

    # 2) Inner Thinking Slabs (`slabs`): Step-by-step `已分析 <file> #L<start>-<end>` & `已编辑 <file>` slices
    #    matching Antigravity's real thinking trace (newest turn first, scoped strictly to this conversation's files!).
    slabs: list[dict[str, Any]] = []
    seen_slab_slices: set[tuple[str, str, str]] = set()
    scoped_slab_events = [
        ev for ev in all_file_events
        if ev["op"] in {"read", "write"}
        and ev["path"].is_file()
        and not _is_noise_file(ev["path"])
        and ev["path"].suffix.lower() in TEXT_PREVIEW_EXTS
        and "/antigravity/scratch/" not in ev["path"].as_posix().lower()
        and _belongs_to_conversation_scope(ev)
    ]
    scoped_slab_events.sort(
        key=lambda e: (-int(e.get("turnIdx") or 0), -int(e.get("stepIndex") or 0))
    )

    for ev in scoped_slab_events:
        if len(slabs) >= 28:
            break
        p_obj = ev["path"]
        norm_k = os.path.normcase(os.path.normpath(str(p_obj)))
        sub_op = str(ev.get("subOp") or ("analyze" if ev["op"] == "read" else "edit"))
        line_tag = str(ev.get("lineTag") or "")
        slice_key = (norm_k, sub_op, line_tag)
        if slice_key in seen_slab_slices:
            continue
        seen_slab_slices.add(slice_key)

        ext_up = p_obj.suffix.lstrip(".").upper() or "FILE"
        if sub_op == "analyze":
            prefix_cn = "已分析"
            kind_badge = f"已分析 · {ext_up}"
        elif sub_op == "create":
            prefix_cn = "已生成"
            kind_badge = f"已生成 · {ext_up}"
        else:
            prefix_cn = "已编辑"
            kind_badge = f"已编辑 · {ext_up}"

        display_label = f"{prefix_cn} {p_obj.name}" + (f" {line_tag}" if line_tag else "")
        slabs.append({
            "file": display_label,
            "rawFile": p_obj.name,
            "fullPath": os.path.normpath(str(p_obj)),
            "kind": kind_badge,
            "op": ev["op"],
            "code": read_line_range_preview(
                p_obj,
                ev.get("startLine"),
                ev.get("endLine"),
                max_lines=76,
            ),
        })

    # Cumulative conversation-wide deliverables (oldest -> newest tracked across ALL turns, returned newest-first
    # up to 64 historical records so the 3D outermost eyes fill 1-by-1 and rotate FIFO while modal shows full history!)
    runtime_state_names = {
        "ophanim_wallpaper_state.json",
        "ophanim_config.json",
        "ophanim_toy_config.json",
        "ophanim_session_meta.json",
    }
    deliv_events_chron = [
        ev for ev in all_file_events
        if ev["op"] in {"write", "link"}
        and ev["path"].is_file()
        and not _is_noise_file(ev["path"])
        and ev["path"].name.lower() not in runtime_state_names
        and "/.user_uploaded/" not in ev["path"].as_posix().lower()
        and ("/antigravity/scratch/" not in ev["path"].as_posix().lower() or ev["linked"])
    ]
    deliv_events_chron.sort(
        key=lambda e: (int(e.get("turnIdx") or 0), int(e.get("stepIndex") or 0))
    )

    cum_deliv_map: dict[str, dict[str, Any]] = {}
    for ev in deliv_events_chron:
        p_obj = ev["path"]
        nk = os.path.normcase(os.path.normpath(str(p_obj)))
        t_num = max(1, int(ev.get("turnIdx") or 1))
        s_idx = int(ev.get("stepIndex") or 0)
        if nk not in cum_deliv_map:
            cum_deliv_map[nk] = {
                "path": p_obj,
                "firstTurn": t_num,
                "latestTurn": t_num,
                "latestStep": s_idx,
                "deliveryCount": 1,
                "linked": bool(ev.get("linked")),
            }
        else:
            rec = cum_deliv_map[nk]
            rec["path"] = p_obj
            if (t_num, s_idx) >= (rec["latestTurn"], rec["latestStep"]):
                if t_num != rec["latestTurn"] or ev["op"] == "write":
                    rec["deliveryCount"] += 1
                rec["latestTurn"] = t_num
                rec["latestStep"] = s_idx
            if ev.get("linked"):
                rec["linked"] = True

    sorted_cum_records = sorted(
        cum_deliv_map.values(),
        key=lambda r: (-int(r["latestTurn"]), -int(r["latestStep"])),
    )

    deliverables: list[dict[str, Any]] = []
    for rec in sorted_cum_records[:64]:
        p_obj = rec["path"]
        try:
            sz = p_obj.stat().st_size
        except OSError:
            continue
        try:
            siblings = [
                x.name for x in p_obj.parent.iterdir()
                if x.is_file() and x.name != p_obj.name and not _is_noise_file(x)
            ][:8]
        except OSError:
            siblings = []
        ext_up = p_obj.suffix.lstrip(".").upper() or "FILE"
        deliverables.append({
            "file": p_obj.name,
            "badge": f"{ext_up} · {format_size(sz)}",
            "turnNumber": int(rec["latestTurn"]),
            "firstTurnNumber": int(rec["firstTurn"]),
            "deliveryCount": int(rec["deliveryCount"]),
            "dirPath": os.path.normpath(str(p_obj.parent)),
            "fullPath": os.path.normpath(str(p_obj)),
            "siblings": siblings,
            "code": read_preview(p_obj, 64),
        })

    return {
        "cascadeId": cid,
        "shortId": cid[:8] if cid else "NEW",
        "title": title,
        "status": status,
        "statusRaw": status_raw,
        "activeModel": detected_model or "gemini-4-carbon-medium",
        "stepCount": int(info.get("stepCount") or len(messages)),
        "turns": turns,
        "messages": messages[-64:],
        "workers": workers[:12],
        "slabs": slabs,
        "outerFiles": outer_files,
        "deliverables": deliverables,
        "tokenStats": {
            "totalTokens": tot_in_tok + tot_out_tok + tot_cache_tok,
            "inputTokens": tot_in_tok,
            "outputTokens": tot_out_tok,
            "cacheReadTokens": tot_cache_tok,
            "recentRates": [int(s["rate"]) for s in combined_step_samples[-56:]],
        },
    }


class ConversationLiveTracker:
    def __init__(self) -> None:
        self.bound_cid: str = ""
        self.file_offsets: dict[str, int] = {}
        self.board_offset: int = 0
        self.last_board_seq: int = 0
        self.last_status: str = "idle"
        self.last_msg_sig: tuple[int, str] = (0, "")
        self.last_running_snap_mono: float = 0.0
        self.pending_returns: dict[str, list[dict[str, Any]]] = {}

    def bind(self, cid: str) -> None:
        cid = str(cid or "").strip()
        self.bound_cid = cid
        self.file_offsets.clear()
        self.pending_returns.clear()
        self.board_offset = 0
        self.last_board_seq = 0
        self.last_running_snap_mono = 0.0
        if not cid:
            return
        main_t = _resolve_brain_dir(cid) / ".system_generated/logs/transcript.jsonl"
        if main_t.is_file():
            self.file_offsets[str(main_t)] = main_t.stat().st_size
        for _, w_info in _read_swarm_child_ids(cid):
            w_cid = str(w_info.get("conversation_id") or "").strip()
            if w_cid:
                wt = _resolve_brain_dir(w_cid) / ".system_generated/logs/transcript.jsonl"
                if wt.is_file():
                    self.file_offsets[str(wt)] = wt.stat().st_size
        board_f = _resolve_brain_dir(cid) / ".system_generated/swarm/board.jsonl"
        if board_f.is_file():
            try:
                raw_b = board_f.read_bytes()
                self.board_offset = len(raw_b)
                for ln in raw_b.decode("utf-8", errors="replace").splitlines():
                    if ln.strip():
                        self.last_board_seq = max(self.last_board_seq, int(json.loads(ln).get("seq") or 0))
            except Exception:
                pass

    def poll_updates(self, cid: str) -> dict[str, Any]:
        cid = str(cid or "").strip()
        if not cid:
            return {"changed": False, "beamEvents": [], "snapshot": None}
        if cid != self.bound_cid:
            self.bind(cid)

        beam_events: list[dict[str, Any]] = []
        has_new_lines = False

        swarm_workers = _read_swarm_child_ids(cid)
        worker_index_by_cid = {
            str(info.get("conversation_id") or "").strip(): idx
            for idx, (_, info) in enumerate(swarm_workers[:12])
            if info.get("conversation_id")
        }
        worker_index_by_name = {name: idx for idx, (name, _) in enumerate(swarm_workers[:12])}

        watched_paths: list[tuple[Path, int | None]] = [
            (_resolve_brain_dir(cid) / ".system_generated/logs/transcript.jsonl", None)
        ]
        for w_cid, w_idx in worker_index_by_cid.items():
            watched_paths.append((_resolve_brain_dir(w_cid) / ".system_generated/logs/transcript.jsonl", w_idx))

        for t_path, worker_idx in watched_paths:
            if not t_path.is_file():
                continue
            key = str(t_path)
            try:
                cur_sz = t_path.stat().st_size
            except OSError:
                continue
            prev_sz = self.file_offsets.get(key, 0)
            if cur_sz < prev_sz:
                prev_sz = 0
            if cur_sz == prev_sz:
                continue

            self.file_offsets[key] = cur_sz
            has_new_lines = True
            try:
                with open(t_path, "rb") as fh:
                    fh.seek(prev_sz)
                    chunk = fh.read(cur_sz - prev_sz).decode("utf-8", errors="replace")
                for raw_ln in chunk.splitlines():
                    if not raw_ln.strip():
                        continue
                    try:
                        step = json.loads(raw_ln)
                    except Exception:
                        continue
                    stype = str(step.get("type") or "")
                    if stype in {"GENERIC", "TOOL_RESULT", "TOOL_RESPONSE", "MCP_TOOL_RESULT"}:
                        queued = self.pending_returns.get(key) or []
                        if queued:
                            beam_events.append(queued.pop(0))
                        continue
                    if stype != "PLANNER_RESPONSE":
                        continue
                    ret_queue = self.pending_returns.setdefault(key, [])
                    for tc in (step.get("tool_calls") or []):
                        if not isinstance(tc, dict):
                            continue
                        tname = str(tc.get("name") or "")
                        targs = tc.get("args") if isinstance(tc.get("args"), dict) else {}
                        if tname in {"read_file", "write_file", "edit_file"}:
                            p_obj = _normalize_local_path(_unwrap_arg_str(targs.get("Path")))
                            s_ln_raw = _unwrap_arg_str(targs.get("StartLine"))
                            e_ln_raw = _unwrap_arg_str(targs.get("EndLine"))
                            s_ln = int(s_ln_raw) if s_ln_raw.isdigit() else None
                            e_ln = int(e_ln_raw) if e_ln_raw.isdigit() else None
                            line_tag = f"#L{s_ln}-{e_ln}" if (s_ln and e_ln) else (f"#L{s_ln}+" if s_ln else "")
                            if p_obj and p_obj.is_file() and not _is_noise_file(p_obj):
                                ext_up = p_obj.suffix.lstrip(".").upper() or "FILE"
                                if tname == "read_file":
                                    disp_lbl = f"已分析 {p_obj.name}" + (f" {line_tag}" if line_tag else "")
                                    slice_code = read_line_range_preview(p_obj, s_ln, e_ln, max_lines=72)
                                    ret_queue.append({
                                        "op": "read",
                                        "file": disp_lbl,
                                        "kind": f"已分析 · {ext_up}",
                                        "code": slice_code,
                                    })
                                    beam_events.append({
                                        "op": "read",
                                        "file": disp_lbl,
                                        "kind": f"已分析 · {ext_up}",
                                        "code": slice_code,
                                    })
                                elif _is_deliverable_candidate(p_obj, False):
                                    st_sz = p_obj.stat().st_size
                                    beam_events.append({
                                        "op": "deliver",
                                        "file": p_obj.name,
                                        "badge": f"{ext_up} · {format_size(st_sz)}",
                                        "dirPath": os.path.normpath(str(p_obj.parent)),
                                        "fullPath": os.path.normpath(str(p_obj)),
                                        "code": read_preview(p_obj, 55),
                                    })
                                    ret_queue.append({"op": "read", "file": f"已生成 {p_obj.name}", "kind": f"已生成 · {ext_up}"})
                                else:
                                    op_lbl = "已生成" if tname == "write_file" else "已编辑"
                                    disp_w_lbl = f"{op_lbl} {p_obj.name}"
                                    is_c, c_role = _is_core_file(p_obj)
                                    if is_c:
                                        beam_events.append({
                                            "op": "exec",
                                            "tier": "outer",
                                            "file": p_obj.name,
                                            "role": c_role,
                                            "code": read_preview(p_obj, 46),
                                        })
                                    beam_events.append({
                                        "op": "write",
                                        "file": disp_w_lbl,
                                        "kind": f"{op_lbl} · {ext_up}",
                                        "code": read_preview(p_obj, 68),
                                    })
                                    ret_queue.append({"op": "read", "file": disp_w_lbl, "kind": f"{op_lbl} · {ext_up}"})
                                if worker_idx is not None:
                                    beam_events.append({
                                        "op": "swarm_beam",
                                        "workerIdx": worker_idx,
                                        "dir": "star_to_slab",
                                    })
                        elif tname in {"swarm", "invoke_subagent", "send_message"}:
                            w_target = worker_idx if worker_idx is not None else 0
                            beam_events.append({
                                "op": "swarm_beam",
                                "workerIdx": w_target,
                                "dir": "carbon_to_star" if worker_idx is None else "star_to_carbon",
                            })
                            ret_queue.append({
                                "op": "swarm_beam",
                                "workerIdx": w_target,
                                "dir": "star_to_carbon",
                            })
                        elif tname in {"run_command", "call_mcp_tool", "search_web", "grep_search", "find_by_name"}:
                            cmd_label = _unwrap_arg_str(targs.get("toolSummary") or targs.get("ToolName") or targs.get("query") or tname)[:36] or tname
                            cmd_body = _unwrap_arg_str(targs.get("CommandLine") or targs.get("Arguments") or targs.get("query") or tname)[:600]
                            beam_events.append({
                                "op": "write",
                                "file": f"{tname}.call",
                                "kind": "TOOL_CALL",
                                "code": f"# TOOL DISPATCH: {cmd_label}\n{cmd_body}",
                            })
                            ret_queue.append({
                                "op": "read",
                                "file": f"{tname}.call",
                                "kind": "TOOL_RET",
                            })
            except Exception as exc:
                logger.debug("Incremental chunk error: %s", exc)

        board_f = _resolve_brain_dir(cid) / ".system_generated/swarm/board.jsonl"
        if board_f.is_file():
            try:
                cur_bsz = board_f.stat().st_size
                if cur_bsz < self.board_offset:
                    self.board_offset = 0
                if cur_bsz > self.board_offset:
                    with open(board_f, "rb") as bfh:
                        bfh.seek(self.board_offset)
                        b_chunk = bfh.read(cur_bsz - self.board_offset).decode("utf-8", errors="replace")
                    self.board_offset = cur_bsz
                    for bln in b_chunk.splitlines():
                        if not bln.strip():
                            continue
                        b_obj = json.loads(bln)
                        seq = int(b_obj.get("seq") or 0)
                        if seq > self.last_board_seq:
                            self.last_board_seq = seq
                            has_new_lines = True
                            sender = str(b_obj.get("agent") or "")
                            btxt = str(b_obj.get("text") or "")
                            if sender == "coordinator":
                                targets = [idx for nm, idx in worker_index_by_name.items() if f"@{nm}" in btxt]
                                for idx in (targets or [0])[:3]:
                                    beam_events.append({"op": "swarm_beam", "workerIdx": idx, "dir": "carbon_to_star"})
                            elif sender in worker_index_by_name:
                                beam_events.append({
                                    "op": "swarm_beam",
                                    "workerIdx": worker_index_by_name[sender],
                                    "dir": "star_to_carbon",
                                })
            except Exception:
                pass

        summaries = _fetch_all_summaries_safe()
        info = summaries.get(cid) if isinstance(summaries.get(cid), dict) else {}
        cur_status = "running" if ("RUNNING" in str(info.get("status") or "") or _is_cli_proc_running(cid)) else "idle"
        status_changed = cur_status != self.last_status
        self.last_status = cur_status

        now_m = time.monotonic()
        running_periodic_due = (cur_status == "running") and ((now_m - self.last_running_snap_mono) >= 5.0)
        if has_new_lines or status_changed or running_periodic_due:
            self.last_running_snap_mono = now_m
            snap = build_conversation_snapshot(cid, summaries=summaries)
            turns = snap.get("turns") or []
            last_t_txt = turns[-1]["assistantText"][:96] if turns else ""
            done_cnt = sum(1 for tr in turns if tr.get("hasFinalReply"))
            queued_cnt = sum(1 for tr in turns if tr.get("status") == "queued")
            msg_sig = (
                len(turns),
                f"{snap['status']}:{done_cnt}:{queued_cnt}:{len(snap['workers'])}:{len(snap['slabs'])}:{last_t_txt}",
            )
            if has_new_lines or status_changed or msg_sig != self.last_msg_sig:
                self.last_msg_sig = msg_sig
                return {
                    "changed": True,
                    "beamEvents": beam_events[:8],
                    "snapshot": snap,
                }

        return {"changed": False, "beamEvents": beam_events[:8], "snapshot": None}


def _load_best_cascade_config(target_cid: str, model_key: str = "inherit") -> dict[str, Any]:
    cfg: dict[str, Any] = {}

    if target_cid:
        try:
            t_resp = agy_rpc("GetCascadeTrajectory", {"cascadeId": target_cid}, timeout=5.0)
            ems = ((t_resp.get("trajectory") or {}).get("executorMetadatas") or [])
            for em in reversed(ems):
                if isinstance(em, dict) and isinstance(em.get("cascadeConfig"), dict):
                    cfg = copy.deepcopy(em["cascadeConfig"])
                    break
        except Exception:
            pass

    now = time.monotonic()
    if not cfg and _CASCADE_CFG_CACHE["cfg"] and (now - float(_CASCADE_CFG_CACHE["ts"])) < 120.0:
        cfg = copy.deepcopy(_CASCADE_CFG_CACHE["cfg"])

    if not cfg:
        summaries = _fetch_all_summaries_safe()
        sorted_cids = sorted(
            summaries.keys(),
            key=lambda k: str((summaries.get(k) or {}).get("lastModifiedTime") or ""),
            reverse=True,
        )
        for cand_id in sorted_cids[:6]:
            try:
                t_resp = agy_rpc("GetCascadeTrajectory", {"cascadeId": cand_id}, timeout=4.0)
                ems = ((t_resp.get("trajectory") or {}).get("executorMetadatas") or [])
                for em in reversed(ems):
                    if isinstance(em, dict) and isinstance(em.get("cascadeConfig"), dict):
                        cfg = copy.deepcopy(em["cascadeConfig"])
                        _CASCADE_CFG_CACHE.update({"cfg": copy.deepcopy(cfg), "ts": now})
                        break
                if cfg:
                    break
            except Exception:
                continue

    if not cfg and CASCADE_TEMPLATE_FILE.is_file():
        try:
            cfg = json.loads(CASCADE_TEMPLATE_FILE.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            cfg = {}

    if isinstance(cfg, dict) and model_key in MODEL_CATALOG_PB and model_key != "inherit":
        pb_val = MODEL_CATALOG_PB[model_key]["pb"]
        if pb_val:
            pcfg = cfg.setdefault("plannerConfig", {})
            if isinstance(pcfg, dict):
                pcfg["planModel"] = pb_val
                pcfg["modelName"] = model_key

    return cfg if isinstance(cfg, dict) else {}


def _send_via_agy_cli_ophanim(
    target_cid: str,
    exact_text: str,
    model_key: str = "inherit",
    staged_paths: list[str] | None = None,
) -> dict[str, Any]:
    """官方 `agy.exe` 非阻塞流式执行通道（当桌面 LS 返回 401 时由 Ophanim 自动接管）。"""
    agy_bin = _find_agy_cli_bin()
    if not agy_bin:
        return {"ok": False, "error": "桌面端 LS 返回 401 且未找到官方 agy CLI（请配置 PATH 或 OPHANIM_AGY_BIN 环境变量）"}

    req_cid = str(target_cid or "").strip()
    is_new_req = (not req_cid) or req_cid == "__new__" or req_cid.startswith("cli-new-")
    resume_cli_cid = ""
    source_desktop_cid = ""
    desktop_ctx = ""

    if not is_new_req:
        if (CLI_CONV_DIR / f"{req_cid}.db").is_file():
            resume_cli_cid = req_cid
        else:
            with _OPHANIM_CLI_LOCK:
                aliased = _OPHANIM_CLI_ALIAS.get(req_cid, "")
            if aliased and (CLI_CONV_DIR / f"{aliased}.db").is_file():
                resume_cli_cid = aliased
            elif (BRAIN_DIR / req_cid / ".system_generated/logs/transcript.jsonl").is_file():
                source_desktop_cid = req_cid
                t_path = BRAIN_DIR / req_cid / ".system_generated/logs/transcript.jsonl"
                try:
                    msgs, _, _, _ = _extract_file_touches_from_transcript(t_path)
                    recent_m = msgs[-6:]
                    ctx_lines = [f"【衔接桌面端 Antigravity 会话（{_extract_first_user_title(req_cid) or req_cid[:8]}）】"]
                    for m_it in recent_m:
                        role_lbl = "用户" if m_it.get("role") == "user" else "助手"
                        txt_m = str(m_it.get("text") or "").strip()
                        if txt_m:
                            ctx_lines.append(f"[{role_lbl}] {txt_m[:1500]}")
                    desktop_ctx = "\n".join(ctx_lines)[-5000:]
                except Exception:
                    desktop_ctx = ""

    eff_model = str(model_key or "").strip()
    if not eff_model or eff_model == "inherit":
        eff_model = "gemini-4-neon-medium"

    prompt_parts: list[str] = []
    if desktop_ctx:
        prompt_parts.append(desktop_ctx)
        prompt_parts.append("【用户在 Ophanim 圣殿中针对以上会话的最新指令】")
    if staged_paths:
        att_lines = "\n".join(f"- {p}" for p in staged_paths)
        prompt_parts.append(f"【用户附带的本地文件/图片路径（可用 read_file 查看）】\n{att_lines}")
    if exact_text.strip():
        prompt_parts.append(exact_text)
    full_prompt = "\n\n".join(prompt_parts).strip() or "请查看附带的文件"
    if len(full_prompt) > 24000:
        full_prompt = full_prompt[-24000:]

    cmd = [
        agy_bin,
        "-p",
        full_prompt,
        "--model",
        eff_model,
        "--dangerously-skip-permissions",
        "--output-format",
        "stream-json",
    ]
    if resume_cli_cid:
        cmd.extend(["--conversation", resume_cli_cid])

    try:
        proc = subprocess.Popen(
            cmd,
            cwd=_resolve_agy_cli_cwd(),
            env=_build_cli_env_oph(),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=_NO_WINDOW if os.name == "nt" else 0,
        )
    except Exception as exc:
        return {"ok": False, "error": f"启动官方 agy.exe 失败: {exc}"}

    init_evt = threading.Event()
    cid_holder: dict[str, str] = {"cid": resume_cli_cid}

    def _watch_cli() -> None:
        bound_cid = resume_cli_cid
        try:
            if proc.stdout is not None:
                for raw_ln in proc.stdout:
                    s_ln = raw_ln.strip()
                    if not s_ln:
                        continue
                    try:
                        ev = json.loads(s_ln)
                    except Exception:
                        continue
                    if isinstance(ev, dict):
                        cid_ev = str(ev.get("conversation_id") or ((ev.get("step_update") or {}).get("conversation_id")) or ((ev.get("result") or {}).get("conversation_id")) or "").strip()
                        if cid_ev and not bound_cid:
                            bound_cid = cid_ev
                            cid_holder["cid"] = cid_ev
                            with _OPHANIM_CLI_LOCK:
                                _OPHANIM_CLI_PROCS[cid_ev] = proc
                                if source_desktop_cid and source_desktop_cid != cid_ev:
                                    _OPHANIM_CLI_ALIAS[source_desktop_cid] = cid_ev
                            init_evt.set()
            proc.wait(timeout=1200)
        except Exception:
            pass
        finally:
            if proc.stdout is not None:
                try:
                    proc.stdout.close()
                except Exception:
                    pass
            try:
                if proc.poll() is None:
                    proc.wait(timeout=5)
            except Exception:
                pass
            if bound_cid:
                with _OPHANIM_CLI_LOCK:
                    if _OPHANIM_CLI_PROCS.get(bound_cid) is proc:
                        _OPHANIM_CLI_PROCS.pop(bound_cid, None)
            init_evt.set()

    if resume_cli_cid:
        with _OPHANIM_CLI_LOCK:
            _OPHANIM_CLI_PROCS[resume_cli_cid] = proc

    threading.Thread(target=_watch_cli, daemon=True).start()
    if not cid_holder["cid"]:
        init_evt.wait(timeout=8.0)

    final_cid = cid_holder["cid"] or resume_cli_cid or f"cli-{uuid.uuid4().hex[:12]}"
    return {
        "ok": True,
        "cascadeId": final_cid,
        "createdNew": bool(is_new_req or (source_desktop_cid and final_cid != source_desktop_cid)),
        "flushedNow": False,
        "stagedPaths": staged_paths or [],
        "backend": "agy_cli",
    }


def create_new_conversation(focus_ide: bool = True) -> dict[str, Any]:
    try:
        resp = agy_rpc(
            "StartCascade",
            {
                "source": "CORTEX_TRAJECTORY_SOURCE_CASCADE_CLIENT",
                "trajectoryType": "CORTEX_TRAJECTORY_TYPE_CASCADE",
            },
            timeout=10.0,
        )
        new_cid = str(resp.get("cascadeId") or "").strip()
        if not new_cid:
            raise RuntimeError("StartCascade 未返回有效会话 ID")
        if focus_ide:
            try:
                agy_rpc("SmartFocusConversation", {"cascadeId": new_cid}, timeout=3.0)
            except Exception:
                pass
        return {"ok": True, "cascadeId": new_cid}
    except Exception:
        if _find_agy_cli_bin():
            return {"ok": True, "cascadeId": f"cli-new-{uuid.uuid4().hex[:8]}", "backend": "agy_cli"}
        raise


def _sanitize_upload_filename(raw_name: str) -> str:
    base = Path(str(raw_name or "attachment.bin")).name
    safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", base).strip(" ._")
    return (safe or "attachment.bin")[:120]


def _stage_attachment_to_f_drive(att: dict[str, Any]) -> tuple[Path, str, str] | None:
    """Save dropped/pasted/selected image or file strictly under UPLOAD_STAGE_DIR."""
    UPLOAD_STAGE_DIR.mkdir(parents=True, exist_ok=True)
    raw_name = _sanitize_upload_filename(str(att.get("name") or "file"))
    raw_mime = str(att.get("mimeType") or "").strip().lower()
    if not raw_mime:
        guessed, _ = mimetypes.guess_type(raw_name)
        raw_mime = guessed or "application/octet-stream"

    b64_data = str(att.get("dataBase64") or "").strip()
    if "," in b64_data and b64_data.startswith("data:"):
        b64_data = b64_data.split(",", 1)[1].strip()
    if not b64_data:
        return None

    raw_bytes = base64.b64decode(b64_data)
    saved_path = UPLOAD_STAGE_DIR / f"{int(time.time() * 1000)}_{raw_name}"
    saved_path.write_bytes(raw_bytes)
    return saved_path, raw_mime, b64_data


def send_verbatim_message(
    cascade_id: str,
    raw_text: str | None,
    model_key: str = "inherit",
    focus_ide: bool = True,
    attachments: list[dict[str, Any]] | None = None,
    send_mode: str = "queue",
) -> dict[str, Any]:
    """Send `raw_text` 100% VERBATIM plus any dropped images/files natively into Antigravity (auto-fallback to official `agy.exe` CLI on 44.9.1+ LS 401)."""
    exact_text = "" if raw_text is None else str(raw_text)
    att_list = [a for a in (attachments or []) if isinstance(a, dict)]
    if not exact_text.strip() and not att_list:
        return {"ok": False, "error": "消息内容与附件不能同时为空"}

    target_cid = str(cascade_id or "").strip()
    items_payload: list[dict[str, Any]] = []
    media_payload: list[dict[str, Any]] = []
    staged_paths: list[str] = []
    image_exts = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}

    for att in att_list[:16]:
        staged = _stage_attachment_to_f_drive(att)
        if not staged:
            continue
        saved_path, mime_type, clean_b64 = staged
        staged_paths.append(os.path.normpath(str(saved_path.resolve())))
        is_img = mime_type.startswith("image/") or (saved_path.suffix.lower() in image_exts)
        if is_img:
            if not mime_type.startswith("image/"):
                mime_type = "image/png" if saved_path.suffix.lower() == ".png" else "image/jpeg"
            media_payload.append({
                "mimeType": mime_type,
                "inlineData": clean_b64,
                "uri": saved_path.resolve().as_posix(),
                "description": saved_path.name,
            })
        else:
            items_payload.append({
                "item": {
                    "file": {
                        "absoluteUri": saved_path.resolve().as_uri(),
                    }
                }
            })
            items_payload.append({"text": " "})

    if (
        time.time() < _LS_RPC_FAIL_UNTIL
        or target_cid.startswith("cli-new-")
        or (target_cid and (CLI_CONV_DIR / f"{target_cid}.db").is_file())
    ):
        return _send_via_agy_cli_ophanim(target_cid, exact_text, model_key=model_key, staged_paths=staged_paths)

    created_new = False
    try:
        if not target_cid or target_cid == "__new__":
            started = create_new_conversation(focus_ide=focus_ide)
            target_cid = started["cascadeId"]
            created_new = True
            if started.get("backend") == "agy_cli" or target_cid.startswith("cli-new-"):
                return _send_via_agy_cli_ophanim(target_cid, exact_text, model_key=model_key, staged_paths=staged_paths)
        elif focus_ide:
            try:
                agy_rpc("SmartFocusConversation", {"cascadeId": target_cid}, timeout=3.0)
            except Exception:
                pass

        items_payload.append({"text": exact_text if exact_text.strip() else " "})
        cascade_cfg = _load_best_cascade_config(target_cid, model_key=model_key)
        send_payload: dict[str, Any] = {
            "cascadeId": target_cid,
            "items": items_payload,
        }
        if media_payload:
            send_payload["media"] = media_payload
        if cascade_cfg:
            send_payload["cascadeConfig"] = cascade_cfg

        agy_rpc("SendUserCascadeMessage", send_payload, timeout=20.0)
    except Exception:
        if _find_agy_cli_bin():
            return _send_via_agy_cli_ophanim(target_cid, exact_text, model_key=model_key, staged_paths=staged_paths)
        raise

    flushed_now = False
    norm_mode = str(send_mode or "queue").strip().lower()
    if norm_mode in ("interrupt", "send_now", "flush") and not created_new:
        try:
            flush_payload: dict[str, Any] = {"cascadeId": target_cid}
            if cascade_cfg:
                flush_payload["cascadeConfig"] = cascade_cfg
            agy_rpc("SendAllQueuedMessages", flush_payload, timeout=10.0)
            flushed_now = True
        except Exception as exc:
            logger.debug("SendAllQueuedMessages after send warning: %s", exc)

    return {
        "ok": True,
        "cascadeId": target_cid,
        "createdNew": created_new,
        "flushedNow": flushed_now,
        "stagedPaths": staged_paths,
    }


def flush_queued_messages(cascade_id: str, model_key: str = "inherit") -> dict[str, Any]:
    """Actively push all queued user turns into the running Antigravity execution (`SendAllQueuedMessages`)."""
    target_cid = str(cascade_id or "").strip()
    if not target_cid or target_cid == "__new__":
        return {"ok": False, "error": "无效的会话 ID"}
    cascade_cfg = _load_best_cascade_config(target_cid, model_key=model_key)
    payload: dict[str, Any] = {"cascadeId": target_cid}
    if cascade_cfg:
        payload["cascadeConfig"] = cascade_cfg
    try:
        agy_rpc("SendAllQueuedMessages", payload, timeout=10.0)
        return {"ok": True, "cascadeId": target_cid, "action": "flush"}
    except Exception as exc:
        return {"ok": False, "cascadeId": target_cid, "action": "flush", "error": str(exc)}


def delete_queued_step(cascade_id: str, step_index: int) -> dict[str, Any]:
    """Cancel / withdraw a queued user turn before Antigravity consumes it (`DeleteQueuedUserInputStep`)."""
    target_cid = str(cascade_id or "").strip()
    if not target_cid or target_cid == "__new__" or step_index < 0:
        return {"ok": False, "error": "无效的排队步骤参数"}
    try:
        agy_rpc("DeleteQueuedUserInputStep", {"cascadeId": target_cid, "stepIndex": int(step_index)}, timeout=8.0)
        return {"ok": True, "cascadeId": target_cid, "action": "delete_step", "stepIndex": int(step_index)}
    except Exception as exc:
        return {"ok": False, "cascadeId": target_cid, "action": "delete_step", "error": str(exc)}


def cancel_cascade_execution(cascade_id: str) -> dict[str, Any]:
    """Immediately pause / stop an actively running Antigravity cascade or CLI execution."""
    target_cid = str(cascade_id or "").strip()
    if not target_cid or target_cid == "__new__":
        return {"ok": False, "action": "cancel", "error": "无效的会话 ID"}
    with _OPHANIM_CLI_LOCK:
        proc = _OPHANIM_CLI_PROCS.pop(target_cid, None)
    if proc is not None and proc.poll() is None:
        try:
            proc.terminate()
        except Exception:
            pass
        return {"ok": True, "cascadeId": target_cid, "action": "cancel", "backend": "agy_cli"}
    last_err = ""
    for rpc_method, payload in (
        ("CancelCascadeInvocation", {"cascadeId": target_cid}),
        ("ForceStopCascadeTree", {"conversationId": target_cid}),
        ("CancelCascadeSteps", {"cascadeId": target_cid}),
    ):
        try:
            agy_rpc(rpc_method, payload, timeout=8.0)
            return {"ok": True, "cascadeId": target_cid, "action": "cancel", "rpcMethod": rpc_method}
        except Exception as exc:
            last_err = str(exc)
    return {"ok": False, "cascadeId": target_cid, "action": "cancel", "error": last_err or "停止请求未响应"}
