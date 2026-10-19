"""NeoPilot 执行引擎.

引擎不直接调设备能力——它只做四件事：把例程展开成带参数的步骤、维持游标、
接收执行回执、按验收规则判分。真正的 ability 调用由执行方发起，
这样同一份例程既能由 agent 跑，也能由人在任意端上照着跑。
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import catalog
from .store import Store

TZ = timezone(timedelta(hours=8))
WEEK_CN = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


# ── 时间与模板 ───────────────────────────────────────────────
def now() -> datetime:
    return datetime.now(TZ)


def template_context(extra: Optional[Dict] = None) -> Dict[str, str]:
    n = now()
    tmr = n + timedelta(days=1)
    week_start = n - timedelta(days=n.weekday())
    ctx = {
        "$today": n.strftime("%Y-%m-%d"),
        "$tomorrow": tmr.strftime("%Y-%m-%d"),
        "$today_0000": n.strftime("%Y-%m-%d 00:00:00"),
        "$today_2359": n.strftime("%Y-%m-%d 23:59:59"),
        "$tomorrow_0000": tmr.strftime("%Y-%m-%d 00:00:00"),
        "$tomorrow_2359": tmr.strftime("%Y-%m-%d 23:59:59"),
        "$now": n.strftime("%Y-%m-%d %H:%M:%S"),
        "$hour": str(n.hour),
        "$weekday": WEEK_CN[n.weekday()],
        "$week_start": week_start.strftime("%Y-%m-%d 00:00:00"),
        "$week_album": f"{week_start.strftime('%Y-W%W')} 周照片",
        "$city": "",
        "$loc_gcj": "",
        "$home_work_gcj": "",
    }
    if extra:
        ctx.update({k: v for k, v in extra.items() if v})
    return ctx


def resolve(value: Any, ctx: Dict[str, str]) -> Any:
    if isinstance(value, str):
        out = value
        for k in sorted(ctx, key=len, reverse=True):
            if k in out and ctx[k]:
                out = out.replace(k, ctx[k])
        return out
    if isinstance(value, dict):
        return {k: resolve(v, ctx) for k, v in value.items()}
    if isinstance(value, list):
        return [resolve(v, ctx) for v in value]
    return value


def unresolved(value: Any, ctx: Dict[str, str]) -> List[str]:
    """返回参数里仍然没被替换掉的模板变量，用来在起跑前拦住缺配置的例程。"""
    found: List[str] = []

    def walk(v):
        if isinstance(v, str):
            for k in ctx:
                if k in v and not ctx[k]:
                    found.append(k)
        elif isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)

    walk(value)
    return sorted(set(found))


# ── 运行生命周期 ─────────────────────────────────────────────
def new_run_id(routine_id: str) -> str:
    return f"{now().strftime('%Y%m%d-%H%M%S')}-{routine_id[:10]}-{uuid.uuid4().hex[:4]}"


def start_run(store: Store, routine: Dict, ctx_extra: Optional[Dict] = None,
              trigger: str = "manual") -> Dict:
    ctx = template_context(ctx_extra)
    steps = []
    for s in routine["steps"]:
        if not catalog.exists(s["cap"]):
            raise KeyError(f"例程 {routine['id']} 引用了未知能力: {s['cap']}")
        steps.append({
            "id": s["id"],
            "cap": s["cap"],
            "label": s.get("label", s["id"]),
            "must": s.get("must", True),
            "retry": s.get("retry", 0),
            "params": resolve(s.get("params", {}), ctx),
            "attempt": 0,
            "status": "pending",
            "started_at": None,
            "ended_at": None,
            "ms": None,
            "data": None,
            "error": None,
        })

    run = {
        "run_id": new_run_id(routine["id"]),
        "routine": routine["id"],
        "routine_name": routine.get("name", routine["id"]),
        "trigger": trigger,
        "started_at": now().strftime("%Y-%m-%dT%H:%M:%S%z"),
        "ended_at": None,
        "status": "running",
        "cursor": 0,
        "steps": steps,
        "verify": routine.get("verify", {"min_ok": 1, "must_all_ok": False}),
        "notes": [],
    }
    store.save_run(run)
    return run


def pending_steps(run: Dict) -> List[Dict]:
    return [s for s in run["steps"] if s["status"] in ("pending", "retry")]


def next_step(run: Dict) -> Optional[Dict]:
    for s in run["steps"]:
        if s["status"] in ("pending", "retry"):
            return s
    return None


def advance_cursor(run: Dict) -> None:
    for i, s in enumerate(run["steps"]):
        if s["status"] not in ("ok", "skipped"):
            run["cursor"] = i
            return
    run["cursor"] = len(run["steps"])


def report_step(store: Store, run: Dict, step_id: str, status: str,
                data: Any = None, error: Optional[str] = None,
                ms: Optional[int] = None) -> Dict:
    """回填一条步骤结果。status: ok / fail / skip。"""
    target = None
    for s in run["steps"]:
        if s["id"] == step_id:
            target = s
            break
    if target is None:
        raise KeyError(f"例程里没有这一步: {step_id}")

    target["attempt"] = int(target.get("attempt", 0)) + 1
    target["ended_at"] = now().strftime("%Y-%m-%dT%H:%M:%S%z")
    if target.get("started_at") is None:
        target["started_at"] = target["ended_at"]

    if status == "ok":
        target["status"] = "ok"
        target["data"] = data
        target["error"] = None
    elif status == "skip":
        target["status"] = "skipped"
        target["error"] = error or "skipped"
    else:
        if target["attempt"] <= target["retry"]:
            target["status"] = "retry"
        else:
            target["status"] = "fail"
        target["error"] = error or "unknown error"
    if ms is not None:
        target["ms"] = ms

    advance_cursor(run)
    if next_step(run) is None:
        evaluate(run)

    # 写操作自动留痕：只要这一步会改设备状态，不管成败都记一笔
    try:
        cap = catalog.get(target["cap"])
        if cap.kind in ("write", "navigate"):
            store.audit({
                "at": now().strftime("%Y-%m-%d %H:%M:%S"),
                "run_id": run["run_id"],
                "routine": run.get("routine"),
                "step": step_id,
                "method": cap.method,
                "name": cap.name,
                "kind": cap.kind,
                "risk": cap.risk,
                "params": target.get("params") or {},
                "status": status,
                "error": error,
            })
    except Exception:
        pass

    store.save_run(run)
    return run


def evaluate(run: Dict) -> Dict:
    """按 verify 规则判分：success / partial / failed。"""
    ok = [s for s in run["steps"] if s["status"] == "ok"]
    failed_must = [s for s in run["steps"] if s["must"] and s["status"] == "fail"]
    rule = run.get("verify", {}) or {}
    min_ok = rule.get("min_ok", 1)
    must_all_ok = rule.get("must_all_ok", False)

    fail_any = any(s["status"] == "fail" for s in run["steps"])

    if failed_must and must_all_ok:
        status = "failed"
    elif not ok:
        status = "failed"
    elif len(ok) < min_ok:
        status = "partial"
    elif fail_any:
        status = "partial"
    else:
        status = "success"

    run["status"] = status
    run["ended_at"] = now().strftime("%Y-%m-%dT%H:%M:%S%z")
    run["duration_ms"] = _duration_ms(run)
    return run


def _duration_ms(run: Dict) -> int:
    try:
        a = datetime.strptime(run["started_at"], "%Y-%m-%dT%H:%M:%S%z")
        b = datetime.strptime(run["ended_at"], "%Y-%m-%dT%H:%M:%S%z")
        return int((b - a).total_seconds() * 1000)
    except Exception:
        return 0


def cancel_run(store: Store, run: Dict, reason: str = "") -> Dict:
    for s in run["steps"]:
        if s["status"] in ("pending", "retry"):
            s["status"] = "skipped"
            s["error"] = "cancelled"
    run["status"] = "cancelled"
    run["ended_at"] = now().strftime("%Y-%m-%dT%H:%M:%S%z")
    if reason:
        run.setdefault("notes", []).append(reason)
    store.save_run(run)
    return run


# ── 健康度与统计 ─────────────────────────────────────────────
def routine_health(store: Store, routine_id: str, window: int = 20) -> Dict:
    runs = [r for r in store.runs(limit=200) if r.get("routine") == routine_id][:window]
    total = len(runs)
    ok = sum(1 for r in runs if r.get("status") == "success")
    partial = sum(1 for r in runs if r.get("status") == "partial")
    failed = sum(1 for r in runs if r.get("status") == "failed")
    rate = round(ok / total * 100) if total else None
    streak = 0
    for r in runs:
        if r.get("status") == "success":
            streak += 1
        else:
            break
    return {
        "runs": total, "success": ok, "partial": partial, "failed": failed,
        "rate": rate, "streak": streak, "last": runs[0] if runs else None,
    }


def overview(store: Store) -> Dict:
    routines = store.routines()
    runs = store.runs(limit=200)
    total = len(runs)
    ok = sum(1 for r in runs if r.get("status") == "success")
    step_total = sum(len(r.get("steps", [])) for r in runs)
    step_ok = sum(1 for r in runs for s in r.get("steps", []) if s.get("status") == "ok")
    return {
        "routines": len(routines),
        "enabled": sum(1 for r in routines if r.get("enabled")),
        "scheduled": sum(1 for r in routines if r.get("schedule")),
        "runs": total,
        "success_rate": round(ok / total * 100) if total else None,
        "step_total": step_total,
        "step_ok": step_ok,
        "step_rate": round(step_ok / step_total * 100) if step_total else None,
        "caps": catalog.stats(),
        "usage": store.usage(),
    }


# ── 下一次该跑什么（表调度模拟）──────────────────────────────
def _cron_field_match(field: str, value: int, lo: int, hi: int) -> bool:
    if field == "*":
        return True
    for part in field.split(","):
        if part.startswith("*/"):
            try:
                stepn = int(part[2:])
                if stepn and (value - lo) % stepn == 0:
                    return True
            except ValueError:
                continue
        elif "-" in part:
            try:
                a, b = part.split("-")
                if int(a) <= value <= int(b):
                    return True
            except ValueError:
                continue
        else:
            try:
                if int(part) == value:
                    return True
            except ValueError:
                continue
    return False


def cron_matches(expr: str, dt: datetime) -> bool:
    parts = expr.split()
    if len(parts) != 5:
        return False
    m, h, dom, mon, dow = parts
    cron_dow = (dt.weekday() + 1) % 7  # 0 = 周日
    return (
        _cron_field_match(m, dt.minute, 0, 59)
        and _cron_field_match(h, dt.hour, 0, 23)
        and _cron_field_match(dom, dt.day, 1, 31)
        and _cron_field_match(mon, dt.month, 1, 12)
        and (_cron_field_match(dow, cron_dow, 0, 6) or _cron_field_match(dow, dt.weekday() + 1, 1, 7))
    )


def next_occurrence(expr: str, frm: Optional[datetime] = None, horizon_days: int = 8) -> Optional[datetime]:
    if not expr:
        return None
    cur = (frm or now()).replace(second=0, microsecond=0) + timedelta(minutes=1)
    for _ in range(horizon_days * 1440):
        if cron_matches(expr, cur):
            return cur
        cur += timedelta(minutes=1)
    return None


def _last_started_at(store: Store, routine_id: str):
    last = store.latest_run(routine_id)
    if not last:
        return None
    try:
        return datetime.strptime(last["started_at"], "%Y-%m-%dT%H:%M:%S%z")
    except Exception:
        return None


def work_queue(store: Store) -> List[Dict]:
    """所有未跑完的运行里，还没执行的步骤。

    cron 只负责把例程「起跑」，真正的能力调用由执行方按这个队列逐条做。
    这样引擎的状态机（重试、断点、验收）才真正生效，而不是每次让 agent
    重新理解一遍任务描述。
    """
    out: List[Dict] = []
    for run in store.runs(limit=100):
        if run.get("status") != "running":
            continue
        step = next_step(run)
        if not step:
            continue
        out.append({
            "run_id": run["run_id"],
            "routine": run.get("routine"),
            "routine_name": run.get("routine_name"),
            "step": step["id"],
            "cap": step["cap"],
            "label": step["label"],
            "params": step["params"],
            "attempt": step.get("attempt", 0),
            "retry": step.get("retry", 0),
        })
    return out


def due_routines(store: Store, window_min: int = 15, frm: Optional[datetime] = None) -> List[Dict]:
    """回溯 window_min 分钟，找出已经到点、且这一轮还没跑过的例程。

    判定「这一轮跑过没有」用的是最近一次 run 的开始时间：
    只要它在本次触发点之后，就算已经跑过，不再重复触发。
    """
    base = frm or now()
    out: List[Dict] = []
    for r in store.routines():
        if not r.get("enabled") or not r.get("schedule"):
            continue
        hit = None
        for k in range(0, window_min + 1):
            t = (base - timedelta(minutes=k)).replace(second=0, microsecond=0)
            if cron_matches(r["schedule"], t):
                hit = t
                break
        if hit is None:
            continue
        last = _last_started_at(store, r["id"])
        if last is not None and last >= hit - timedelta(minutes=1):
            continue
        ctx = template_context()
        missing = sorted({m for st in r.get("steps", [])
                          for m in unresolved(st.get("params", {}), ctx)})
        out.append({
            "id": r["id"],
            "name": r["name"],
            "hit_at": hit.strftime("%Y-%m-%d %H:%M"),
            "lag_min": int((base - hit).total_seconds() // 60),
            "blocked": bool(missing),
            "missing": missing,
        })
    out.sort(key=lambda x: x["hit_at"])
    return out


def tick(store: Store, window_min: int = 15, skip_blocked: bool = True) -> List[Dict]:
    """把到点且未跑的例程真正启动起来，返回本轮的启动清单。"""
    started: List[Dict] = []
    for d in due_routines(store, window_min=window_min):
        if d["blocked"] and skip_blocked:
            started.append({**d, "started": False, "reason": "缺配置 " + ",".join(d["missing"])})
            continue
        r = store.load_routine(d["id"])
        run = start_run(store, r, trigger=f"schedule:{d['hit_at']}")
        started.append({**d, "started": True, "run_id": run["run_id"]})
    return started


def crontab_lines(store: Store, python_bin: str = "python3", entry: str = "neopilot.py") -> List[str]:
    """输出可直接粘进系统 crontab 的行：每分钟问一次引擎有没有到点。"""
    lines = ["# NeoPilot 调度入口：每 5 分钟问一次引擎「有没有到点的例程」",
             f"*/5 * * * * cd {Path.cwd()} && {python_bin} {entry} tick --window 6 >> .neopilot/tick.log 2>&1"]
    return lines


def upcoming(store: Store, limit: int = 6) -> List[Dict]:
    items = []
    for r in store.routines():
        if not r.get("enabled") or not r.get("schedule"):
            continue
        nxt = next_occurrence(r["schedule"])
        if nxt:
            ctx = template_context()
            missing = sorted({m for st in r.get("steps", [])
                              for m in unresolved(st.get("params", {}), ctx)})
            items.append({
                "id": r["id"], "name": r["name"], "at": nxt.strftime("%Y-%m-%d %H:%M"),
                "in_hours": round((nxt - now()).total_seconds() / 3600, 1),
                "blocked": bool(missing), "missing": missing,
            })
    items.sort(key=lambda x: x["at"])
    return items[:limit]
