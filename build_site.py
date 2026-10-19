"""构建 PWA 站点（site/）。

产物：index.html + manifest.webmanifest + sw.js + icons/
和 APK 共用同一份 web/ 模板与同一份状态数据，只有外壳不同。
"""

import json
import shutil
from pathlib import Path

from neopilot import state as state_mod, web
from neopilot.store import Store

ROOT = Path(__file__).resolve().parent
SITE = ROOT / "site"

MANIFEST = {
    "name": "NeoPilot 个人自动化中枢",
    "short_name": "NeoPilot",
    "description": "把 STEPX Neo 的原子能力编成可定时、可重试、可审计的例程",
    "start_url": "./index.html",
    "scope": "./",
    "display": "standalone",
    "orientation": "portrait",
    "background_color": "#F5F6F7",
    "theme_color": "#3370FF",
    "lang": "zh-CN",
    "icons": [
        {"src": "icons/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any maskable"},
        {"src": "icons/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"},
    ],
}

SW = """const CACHE = 'neopilot-v2';
const ASSETS = ['./', './index.html', './manifest.webmanifest',
                './icons/icon-192.png', './icons/icon-512.png'];
self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(ASSETS)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(ks =>
    Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k)))
  ).then(() => self.clients.claim()));
});
self.addEventListener('fetch', e => {
  if (e.request.method !== 'GET') return;
  e.respondWith(caches.match(e.request).then(hit => {
    const net = fetch(e.request).then(res => {
      if (res && res.status === 200 && res.type === 'basic') {
        const copy = res.clone();
        caches.open(CACHE).then(c => c.put(e.request, copy));
      }
      return res;
    }).catch(() => hit);
    return hit || net;
  }));
});
"""


def build() -> Path:
    SITE.mkdir(parents=True, exist_ok=True)
    (SITE / "icons").mkdir(exist_ok=True)

    store = Store()
    html = web.build_html(state_mod.build(store))
    (SITE / "index.html").write_text(html, encoding="utf-8")
    (SITE / "manifest.webmanifest").write_text(
        json.dumps(MANIFEST, ensure_ascii=False, indent=2), encoding="utf-8")
    (SITE / "sw.js").write_text(SW, encoding="utf-8")

    icon_src = ROOT / "site_icons_tmp"
    if icon_src.exists():
        for f in icon_src.glob("*.png"):
            shutil.copy(f, SITE / "icons" / f.name)
    return SITE


if __name__ == "__main__":
    out = build()
    for f in sorted(p for p in out.rglob("*") if p.is_file()):
        print(f"  {f.relative_to(out)}  {f.stat().st_size} B")
