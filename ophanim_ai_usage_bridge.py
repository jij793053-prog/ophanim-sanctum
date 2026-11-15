#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ophanim_ai_usage_bridge.py
Thread-safe bridge porting 100% of the local `AI Usage` (`simple-token-view`)
telemetry, quota pools, daily history, DeepSeek ledger, and per-turn session
breakdown into Ophanim Sanctum — storing all runtime caches/SQLite strictly in
an isolated local cache directory (zero lock contention).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
import importlib.util
import json
import logging
import os
from pathlib import Path
import shutil
import sqlite3
import threading
import time
from typing import Any

logger = logging.getLogger("ophanim_ai_usage")

PROJECT_DIR = Path(__file__).resolve().parent
STV_DIR = Path(
    os.environ.get("OPHANIM_STV_DIR", str(Path.home() / ".gemini/antigravity/scratch/simple-token-view"))
)
STV_QUOTA_PY = STV_DIR / "quota.py"
STV_QUOTA_DB = STV_DIR / "quota.db"
STV_DIRECT_CACHE = STV_DIR / "direct-sessions-cache-v12.json"

_PARENT_CACHE_CAND = PROJECT_DIR.parent.parent / "cache"
OPHANIM_CACHE_DIR = Path(
    os.environ.get(
        "OPHANIM_CACHE_DIR",
        str(_PARENT_CACHE_CAND if _PARENT_CACHE_CAND.is_dir() else (PROJECT_DIR / ".ophanim_cache")),
    )
)
OPHANIM_USAGE_DB = OPHANIM_CACHE_DIR / "ophanim_ai_usage_quota.db"
OPHANIM_DIRECT_CACHE = OPHANIM_CACHE_DIR / "ophanim_ai_usage_sessions_cache.json"

DATA_FILE = Path(os.environ.get("APPDATA", "")) / "Token Monitor" / "daily-history-archive.json"

TOOL_NAMES = {
    "antigravity": "Antigravity",
    "dsh": "dsh（DeepSeek 工具）",
    "claude": "Claude Code",
    "codex": "Codex",
    "cursor": "Cursor",
}
MODEL_NAMES = {
    "deepseek-v4-flash-vision-exp": "DeepSeek V4 Flash 识图版",
    "deepseek-v4-flash": "DeepSeek V4 Flash",
    "deepseek-v4-pro": "DeepSeek V4 Pro",
    "deepseek-flash": "DeepSeek Flash",
    "claude-opus-5-5": "Claude Opus 5.5",
    "claude-sonnet-5-5": "Claude Sonnet 5.5",
    "gemini-4-argon": "Gemini 4 Argon",
    "gemini-4-carbon": "Gemini 4 Carbon",
    "gemini-3.8-flash": "Gemini 3.8 Flash",
    "gemini-3.8-flash-n": "Gemini 3.8 Flash",
    "gpt-oss-120b": "GPT-OSS 120B",
    "unknown": "其他",
}

_INIT_LOCK = threading.Lock()
_QUERY_LOCK = threading.Lock()
_RECORDER: Any = None
_STV_MOD: Any = None
_BUNDLE_CACHE: dict[str, Any] = {"ts": 0.0, "sync_ts": 0.0, "payload": None}


def _seed_f_drive_stores() -> None:
    """Seed isolated cache DB & session cache once in read-only mode from simple-token-view."""
    OPHANIM_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    if not OPHANIM_DIRECT_CACHE.is_file() and STV_DIRECT_CACHE.is_file():
        try:
            shutil.copyfile(STV_DIRECT_CACHE, OPHANIM_DIRECT_CACHE)
        except Exception as exc:
            logger.debug("Seed direct cache warning: %s", exc)

    if not OPHANIM_USAGE_DB.is_file() and STV_QUOTA_DB.is_file():
        try:
            src_con = sqlite3.connect(f"file:{STV_QUOTA_DB.as_posix()}?mode=ro", uri=True, timeout=3.0)
            dst_con = sqlite3.connect(str(OPHANIM_USAGE_DB), timeout=5.0)
            with dst_con:
                src_con.backup(dst_con)
            dst_con.close()
            src_con.close()
        except Exception as exc:
            logger.debug("Seed quota db backup warning: %s", exc)


def _ensure_recorder() -> tuple[Any, Any]:
    global _RECORDER, _STV_MOD
    if _RECORDER is not None and _STV_MOD is not None:
        return _STV_MOD, _RECORDER

    with _INIT_LOCK:
        if _RECORDER is not None and _STV_MOD is not None:
            return _STV_MOD, _RECORDER

        if not STV_QUOTA_PY.is_file():
            raise RuntimeError(f"未找到本地 AI Usage 模块: {STV_QUOTA_PY}")

        _seed_f_drive_stores()

        spec = importlib.util.spec_from_file_location("ophanim_stv_quota", str(STV_QUOTA_PY))
        if spec is None or spec.loader is None:
            raise RuntimeError("无法加载 quota.py 模块规范")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        # Guard subprocess calls inside quota.py against GBK byte decode errors on Chinese Windows
        if hasattr(mod, "subprocess"):
            import subprocess as _real_sp
            _orig_run = _real_sp.run

            class _SafeSubprocessProxy:
                def __getattr__(self, name: str) -> Any:
                    return getattr(_real_sp, name)

                @staticmethod
                def run(*args: Any, **kwargs: Any) -> Any:
                    if (kwargs.get("text") or kwargs.get("encoding")) and "errors" not in kwargs:
                        kwargs["errors"] = "replace"
                    return _orig_run(*args, **kwargs)

            mod.subprocess = _SafeSubprocessProxy()

        # Redirect all cache/db writes strictly to OPHANIM_CACHE_DIR
        mod.DIRECT_CACHE_FILE = OPHANIM_DIRECT_CACHE
        if OPHANIM_DIRECT_CACHE.is_file():
            try:
                loaded_dc = json.loads(OPHANIM_DIRECT_CACHE.read_text(encoding="utf-8", errors="replace"))
                if isinstance(loaded_dc, dict) and len(loaded_dc) >= len(getattr(mod, "_direct_cache", {})):
                    mod._direct_cache.clear()
                    mod._direct_cache.update(loaded_dc)
            except Exception:
                pass

        rec = mod.QuotaRecorder(OPHANIM_USAGE_DB)
        rec.start()
        _STV_MOD = mod
        _RECORDER = rec
        return _STV_MOD, _RECORDER


def _load_days(rec: Any, all_turns: list[dict[str, Any]] | None = None) -> tuple[dict[str, Any], float]:
    days: dict[str, Any] = {}
    latest_mtime = 0.0
    if DATA_FILE.is_file():
        try:
            latest_mtime = DATA_FILE.stat().st_mtime
            raw = json.loads(DATA_FILE.read_text(encoding="utf-8", errors="replace"))
            days = {k: json.loads(json.dumps(v)) for k, v in (raw.get("days") or {}).items()}
            for d, v in (raw.get("liveDays") or {}).items():
                if d not in days:
                    days[d] = json.loads(json.dumps(v))
        except Exception:
            pass

    if all_turns is None:
        _, all_turns = rec.load_all_merged_sessions()

    live_by_day: dict[str, dict[tuple[str, str], dict[str, Any]]] = {}
    day_spans: dict[str, int] = {}
    for t in (all_turns or []):
        d = t.get("day")
        if not d:
            continue
        ts = float(t.get("last_ts") or t.get("first_ts") or 0.0)
        if ts > latest_mtime:
            latest_mtime = ts
        client = str(t.get("client") or "other")
        model = str(t.get("model") or "unknown")
        ob = live_by_day.setdefault(d, {}).setdefault(
            (client, model),
            {
                "client": client,
                "modelId": model,
                "tokens": 0,
                "cacheReadTokens": 0,
                "outputTokens": 0,
                "messages": 0,
                "cost": 0.0,
            },
        )
        ob["tokens"] += int(t.get("tokens") or 0)
        ob["cacheReadTokens"] += int(t.get("cache") or 0)
        ob["outputTokens"] += int(t.get("output") or 0)
        ob["messages"] += max(1, int(t.get("steps") or 1))
        ob["cost"] += float(t.get("cost") or 0.0)
        span = max(
            30000,
            min(1800000, int((float(t.get("last_ts") or 0) - float(t.get("first_ts") or 0)) * 1000) or 60000),
        )
        day_spans[d] = day_spans.get(d, 0) + span

    for d, cmap in live_by_day.items():
        day_obj = days.setdefault(d, {"activeTimeMs": 0, "observations": {}})
        obs = day_obj.setdefault("observations", {})
        if day_obj.get("activeTimeMs", 0) < day_spans.get(d, 0):
            day_obj["activeTimeMs"] = max(day_obj.get("activeTimeMs", 0), day_spans.get(d, 0))
        for (client, model), live_ob in cmap.items():
            k = json.dumps([client, model], separators=(",", ":"))
            cur = obs.get(k)
            if not cur:
                obs[k] = live_ob
            elif live_ob["tokens"] > cur.get("tokens", 0):
                cur["tokens"] = max(cur.get("tokens", 0), live_ob["tokens"])
                cur["cacheReadTokens"] = max(cur.get("cacheReadTokens", 0), live_ob["cacheReadTokens"])
                cur["outputTokens"] = max(cur.get("outputTokens", 0), live_ob["outputTokens"])
                cur["messages"] = max(cur.get("messages", 0), live_ob["messages"])
                cur["cost"] = max(cur.get("cost", 0.0), live_ob["cost"])

    return days, (latest_mtime or time.time())


def _summarize(days: dict[str, Any], start: date, end: date) -> dict[str, Any]:
    s: dict[str, Any] = dict(total=0, cache=0, output=0, msgs=0, active_ms=0, tools={}, models={})
    for d, v in days.items():
        try:
            dd = datetime.strptime(d, "%Y-%m-%d").date()
        except Exception:
            continue
        if not (start <= dd <= end):
            continue
        s["active_ms"] += int(v.get("activeTimeMs") or 0)
        for ob in (v.get("observations") or {}).values():
            t = int(ob.get("tokens") or 0)
            if t <= 0:
                continue
            s["total"] += t
            s["cache"] += int(ob.get("cacheReadTokens") or 0)
            s["output"] += int(ob.get("outputTokens") or 0)
            s["msgs"] += int(ob.get("messages") or 0)
            c_key = str(ob.get("client") or "")
            m_key = str(ob.get("modelId") or "")
            tool = TOOL_NAMES.get(c_key, c_key or "其他")
            model = MODEL_NAMES.get(m_key, m_key or "其他")
            s["tools"][tool] = s["tools"].get(tool, 0) + t
            s["models"][model] = s["models"].get(model, 0) + t
    return s


def _day_total(days: dict[str, Any], d: date) -> int:
    v = days.get(d.isoformat())
    return sum(int(o.get("tokens") or 0) for o in (v.get("observations") or {}).values()) if v else 0


def _sum_quota_days(q_by_day: dict[str, Any], start_d: str, end_d: str) -> dict[str, Any]:
    res: dict[str, Any] = {}
    for d, grps in q_by_day.items():
        if start_d <= d <= end_d:
            for g, v in grps.items():
                dst = res.setdefault(
                    g,
                    {"p5": 0.0, "pw": 0.0, "tokens": 0, "turns": 0, "steps": 0, "cost": 0.0, "cache": 0, "input": 0},
                )
                dst["p5"] += float(v.get("p5") or 0.0)
                dst["pw"] += float(v.get("pw") or 0.0)
                dst["tokens"] += int(v.get("tokens") or 0)
                dst["turns"] += int(v.get("turns") or 0)
                dst["steps"] += int(v.get("steps") or 0)
                dst["cost"] += float(v.get("cost") or 0.0)
                dst["cache"] += int(v.get("cache") or 0)
                dst["input"] += int(v.get("input") or 0)
    return res


def _sum_sess_quota(sess_by_day: dict[str, Any], start_d: str, end_d: str) -> dict[Any, dict[str, Any]]:
    res: dict[Any, dict[str, Any]] = {}
    for d, smap in sess_by_day.items():
        if start_d <= d <= end_d:
            for k, v in smap.items():
                dst = res.setdefault(k, {"p5": 0.0, "pw": 0.0, "n": 0})
                dst["p5"] += float(v.get("p5") or 0.0)
                dst["pw"] += float(v.get("pw") or 0.0)
                dst["n"] += int(v.get("n") or 0)
    return res


def _turns_to_period(mod: Any, tlist: list[dict[str, Any]], title: str, proj: str) -> dict[str, Any]:
    models: dict[str, int] = {}
    accounts: list[str] = []
    seen_acc: set[str] = set()
    tok = cac = outp = inp = steps = 0
    cost = 0.0
    for t in tlist:
        tk = int(t.get("tokens") or 0)
        tok += tk
        cac += int(t.get("cache") or 0)
        outp += int(t.get("output") or 0)
        inp += int(t.get("input") or 0)
        steps += max(1, int(t.get("steps") or 1))
        cost += float(t.get("cost") or 0.0)
        m = str(t.get("model") or "unknown")
        models[m] = models.get(m, 0) + tk
        acc = str(t.get("account") or "")
        tier = str(t.get("tier") or "")
        if acc and acc not in seen_acc:
            seen_acc.add(acc)
            accounts.append(f"{acc} ({tier})" if tier else acc)
    fts = min((float(t.get("first_ts") or t.get("last_ts") or 0.0) for t in tlist), default=0.0)
    lts = max((float(t.get("last_ts") or t.get("first_ts") or 0.0) for t in tlist), default=0.0)
    return {
        "title": title,
        "projectLabel": proj,
        "totalTokens": tok,
        "messageCount": steps,
        "cacheReadTokens": cac,
        "outputTokens": outp,
        "inputTokens": inp,
        "cacheWriteTokens": 0,
        "costUsd": cost,
        "models": models,
        "accounts": accounts,
        "startedAt": mod._ts_iso(fts),
        "lastUsedAt": mod._ts_iso(lts),
    }


def _build_sessions_payload(mod: Any, rec: Any, merged_sessions: dict[Any, Any]) -> dict[str, Any]:
    if not merged_sessions:
        return {"error": "还没有对话记录。"}

    today_dt = date.today()
    today = today_dt.isoformat()
    yday = (today_dt - timedelta(days=1)).isoformat()
    w_start = (today_dt - timedelta(days=6)).isoformat()
    month = today[:7]
    m_start = f"{month}-01"

    q_by_day, sess_q_by_day, q_first_day = rec.daily_summary()
    totals_all = rec.totals()
    q_sess_periods = {
        "today": _sum_sess_quota(sess_q_by_day, today, today),
        "yesterday": _sum_sess_quota(sess_q_by_day, yday, yday),
        "week": _sum_sess_quota(sess_q_by_day, w_start, today),
        "month": _sum_sess_quota(sess_q_by_day, m_start, today),
        "all": totals_all,
    }

    out: dict[str, Any] = {"today": [], "yesterday": [], "week": [], "month": [], "all": [], "by_day": {}}

    def make_item(client: str, sid: str, p: dict[str, Any], turns_cnt: int, q_entry: dict[str, Any] | None) -> dict[str, Any] | None:
        if not p or not p.get("totalTokens"):
            return None
        models = p.get("models") or {}
        top = max(models, key=models.get) if models else "unknown"
        cache = int(p.get("cacheReadTokens") or 0)
        fresh = int(p.get("inputTokens") or 0) + int(p.get("cacheWriteTokens") or 0)
        msgs = max(1, int(p.get("messageCount") or 0))
        return {
            "id": f"{client}:{sid}",
            "title": (p.get("title") or "").strip() or "未命名对话",
            "tool": TOOL_NAMES.get(client, client),
            "model": MODEL_NAMES.get(top, top),
            "project": p.get("projectLabel") or "",
            "total": int(p.get("totalTokens") or 0),
            "msgs": msgs,
            "turns": turns_cnt,
            "cache": cache,
            "output": int(p.get("outputTokens") or 0),
            "input": fresh,
            "hit": (cache / (cache + fresh)) if (cache + fresh) > 0 else None,
            "cost": float(p.get("costUsd") or 0.0),
            "start": p.get("startedAt") or "",
            "last": p.get("lastUsedAt") or "",
            "q5": q_entry["p5"] if q_entry else None,
            "qw": q_entry["pw"] if q_entry else None,
            "accounts": p.get("accounts") or [],
        }

    for (client, sid), sinfo in merged_sessions.items():
        turns = sinfo.get("turns") or []
        if not turns:
            continue
        title = sinfo.get("title") or "未命名对话"
        proj = sinfo.get("project") or ""
        by_d: dict[str, list[dict[str, Any]]] = {}
        for t in turns:
            by_d.setdefault(t["day"], []).append(t)

        for d, d_turns in by_d.items():
            sl = _turns_to_period(mod, d_turns, title, proj)
            q_d = sess_q_by_day.get(d, {}).get((client, sid))
            item = make_item(client, sid, sl, len(d_turns), q_d)
            if item:
                out["by_day"].setdefault(d, []).append(item)

        if today in by_d:
            sl = _turns_to_period(mod, by_d[today], title, proj)
            item = make_item(client, sid, sl, len(by_d[today]), q_sess_periods["today"].get((client, sid)))
            if item:
                out["today"].append(item)
        if yday in by_d:
            sl = _turns_to_period(mod, by_d[yday], title, proj)
            item = make_item(client, sid, sl, len(by_d[yday]), q_sess_periods["yesterday"].get((client, sid)))
            if item:
                out["yesterday"].append(item)

        w_turns = [t for d, dt in by_d.items() if w_start <= d <= today for t in dt]
        if w_turns:
            sl = _turns_to_period(mod, w_turns, title, proj)
            item = make_item(client, sid, sl, len(w_turns), q_sess_periods["week"].get((client, sid)))
            if item:
                out["week"].append(item)

        m_turns = [t for d, dt in by_d.items() if d.startswith(month) for t in dt]
        if m_turns:
            sl = _turns_to_period(mod, m_turns, title, proj)
            item = make_item(client, sid, sl, len(m_turns), q_sess_periods["month"].get((client, sid)))
            if item:
                out["month"].append(item)

        sl_all = _turns_to_period(mod, turns, title, proj)
        if sinfo.get("startedAt"):
            sl_all["startedAt"] = sinfo["startedAt"]
        if sinfo.get("lastUsedAt"):
            sl_all["lastUsedAt"] = sinfo["lastUsedAt"]
        item = make_item(client, sid, sl_all, len(turns), q_sess_periods["all"].get((client, sid)))
        if item:
            out["all"].append(item)

    out["q_by_day"] = q_by_day
    out["q_first_day"] = q_first_day
    out["q_periods"] = {
        "today": _sum_quota_days(q_by_day, today, today),
        "yesterday": _sum_quota_days(q_by_day, yday, yday),
        "week": _sum_quota_days(q_by_day, w_start, today),
        "month": _sum_quota_days(q_by_day, m_start, today),
        "all": _sum_quota_days(q_by_day, "0000-00-00", "9999-99-99"),
    }
    return out


def get_ai_usage_bundle(force: bool = False) -> dict[str, Any]:
    """Return `{ ok, overview, sessions }` matching AI Usage's exact calculations."""
    now_m = time.monotonic()
    if not force and _BUNDLE_CACHE["payload"] is not None and (now_m - float(_BUNDLE_CACHE["ts"])) < 2.6:
        return _BUNDLE_CACHE["payload"]

    with _QUERY_LOCK:
        now_m = time.monotonic()
        if not force and _BUNDLE_CACHE["payload"] is not None and (now_m - float(_BUNDLE_CACHE["ts"])) < 2.6:
            return _BUNDLE_CACHE["payload"]

        try:
            mod, rec = _ensure_recorder()
            if force or (now_m - float(_BUNDLE_CACHE["sync_ts"])) >= 8.0:
                rec.sync_history()
                _BUNDLE_CACHE["sync_ts"] = now_m
            merged_sessions, all_turns = rec.load_all_merged_sessions()
            days, latest_mtime = _load_days(rec, all_turns)
        except Exception as exc:
            logger.warning("get_ai_usage_bundle error: %s", exc)
            return {"ok": False, "error": f"读取 AI Usage 数据失败: {exc}"}

        if not days:
            return {"ok": False, "error": "暂无本机 AI 用量记录"}

        today = date.today()
        yday = today - timedelta(days=1)
        w_start = today - timedelta(days=6)
        m_start = today.replace(day=1)
        all_start = min((datetime.strptime(d, "%Y-%m-%d").date() for d in days), default=today)
        t_iso, y_iso, w_iso, m_iso = today.isoformat(), yday.isoformat(), w_start.isoformat(), m_start.isoformat()

        periods = {
            "today": _summarize(days, today, today),
            "yesterday": _summarize(days, yday, yday),
            "week": _summarize(days, w_start, today),
            "month": _summarize(days, m_start, today),
            "all": _summarize(days, all_start, today),
        }
        by_day = {}
        daily = {}
        for d in days:
            try:
                dd = datetime.strptime(d, "%Y-%m-%d").date()
            except Exception:
                continue
            by_day[d] = _summarize(days, dd, dd)
            daily[d] = _day_total(days, dd)

        updated = datetime.fromtimestamp(latest_mtime).strftime("%H:%M")
        sessions_payload = _build_sessions_payload(mod, rec, merged_sessions)

        current = None
        if not sessions_payload.get("error") and sessions_payload.get("all"):
            current = dict(max(sessions_payload["all"], key=lambda s: s.get("last") or ""))
            c_part, sid_part = current["id"].split(":", 1)
            rec_turns = rec.turns_for(c_part, sid_part, limit=1)
            current["now_turn"] = rec_turns[0] if rec_turns else None

        q_view = rec.quota_view()
        q_by_day, _, q_first_day = rec.daily_summary()
        q_view["by_day"] = q_by_day
        q_view["first_day"] = q_first_day
        q_view["periods"] = {
            "today": _sum_quota_days(q_by_day, t_iso, t_iso),
            "yesterday": _sum_quota_days(q_by_day, y_iso, y_iso),
            "week": _sum_quota_days(q_by_day, w_iso, t_iso),
            "month": _sum_quota_days(q_by_day, m_iso, t_iso),
            "all": _sum_quota_days(q_by_day, "0000-00-00", "9999-99-99"),
        }

        overview = {
            "periods": periods,
            "by_day": by_day,
            "daily": daily,
            "today": t_iso,
            "updated": updated,
            "current": current,
            "quota": q_view,
        }
        payload = {
            "type": "ophanim_ai_usage_data",
            "ok": True,
            "overview": overview,
            "sessions": sessions_payload,
        }
        _BUNDLE_CACHE["ts"] = time.monotonic()
        _BUNDLE_CACHE["payload"] = payload
        return payload


def get_ai_usage_turns(sess_id: str) -> dict[str, Any]:
    raw_id = str(sess_id or "").strip()
    if ":" not in raw_id:
        return {"type": "ophanim_ai_usage_turns", "ok": False, "id": raw_id, "turns": []}
    client, sid = raw_id.split(":", 1)
    try:
        _, rec = _ensure_recorder()
        turns = rec.turns_for(client, sid, limit=200)
        return {"type": "ophanim_ai_usage_turns", "ok": True, "id": raw_id, "turns": turns}
    except Exception as exc:
        return {"type": "ophanim_ai_usage_turns", "ok": False, "id": raw_id, "error": str(exc), "turns": []}
