"""能力探测：确认某一个 method 在这台设备上此刻是否真的可用。

目录里的 42 项是「探测结果汇总」，不等于「现在一定能调通」——
系统版本、权限、账号状态都会让某项失效。这里负责把静态清单变成实测状态。

只探测只读能力：write / navigate 类一旦调用会改设备状态或跳走页面，
不适合自动巡检，状态标记为 untested，由人工按需确认。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from . import catalog
from .store import Store

TZ = timezone(timedelta(hours=8))
PROBE_KINDS = ("read",)
DEFAULT_MAX_AGE_DAYS = 7


def _now() -> datetime:
    return datetime.now(TZ)


def _age_days(iso: str) -> float:
    try:
        t = datetime.strptime(iso, "%Y-%m-%d %H:%M:%S").replace(tzinfo=TZ)
        return (_now() - t).total_seconds() / 86400
    except Exception:
        return 9e9


def pending(store: Store, max_age_days: int = DEFAULT_MAX_AGE_DAYS) -> List[Dict]:
    """列出需要探测的能力：只读 + 未测过或结果过期。"""
    data = store.load_probe()
    out: List[Dict] = []
    for c in catalog.all_caps():
        if c.kind not in PROBE_KINDS:
            continue
        rec = data.get(c.method)
        if rec and _age_days(rec.get("at", "")) < max_age_days:
            continue
        out.append({"method": c.method, "name": c.name, "app": c.app,
                    "params": [], "last": rec})
    return out


def report(store: Store, method: str, status: str, note: str = "") -> Dict:
    if not catalog.exists(method):
        raise KeyError(f"未知能力: {method}")
    data = store.load_probe()
    data[method] = {"status": status, "at": _now().strftime("%Y-%m-%d %H:%M:%S"),
                    "note": note}
    store.save_probe(data)
    return data[method]


def summary(store: Store) -> Dict[str, Any]:
    data = store.load_probe()
    counts = {"ok": 0, "fail": 0, "skip": 0, "untested": 0}
    for c in catalog.all_caps():
        if c.kind not in PROBE_KINDS:
            counts["untested"] += 1
            continue
        rec = data.get(c.method)
        if not rec:
            counts["untested"] += 1
        else:
            counts[rec.get("status", "untested")] = counts.get(rec.get("status", "untested"), 0) + 1
    return counts


def status_of(store: Store, method: str, kind: str) -> str:
    """给前端用的单条状态：ok / fail / skip / untested。"""
    if kind not in PROBE_KINDS:
        return "untested"
    rec = store.load_probe().get(method)
    return rec.get("status", "untested") if rec else "untested"
