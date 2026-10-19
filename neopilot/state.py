"""统一数据契约.

三类来源（云端存储 / 本机采集 / 构建内联）都必须长成同一个形状，
前端只认这一种：

    {
      "meta":   {generated_at, source, version},
      "today":  {city, address, battery, now, daily, tips, events, headline},
      "engine": {kpi, upcoming, runs, routines},
      "caps":   [{name, app, desc, method, kind, risk, category}]
    }

以前三种来源字段名各写各的，前端要写三套兜底，加一个字段改三处。
现在只在这一层做归一，前端只写一次。
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Dict, List, Optional

from . import catalog, engine, probe as probe_mod
from .store import Store

VERSION = "2.0"

EMPTY_TODAY: Dict[str, Any] = {
    "city": "", "address": "", "battery": "",
    "now": {"temp": "", "text": "", "humidity": "", "aqi": "", "quality": ""},
    "daily": {"low": "", "high": "", "pop": "", "day": "", "sunrise": "", "sunset": ""},
    "tips": [], "events": [], "headline": "",
}


def _norm_today(raw: Optional[Dict]) -> Dict[str, Any]:
    """把历史格式的 today 快照归一成新契约。"""
    out = {k: (v.copy() if isinstance(v, (dict, list)) else v) for k, v in EMPTY_TODAY.items()}
    if not raw:
        return out
    out["city"] = raw.get("city", "")
    out["address"] = raw.get("address", "")
    out["battery"] = raw.get("battery", "")
    out["tips"] = raw.get("tips", []) or []
    out["events"] = raw.get("events", []) or []
    out["headline"] = raw.get("headline", "")

    now = raw.get("now") or {}
    if isinstance(now, dict):
        for k in ("temp", "text", "humidity", "aqi", "quality"):
            if now.get(k):
                out["now"][k] = now[k]

    # 兼容两种命名：daily 与 today
    day = raw.get("daily") or raw.get("today") or {}
    if isinstance(day, dict):
        for k in ("low", "high", "pop", "day", "sunrise", "sunset"):
            if day.get(k) not in (None, ""):
                out["daily"][k] = day[k]
    return out


def _friendly_at(at: str) -> str:
    """把 2026-10-19 22:00 变成「22:00 / 明天 22:00 / 10-21 08:00」。"""
    try:
        d, _, hm = at.partition(" ")
        n = engine.now()
        if d == n.strftime("%Y-%m-%d"):
            return hm
        if d == (n + timedelta(days=1)).strftime("%Y-%m-%d"):
            return "明天 " + hm
        return at[5:]
    except Exception:
        return at


def _routines(store: Store) -> List[Dict]:
    out = []
    for r in store.routines():
        h = engine.routine_health(store, r["id"])
        out.append({
            "id": r["id"],
            "name": r.get("name", r["id"]),
            "desc": r.get("desc", ""),
            "enabled": bool(r.get("enabled")),
            "schedule": r.get("schedule") or "",
            "schedule_text": r.get("schedule_text") or "手动",
            "steps": [s.get("label") or s["id"] for s in r.get("steps", [])],
            "runs": h["runs"],
            "rate": h["rate"],
        })
    return out


def build(store: Store, source: str = "cloud") -> Dict[str, Any]:
    ov = engine.overview(store)
    ups = engine.upcoming(store, limit=6)
    runs = store.runs(limit=5)

    return {
        "meta": {
            "generated_at": engine.now().strftime("%Y-%m-%d %H:%M"),
            "source": source,
            "version": VERSION,
            # 合并策略：today 归本机采集（本地值覆盖云端），
            # engine 归云端（本地拿不到例程运行态），caps 为静态目录+实测状态。
            "merge_policy": {"today": "local-first", "engine": "cloud-only"},
        },
        "today": _norm_today(store.load_snapshot("today")),
        "engine": {
            "kpi": {
                "routines": ov["routines"],
                "enabled": ov["enabled"],
                "rate": (str(ov["success_rate"]) + "%") if ov["success_rate"] is not None else "",
                "caps": catalog.stats()["total"],
            },
            "upcoming": [
                {"name": u["name"], "at": _friendly_at(u["at"]), "in_hours": u["in_hours"],
                 "blocked": u.get("blocked", False)}
                for u in ups
            ],
            "runs": [
                {"routine": r.get("routine_name"), "status": r.get("status"),
                 "started": (r.get("started_at") or "")[:19].replace("T", " "),
                 "ok": sum(1 for s in r.get("steps", []) if s.get("status") == "ok"),
                 "total": len(r.get("steps", []))}
                for r in runs
            ],
            "routines": _routines(store),
        },
        "caps": [
            {"name": c.name, "app": c.app, "desc": c.desc, "method": c.method,
             "kind": c.kind, "risk": c.risk, "category": c.category,
             "status": probe_mod.status_of(store, c.method, c.kind)}
            for c in catalog.all_caps()
        ],
    }
