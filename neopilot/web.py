"""把模板和数据装配成单文件 HTML.

只有这一处负责「拼页面」，而且拼的是骨架：结构全在 web/index.html，
样式在 web/styles.css，渲染逻辑在 web/app.js。Python 不再逐字段写 HTML，
这样前端只维护一份，加字段不必回头改 Python。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

WEB_DIR = Path(__file__).resolve().parent.parent / "web"


def _read(name: str) -> str:
    return (WEB_DIR / name).read_text(encoding="utf-8")


def build_html(state: Dict[str, Any]) -> str:
    html = _read("index.html")
    html = html.replace("__CSS__", _read("styles.css"))
    html = html.replace("__JS__", _read("app.js"))
    payload = json.dumps(state, ensure_ascii=False)
    # 防止数据里出现 </script> 截断标签
    payload = payload.replace("</", "<\\/")
    html = html.replace("__BOOTSTRAP__", payload)
    return html
