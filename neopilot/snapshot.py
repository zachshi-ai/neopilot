"""云端快照：输出给 App 消费的 JSON（与 state 契约同构）。

通道：云端跑完例程 → 生成本文件 → 推到手机
/sdcard/Android/data/com.stepx.neopilot/files/data.json
→ App 启动时作为兜底数据读入。

选这个目录是因为它属于 App 自己的外部私有目录，读写都不需要
READ_EXTERNAL_STORAGE / MANAGE_EXTERNAL_STORAGE 这类敏感权限。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

from . import state as state_mod
from .store import Store

APP_FILES_DIR = "/sdcard/Android/data/com.stepx.neopilot/files"


def build(store: Store) -> Dict:
    return state_mod.build(store, source="cloud")


def write(store: Store, path: Path | None = None) -> Path:
    snap = build(store)
    p = path or (store.data_dir / "app_snapshot.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(snap, ensure_ascii=False, indent=2), encoding="utf-8")
    return p
