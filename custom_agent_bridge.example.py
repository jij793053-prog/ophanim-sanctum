#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
custom_agent_bridge.example.py
Template for connecting DeepSeek Harness / OpenAI Codex / Claude Code / Any Custom Agent
to Ophanim Sanctum's bidirectional chat workbench (`AGENT 控制台` & Central Core Sphere).

HOW FOR AN AI AGENT TO ACTIVATE THIS:
  1. Copy/rename this file to `custom_agent_bridge.py` in the project root directory.
  2. Create `ophanim_agent_backend.json` in the project root directory:
     {
       "provider": "external",
       "mode": "python_bridge",
       "agentName": "DEEPSEEK HARNESS",
       "bridgeScript": "custom_agent_bridge.py"
     }
  3. Replace the body of `handle_ophanim_turn(...)` below so it invokes YOUR actual
     Agent Harness / SDK / CLI / API, calls `ctx.emit_read(...)` / `ctx.emit_write(...)`
     as tools run, calls `ctx.stream_partial(...)` for live streaming, and returns the
     final Markdown string!
"""
from __future__ import annotations

from typing import Any


def handle_ophanim_turn(
    prompt: str,
    session_id: str,
    history: list[dict[str, Any]],
    attachments: list[dict[str, Any]],
    model: str,
    ctx: Any,
) -> str:
    """
    Called automatically whenever the user sends a message from Ophanim UI!

    Available real-time 3D astrolabe hooks on `ctx`:
      - ctx.stream_partial(markdown_so_far)       # Live-stream text into Ophanim chat pane
      - ctx.emit_read("src/main.py")              # Trigger 3D inward READ beam + slab
      - ctx.emit_write("src/app.py", code="...")  # Trigger 3D outward WRITE beam + slab
      - ctx.emit_outer("src/core.py", role="CORE")# Engrave outermost double-sided bezel window
      - ctx.emit_deliver("dist/out.md", "摘要")   # Populate outermost patterned eye deliverable
      - ctx.emit_swarm(3)                         # Spawn 4-pointed star subagent nodes
    """
    ctx.stream_partial("✦ DeepSeek Harness 正在推理与调度本地工具...")

    # TODO (For the Receiving Agent): Replace the demo logic below with a real call
    # into your DeepSeek Harness / Agent loop / OpenAI-compatible SDK!
    raise NotImplementedError(
        "请在 custom_agent_bridge.py 的 handle_ophanim_turn() 中接入你的真实 DeepSeek Harness / Agent 执行逻辑！"
    )
