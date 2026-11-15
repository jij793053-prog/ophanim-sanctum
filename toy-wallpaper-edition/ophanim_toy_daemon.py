#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ophanim_toy_daemon.py
Lightweight local server & interactive Windows 10/11 (incl. 24H2) 3D desktop wallpaper
controller for Ophanim Sanctum Toy Edition (`127.0.0.1:18791`).
Zero AI IDE dependencies; strictly loopback-bound with Host & Origin security guards.
"""
from __future__ import annotations

import argparse
import asyncio
import ctypes
import json
import logging
import os
from pathlib import Path
import sys
from typing import Any
from urllib.parse import urlparse
import urllib.request

PROJECT_DIR = Path(__file__).resolve().parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

DAEMON_LOG_PATH = PROJECT_DIR / "toy_daemon.log"
if sys.stdout is None or sys.stderr is None:
    _fh = open(DAEMON_LOG_PATH, "a", encoding="utf-8", buffering=1)
    if sys.stdout is None:
        sys.stdout = _fh
    if sys.stderr is None:
        sys.stderr = _fh

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(DAEMON_LOG_PATH, encoding="utf-8")],
)
logger = logging.getLogger("ophanim_toy_daemon")

from aiohttp import WSMsgType, web  # noqa: E402
import ophanim_wallpaper_manager as wp_mgr  # noqa: E402

HOST = os.environ.get("OPHANIM_TOY_HOST", "127.0.0.1")
PORT = int(os.environ.get("OPHANIM_TOY_PORT", "18791"))
API_TOKEN = os.environ.get("OPHANIM_API_TOKEN", "").strip()
HTML_PATH = PROJECT_DIR / "ophanim_toy_sanctum.html"
LOGO_ICO_PATH = PROJECT_DIR / "ophanim_logo.ico"
CONFIG_SAVE_PATH = PROJECT_DIR / "ophanim_toy_config.json"

_TRUSTED_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1", "[::1]"}
_DIRECT_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))

CLIENTS: set[web.WebSocketResponse] = set()
WP_CLIENTS: set[web.WebSocketResponse] = set()
SHUTDOWN_EVENT = asyncio.Event()

NO_CACHE_HEADERS = {
    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
    "Pragma": "no-cache",
}


def _extract_hostname(host_header: str) -> str:
    raw = (host_header or "").strip().lower()
    if not raw:
        return ""
    if raw.startswith("["):
        idx = raw.find("]")
        return raw[: idx + 1] if idx != -1 else raw
    return raw.split(":", 1)[0]


def _validated_cors_origin(origin_header: str) -> str | None:
    orig = (origin_header or "").strip()
    if not orig:
        return ""
    if orig == "null":
        return "null"
    try:
        parsed = urlparse(orig)
    except Exception:
        return None
    if parsed.scheme not in ("http", "https"):
        return None
    if (parsed.hostname or "").strip().lower() in {"127.0.0.1", "localhost", "::1"}:
        return orig
    return None


@web.middleware
async def localhost_security_middleware(request: web.Request, handler: Any) -> web.StreamResponse:
    req_host = _extract_hostname(request.headers.get("Host", ""))
    if req_host and req_host not in _TRUSTED_LOCAL_HOSTS:
        return web.json_response({"ok": False, "error": "Untrusted Host header"}, status=403)

    raw_origin = request.headers.get("Origin", "")
    cors_origin = _validated_cors_origin(raw_origin)
    if raw_origin and cors_origin is None:
        return web.json_response({"ok": False, "error": "Cross-origin request blocked"}, status=403)

    if API_TOKEN and request.method != "OPTIONS" and request.path.startswith(("/api/", "/ws")):
        provided = (
            request.headers.get("X-Ophanim-Token", "").strip()
            or request.query.get("token", "").strip()
        )
        if provided != API_TOKEN:
            return web.json_response({"ok": False, "error": "Invalid API token"}, status=401)

    resp = await handler(request)
    if cors_origin:
        resp.headers["Access-Control-Allow-Origin"] = cors_origin
        resp.headers["Vary"] = "Origin"
    return resp


def _is_interactive_desktop() -> bool:
    if os.name != "nt":
        return True
    try:
        u32 = ctypes.windll.user32
        k32 = ctypes.windll.kernel32
        hdesk = u32.GetThreadDesktop(k32.GetCurrentThreadId())
        buf = ctypes.create_unicode_buffer(256)
        needed = ctypes.c_ulong(0)
        if hdesk and u32.GetUserObjectInformationW(hdesk, 2, buf, 512, ctypes.byref(needed)):
            return str(buf.value or "").lower() == "default"
    except Exception:
        pass
    return True


def _load_saved_config() -> dict[str, Any] | None:
    if not CONFIG_SAVE_PATH.is_file():
        return None
    try:
        data = json.loads(CONFIG_SAVE_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _save_config(cfg: dict[str, Any]) -> None:
    tmp = CONFIG_SAVE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(CONFIG_SAVE_PATH)


async def _send_ws(ws: web.WebSocketResponse, payload: dict[str, Any]) -> None:
    if not ws.closed:
        await ws.send_str(json.dumps(payload, ensure_ascii=False))


async def _broadcast(payload: dict[str, Any]) -> None:
    msg = json.dumps(payload, ensure_ascii=False)
    for ws in list(CLIENTS):
        if ws.closed:
            CLIENTS.discard(ws)
            continue
        try:
            await ws.send_str(msg)
        except Exception:
            CLIENTS.discard(ws)


async def handle_index(request: web.Request) -> web.Response:
    body = await asyncio.to_thread(HTML_PATH.read_bytes)
    return web.Response(body=body, content_type="text/html", charset="utf-8", headers=NO_CACHE_HEADERS)


async def handle_logo_ico(request: web.Request) -> web.Response:
    if not LOGO_ICO_PATH.is_file():
        return web.Response(status=204)
    body = await asyncio.to_thread(LOGO_ICO_PATH.read_bytes)
    return web.Response(body=body, content_type="image/x-icon", headers=NO_CACHE_HEADERS)


async def handle_health(request: web.Request) -> web.Response:
    return web.json_response(
        {"ok": True, "service": "ophanim_toy_daemon", "pid": os.getpid(), "interactiveWallpaper": True},
        headers=NO_CACHE_HEADERS,
    )


async def handle_cors_options(request: web.Request) -> web.Response:
    return web.Response(
        status=204,
        headers={
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, X-Ophanim-Token",
        },
    )


async def _exec_wallpaper(body: dict[str, Any]) -> dict[str, Any]:
    action = str(body.get("action") or "status").strip().lower()
    wp_mode = str(body.get("wallpaperMode") or "agy_live").strip()
    beam_mode = str(body.get("beamMode") or "ambient").strip()
    if isinstance(body.get("config"), dict):
        await asyncio.to_thread(_save_config, body["config"])
        await _broadcast({"type": "ophanim_config_updated", "config": body["config"]})
    if action == "status":
        st = await asyncio.to_thread(wp_mgr.get_wallpaper_status)
        return {"type": "ophanim_wallpaper_status", **st}
    if os.name == "nt" and not _is_interactive_desktop():
        return {"type": "ophanim_wallpaper_status", "ok": False, "active": False, "error": "请在用户桌面双击 Start_Toy_Wallpaper_App.bat 启动"}
    if action == "enable":
        st = await asyncio.to_thread(wp_mgr.enable_live_wallpaper, HOST, PORT, wp_mode, beam_mode)
    elif action == "disable":
        st = await asyncio.to_thread(wp_mgr.disable_live_wallpaper)
    else:
        return {"type": "ophanim_wallpaper_status", "ok": False, "error": f"Unknown action: {action}"}
    payload = {"type": "ophanim_wallpaper_status", **st}
    await _broadcast(payload)
    return payload


async def handle_wallpaper_get(request: web.Request) -> web.Response:
    st = await asyncio.to_thread(wp_mgr.get_wallpaper_status)
    return web.json_response({"type": "ophanim_wallpaper_status", **st}, headers=NO_CACHE_HEADERS)


async def handle_wallpaper_post(request: web.Request) -> web.Response:
    try:
        body = await request.json()
    except Exception as exc:
        return web.json_response({"ok": False, "error": str(exc)}, status=400)
    res = await _exec_wallpaper(body if isinstance(body, dict) else {})
    return web.json_response(res, status=200 if res.get("ok", True) else 400, headers=NO_CACHE_HEADERS)


async def handle_event_post(request: web.Request) -> web.Response:
    try:
        body = await request.json()
    except Exception as exc:
        return web.json_response({"ok": False, "error": str(exc)}, status=400)
    if isinstance(body, dict):
        await _broadcast(body)
    return web.json_response({"ok": True, "clients": len(CLIENTS)}, headers=NO_CACHE_HEADERS)


async def handle_shutdown(request: web.Request) -> web.Response:
    SHUTDOWN_EVENT.set()
    return web.json_response({"ok": True}, headers=NO_CACHE_HEADERS)


async def handle_ws(request: web.Request) -> web.WebSocketResponse:
    ws = web.WebSocketResponse(heartbeat=25.0)
    await ws.prepare(request)
    CLIENTS.add(ws)
    if request.query.get("wallpaper") == "1":
        WP_CLIENTS.add(ws)
    try:
        saved = await asyncio.to_thread(_load_saved_config)
        if saved:
            await _send_ws(ws, {"type": "ophanim_saved_config", "config": saved})
        wp_st = await asyncio.to_thread(wp_mgr.get_wallpaper_status)
        await _send_ws(ws, {"type": "ophanim_wallpaper_status", **wp_st})
        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)
                except Exception:
                    continue
                if not isinstance(data, dict):
                    continue
                mtype = str(data.get("type") or "")
                if mtype == "ophanim_wallpaper_hello":
                    WP_CLIENTS.add(ws)
                    snap = wp_mgr.sample_desktop_pointer()
                    if snap:
                        await _send_ws(ws, snap)
                elif mtype == "ophanim_wallpaper_action":
                    res = await _exec_wallpaper(data)
                    await _send_ws(ws, res)
                elif mtype in ("ophanim_ack_completions", "ophanim_preview_completion"):
                    for peer in list(CLIENTS):
                        if peer is not ws and not peer.closed:
                            try:
                                await _send_ws(peer, data)
                            except Exception:
                                pass
                elif mtype == "ophanim_save_config" and isinstance(data.get("config"), dict):
                    await asyncio.to_thread(_save_config, data["config"])
    finally:
        WP_CLIENTS.discard(ws)
        CLIENTS.discard(ws)
    return ws


async def pointer_relay_loop() -> None:
    last_sig = None
    while not SHUTDOWN_EVENT.is_set():
        if not WP_CLIENTS:
            last_sig = None
            await asyncio.sleep(0.25)
            continue
        snap = wp_mgr.sample_desktop_pointer()
        if snap:
            wheel_val = float(snap.get("wheel") or 0.0)
            click_val = int(snap.get("click") or 0)
            sig = (snap.get("px"), snap.get("py"), snap.get("btn"), snap.get("desk"), snap.get("icon"))
            if wheel_val != 0.0 or click_val != 0 or sig != last_sig:
                last_sig = sig
                msg = json.dumps(snap, separators=(",", ":"))
                for ws in list(WP_CLIENTS):
                    if ws.closed:
                        WP_CLIENTS.discard(ws)
                        continue
                    try:
                        await ws.send_str(msg)
                    except Exception:
                        WP_CLIENTS.discard(ws)
        await asyncio.sleep(0.016)


def probe_existing(host: str, port: int) -> bool:
    try:
        req = urllib.request.Request(f"http://{host}:{port}/api/health", method="GET")
        with _DIRECT_OPENER.open(req, timeout=1.0) as resp:
            return resp.status == 200
    except Exception:
        return False


async def run_server(host: str, port: int) -> int:
    if (host or "").strip().lower() not in _TRUSTED_LOCAL_HOSTS:
        logger.error("Refusing non-loopback bind %r in Toy Edition.", host)
        return 2
    if await asyncio.to_thread(probe_existing, host, port):
        return 0
    app = web.Application(middlewares=[localhost_security_middleware])
    app.router.add_get("/", handle_index)
    app.router.add_get("/ophanim_sanctum.html", handle_index)
    app.router.add_get("/ophanim_toy_sanctum.html", handle_index)
    app.router.add_get("/favicon.ico", handle_logo_ico)
    app.router.add_get("/ophanim_logo.ico", handle_logo_ico)
    app.router.add_get("/api/health", handle_health)
    app.router.add_get("/api/wallpaper", handle_wallpaper_get)
    app.router.add_post("/api/wallpaper", handle_wallpaper_post)
    app.router.add_options("/api/wallpaper", handle_cors_options)
    app.router.add_post("/api/event", handle_event_post)
    app.router.add_options("/api/event", handle_cors_options)
    app.router.add_post("/api/shutdown", handle_shutdown)
    app.router.add_get("/ws", handle_ws)

    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    ptr_task = asyncio.create_task(pointer_relay_loop())
    logger.info("Ophanim Toy & Wallpaper Server listening on http://%s:%s", host, port)
    try:
        await SHUTDOWN_EVENT.wait()
    finally:
        ptr_task.cancel()
        await asyncio.gather(ptr_task, return_exceptions=True)
        await runner.cleanup()
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--host", default=HOST)
    p.add_argument("--port", type=int, default=PORT)
    a = p.parse_args()
    sys.exit(asyncio.run(run_server(a.host, a.port)))
