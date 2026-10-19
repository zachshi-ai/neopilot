"""驾驶舱渲染入口.

2.0 起这里只剩胶水：取数据 → 交给 web 层装配。原先 483 行
「HTML + CSS + JS + 逐字段绑定」的实现已迁到 web/，Python 不再拼结构。
"""

from __future__ import annotations

from pathlib import Path

from . import state as state_mod, web
from .store import Store


def render(store: Store, title: str = "NeoPilot") -> str:
    return web.build_html(state_mod.build(store))


def write(store: Store, path: Path, title: str = "NeoPilot") -> str:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render(store, title), encoding="utf-8")
    return str(path)
