"""NeoPilot 简报生成.

例程跑完只是拿到一堆 JSON，人不想看 JSON。这一层把运行结果按例程类型
翻译成两三句能直接读的话——纯规则拼装，不调模型，保证离线、确定、可复现。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

TZ = timezone(timedelta(hours=8))


def _step(run: Dict, sid: str) -> Optional[Dict]:
    for s in run.get("steps", []):
        if s["id"] == sid:
            return s
    return None


def _data(run: Dict, sid: str) -> Dict:
    s = _step(run, sid)
    if not s or s.get("status") != "ok" or not isinstance(s.get("data"), dict):
        return {}
    return s["data"]


def _d(v: Any) -> Dict:
    return v if isinstance(v, dict) else {}


def _dig(d: Dict, path: str, default=None):
    cur: Any = d
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]
    return cur


def _passed(hm: str) -> bool:
    """判断 HH:MM 是否已经过去，用来避免把已结束的日程说成待办。"""
    try:
        h, m = hm.split(":")
        now = datetime.now(TZ)
        return (int(h), int(m)) <= (now.hour, now.minute)
    except Exception:
        return False


def _fmt_event(e: Dict) -> str:
    t = e.get("title", "未命名")
    st = (e.get("start") or "")[11:16] or e.get("start", "")
    en = (e.get("end") or "")[11:16] or e.get("end", "")
    return f"{st}–{en} {t}" if st else t


def _event_lines(run: Dict, sid: str, limit: int = 4) -> List[str]:
    d = _data(run, sid)
    evs = d.get("events") or []
    return [_fmt_event(e) for e in evs[:limit]]


# ── 各例程的结论文本 ─────────────────────────────────────────
def _brief_env_probe(run: Dict) -> str:
    bat = _data(run, "battery").get("level", "未知")
    loc = _data(run, "location")
    w = _data(run, "weather")
    today = _d(w.get("today"))
    now = _d(w.get("now"))
    evs = _event_lines(run, "calendar")

    parts: List[str] = []
    parts.append(f"设备电量 {bat}，位置在{loc.get('address', '未知位置')}。")
    if w:
        parts.append(
            f"当前{now.get('text', '')}{now.get('temp', '')}，今天{today.get('day', '')}"
            f"{today.get('low', '?')}–{today.get('high', '?')}，"
            f"降水概率 {today.get('pop', 0)}%，空气{today.get('quality', '')}。"
        )
        tips = w.get("tips") or []
        if tips:
            parts.append("生活提示：" + "、".join(tips) + "。")
    if evs:
        parts.append("今天日程：" + "；".join(evs) + "。")
    else:
        parts.append("今天没有排定的日程。")
    return "".join(parts)


def _brief_morning(run: Dict) -> str:
    w = _data(run, "weather")
    today = _d(w.get("today"))
    now = _d(w.get("now"))
    bat = _data(run, "battery").get("level")
    evs = _event_lines(run, "calendar")

    head = "早上好。"
    if w:
        head += (f"今天{today.get('day', '')}，"
                 f"{today.get('low', '?')}–{today.get('high', '?')}℃，")
        try:
            pop = int(today.get("pop", 0) or 0)
        except (TypeError, ValueError):
            pop = 0
        head += "大概率不会下雨。" if pop < 30 else f"降水概率 {pop}%，记得带伞。"
    if evs:
        head += f" 今天有 {len(evs)} 件事：" + "；".join(evs) + "。"
        first = evs[0]
        title = first.split(" ", 1)[-1]
        start_hm = first[:5]
        head += (" 第一件 " + title + " 已经开始了（" + start_hm + "），"
                 "看看要不要补一个后续安排。"
                 if _passed(start_hm) else
                 " 第一件是 " + title + "，按 " + start_hm + " 倒推出门。")
    else:
        head += " 今天日历是空的，可以安排整块时间。"
    if bat:
        head += f" 手机还剩 {bat}。"
    if w:
        head += f" 体感温度 {now.get('temp', '—')}，穿短袖就够。"
    return head


def _brief_evening(run: Dict) -> str:
    t_ev = _event_lines(run, "today")
    m_ev = _event_lines(run, "tomorrow")
    w = _data(run, "weather")
    tm = _d(w.get("today"))
    bat = _data(run, "battery").get("level")

    out = "今天收个尾。"
    out += (f" 完成/待办了 {len(t_ev)} 件事。" if t_ev else " 今天没有记在日历上的安排。")
    if m_ev:
        out += " 明天先看这几件：" + "；".join(m_ev) + "。"
    else:
        out += " 明天日历还空着。"
    if w:
        out += f" 明天{tm.get('day', '')}，{tm.get('low', '?')}–{tm.get('high', '?')}℃。"
    if bat:
        out += f" 电量 {bat}，" + ("记得插上充电器。" if _pct(bat) < 40 else "够撑到早上。")
    return out


def _pct(s: str) -> int:
    try:
        return int(str(s).replace("%", "").strip())
    except Exception:
        return 100


def _brief_generic(run: Dict) -> str:
    lines = []
    for s in run.get("steps", []):
        if s.get("status") == "ok":
            d = s.get("data")
            summary = ""
            if isinstance(d, dict):
                scalars = [f"{k}={v}" for k, v in list(d.items())[:3]
                           if isinstance(v, (str, int, float))]
                summary = "，".join(scalars)
            elif d is not None:
                summary = str(d)[:60]
            lines.append(f"{s.get('label')}：{summary}" if summary else str(s.get("label")))
        elif s.get("status") == "fail":
            lines.append(f"{s.get('label')}：失败（{s.get('error') or '未知原因'}）")
    head = f"{run.get('routine_name')} 跑完了，{run.get('status')}。"
    return head + (" " + "；".join(lines) + "。" if lines else "")


FORMATTERS = {
    "env-probe": _brief_env_probe,
    "morning-cockpit": _brief_morning,
    "evening-review": _brief_evening,
}


def brief(run: Dict) -> str:
    fn = FORMATTERS.get(run.get("routine"), _brief_generic)
    try:
        return fn(run)
    except Exception as exc:  # 简报不该把整条运行带崩
        return f"{run.get('routine_name')} 已结束（{run.get('status')}），简报生成异常：{exc}"
