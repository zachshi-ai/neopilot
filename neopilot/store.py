"""NeoPilot 存储层.

所有状态都落在本地一个目录里，纯 JSON 文件，没有数据库、没有服务进程。
这样做的理由：例程要在手机 / 云端的任意一次会话里被读写，文件是最稳的
跨进程交接介质，也方便直接 git 备份。
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

DEFAULT_HOME = Path(os.environ.get("NEOPILOT_HOME", ".neopilot")).expanduser()

SCHEMA_VERSION = 1


class Store:
    def __init__(self, home: Optional[Path] = None) -> None:
        self.home = Path(home) if home else DEFAULT_HOME
        self.routines_dir = self.home / "routines"
        self.runs_dir = self.home / "runs"
        self.data_dir = self.home / "data"
        self.out_dir = self.home / "out"
        self.audit_path = self.home / "audit.jsonl"

    # ── 生命周期 ─────────────────────────────────────────────
    def init(self) -> None:
        for d in (self.home, self.routines_dir, self.runs_dir, self.data_dir, self.out_dir):
            d.mkdir(parents=True, exist_ok=True)
        meta = self.home / "meta.json"
        if not meta.exists():
            self._atomic_write(meta, {
                "schema": SCHEMA_VERSION,
                "created_at": self.now_iso(),
                "engine": "neopilot",
            })

    def exists(self) -> bool:
        return (self.home / "meta.json").exists()

    # ── 基础 IO ──────────────────────────────────────────────
    @staticmethod
    def _atomic_write(path: Path, obj: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(obj, fh, ensure_ascii=False, indent=2)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    @staticmethod
    def _read(path: Path) -> Any:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)

    @staticmethod
    def now_iso() -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%S%z")

    @staticmethod
    def stamp() -> str:
        return time.strftime("%Y%m%d-%H%M%S")

    # ── 例程 ────────────────────────────────────────────────
    def save_routine(self, routine: Dict) -> None:
        self._atomic_write(self.routines_dir / f"{routine['id']}.json", routine)

    def load_routine(self, rid: str) -> Dict:
        return self._read(self.routines_dir / f"{rid}.json")

    def routines(self) -> List[Dict]:
        out = [self._read(p) for p in sorted(self.routines_dir.glob("*.json"))]
        return out

    def delete_routine(self, rid: str) -> bool:
        p = self.routines_dir / f"{rid}.json"
        if p.exists():
            p.unlink()
            return True
        return False

    # ── 运行记录 ────────────────────────────────────────────
    def save_run(self, run: Dict) -> None:
        self._atomic_write(self.runs_dir / f"{run['run_id']}.json", run)

    def load_run(self, run_id: str) -> Dict:
        return self._read(self.runs_dir / f"{run_id}.json")

    def runs(self, limit: int = 60) -> List[Dict]:
        paths = sorted(self.runs_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        return [self._read(p) for p in paths[:limit]]

    def find_run(self, prefix: str) -> Dict:
        """允许用 run_id 前缀定位，省得每次抄一长串。"""
        hits = [p for p in self.runs_dir.glob(f"{prefix}*.json")]
        if not hits:
            raise KeyError(f"找不到运行记录: {prefix}")
        if len(hits) > 1:
            raise KeyError(f"前缀不唯一，匹配到 {len(hits)} 条: {prefix}")
        return self._read(hits[0])

    def latest_run(self, routine_id: str) -> Optional[Dict]:
        for r in self.runs(limit=200):
            if r.get("routine") == routine_id:
                return r
        return None

    # ── 数据快照 ────────────────────────────────────────────
    def save_snapshot(self, name: str, payload: Any) -> Path:
        p = self.data_dir / f"{name}.json"
        self._atomic_write(p, payload)
        return p

    def load_snapshot(self, name: str) -> Any:
        p = self.data_dir / f"{name}.json"
        return self._read(p) if p.exists() else None

    # ── 写操作审计 ──────────────────────────────────────────
    def audit(self, entry: Dict[str, Any]) -> None:
        """追加一条写操作记录。用 jsonl 而不是 json，
        是因为审计只追加不修改，多进程同时写也不会互相覆盖整份文件。"""
        self.home.mkdir(parents=True, exist_ok=True)
        with open(self.audit_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def audits(self, limit: int = 50) -> List[Dict[str, Any]]:
        if not self.audit_path.exists():
            return []
        lines = self.audit_path.read_text(encoding="utf-8").splitlines()
        out: List[Dict[str, Any]] = []
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                continue
            if len(out) >= limit:
                break
        return out

    # ── 能力探测结果 ────────────────────────────────────────
    def load_probe(self) -> Dict[str, Any]:
        return self.load_snapshot("caps_probe") or {}

    def save_probe(self, data: Dict[str, Any]) -> None:
        self.save_snapshot("caps_probe", data)

    # ── 维护 ────────────────────────────────────────────────
    def prune_runs(self, keep: int = 200) -> int:
        paths = sorted(self.runs_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        removed = 0
        for p in paths[keep:]:
            p.unlink()
            removed += 1
        return removed

    def usage(self) -> Dict[str, Any]:
        total = 0
        files = 0
        for p in self.home.rglob("*"):
            if p.is_file():
                files += 1
                total += p.stat().st_size
        return {"files": files, "bytes": total, "human": human_bytes(total)}

    def backup(self, dest: Path) -> Path:
        dest = Path(dest)
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(self.home, dest)
        return dest


def human_bytes(n: int) -> str:
    units = ["B", "KB", "MB", "GB"]
    v = float(n)
    for u in units:
        if v < 1024 or u == units[-1]:
            return f"{v:.1f} {u}" if u != "B" else f"{int(v)} B"
        v /= 1024
    return f"{n} B"
