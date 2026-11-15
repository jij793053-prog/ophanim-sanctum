# Ophanim Sanctum — 跨平台 AI Agent 自动部署与双向工作台接入交接文档 (Agent Handoff Guide)

> **给人类用户的一句话用法**：
> 不管你用的是 **Google Antigravity**、**DeepSeek Harness**、**OpenAI Codex**、**Claude Code**、**Cursor** 还是其他本地 Agent，把本项目解压后，直接把下面这段话发给你的 Agent：
>
> **「请完整阅读当前目录下的 `AGENT_HANDOFF_GUIDE.md`（重点看第 3 节双向对话桥接！）和 `skills/ophanim-sanctum/SKILL.md`，帮我启动 Ophanim Sanctum，并为你自己的 Harness 生成 `ophanim_agent_backend.json` 与 `custom_agent_bridge.py` 完成双向收发适配，最后用 `/api/conversation/send` 自测确认在圣轮面板发消息能正常收到你的回复！」**

---

## 以下内容专为接手部署的 AI Agent 编写 (Mandatory Spec for the Receiving AI Agent)

你好，接手本项目的 AI Agent！请务必仔细阅读：**Ophanim Sanctum 包含两套独立机制，如果你不是 Google Antigravity（例如你是 DeepSeek Harness、OpenAI Codex、Claude Code 等），你必须同时完成「双向对话后端挂载」和「3D 圣轮事件驱动」，绝对不能只启动守护进程就结束！**

> [!IMPORTANT]
> **为什么直接启动就收工会导致「发送失败: 未检测到运行中的本地 Antigravity Language Server」？**
> 默认未配置状态下，前端工作台（左上角 `AGENT 控制台` 与中央圣球聊天窗）点「✦ 发送」时会尝试连接本地 Google Antigravity 私有 Language Server。
> **只要你不是 Google Antigravity，你就必须按下方【第三节】在项目根目录创建 `ophanim_agent_backend.json`（及 `custom_agent_bridge.py`），把前端发消息接口切换到内置的通用外部桥接引擎 `ophanim_external_bridge.py`（无需重启守护进程即可热生效）！**

---

### 第一步：环境检查与启动本地守护进程

1. 安装依赖（需 Python 3.10+）：
   ```bash
   pip install -r requirements.txt
   ```
2. 启动服务（默认仅安全监听本地回环 `127.0.0.1:18790`）：
   - **Windows 桌面环境**：运行 `pythonw ophanim_app_launcher.pyw`（可同时运行 `Create_Desktop_Shortcut.bat` 在桌面生成带圣轮星盘图标的快捷方式）。
   - **macOS / Linux 或后台纯服务**：运行 `python ophanim_agy_daemon.py`，浏览器打开 `http://127.0.0.1:18790/ophanim_sanctum.html?ws=ws://127.0.0.1:18790/ws`。
3. 检查健康状态：`curl http://127.0.0.1:18790/api/health` 返回 `{"ok": true, ...}`。

---

### 第二步：如果你是 Google Antigravity（零配置原生模式）

- 你什么都不用额外配置！`ophanim_agy_daemon.py` 会自动发现运行中的 Antigravity Language Server 与 `~/.gemini/antigravity/brain/` 会话目录。
- 可将 `skills/ophanim-sanctum` 复制到 `~/.gemini/antigravity/skills/ophanim-sanctum` 备查。

---

### 第三步：【必做！】如果你是 DeepSeek Harness / Codex / Claude Code / 其他 Agent —— 挂载双向聊天工作台

`ophanim_external_bridge.py` 已经为你内置好了完整的本地会话管理（新建/切换/置顶/归档/删除会话、多轮折叠卡片、附件落盘、流式回执推送、完工白球与七层阶梯金字塔触发）。
**请根据你自身的架构，从以下 4 种方式中任选最合适的一种，在项目根目录生成配置文件（禁止保留未实现的占位报错）：**

#### 方式 A（最推荐 · 适合 DeepSeek Harness / 自定义 Python Agent 框架）：`python_bridge` 模式
1. 在项目根目录写入 `ophanim_agent_backend.json`：
   ```json
   {
     "provider": "external",
     "mode": "python_bridge",
     "agentName": "DEEPSEEK HARNESS",
     "bridgeScript": "custom_agent_bridge.py"
   }
   ```
2. 在项目根目录创建 `custom_agent_bridge.py`（可参考 `custom_agent_bridge.example.py`），实现 `handle_ophanim_turn(prompt, session_id, history, attachments, model, ctx)`（支持普通 `def` 或 `async def`）：
   - 当用户在圣轮 UI 点击「✦ 发送」时，守护进程会自动在新线程调用你的 `handle_ophanim_turn(...)`！
   - 你在函数内部直接调用你的 **DeepSeek Harness 核心 Agent Loop / 工具执行器 / DeepSeek API**：
     - 流式输出中间文本：`ctx.stream_partial(markdown_so_far)`
     - 读文件时点亮圣轮向内光束：`ctx.emit_read(file_path)`
     - 写文件时点亮圣轮向外光束与代码薄板：`ctx.emit_write(file_path, code)`
     - 核心模块刻入最外环：`ctx.emit_outer(file_path, role="CORE", code=code)`
     - 终稿文件装入最外环圣瞳：`ctx.emit_deliver(file_path, summary="交付说明")`
     - 子智能体并发：`ctx.emit_swarm(count)`
   - 函数返回最终的 Markdown 字符串后，Ophanim 会自动落盘本轮回执、切换状态为 `✓ 已完成`，并**自动点亮纯白圣球 + 展开七层阶梯金字塔**！

#### 方式 B（适合独立命令行 CLI Harness，如 `codex`、`claude -p` 或你的 CLI 入口脚本）：`cli_command` 模式
在项目根目录写入 `ophanim_agent_backend.json`：
```json
{
  "provider": "external",
  "mode": "cli_command",
  "agentName": "DEEPSEEK HARNESS",
  "command": ["python", "你的harness入口脚本.py", "--session", "{session_id}", "--prompt", "{prompt}"],
  "cwd": "."
}
```
> 若你的 CLI 从 `stdin` 读取输入，只需在 `command` 中不写 `{prompt}`，桥接器会自动把用户消息写入子进程 `stdin`，并实时流式捕获 `stdout` 显示在聊天框内；你的 CLI 内部可随时调用 `python ophanim_client_hook.py --op read/write/...` 驱动 3D 圣轮。

#### 方式 C（适合直接连 DeepSeek 官方 API / OpenAI 兼容接口）：`openai_compatible` 模式
在项目根目录写入 `ophanim_agent_backend.json`（并确保环境变量 `DEEPSEEK_API_KEY` 已设置，或填入 `apiKey`）：
```json
{
  "provider": "external",
  "mode": "openai_compatible",
  "agentName": "DEEPSEEK AGENT",
  "baseUrl": "https://api.deepseek.com/v1",
  "apiKeyEnv": "DEEPSEEK_API_KEY",
  "defaultModel": "deepseek-chat"
}
```
> 原生支持 DeepSeek `deepseek-chat` 与 `deepseek-reasoner`（自动流式渲染思考过程引用块 + 正文 Markdown）！

#### 方式 D（适合你当前正运行在另一个长驻终端进程里，想自己拉取消息回复）：`http_relay` 模式
1. `ophanim_agent_backend.json` 设为 `{"provider": "external", "mode": "http_relay", "agentName": "DEEPSEEK HARNESS"}`。
2. 你的常驻进程循环长轮询拉取用户在 UI 输入的消息：
   - 拉取待处理请求：`GET http://127.0.0.1:18790/api/external/pending?wait=20` -> 返回 `{"ok": true, "task": {"cascadeId": "...", "turnNumber": 1, "prompt": "...", ...}}`
   - 流式更新或提交最终回答：`POST http://127.0.0.1:18790/api/external/reply`，JSON 体：`{"cascadeId": "...", "turnNumber": 1, "text": "你的 Markdown 回复", "finished": true}`。

---

### 第四步：独立 CLI 3D 动效钩子（在你平时终端执行任务时同步驱动圣轮）

即使不在网页聊天框内发起，你在终端里执行任务时也可以随时调用零依赖脚本 `ophanim_client_hook.py` 让屏幕/桌面壁纸上的圣轮实时联动：
- 开始新一轮任务（归位金字塔）：`python ophanim_client_hook.py --op ack_complete`
- 读取文件：`python ophanim_client_hook.py --op read --file "src/router.ts"`
- 编写代码：`python ophanim_client_hook.py --op write --file "src/app.py" --code-file "src/app.py"`
- 镌刻外环核心模块：`python ophanim_client_hook.py --op outer --file "src/core.py" --role "CORE" --code-file "src/core.py"`
- 子代理星群：`python ophanim_client_hook.py --op swarm --count 3` 与 `python ophanim_client_hook.py --op swarm_beam --worker 0 --dir out`
- 终稿交付：`python ophanim_client_hook.py --op deliver --file "output/result.md" --summary "交付摘要"`
- 任务完工（亮起白球 + 展开七层阶梯金字塔）：`python ophanim_client_hook.py --op complete --unread 1 --title "任务已完成"`

---

### 第五步：【交付前强制自检】验证发消息不再报错！

在你向人类用户汇报“部署完成”之前，**必须**执行以下两条验证命令：
1. 检查当前激活的 Agent 后端是否已变成你的名字且 `"ready": true`：
   ```bash
   curl http://127.0.0.1:18790/api/health
   ```
   确认返回 JSON 中的 `agentBackend` 为 `{"backend": "external", "ready": true, ...}`。
2. 模拟前端聊天框发送一条真实测试消息：
   ```bash
   curl -X POST http://127.0.0.1:18790/api/conversation/send -H "Content-Type: application/json" -d "{\"cascadeId\":\"__new__\",\"text\":\"你好，请回复收到以确认工作台桥接正常\"}"
   ```
   确认返回 `"ok": true`，且几秒后 `GET http://127.0.0.1:18790/api/conversations` 中能看到生成的完整回复！只有通过此自检，才算真正完成适配。
