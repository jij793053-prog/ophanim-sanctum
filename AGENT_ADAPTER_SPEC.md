# Ophanim Sanctum — 外部 Agent 双向工作台与 3D 事件协议规范 (Agent Adapter Protocol Spec)

- **本地服务地址**：`http://127.0.0.1:18790`（仅安全绑定本地回环）
- **WebSocket 端点**：`ws://127.0.0.1:18790/ws`
- **可选鉴权头**：若设置了环境变量 `OPHANIM_API_TOKEN`，所有 `/api/*` 请求附带 `X-Ophanim-Token: <token>`。

---

## 一、双向对话工作台桥接接口 (`ophanim_external_bridge.py`)

对于 **DeepSeek Harness / OpenAI Codex / Claude Code / 自定义 Agent**，在项目根目录创建 `ophanim_agent_backend.json` 即可接管前端 `AGENT 控制台` 与中央圣球的所有会话列表与消息收发（详见 `AGENT_HANDOFF_GUIDE.md` 第三节）：

| 模式 (`mode`) | 适用场景 | 核心配置字段 |
| :--- | :--- | :--- |
| `python_bridge` | Python Harness / 自定义多工具 Agent Loop（最推荐） | `"bridgeScript": "custom_agent_bridge.py"`，实现 `handle_ophanim_turn(prompt, session_id, history, attachments, model, ctx)` |
| `cli_command` | 命令行 CLI Harness（如 `deepseek`, `codex`, `claude -p`） | `"command": ["...", "{prompt}"]`, `"cwd": "."` |
| `openai_compatible` | 直连 DeepSeek API / OpenAI / Ollama / vLLM | `"baseUrl": "https://api.deepseek.com/v1"`, `"apiKeyEnv": "DEEPSEEK_API_KEY"`, `"defaultModel": "deepseek-chat"` |
| `http_relay` | 外部已常驻运行的终端 Agent 主动拉取并回传 | `GET /api/external/pending?wait=20` 拉取任务；`POST /api/external/reply` 提交回复 |

### HTTP Relay 模式接口定义
- **拉取前端发送的待处理消息**：`GET http://127.0.0.1:18790/api/external/pending?wait=20`
  - 返回：`{"ok": true, "task": {"cascadeId": "a1b2c3d4", "turnNumber": 1, "prompt": "...", "history": [...], "attachments": [...]}}`（无新消息时 `task` 为 `null`）。
- **流式推送或完结本轮回复**：`POST http://127.0.0.1:18790/api/external/reply`
  - 请求体：`{"cascadeId": "a1b2c3d4", "turnNumber": 1, "text": "Markdown 回复内容", "finished": true}`（`finished: true` 时自动点亮纯白圣球并展开七层阶梯金字塔）。

---

## 二、实时 3D 圣轮事件推送接口 (`POST /api/event`)

- **写内圈薄板**：`{"op": "write", "file": "src/app.py", "kind": "PYTHON", "code": "..."}`
- **读内圈薄板**：`{"op": "read", "file": "src/app.py"}`
- **镌刻最外环双面窗**：`{"op": "outer", "file": "src/kernel.rs", "role": "CORE_KERNEL", "code": "..."}`
- **注入最外环纹路眼交付物**：`{"op": "deliver", "file": "./output/report.md", "summary": "..."}`
- **控制外围四芒星子代理**：`{"op": "swarm", "count": 4}` / `{"op": "swarm_beam", "workerIdx": 0, "dir": "carbon_to_star"}`
- **更新实时配额曲线**：`{"quota": {"usedPct": 34.5, "burnRateTokPerSec": 1420, "peakTokPerSec": 2890}}`
- **触发任务完结白球与七层阶梯金字塔**：`{"op": "complete", "unread": 1, "title": "任务已完成"}`
- **查收归位**：`{"op": "ack_complete"}`
