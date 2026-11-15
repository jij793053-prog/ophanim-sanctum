---
name: ophanim-sanctum
description: Deploys and connects the 3D Ophanim Sanctum real-time visual telemetry, bidirectional chat workbench, code-slab rings, /swarm 4-pointed star constellation, quota monitor, and task-completion stepped pyramid to any AI Agent (Google Antigravity, DeepSeek Harness, OpenAI Codex, Claude Code, Cursor, or custom Python/CLI agents). Activate when the user asks to launch, connect, adapt, or configure Ophanim Sanctum.
---

# Ophanim Sanctum — Universal Agent Skill

Ophanim Sanctum (`127.0.0.1:18790`) has **two integrated layers**:
1. **Bidirectional Agent Workbench (`AGENT 控制台` + Central Core Sphere)**: Session list, multi-turn chat composer, file attachments, live streaming replies, and unread completion tracking.
2. **3D Ezekiel Astrolabe Visual Engine**:
   - **Inner Dual-Rail Slabs**: Live files read (`read`) or edited (`write`).
   - **Outermost Ring Bevel Windows**: Core architectural modules (`outer`).
   - **Outermost Ring Patterned Oculi (Eyes)**: Final deliverables (`deliver`).
   - **Surrounding 4-Pointed Stars**: Active subagents / `/swarm` workers (`swarm`, `swarm_beam`).
   - **Stepped 7-Tier Pyramid + Radiant White Sphere**: Unfolds when a turn finishes (`complete`), folding back when clicked on window or desktop wallpaper (`ack_complete`).

## 1. Quick Start & Service Launch

1. Install Python dependency (Python 3.10+):
   ```bash
   pip install -r requirements.txt
   ```
2. Launch local daemon + 3D app window:
   - **Windows**: `pythonw ophanim_app_launcher.pyw` (or `Start_Ophanim_Sanctum.bat`; run `Create_Desktop_Shortcut.bat` for custom-icon shortcut).
   - **Headless / Daemon only**: `python ophanim_agy_daemon.py`

## 2. Connecting the Bidirectional Chat Workbench (CRITICAL!)

- **If you ARE Google Antigravity**: Zero config needed. `ophanim_agy_daemon.py` auto-discovers the local Antigravity Language Server and `~/.gemini/antigravity/brain/`.
- **If you are NOT Google Antigravity (e.g., DeepSeek Harness, OpenAI Codex, Claude Code, Cursor, Custom Agent)**:
  **DO NOT stop after launching the daemon!** By default, the Send button looks for Antigravity Language Server. You **MUST** create `ophanim_agent_backend.json` in the project root (see `AGENT_HANDOFF_GUIDE.md` Section 3 for full templates) using one of these 4 built-in modes in `ophanim_external_bridge.py`:
  1. **`python_bridge` (Recommended for DeepSeek Harness / Python Agents)**: Set `{"provider": "external", "mode": "python_bridge", "agentName": "DEEPSEEK HARNESS", "bridgeScript": "custom_agent_bridge.py"}` and implement `handle_ophanim_turn(prompt, session_id, history, attachments, model, ctx)` in `custom_agent_bridge.py` (calling `ctx.emit_read`, `ctx.emit_write`, `ctx.stream_partial`, etc.).
  2. **`cli_command` (For CLI Harnesses)**: Set `{"provider": "external", "mode": "cli_command", "agentName": "DEEPSEEK HARNESS", "command": ["...", "{prompt}"]}`.
  3. **`openai_compatible` (Direct DeepSeek / OpenAI SSE API)**: Set `{"provider": "external", "mode": "openai_compatible", "agentName": "DEEPSEEK AGENT", "baseUrl": "https://api.deepseek.com/v1", "apiKeyEnv": "DEEPSEEK_API_KEY", "defaultModel": "deepseek-chat"}`.
  4. **`http_relay` (External Running Terminal Harness)**: Set `"mode": "http_relay"`, poll `GET /api/external/pending?wait=20`, and submit answers via `POST /api/external/reply`.
  - **Mandatory Verification**: Always test `curl http://127.0.0.1:18790/api/health` (`agentBackend.ready == true`) and `POST http://127.0.0.1:18790/api/conversation/send` before finishing!

## 3. Standalone CLI Visual Hooks (`ophanim_client_hook.py`)
- `python ophanim_client_hook.py --op read --file "src/router.ts"`
- `python ophanim_client_hook.py --op write --file "src/engine.py" --kind PYTHON --code-file "src/engine.py"`
- `python ophanim_client_hook.py --op outer --file "src/kernel.rs" --role CORE_KERNEL --code-file "src/kernel.rs"`
- `python ophanim_client_hook.py --op swarm --count 3`
- `python ophanim_client_hook.py --op deliver --file "dist/report.md" --summary "Completed report"`
- `python ophanim_client_hook.py --op complete --unread 1 --title "Task Completed"`
- `python ophanim_client_hook.py --op ack_complete`

## 4. Security Rules
- Never bind `ophanim_agy_daemon.py` to `0.0.0.0` without both `OPHANIM_ALLOW_REMOTE=1` and `OPHANIM_API_TOKEN`.
- Never commit `ophanim_agent_backend.json`, `custom_agent_bridge.py` (if containing keys), `ophanim_config.json`, `*.log`, or `.ophanim_cache/` to Git.
