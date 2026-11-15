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
import copy
from datetime import datetime, timezone
import json
import logging
import mimetypes
import os
from pathlib import Path
import re
import socket
import subprocess
import time
from typing import Any
import urllib.error
import urllib.request

logger = logging.getLogger("ophanim_agy_bridge")

PROJECT_DIR = Path(__file__).resolve().parent
BRAIN_DIR = Path(os.environ.get("OPHANIM_BRAIN_DIR", str(Path.home() / ".gemini/antigravity/brain")))
HERMES_BRIDGE_DIR = Path(os.environ.get("OPHANIM_HERMES_DIR", str(PROJECT_DIR.parent / "hermes-agy-bridge")))
AGY_ENV_FILE = HERMES_BRIDGE_DIR / "agy_env.json"
CASCADE_TEMPLATE_FILE = HERMES_BRIDGE_DIR / "cascade_config_template.json"
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

_LS_CACHE: dict[str, Any] = {"addr": "", "token": "", "ts": 0.0}
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


def discover_agy_ls(force: bool = False) -> tuple[str, str]:
    now = time.monotonic()
    if (
        not force
        and _LS_CACHE["addr"]
        and (now - float(_LS_CACHE["ts"])) < 10.0
        and _is_port_alive(str(_LS_CACHE["addr"]))
    ):
        return str(_LS_CACHE["addr"]), str(_LS_CACHE["token"])

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
        _LS_CACHE.update({"addr": addr, "token": token, "ts": now})
        return addr, token

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
                addr = f"localhost:{chosen_port}"
                token = cand_tok
                if isinstance(saved_env, dict) and AGY_ENV_FILE.parent.is_dir():
                    try:
                        saved_env["ANTIGRAVITY_LS_ADDRESS"] = addr
                        if token:
                            saved_env["ANTIGRAVITY_CSRF_TOKEN"] = token
                        AGY_ENV_FILE.write_text(
                            json.dumps(saved_env, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8",
                        )
                    except Exception:
                        pass
    except Exception as exc:
        logger.debug("LS discovery error: %s", exc)

    _LS_CACHE.update({"addr": addr, "token": token, "ts": now})
    return addr, token


def agy_rpc(method: str, payload: dict[str, Any], timeout: float = 8.0) -> dict[str, Any]:
    for attempt in range(2):
        addr, tok = discover_agy_ls(force=(attempt > 0))
        if not addr:
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
            with _DIRECT_OPENER.open(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                return json.loads(raw) if raw.strip() else {}
        except urllib.error.HTTPError as he:
            if attempt == 0 and he.code in (401, 403, 502, 503):
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
            raise RuntimeError(f"Antigravity RPC {method} 调用失败: {exc}") from exc
    return {}


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
    t_path = BRAIN_DIR / cid / ".system_generated/logs/transcript.jsonl"
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
    mem_path = BRAIN_DIR / cid / ".system_generated/swarm/members.json"
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


def load_session_meta() -> dict[str, set[str]]:
    """Load persisted pinned / archived / deleted conversation ID sets."""
    out: dict[str, set[str]] = {"pinned": set(), "archived": set(), "deleted": set()}
    if not SESSION_META_FILE.is_file():
        return out
    try:
        raw = json.loads(SESSION_META_FILE.read_text(encoding="utf-8", errors="replace"))
        if isinstance(raw, dict):
            for k in ("pinned", "archived", "deleted"):
                vals = raw.get(k)
                if isinstance(vals, list):
                    out[k] = {str(v).strip() for v in vals if str(v).strip()}
    except Exception as exc:
        logger.debug("load_session_meta error: %s", exc)
    return out


def save_session_meta(meta: dict[str, set[str]]) -> None:
    """Atomically persist pinned / archived / deleted conversation ID sets."""
    SESSION_META_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = SESSION_META_FILE.parent / f".ophanim_session_meta.{os.getpid()}.{time.time_ns()}.tmp"
    payload = {
        "pinned": sorted(meta.get("pinned", set())),
        "archived": sorted(meta.get("archived", set())),
        "deleted": sorted(meta.get("deleted", set())),
        "updatedAt": int(time.time()),
    }
    try:
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, SESSION_META_FILE)
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


_LAST_DONE_META_CACHE: dict[str, tuple[float, int, str, dict[str, Any] | None]] = {}


def _peek_last_completed_turn_meta(t_path: Path, conv_status: str) -> dict[str, Any] | None:
    """Fast mtime-cached check for the latest genuinely completed turn (non-empty final assistant text)."""
    if not t_path.is_file():
        return None
    key = str(t_path)
    try:
        st = t_path.stat()
        mtime = float(st.st_mtime)
        sz = int(st.st_size)
    except OSError:
        return None
    cached = _LAST_DONE_META_CACHE.get(key)
    if cached and cached[0] == mtime and cached[1] == sz and cached[2] == conv_status:
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
    _LAST_DONE_META_CACHE[key] = (mtime, sz, conv_status, meta_out)
    return meta_out


def list_conversations(limit: int = 48, include_archived: bool = True) -> list[dict[str, Any]]:
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

    all_candidate_cids = set(summaries.keys())
    if BRAIN_DIR.is_dir():
        try:
            for d in BRAIN_DIR.iterdir():
                if d.is_dir() and len(d.name) >= 32 and d.name != "tempmediaStorage":
                    all_candidate_cids.add(d.name)
        except Exception:
            pass

    for pid in list(all_candidate_cids):
        for _, m_info in _read_swarm_child_ids(pid):
            w_cid = str(m_info.get("conversation_id") or "").strip()
            if w_cid and w_cid != pid:
                child_cids.add(w_cid)
                children_by_parent.setdefault(pid, set()).add(w_cid)

    results: list[dict[str, Any]] = []
    for cid in all_candidate_cids:
        if cid in child_cids or cid in deleted_ids or cid == "tempmediaStorage":
            continue
        is_archived = cid in archived_ids
        if is_archived and not include_archived:
            continue
        info = summaries.get(cid) if isinstance(summaries.get(cid), dict) else {}
        t_path = BRAIN_DIR / cid / ".system_generated/logs/transcript.jsonl"
        if not info and not t_path.is_file():
            continue

        status_raw = str(info.get("status") or "CASCADE_RUN_STATUS_IDLE")
        status = "running" if "RUNNING" in status_raw else "idle"

        annotations = info.get("annotations") if isinstance(info.get("annotations"), dict) else {}
        title = str(annotations.get("title") or info.get("summary") or "").strip()
        if not title:
            title = _extract_first_user_title(cid) or f"对话 {cid[:8]}"

        t_mtime = 0.0
        if t_path.is_file():
            try:
                t_mtime = t_path.stat().st_mtime
            except OSError:
                pass
        updated_str = str(info.get("lastModifiedTime") or info.get("createdTime") or "")
        updated_epoch = max(_parse_iso_epoch(updated_str, t_mtime), t_mtime)
        if not updated_str and updated_epoch > 0:
            updated_str = datetime.fromtimestamp(updated_epoch, tz=timezone.utc).isoformat()

        step_count = int(info.get("stepCount") or 0)
        if step_count == 0 and t_path.is_file():
            try:
                with open(t_path, "rb") as fh:
                    step_count = sum(1 for _ in fh)
            except Exception:
                pass

        subagent_total = max(len(children_by_parent.get(cid, set())), len(_read_swarm_child_ids(cid)))
        is_pinned = cid in pinned_ids
        last_done_meta = _peek_last_completed_turn_meta(t_path, status) if (status == "running" or len(results) < 16) else None
        results.append({
            "id": cid,
            "shortId": cid[:8],
            "title": title[:54],
            "status": status,
            "statusRaw": status_raw,
            "stepCount": step_count,
            "subagentCount": subagent_total,
            "pinned": is_pinned,
            "archived": is_archived,
            "updatedAt": updated_str,
            "updatedEpoch": round(updated_epoch, 3),
            "lastCompletedTurn": last_done_meta,
        })

    results.sort(key=lambda x: (1 if x.get("archived") else 0, 0 if x.get("pinned") else 1, -float(x["updatedEpoch"])))
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
        full_t_path = BRAIN_DIR / worker_cid / ".system_generated/logs/transcript_full.jsonl"
        compact_t_path = BRAIN_DIR / worker_cid / ".system_generated/logs/transcript.jsonl"
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


def build_conversation_snapshot(cid: str) -> dict[str, Any]:
    cid = str(cid or "").strip()
    summaries = _fetch_all_summaries_safe()
    info = summaries.get(cid) if isinstance(summaries.get(cid), dict) else {}
    status_raw = str(info.get("status") or "CASCADE_RUN_STATUS_IDLE")
    status = "running" if "RUNNING" in status_raw else "idle"

    annotations = info.get("annotations") if isinstance(info.get("annotations"), dict) else {}
    title = str(annotations.get("title") or info.get("summary") or "").strip()
    if not title:
        title = _extract_first_user_title(cid) or (f"新对话 {cid[:8]}" if cid else "新建对话")

    main_t_path = BRAIN_DIR / cid / ".system_generated/logs/transcript.jsonl"
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

    swarm_dir = BRAIN_DIR / cid / ".system_generated/swarm"
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
        wt_path = BRAIN_DIR / w_cid / ".system_generated/logs/transcript.jsonl"
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
        self.last_board_seq: int = 0
        self.last_status: str = "idle"
        self.last_msg_sig: tuple[int, str] = (0, "")
        self.pending_returns: dict[str, list[dict[str, Any]]] = {}

    def bind(self, cid: str) -> None:
        cid = str(cid or "").strip()
        self.bound_cid = cid
        self.file_offsets.clear()
        self.pending_returns.clear()
        self.last_board_seq = 0
        if not cid:
            return
        main_t = BRAIN_DIR / cid / ".system_generated/logs/transcript.jsonl"
        if main_t.is_file():
            self.file_offsets[str(main_t)] = main_t.stat().st_size
        for _, w_info in _read_swarm_child_ids(cid):
            w_cid = str(w_info.get("conversation_id") or "").strip()
            if w_cid:
                wt = BRAIN_DIR / w_cid / ".system_generated/logs/transcript.jsonl"
                if wt.is_file():
                    self.file_offsets[str(wt)] = wt.stat().st_size
        board_f = BRAIN_DIR / cid / ".system_generated/swarm/board.jsonl"
        if board_f.is_file():
            try:
                for ln in board_f.read_text(encoding="utf-8", errors="replace").splitlines():
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
            (BRAIN_DIR / cid / ".system_generated/logs/transcript.jsonl", None)
        ]
        for w_cid, w_idx in worker_index_by_cid.items():
            watched_paths.append((BRAIN_DIR / w_cid / ".system_generated/logs/transcript.jsonl", w_idx))

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

        board_f = BRAIN_DIR / cid / ".system_generated/swarm/board.jsonl"
        if board_f.is_file():
            try:
                for bln in board_f.read_text(encoding="utf-8", errors="replace").splitlines():
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
        cur_status = "running" if "RUNNING" in str(info.get("status") or "") else "idle"
        status_changed = cur_status != self.last_status
        self.last_status = cur_status

        if has_new_lines or status_changed or cur_status == "running":
            snap = build_conversation_snapshot(cid)
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


def create_new_conversation(focus_ide: bool = True) -> dict[str, Any]:
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
    """Send `raw_text` 100% VERBATIM plus any dropped images/files natively into Antigravity.

    `send_mode`:
      - `"queue"` (default): normal send (queues if cascade is currently running).
      - `"interrupt"` / `"send_now"`: sends AND immediately calls `SendAllQueuedMessages` to push into active run!
    """
    exact_text = "" if raw_text is None else str(raw_text)
    att_list = [a for a in (attachments or []) if isinstance(a, dict)]
    if not exact_text.strip() and not att_list:
        return {"ok": False, "error": "消息内容与附件不能同时为空"}

    target_cid = str(cascade_id or "").strip()
    created_new = False

    if not target_cid or target_cid == "__new__":
        started = create_new_conversation(focus_ide=focus_ide)
        target_cid = started["cascadeId"]
        created_new = True
    elif focus_ide:
        try:
            agy_rpc("SmartFocusConversation", {"cascadeId": target_cid}, timeout=3.0)
        except Exception:
            pass

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
    """Immediately pause / stop an actively running Antigravity cascade execution (`CancelCascadeInvocation`)."""
    target_cid = str(cascade_id or "").strip()
    if not target_cid or target_cid == "__new__":
        return {"ok": False, "action": "cancel", "error": "无效的会话 ID"}
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
