#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ophanim_external_bridge.py
Universal Pluggable Agent Workbench Backend for Ophanim Sanctum.

Allows ANY non-Antigravity agent or harness (DeepSeek Harness, OpenAI Codex,
Claude Code, Cursor, local Ollama/vLLM, or custom Python/CLI agents) to power
the full bidirectional Ophanim Workbench (`AGENT 控制台` + Central Core Sphere
chat, session list CRUD, live 3D slabs/eyes/stars, and completion pyramid)
without requiring Google Antigravity's local Language Server.

Supported integration modes (configured via `ophanim_agent_backend.json`,
environment variables, or by dropping `custom_agent_bridge.py` in project root):
  1. `python_bridge`     : Calls `handle_ophanim_turn(...)` in `custom_agent_bridge.py`
  2. `cli_command`       : Executes a local CLI / Harness command template
  3. `openai_compatible` : Streams directly from DeepSeek / OpenAI / local v1/chat/completions API
  4. `http_relay`        : Queues user prompts for an external running Harness polling
                           `/api/external/pending` and posting replies to `/api/external/reply`
"""
from __future__ import annotations

import asyncio
import base64
from datetime import datetime, timezone
import importlib.util
import inspect
import json
import logging
import os
from pathlib import Path
import re
import subprocess
import threading
import time
from typing import Any, Callable
import urllib.error
import urllib.request
import uuid

logger = logging.getLogger("ophanim_external_bridge")

PROJECT_DIR = Path(__file__).resolve().parent
BACKEND_CONFIG_PATH = PROJECT_DIR / "ophanim_agent_backend.json"
CUSTOM_BRIDGE_PY_PATH = PROJECT_DIR / "custom_agent_bridge.py"
EXT_SESSIONS_DIR = PROJECT_DIR / ".ophanim_cache" / "external_sessions"
EXT_UPLOADS_DIR = PROJECT_DIR / ".ophanim_cache" / "uploads"

_NO_WINDOW = 0x08000000 if os.name == "nt" else 0
_LOCK = threading.RLock()
_EVENT_SINKS: list[Callable[[dict[str, Any]], None]] = []
_PENDING_RELAY_CV = threading.Condition(_LOCK)
_PENDING_RELAY_QUEUE: list[dict[str, Any]] = []
_CANCEL_EVENTS: dict[str, threading.Event] = {}
_ACTIVE_PROCS: dict[str, subprocess.Popen[bytes]] = {}


def is_turn_cancelled(cid: str) -> bool:
    ev = _CANCEL_EVENTS.get(str(cid or "").strip())
    return bool(ev and ev.is_set())


def register_event_sink(cb: Callable[[dict[str, Any]], None]) -> None:
    if cb not in _EVENT_SINKS:
        _EVENT_SINKS.append(cb)


def _emit_payload(payload: dict[str, Any]) -> None:
    for cb in list(_EVENT_SINKS):
        try:
            cb(payload)
        except Exception as exc:
            logger.debug("External bridge sink error: %s", exc)


def _iso_now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _hhmm_now() -> str:
    return datetime.now().strftime("%H:%M")


def _guess_kind(filename: str) -> str:
    ext = Path(filename or "").suffix.lower()
    mapping = {
        ".py": "PYTHON",
        ".pyw": "PYTHON",
        ".js": "JS",
        ".ts": "TS",
        ".tsx": "TSX",
        ".jsx": "JSX",
        ".html": "HTML",
        ".css": "CSS",
        ".json": "JSON",
        ".md": "MARKDOWN",
        ".rs": "RUST",
        ".go": "GO",
        ".cpp": "CPP",
        ".c": "C",
        ".sh": "SHELL",
        ".bat": "BATCH",
        ".ps1": "POWERSHELL",
    }
    return mapping.get(ext, (ext[1:].upper() if ext else "FILE"))


def load_backend_config() -> dict[str, Any]:
    cfg: dict[str, Any] = {}
    if BACKEND_CONFIG_PATH.is_file():
        try:
            raw = json.loads(BACKEND_CONFIG_PATH.read_text(encoding="utf-8", errors="replace"))
            if isinstance(raw, dict):
                cfg = raw
        except Exception as exc:
            logger.warning("Failed reading ophanim_agent_backend.json: %s", exc)

    env_provider = os.environ.get("OPHANIM_AGENT_PROVIDER", "").strip()
    env_mode = os.environ.get("OPHANIM_AGENT_MODE", "").strip()
    if env_provider:
        cfg.setdefault("provider", env_provider)
    if env_mode:
        cfg.setdefault("mode", env_mode)
    return cfg


def is_external_backend_preferred(agy_ls_alive: bool) -> bool:
    """
    Decide whether Ophanim should route chat/session operations to the Universal
    External Bridge instead of Antigravity Language Server.
    - If `ophanim_agent_backend.json` explicitly sets `provider` to anything other than
      `antigravity` / `auto` (e.g. `external`, `deepseek`, `codex`, `claude`, `custom`),
      always use External Bridge.
    - If `provider` is `antigravity`, never use External Bridge.
    - In `auto` mode (default): if Antigravity LS is running, keep native Antigravity!
      If Antigravity LS is NOT running, automatically activate External Bridge when
      `custom_agent_bridge.py`, `ophanim_agent_backend.json`, `DEEPSEEK_API_KEY`,
      `OPENAI_API_KEY`, or existing external sessions are present.
    """
    cfg = load_backend_config()
    provider = str(cfg.get("provider") or "auto").strip().lower()
    if provider == "antigravity":
        return False
    if provider not in ("", "auto"):
        return True
    if agy_ls_alive:
        return False
    if CUSTOM_BRIDGE_PY_PATH.is_file() or BACKEND_CONFIG_PATH.is_file():
        return True
    if os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("OPENAI_API_KEY"):
        return True
    if EXT_SESSIONS_DIR.is_dir() and any(EXT_SESSIONS_DIR.glob("*.json")):
        return True
    return False


def resolve_effective_mode(cfg: dict[str, Any] | None = None) -> str:
    cfg = cfg if cfg is not None else load_backend_config()
    explicit = str(cfg.get("mode") or "").strip().lower()
    if explicit in ("python_bridge", "cli_command", "openai_compatible", "http_relay"):
        return explicit

    script_rel = str(cfg.get("bridgeScript") or "custom_agent_bridge.py").strip()
    script_path = (PROJECT_DIR / script_rel) if not Path(script_rel).is_absolute() else Path(script_rel)
    if script_path.is_file():
        return "python_bridge"
    if cfg.get("command"):
        return "cli_command"
    if cfg.get("apiKey") or cfg.get("baseUrl") or os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("OPENAI_API_KEY"):
        return "openai_compatible"
    if str(cfg.get("provider") or "").strip().lower() in ("relay", "http_relay"):
        return "http_relay"
    return "unconfigured"


def get_backend_info(agy_ls_alive: bool = False) -> dict[str, Any]:
    cfg = load_backend_config()
    use_ext = is_external_backend_preferred(agy_ls_alive)
    if not use_ext and agy_ls_alive:
        return {
            "backend": "antigravity",
            "mode": "agy_ls",
            "agentName": "ANTIGRAVITY AGENT",
            "ready": True,
        }
    mode = resolve_effective_mode(cfg)
    default_label = "DEEPSEEK HARNESS" if (os.environ.get("DEEPSEEK_API_KEY") or "deepseek" in json.dumps(cfg).lower()) else "EXTERNAL AGENT"
    agent_name = str(cfg.get("agentName") or cfg.get("providerName") or default_label).strip()
    return {
        "backend": "external",
        "mode": mode,
        "agentName": agent_name,
        "ready": mode != "unconfigured",
        "configPath": str(BACKEND_CONFIG_PATH.name),
        "bridgeScript": str(cfg.get("bridgeScript") or "custom_agent_bridge.py"),
    }


def _session_path(cid: str) -> Path:
    safe_id = re.sub(r"[^a-zA-Z0-9_\-]", "", str(cid or "")) or "default"
    return EXT_SESSIONS_DIR / f"{safe_id}.json"


def _load_session(cid: str) -> dict[str, Any] | None:
    p = _session_path(cid)
    if not p.is_file():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8", errors="replace"))
        if isinstance(data, dict):
            return data
    except Exception as exc:
        logger.debug("Load external session %s error: %s", cid, exc)
    return None


def _save_session(doc: dict[str, Any]) -> None:
    EXT_SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    cid = str(doc.get("id") or "").strip()
    if not cid:
        return
    p = _session_path(cid)
    tmp = EXT_SESSIONS_DIR / f".{cid}.{os.getpid()}.{time.time_ns()}.tmp"
    try:
        tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, p)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def _create_blank_session(title: str = "新建外部 Agent 会话") -> dict[str, Any]:
    cid = uuid.uuid4().hex[:16]
    now_iso = _iso_now()
    now_ep = time.time()
    doc: dict[str, Any] = {
        "id": cid,
        "shortId": cid[:8],
        "title": title,
        "status": "idle",
        "pinned": False,
        "archived": False,
        "deleted": False,
        "createdAt": now_iso,
        "updatedAt": now_iso,
        "updatedEpoch": now_ep,
        "turns": [],
        "slabs": [],
        "outerFiles": [],
        "deliverables": [],
        "workers": [],
    }
    _save_session(doc)
    return doc


def _doc_to_summary_item(doc: dict[str, Any]) -> dict[str, Any]:
    turns = doc.get("turns") if isinstance(doc.get("turns"), list) else []
    last_done_meta = None
    for tr in reversed(turns):
        if tr.get("hasFinalReply") and str(tr.get("assistantText") or "").strip():
            a_txt = str(tr.get("assistantText") or "").strip()
            last_done_meta = {
                "turnNumber": int(tr.get("turnNumber") or 1),
                "turnTitle": str(tr.get("title") or ""),
                "snippet": re.sub(r"\s+", " ", a_txt)[:88],
            }
            break
    workers = doc.get("workers") if isinstance(doc.get("workers"), list) else []
    return {
        "id": str(doc.get("id") or ""),
        "shortId": str(doc.get("shortId") or str(doc.get("id") or "")[:8]),
        "title": str(doc.get("title") or "未命名会话"),
        "status": str(doc.get("status") or "idle"),
        "pinned": bool(doc.get("pinned")),
        "archived": bool(doc.get("archived")),
        "updatedAt": str(doc.get("updatedAt") or ""),
        "updatedEpoch": float(doc.get("updatedEpoch") or 0.0),
        "subagentCount": len(workers),
        "turnCount": len(turns),
        "lastDoneTurn": last_done_meta,
    }


def doc_to_snapshot(doc: dict[str, Any]) -> dict[str, Any]:
    turns = doc.get("turns") if isinstance(doc.get("turns"), list) else []
    flat_msgs: list[dict[str, Any]] = []
    for idx, tr in enumerate(turns):
        flat_msgs.append(
            {
                "role": "user",
                "text": str(tr.get("userText") or ""),
                "attachments": tr.get("attachments") or [],
                "time": str(tr.get("time") or ""),
                "stepIndex": idx * 2,
                "stepStatus": "DONE",
            }
        )
        if tr.get("assistantText"):
            flat_msgs.append(
                {
                    "role": "assistant",
                    "text": str(tr.get("assistantText") or ""),
                    "time": str(tr.get("replyTime") or tr.get("time") or ""),
                    "stepIndex": idx * 2 + 1,
                    "stepStatus": "DONE" if tr.get("hasFinalReply") else "RUNNING",
                }
            )
    return {
        "cascadeId": str(doc.get("id") or ""),
        "shortId": str(doc.get("shortId") or str(doc.get("id") or "")[:8]),
        "title": str(doc.get("title") or "外部 Agent 会话"),
        "status": str(doc.get("status") or "idle"),
        "updatedAt": str(doc.get("updatedAt") or ""),
        "turns": turns,
        "messages": flat_msgs,
        "slabs": doc.get("slabs") or [],
        "outerFiles": doc.get("outerFiles") or [],
        "deliverables": doc.get("deliverables") or [],
        "workers": doc.get("workers") or [],
    }


def list_conversations() -> list[dict[str, Any]]:
    with _LOCK:
        if not EXT_SESSIONS_DIR.is_dir():
            return []
        items: list[dict[str, Any]] = []
        for p in EXT_SESSIONS_DIR.glob("*.json"):
            if p.name.startswith("."):
                continue
            try:
                doc = json.loads(p.read_text(encoding="utf-8", errors="replace"))
                if isinstance(doc, dict) and not doc.get("deleted"):
                    items.append(_doc_to_summary_item(doc))
            except Exception:
                continue
        items.sort(
            key=lambda c: (
                0 if c.get("pinned") else 1,
                -float(c.get("updatedEpoch") or 0.0),
            )
        )
        return items


def get_conversation_snapshot(cid: str) -> dict[str, Any]:
    with _LOCK:
        target = str(cid or "").strip()
        if target:
            doc = _load_session(target)
            if doc and not doc.get("deleted"):
                return doc_to_snapshot(doc)
        convs = list_conversations()
        if convs:
            first_doc = _load_session(convs[0]["id"])
            if first_doc:
                return doc_to_snapshot(first_doc)
        info = get_backend_info(False)
        return {
            "cascadeId": "",
            "shortId": "READY",
            "title": f"{info['agentName']} · 待发起新对话",
            "status": "idle",
            "turns": [],
            "messages": [],
            "slabs": [],
            "outerFiles": [],
            "deliverables": [],
            "workers": [],
        }


def mutate_conversation_meta(cid: str, action: str) -> dict[str, Any]:
    with _LOCK:
        doc = _load_session(cid)
        if not doc:
            return {"ok": False, "error": "会话不存在"}
        act = str(action or "").strip().lower()
        if act == "pin":
            doc["pinned"] = True
            doc["archived"] = False
        elif act == "unpin":
            doc["pinned"] = False
        elif act == "toggle_pin":
            doc["pinned"] = not bool(doc.get("pinned"))
            if doc["pinned"]:
                doc["archived"] = False
        elif act == "archive":
            doc["archived"] = True
            doc["pinned"] = False
        elif act == "unarchive":
            doc["archived"] = False
        elif act == "toggle_archive":
            doc["archived"] = not bool(doc.get("archived"))
            if doc["archived"]:
                doc["pinned"] = False
        elif act == "delete":
            doc["deleted"] = True
        else:
            return {"ok": False, "error": f"未知操作: {act}"}
        _save_session(doc)
        return {
            "ok": True,
            "cascadeId": cid,
            "action": act,
            "pinned": bool(doc.get("pinned")),
            "archived": bool(doc.get("archived")),
            "deleted": bool(doc.get("deleted")),
        }


def _stage_attachments(attachments: list[dict[str, Any]] | None) -> tuple[list[dict[str, Any]], list[str]]:
    if not attachments:
        return [], []
    EXT_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    saved_atts: list[dict[str, Any]] = []
    staged_paths: list[str] = []
    for item in attachments:
        if not isinstance(item, dict):
            continue
        raw_name = Path(str(item.get("name") or f"upload_{int(time.time())}.bin")).name
        safe_name = re.sub(r"[^\w.\-\u4e00-\u9fff ]", "_", raw_name).strip() or "upload.bin"
        mime = str(item.get("mimeType") or "application/octet-stream")
        is_img = bool(item.get("isImage")) or mime.lower().startswith("image/")
        local_p = str(item.get("localPath") or "").strip()
        final_path: Path | None = None
        if local_p and Path(local_p).is_file():
            final_path = Path(local_p).resolve()
        else:
            b64 = str(item.get("dataBase64") or "").strip()
            if b64:
                try:
                    raw_bytes = base64.b64decode(b64)
                    dest = EXT_UPLOADS_DIR / f"{int(time.time() * 1000)}_{safe_name}"
                    dest.write_bytes(raw_bytes)
                    final_path = dest.resolve()
                except Exception as exc:
                    logger.warning("Failed staging attachment %s: %s", safe_name, exc)
        path_str = str(final_path) if final_path else ""
        staged_paths.append(path_str)
        saved_atts.append(
            {
                "name": safe_name,
                "kind": "image" if is_img else "file",
                "mimeType": mime,
                "path": path_str,
            }
        )
    return saved_atts, staged_paths


class TurnBridgeContext:
    """Helper passed to `custom_agent_bridge.py:handle_ophanim_turn(..., ctx)`."""

    def __init__(self, cid: str, turn_number: int) -> None:
        self.cascade_id = cid
        self.turn_number = turn_number

    def emit_read(self, file_path: str, code: str = "") -> None:
        p = Path(file_path)
        if not code and p.is_file():
            try:
                code = p.read_text(encoding="utf-8", errors="replace")[:4000]
            except Exception:
                code = ""
        _record_session_slab(self.cascade_id, file_path, code, is_write=False)
        _emit_payload(
            {
                "cascadeId": self.cascade_id,
                "op": "read",
                "file": p.name or file_path,
                "fullPath": str(p.resolve()) if p.exists() else file_path,
                "kind": _guess_kind(p.name),
                "code": code,
            }
        )

    def emit_write(self, file_path: str, code: str = "") -> None:
        p = Path(file_path)
        if not code and p.is_file():
            try:
                code = p.read_text(encoding="utf-8", errors="replace")[:4000]
            except Exception:
                code = ""
        _record_session_slab(self.cascade_id, file_path, code, is_write=True)
        _emit_payload(
            {
                "cascadeId": self.cascade_id,
                "op": "write",
                "file": p.name or file_path,
                "fullPath": str(p.resolve()) if p.exists() else file_path,
                "kind": _guess_kind(p.name),
                "code": code,
            }
        )

    def emit_outer(self, file_path: str, role: str = "CORE_MODULE", code: str = "") -> None:
        p = Path(file_path)
        if not code and p.is_file():
            try:
                code = p.read_text(encoding="utf-8", errors="replace")[:4000]
            except Exception:
                code = ""
        with _LOCK:
            doc = _load_session(self.cascade_id)
            if doc:
                outer = list(doc.get("outerFiles") or [])
                entry = {
                    "file": p.name or file_path,
                    "fullPath": str(p.resolve()) if p.exists() else file_path,
                    "role": role,
                    "code": code[:2400],
                }
                outer = [x for x in outer if x.get("file") != entry["file"]]
                outer.append(entry)
                doc["outerFiles"] = outer[-12:]
                _save_session(doc)
        _emit_payload(
            {
                "cascadeId": self.cascade_id,
                "op": "outer",
                "file": p.name or file_path,
                "fullPath": str(p.resolve()) if p.exists() else file_path,
                "role": role,
                "code": code,
            }
        )

    def emit_deliver(self, file_path: str, summary: str = "") -> None:
        p = Path(file_path)
        full_p = str(p.resolve()) if p.exists() else file_path
        with _LOCK:
            doc = _load_session(self.cascade_id)
            if doc:
                delivs = list(doc.get("deliverables") or [])
                entry = {
                    "file": p.name or file_path,
                    "fullPath": full_p,
                    "dirPath": str(p.resolve().parent) if p.exists() else "",
                    "kind": _guess_kind(p.name),
                    "summary": summary or "Agent 终稿交付产物",
                }
                delivs = [x for x in delivs if x.get("file") != entry["file"]]
                delivs.append(entry)
                doc["deliverables"] = delivs[-12:]
                _save_session(doc)
        _emit_payload(
            {
                "cascadeId": self.cascade_id,
                "op": "deliver",
                "file": p.name or file_path,
                "fullPath": full_p,
                "summary": summary or "Agent 终稿交付产物",
            }
        )

    def emit_swarm(self, count: int, workers: list[dict[str, Any]] | None = None) -> None:
        wks = workers or [{"name": f"worker-{i + 1}", "status": "working"} for i in range(max(0, int(count)))]
        with _LOCK:
            doc = _load_session(self.cascade_id)
            if doc:
                doc["workers"] = wks
                _save_session(doc)
        _emit_payload({"cascadeId": self.cascade_id, "op": "swarm", "count": int(count), "workers": wks})

    def stream_partial(self, partial_markdown: str) -> None:
        if not is_turn_cancelled(self.cascade_id):
            update_turn_progress(self.cascade_id, self.turn_number, partial_markdown, finished=False)

    def is_cancelled(self) -> bool:
        return is_turn_cancelled(self.cascade_id)


def _record_session_slab(cid: str, file_path: str, code: str, is_write: bool) -> None:
    p = Path(file_path)
    with _LOCK:
        doc = _load_session(cid)
        if not doc:
            return
        slabs = list(doc.get("slabs") or [])
        fname = p.name or file_path
        entry = {
            "file": fname,
            "fullPath": str(p.resolve()) if p.exists() else file_path,
            "kind": _guess_kind(fname),
            "op": "write" if is_write else "read",
            "code": (code or f"# {'Edited' if is_write else 'Read'}: {fname}")[:2400],
        }
        slabs = [s for s in slabs if s.get("file") != fname]
        slabs.append(entry)
        doc["slabs"] = slabs[-36:]
        _save_session(doc)


def update_turn_progress(cid: str, turn_number: int, text: str, finished: bool = False) -> dict[str, Any] | None:
    with _LOCK:
        doc = _load_session(cid)
        if not doc:
            return None
        turns = list(doc.get("turns") or [])
        matched = False
        for tr in turns:
            if int(tr.get("turnNumber") or 0) == int(turn_number):
                if tr.get("cancelledByUser"):
                    return doc_to_snapshot(doc)
                tr["assistantText"] = str(text or "")
                tr["replyTime"] = _hhmm_now()
                if finished:
                    tr["hasFinalReply"] = True
                    tr["status"] = "done"
                else:
                    tr["status"] = "running"
                matched = True
                break
        if not matched:
            return None
        any_running = any(t.get("status") == "running" for t in turns)
        doc["turns"] = turns
        doc["status"] = "running" if any_running else "idle"
        doc["updatedAt"] = _iso_now()
        doc["updatedEpoch"] = time.time()
        _save_session(doc)
        snap = doc_to_snapshot(doc)
        convs = list_conversations()

    _emit_payload(
        {
            "type": "agy_conversation_delta",
            "snapshot": snap,
            "conversations": convs,
        }
    )
    if finished:
        _emit_payload(
            {
                "type": "agy_conversations_list",
                "conversations": convs,
                "activeCascadeId": cid,
            }
        )
        _emit_payload({"cascadeId": cid, "op": "complete", "unread": 1, "title": doc.get("title") or "任务已完成"})
    return snap


def _run_python_bridge_turn(
    cfg: dict[str, Any],
    cid: str,
    turn_number: int,
    prompt: str,
    history: list[dict[str, Any]],
    attachments: list[dict[str, Any]],
    model_key: str,
) -> str:
    script_rel = str(cfg.get("bridgeScript") or "custom_agent_bridge.py").strip()
    script_path = (PROJECT_DIR / script_rel) if not Path(script_rel).is_absolute() else Path(script_rel)
    if not script_path.is_file():
        raise RuntimeError(f"未找到桥接脚本: {script_path}")

    spec = importlib.util.spec_from_file_location("ophanim_custom_agent_bridge", str(script_path))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载桥接模块: {script_path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    fn = getattr(mod, "handle_ophanim_turn", None) or getattr(mod, "run_agent_turn", None)
    if not callable(fn):
        raise RuntimeError(f"{script_path.name} 中未定义 `handle_ophanim_turn(prompt, session_id, history, attachments, model, ctx)` 函数")

    ctx = TurnBridgeContext(cid, turn_number)
    sig = inspect.signature(fn)
    kwargs: dict[str, Any] = {}
    positional_map = {
        "prompt": prompt,
        "user_text": prompt,
        "text": prompt,
        "session_id": cid,
        "cascade_id": cid,
        "history": history,
        "messages": history,
        "attachments": attachments,
        "model": model_key,
        "ctx": ctx,
        "context": ctx,
    }
    accepts_var_kw = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())
    if accepts_var_kw:
        kwargs = {
            "prompt": prompt,
            "session_id": cid,
            "history": history,
            "attachments": attachments,
            "model": model_key,
            "ctx": ctx,
        }
        res = fn(**kwargs)
    else:
        call_args: list[Any] = []
        for pname, param in sig.parameters.items():
            if pname in positional_map:
                call_args.append(positional_map[pname])
            elif param.default is inspect.Parameter.empty:
                call_args.append(None)
        res = fn(*call_args)

    if inspect.isawaitable(res):
        res = asyncio.run(res)
    if isinstance(res, dict):
        return str(res.get("reply") or res.get("text") or res.get("content") or json.dumps(res, ensure_ascii=False))
    return str(res or "").strip()


def _run_cli_command_turn(
    cfg: dict[str, Any],
    cid: str,
    turn_number: int,
    prompt: str,
    attachments: list[dict[str, Any]],
    model_key: str,
) -> str:
    cmd_tpl = cfg.get("command")
    if not cmd_tpl:
        raise RuntimeError("ophanim_agent_backend.json 的 cli_command 模式缺少 `command` 数组配置")
    att_paths = ",".join(a.get("path") or "" for a in attachments if a.get("path"))
    replacements = {
        "{prompt}": prompt,
        "{session_id}": cid,
        "{turn_number}": str(turn_number),
        "{model}": model_key,
        "{attachments}": att_paths,
    }
    if isinstance(cmd_tpl, str):
        cmd_list = [cmd_tpl]
        use_shell = True
    else:
        cmd_list = [str(part) for part in cmd_tpl]
        use_shell = False

    final_cmd = []
    prompt_injected = False
    for tok in cmd_list:
        replaced = tok
        if "{prompt}" in tok:
            prompt_injected = True
        for k, v in replacements.items():
            replaced = replaced.replace(k, v)
        final_cmd.append(replaced)

    cwd_raw = str(cfg.get("cwd") or "").strip()
    cwd_path = Path(cwd_raw).resolve() if cwd_raw else PROJECT_DIR
    env = os.environ.copy()
    env["OPHANIM_SESSION_ID"] = cid
    env["OPHANIM_TURN_NUMBER"] = str(turn_number)
    if isinstance(cfg.get("env"), dict):
        for ek, ev in cfg["env"].items():
            env[str(ek)] = str(ev)

    stdin_bytes = None if prompt_injected else (prompt + "\n").encode("utf-8")
    proc = subprocess.Popen(
        final_cmd[0] if use_shell else final_cmd,
        cwd=str(cwd_path),
        env=env,
        shell=use_shell,
        stdin=subprocess.PIPE if stdin_bytes is not None else subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        creationflags=_NO_WINDOW,
    )
    _ACTIVE_PROCS[cid] = proc
    try:
        if stdin_bytes is not None and proc.stdin:
            try:
                proc.stdin.write(stdin_bytes)
                proc.stdin.close()
            except Exception:
                pass

        chunks: list[str] = []
        last_flush = time.monotonic()
        assert proc.stdout is not None
        for raw_line in iter(proc.stdout.readline, b""):
            if is_turn_cancelled(cid):
                try:
                    proc.terminate()
                except Exception:
                    pass
                break
            line = raw_line.decode("utf-8", errors="replace")
            chunks.append(line)
            now = time.monotonic()
            if now - last_flush >= 0.25:
                update_turn_progress(cid, turn_number, "".join(chunks).strip(), finished=False)
                last_flush = now
        proc.wait(timeout=4)
    except Exception:
        if not is_turn_cancelled(cid):
            raise
    finally:
        _ACTIVE_PROCS.pop(cid, None)

    out_text = "".join(chunks).strip()
    if is_turn_cancelled(cid):
        return out_text or "*(已手动停止执行)*"
    if proc.returncode != 0 and not out_text:
        raise RuntimeError(f"CLI Harness 退出码 {proc.returncode}")
    return out_text or "(CLI Harness 执行完毕，无文本输出)"


def _run_openai_compatible_turn(
    cfg: dict[str, Any],
    cid: str,
    turn_number: int,
    prompt: str,
    history: list[dict[str, Any]],
    attachments: list[dict[str, Any]],
    model_key: str,
) -> str:
    api_key = str(cfg.get("apiKey") or "").strip()
    if not api_key:
        env_name = str(cfg.get("apiKeyEnv") or "").strip()
        if env_name:
            api_key = os.environ.get(env_name, "").strip()
    if not api_key:
        api_key = (os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("OPENAI_API_KEY") or "").strip()
    if not api_key:
        raise RuntimeError("未检测到 API Key（请在环境变量设置 DEEPSEEK_API_KEY 或在 ophanim_agent_backend.json 配置 apiKeyEnv）")

    is_ds_default = bool(os.environ.get("DEEPSEEK_API_KEY")) or "deepseek" in str(cfg.get("baseUrl") or "").lower()
    base_url = str(
        cfg.get("baseUrl")
        or ("https://api.deepseek.com/v1" if is_ds_default else "https://api.openai.com/v1")
    ).rstrip("/")
    endpoint = base_url if base_url.endswith("/chat/completions") else f"{base_url}/chat/completions"

    default_model = str(cfg.get("defaultModel") or ("deepseek-chat" if is_ds_default else "gpt-4o")).strip()
    chosen_model = default_model if (not model_key or model_key in ("inherit", "flash", "pro", "flash_lite")) else model_key
    sys_prompt = str(cfg.get("systemPrompt") or "You are a helpful AI engineering agent connected to the 3D Ophanim Sanctum workbench. Reply clearly in Markdown.").strip()

    messages: list[dict[str, Any]] = []
    if sys_prompt:
        messages.append({"role": "system", "content": sys_prompt})
    for h in history[-24:]:
        role = "assistant" if h.get("role") == "assistant" else "user"
        txt = str(h.get("text") or "").strip()
        if txt:
            messages.append({"role": role, "content": txt})

    user_content = prompt
    if attachments:
        att_notes = [f"[附件: {a.get('name')} -> {a.get('path')}]" for a in attachments]
        user_content = (prompt + "\n\n" + "\n".join(att_notes)).strip()
    messages.append({"role": "user", "content": user_content})

    req_body = {
        "model": chosen_model,
        "messages": messages,
        "stream": True,
    }
    req = urllib.request.Request(
        endpoint,
        data=json.dumps(req_body, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    opener = urllib.request.build_opener()
    acc_reasoning: list[str] = []
    acc_content: list[str] = []
    last_emit = time.monotonic()

    with opener.open(req, timeout=180) as resp:
        for raw_line in resp:
            if is_turn_cancelled(cid):
                break
            line = raw_line.decode("utf-8", errors="replace").strip()
            if not line or not line.startswith("data:"):
                continue
            data_str = line[5:].strip()
            if data_str == "[DONE]":
                break
            try:
                pkt = json.loads(data_str)
                choices = pkt.get("choices") or []
                if not choices:
                    continue
                delta = choices[0].get("delta") or {}
                rc = delta.get("reasoning_content")
                cc = delta.get("content")
                if rc:
                    acc_reasoning.append(str(rc))
                if cc:
                    acc_content.append(str(cc))
                now = time.monotonic()
                if now - last_emit >= 0.18:
                    merged = _format_reasoning_and_content("".join(acc_reasoning), "".join(acc_content))
                    if merged:
                        update_turn_progress(cid, turn_number, merged, finished=False)
                    last_emit = now
            except Exception:
                continue

    final_md = _format_reasoning_and_content("".join(acc_reasoning), "".join(acc_content))
    return final_md or "(模型返回空内容)"


def _format_reasoning_and_content(reasoning: str, content: str) -> str:
    r = reasoning.strip()
    c = content.strip()
    if r and c:
        quoted = "\n".join("> " + ln for ln in r.splitlines())
        return f"> **思考过程**\n{quoted}\n\n{c}"
    if r and not c:
        quoted = "\n".join("> " + ln for ln in r.splitlines())
        return f"> **思考中...**\n{quoted}"
    return c


def _execute_turn_worker(
    cid: str,
    turn_number: int,
    prompt: str,
    history: list[dict[str, Any]],
    attachments: list[dict[str, Any]],
    model_key: str,
) -> None:
    cfg = load_backend_config()
    mode = resolve_effective_mode(cfg)
    ctx = TurnBridgeContext(cid, turn_number)
    if prompt:
        # Subtle visual pulse on core when dispatching user prompt
        _emit_payload({"cascadeId": cid, "op": "ack_complete"})

    try:
        if mode == "python_bridge":
            reply_md = _run_python_bridge_turn(cfg, cid, turn_number, prompt, history, attachments, model_key)
            update_turn_progress(cid, turn_number, reply_md, finished=True)
        elif mode == "cli_command":
            reply_md = _run_cli_command_turn(cfg, cid, turn_number, prompt, attachments, model_key)
            update_turn_progress(cid, turn_number, reply_md, finished=True)
        elif mode == "openai_compatible":
            reply_md = _run_openai_compatible_turn(cfg, cid, turn_number, prompt, history, attachments, model_key)
            update_turn_progress(cid, turn_number, reply_md, finished=True)
        elif mode == "http_relay":
            with _PENDING_RELAY_CV:
                _PENDING_RELAY_QUEUE.append(
                    {
                        "cascadeId": cid,
                        "turnNumber": turn_number,
                        "prompt": prompt,
                        "history": history,
                        "attachments": attachments,
                        "model": model_key,
                        "queuedAt": _iso_now(),
                    }
                )
                _PENDING_RELAY_CV.notify_all()
            update_turn_progress(
                cid,
                turn_number,
                "✦ 已投递至外部 Harness 待命队列（等待外部 Agent 调用 `/api/external/pending` 拉取并回传结果）...",
                finished=False,
            )
        else:
            guide_msg = (
                "### 尚未挂载外部 Agent 对话桥接器\n\n"
                "当前环境未运行 **Google Antigravity**，且尚未配置外部 Agent（如 **DeepSeek Harness / Codex / Claude Code**）的双向收发桥接器。\n\n"
                "请直接把下面这句话发给你的外部 Agent（例如 DeepSeek Harness）：\n\n"
                "> **「请阅读项目根目录的 `AGENT_HANDOFF_GUIDE.md` 第三节，在项目根目录创建 `ophanim_agent_backend.json` 和 `custom_agent_bridge.py`（或配置 `http_relay` / `cli_command`），把你的对话执行能力接入 Ophanim 工作台后端，使我在圣轮界面点发送就能直接和你对话并驱动 3D 薄板与完成金字塔。」**"
            )
            ctx.stream_partial(guide_msg)
            update_turn_progress(cid, turn_number, guide_msg, finished=True)
    except Exception as exc:
        logger.warning("External turn execution error: %s", exc)
        err_md = f"**执行出错**：`{exc}`\n\n请检查 `custom_agent_bridge.py` 或 `ophanim_agent_backend.json` 配置。"
        update_turn_progress(cid, turn_number, err_md, finished=True)


def send_verbatim_message(
    target_cid: str,
    exact_text: str | None,
    model_key: str = "inherit",
    allow_create: bool = True,
    attachments: list[dict[str, Any]] | None = None,
    send_mode: str = "queue",
) -> dict[str, Any]:
    cfg = load_backend_config()
    mode = resolve_effective_mode(cfg)
    if mode == "unconfigured":
        return {
            "ok": False,
            "error": (
                "当前未运行 Antigravity，且外部 Agent 尚未完成双向工作台挂载。"
                "请让你的 DeepSeek Harness / Codex 按新版 AGENT_HANDOFF_GUIDE.md 第 3 节生成 "
                "custom_agent_bridge.py 或 ophanim_agent_backend.json 后即可直接在此发消息！"
            ),
        }

    prompt = str(exact_text or "").strip()
    saved_atts, staged_paths = _stage_attachments(attachments)
    if not prompt and not saved_atts:
        return {"ok": False, "error": "消息内容与附件均为空"}

    created_new = False
    with _LOCK:
        cid = str(target_cid or "").strip()
        doc = None if (not cid or cid == "__new__") else _load_session(cid)
        if doc is None:
            if not allow_create:
                return {"ok": False, "error": "目标会话不存在"}
            first_line = (prompt.splitlines()[0] if prompt else "附件分析请求").strip()
            short_title = first_line[:34] + ("…" if len(first_line) > 34 else "")
            doc = _create_blank_session(short_title or "新外部 Agent 会话")
            cid = doc["id"]
            created_new = True

        turns = list(doc.get("turns") or [])
        prior_history: list[dict[str, Any]] = []
        for tr in turns:
            if tr.get("userText"):
                prior_history.append({"role": "user", "text": tr["userText"]})
            if tr.get("assistantText"):
                prior_history.append({"role": "assistant", "text": tr["assistantText"]})

        turn_num = len(turns) + 1
        title_line = (prompt.splitlines()[0] if prompt else "[图片/文件请求]").strip()
        new_turn = {
            "turnNumber": turn_num,
            "title": title_line[:64] + ("…" if len(title_line) > 64 else ""),
            "userText": prompt,
            "attachments": saved_atts,
            "assistantText": "",
            "hasFinalReply": False,
            "userStepIndex": (turn_num - 1) * 2,
            "time": _hhmm_now(),
            "status": "running",
        }
        turns.append(new_turn)
        if len(turns) == 1 and prompt:
            first_line = prompt.splitlines()[0].strip()
            doc["title"] = first_line[:34] + ("…" if len(first_line) > 34 else "")
        doc["turns"] = turns
        doc["status"] = "running"
        doc["updatedAt"] = _iso_now()
        doc["updatedEpoch"] = time.time()
        _CANCEL_EVENTS[cid] = threading.Event()
        _save_session(doc)

    worker_thread = threading.Thread(
        target=_execute_turn_worker,
        args=(cid, turn_num, prompt, prior_history, saved_atts, model_key),
        daemon=True,
    )
    worker_thread.start()

    return {
        "ok": True,
        "cascadeId": cid,
        "createdNew": created_new,
        "flushedNow": send_mode == "interrupt",
        "stagedPaths": staged_paths,
    }


def cancel_running_turn(cid: str) -> dict[str, Any]:
    """Immediately stop/pause an active turn in External Agent mode (CLI / OpenAI / Python / HTTP Relay)."""
    target_cid = str(cid or "").strip()
    if not target_cid or target_cid == "__new__":
        return {"ok": False, "action": "cancel", "error": "无效的会话 ID"}

    ev = _CANCEL_EVENTS.get(target_cid)
    if ev is not None:
        ev.set()

    proc = _ACTIVE_PROCS.pop(target_cid, None)
    if proc is not None:
        try:
            proc.terminate()
        except Exception:
            pass

    with _PENDING_RELAY_CV:
        _PENDING_RELAY_QUEUE[:] = [t for t in _PENDING_RELAY_QUEUE if str(t.get("cascadeId") or "") != target_cid]

    with _LOCK:
        doc = _load_session(target_cid)
        if not doc:
            return {"ok": False, "cascadeId": target_cid, "action": "cancel", "error": "会话不存在"}
        turns = list(doc.get("turns") or [])
        for tr in reversed(turns):
            if tr.get("status") in ("running", "queued", "pending") and not tr.get("hasFinalReply"):
                cur_txt = str(tr.get("assistantText") or "").strip()
                tr["assistantText"] = (cur_txt + "\n\n*(已手动停止本轮执行)*") if cur_txt else "*(已手动停止本轮执行)*"
                tr["replyTime"] = _hhmm_now()
                tr["hasFinalReply"] = True
                tr["status"] = "done"
                tr["cancelledByUser"] = True
                break
        doc["turns"] = turns
        doc["status"] = "idle"
        doc["updatedAt"] = _iso_now()
        doc["updatedEpoch"] = time.time()
        _save_session(doc)
        snap = doc_to_snapshot(doc)
        convs = list_conversations()

    _emit_payload({"type": "agy_conversation_delta", "snapshot": snap, "conversations": convs})
    _emit_payload({"type": "agy_conversations_list", "conversations": convs, "activeCascadeId": target_cid})
    return {"ok": True, "cascadeId": target_cid, "action": "cancel"}


def pop_pending_relay_task(wait_seconds: float = 0.0) -> dict[str, Any] | None:
    """Used by external Harnesses running in `http_relay` mode (`GET /api/external/pending`)."""
    deadline = time.monotonic() + max(0.0, min(30.0, float(wait_seconds or 0.0)))
    with _PENDING_RELAY_CV:
        while not _PENDING_RELAY_QUEUE:
            rem = deadline - time.monotonic()
            if rem <= 0:
                return None
            _PENDING_RELAY_CV.wait(timeout=rem)
        return _PENDING_RELAY_QUEUE.pop(0)


def submit_relay_reply(
    cid: str,
    turn_number: int,
    text: str,
    finished: bool = True,
) -> dict[str, Any]:
    """Used by external Harnesses in `http_relay` mode (`POST /api/external/reply`)."""
    snap = update_turn_progress(cid, turn_number, text, finished=finished)
    if snap is None:
        return {"ok": False, "error": f"未找到会话 {cid} 的第 {turn_number} 轮"}
    return {"ok": True, "cascadeId": cid, "turnNumber": turn_number, "finished": finished, "snapshot": snap}
