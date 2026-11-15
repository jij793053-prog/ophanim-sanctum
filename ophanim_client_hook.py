#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ophanim_client_hook.py
Universal zero-dependency Python SDK & CLI hook for Ophanim Sanctum (`127.0.0.1:18790`).

Allows ANY AI coding agent (DeepSeek, OpenAI Codex, Claude Code, Cursor, Windsurf,
Cline, Roo Code, or custom Python workflows) to drive 3D file slabs, spline light
beams, `/swarm` 4-pointed stars, outer deliverable eyes, token burn-rate charts,
and the Radiant White Sphere + 7-Tier Stepped Pyramid completion state.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any
import urllib.request

OPHANIM_EVENT_URL = os.environ.get("OPHANIM_EVENT_URL", "http://127.0.0.1:18790/api/event")
OPHANIM_API_TOKEN = os.environ.get("OPHANIM_API_TOKEN", "").strip()
_DIRECT_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def notify_ophanim(payload: dict[str, Any], timeout: float = 0.25) -> bool:
    """Send an event payload to the local Ophanim daemon (bypasses system proxy, silent fail)."""
    if not isinstance(payload, dict):
        return False
    headers = {"Content-Type": "application/json; charset=utf-8"}
    if OPHANIM_API_TOKEN:
        headers["X-Ophanim-Token"] = OPHANIM_API_TOKEN
    try:
        req = urllib.request.Request(
            OPHANIM_EVENT_URL,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with _DIRECT_OPENER.open(req, timeout=max(0.05, float(timeout))) as resp:
            resp.read()
        return True
    except Exception:
        return False


def _read_snippet(file_path: str | Path, fallback_note: str = "") -> tuple[Path, str, str]:
    p = Path(str(file_path))
    ext = p.suffix.lstrip(".").upper() or "FILE"
    body = fallback_note
    if not body and p.is_file():
        try:
            body = "\n".join(p.read_text(encoding="utf-8", errors="replace").splitlines()[:56])
        except Exception:
            body = f"# Agent File Operation\n# File: {p.name}"
    return p, ext, body


def notify_file_read(file_path: str | Path, code_preview: str = "") -> bool:
    """Trigger an inward spline light beam reading a 3D Golden File Slab (`op='read'`)."""
    p, ext, body = _read_snippet(file_path, code_preview)
    return notify_ophanim({"op": "read", "file": p.name, "kind": ext, "code": body})


def notify_file_write(file_path: str | Path, code_preview: str = "") -> bool:
    """Populate a 3D File Slab and fire an outward write beam from the central core (`op='write'`)."""
    p, ext, body = _read_snippet(file_path, code_preview)
    return notify_ophanim({"op": "write", "file": p.name, "kind": ext, "code": body})


def notify_outer_module(file_path: str | Path, role: str = "CORE_MOD", code_preview: str = "") -> bool:
    """Mount a core module into one of the 8 double-sided outer bezel windows (`tier='outer'`)."""
    p, _ext, body = _read_snippet(file_path, code_preview)
    return notify_ophanim({"tier": "outer", "op": "exec", "file": p.name, "role": role, "code": body})


def notify_deliverable(file_path: str | Path, code_preview: str = "") -> bool:
    """Deliver a finished artifact into an outermost Sacred Eye Sigil (`op='deliver'`)."""
    p, _ext, body = _read_snippet(file_path, code_preview)
    resolved = p.resolve(strict=False)
    return notify_ophanim(
        {
            "tier": "eye",
            "op": "deliver",
            "file": p.name,
            "dirPath": str(resolved.parent),
            "fullPath": str(resolved),
            "code": body,
        }
    )


def notify_swarm(workers: list[dict[str, str]] | int) -> bool:
    """Ignite outer 4-pointed sub-agent stars (`workers` list or integer count `0..12`)."""
    if isinstance(workers, int):
        return notify_ophanim({"swarmCount": max(0, min(12, workers))})
    return notify_ophanim({"workers": workers})


def notify_swarm_beam(worker_idx: int = 0, direction: str = "out") -> bool:
    """Fire an alternating spline beam between the central core and a 4-pointed sub-agent star."""
    return notify_ophanim({"op": "swarm_beam", "workerIdx": int(worker_idx), "dir": direction})


def notify_quota(used_pct: float, burn_rate_tok_per_sec: int = 0, rem_label: str = "", tier_tag: str = "AGENT") -> bool:
    """Push real-time token velocity and quota percentage to the 60fps Ornamental Deck chart."""
    return notify_ophanim(
        {
            "quota": {
                "usedPct": float(used_pct),
                "burnRateTokPerSec": int(burn_rate_tok_per_sec),
                "remLabel": rem_label,
                "tierTag": tier_tag,
            }
        }
    )


def notify_task_complete(unread_count: int = 1, running_count: int = 0) -> bool:
    """Light up the central Radiant White Sphere and trigger the 7-tier Stepped Pyramid."""
    return notify_ophanim(
        {"completion": {"unreadCount": max(1, int(unread_count)), "runningCount": max(0, int(running_count))}}
    )


def notify_ack_complete() -> bool:
    """Acknowledge completed tasks and return the stepped pyramid to 3D orbital motion."""
    return notify_ophanim({"op": "ack_complete"})


def _cli() -> int:
    parser = argparse.ArgumentParser(description="Send live 3D telemetry events to Ophanim Sanctum")
    parser.add_argument(
        "--op",
        required=True,
        choices=["read", "write", "outer", "deliver", "swarm", "swarm_beam", "quota", "complete", "ack_complete"],
        help="Event operation type",
    )
    parser.add_argument("--file", default="", help="Target file path for read/write/outer/deliver")
    parser.add_argument("--role", default="CORE_MOD", help="Module role tag for --op outer")
    parser.add_argument("--code", default="", help="Optional inline code snippet preview")
    parser.add_argument("--workers", type=int, default=0, help="Sub-agent star count (0..12) for --op swarm")
    parser.add_argument("--worker-idx", type=int, default=0, help="Worker star index for --op swarm_beam")
    parser.add_argument("--used-pct", type=float, default=0.0, help="Quota used percentage for --op quota")
    parser.add_argument("--tok-rate", type=int, default=0, help="Token burn rate (tok/s) for --op quota")
    args = parser.parse_args()

    if args.op == "read":
        ok = notify_file_read(args.file or "README.md", args.code)
    elif args.op == "write":
        ok = notify_file_write(args.file or "module.py", args.code)
    elif args.op == "outer":
        ok = notify_outer_module(args.file or "engine.py", args.role, args.code)
    elif args.op == "deliver":
        ok = notify_deliverable(args.file or "artifact.md", args.code)
    elif args.op == "swarm":
        ok = notify_swarm(args.workers)
    elif args.op == "swarm_beam":
        ok = notify_swarm_beam(args.worker_idx, "out")
    elif args.op == "quota":
        ok = notify_quota(args.used_pct, args.tok_rate)
    elif args.op == "complete":
        ok = notify_task_complete(1, 0)
    else:
        ok = notify_ack_complete()
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(_cli())
