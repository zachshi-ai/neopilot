/* NeoPilot 2.0 渲染器
 *
 * 全站唯一一份渲染逻辑：Python 只负责产出数据（内联在 #bootstrap 里），
 * 页面结构一律由这里生成。这样加一个字段只改一处，不再出现
 * 「Python 加 id + JS 再 setText」的双轨维护。
 */

(function () {
  var state = { meta: {}, today: {}, engine: {}, caps: [] };

  // ── 小工具 ────────────────────────────────────────────
  function h(tag, attrs, children) {
    var el = document.createElement(tag);
    if (attrs) {
      for (var k in attrs) {
        if (attrs[k] === undefined || attrs[k] === null || attrs[k] === '') continue;
        if (k === 'class') el.className = attrs[k];
        else if (k === 'text') el.textContent = attrs[k];
        else el.setAttribute(k, attrs[k]);
      }
    }
    (children || []).forEach(function (c) {
      if (c === null || c === undefined) return;
      el.appendChild(typeof c === 'string' ? document.createTextNode(c) : c);
    });
    return el;
  }
  function clear(node) { while (node.firstChild) node.removeChild(node.firstChild); }
  function pick(o, path, dflt) {
    var cur = o;
    var parts = path.split('.');
    for (var i = 0; i < parts.length; i++) {
      if (!cur || typeof cur !== 'object' || !(parts[i] in cur)) return dflt;
      cur = cur[parts[i]];
    }
    return (cur === undefined || cur === null || cur === '') ? dflt : cur;
  }
  function merge(base, patch) {
    if (!patch) return base;
    var out = Array.isArray(base) ? base.slice() : Object.assign({}, base);
    for (var k in patch) {
      var v = patch[k];
      if (v && typeof v === 'object' && !Array.isArray(v) && base && typeof base[k] === 'object') {
        out[k] = merge(base[k], v);
      } else if (v !== undefined && v !== null && v !== '') {
        out[k] = v;
      }
    }
    return out;
  }

  // ── cron 本地解析 ─────────────────────────────────────
  // 例程定义是静态的，下次什么时候跑完全可以在本地算出来，
  // 没必要等云端推。这样「接下来要跑的」是真正实时的。
  function fieldMatch(field, value) {
    if (field === '*') return true;
    var parts = field.split(',');
    for (var i = 0; i < parts.length; i++) {
      var p = parts[i];
      if (p.indexOf('*/') === 0) {
        var step = parseInt(p.slice(2), 10);
        if (step && value % step === 0) return true;
      } else if (p.indexOf('-') > 0) {
        var ab = p.split('-');
        if (value >= parseInt(ab[0], 10) && value <= parseInt(ab[1], 10)) return true;
      } else if (parseInt(p, 10) === value) {
        return true;
      }
    }
    return false;
  }

  function cronMatch(expr, dt) {
    var f = expr.trim().split(/\s+/);
    if (f.length !== 5) return false;
    var dow = dt.getDay();
    return fieldMatch(f[0], dt.getMinutes())
        && fieldMatch(f[1], dt.getHours())
        && fieldMatch(f[2], dt.getDate())
        && fieldMatch(f[3], dt.getMonth() + 1)
        && (fieldMatch(f[4], dow) || fieldMatch(f[4], dow === 0 ? 7 : dow));
  }

  function nextOccurrence(expr, from) {
    var t = new Date(from.getTime());
    t.setSeconds(0, 0);
    t = new Date(t.getTime() + 60000);
    for (var i = 0; i < 8 * 1440; i++) {
      if (cronMatch(expr, t)) return t;
      t = new Date(t.getTime() + 60000);
    }
    return null;
  }

  function pad(n) { return (n < 10 ? '0' : '') + n; }

  function fmtAt(d, now) {
    var hm = pad(d.getHours()) + ':' + pad(d.getMinutes());
    var a = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    var b = new Date(d.getFullYear(), d.getMonth(), d.getDate());
    var diff = Math.round((b - a) / 86400000);
    if (diff === 0) return hm;
    if (diff === 1) return '明天 ' + hm;
    return pad(d.getMonth() + 1) + '-' + pad(d.getDate()) + ' ' + hm;
  }

  function computeUpcoming() {
    var now = new Date();
    var cloudBlocked = {};
    (pick(state, 'engine.upcoming', []) || []).forEach(function (u) {
      if (u.blocked) cloudBlocked[u.name] = true;
    });
    var out = [];
    (pick(state, 'engine.routines', []) || []).forEach(function (r) {
      if (!r.enabled || !r.schedule) return;
      var nxt = nextOccurrence(r.schedule, now);
      if (!nxt) return;
      out.push({
        name: r.name,
        at: fmtAt(nxt, now),
        in_hours: ((nxt - now) / 3600000).toFixed(1),
        blocked: !!cloudBlocked[r.name],
        ts: nxt.getTime()
      });
    });
    out.sort(function (a, b) { return a.ts - b.ts; });
    return out.slice(0, 6);
  }

  // ── 总览 ─────────────────────────────────────────────
  function renderToday() {
    var box = document.getElementById('p-home');
    clear(box);
    var t = state.today || {};
    var now = t.now || {}, daily = t.daily || {};

    var statItems = [
      ['电量', t.battery || '—'],
      ['降水', (daily.pop !== undefined && daily.pop !== null && daily.pop !== '') ? daily.pop + '%' : '—'],
      ['湿度', now.humidity || '—']
    ];

    var card = h('div', { class: 'card hero-card' }, [
      h('div', { class: 'temp-row' }, [
        h('div', { class: 'temp', text: now.temp || '—' }),
        h('div', { class: 'temp-meta' }, [
          h('div', { class: 'cond', text: now.text || '' }),
          h('div', { class: 'place', text: t.city || t.address || '' })
        ])
      ]),
      h('div', { class: 'stat-row' }, statItems.map(function (s) {
        return h('div', { class: 'stat' }, [
          h('b', { text: s[1] }),
          h('span', { text: s[0] })
        ]);
      })),
      h('div', { class: 'headline', text: t.headline || '' }),
      t.tips && t.tips.length ? h('div', { class: 'chips' },
        t.tips.map(function (x) { return h('span', { class: 'chip', text: x }); })) : null
    ]);
    box.appendChild(card);

    // 今日日程
    var evs = t.events || [];
    var evCard = h('div', { class: 'card' }, [
      h('div', { class: 'card-head' }, [
        h('div', { class: 'card-title', text: '今日日程' }),
        h('div', { class: 'card-sub', text: evs.length ? evs.length + ' 件' : '' })
      ])
    ]);
    if (evs.length) {
      evs.forEach(function (e) {
        evCard.appendChild(h('div', { class: 'row' }, [
          h('div', { class: 'row-time', text: (e.start || '') + '–' + (e.end || '') }),
          h('div', { class: 'row-main', text: e.title || '未命名' })
        ]));
      });
    } else {
      evCard.appendChild(h('div', { class: 'empty', text: '今天没有排定的日程' }));
    }
    box.appendChild(evCard);

    // 接下来要跑的
    var ups = computeUpcoming();
    var upCard = h('div', { class: 'card' }, [
      h('div', { class: 'card-head' }, [
        h('div', { class: 'card-title', text: '接下来要跑的' }),
        h('div', { class: 'card-sub', text: '按本地时间推算' })
      ])
    ]);
    if (ups.length) {
      ups.forEach(function (u) {
        upCard.appendChild(h('div', { class: 'row' }, [
          h('div', { class: 'row-time', text: u.at || '' }),
          h('div', { class: 'row-main' }, [
            document.createTextNode(u.name || ''),
            u.blocked ? h('span', { class: 'tag warn', text: '缺配置', style: 'margin-left:6px' }) : null
          ]),
          h('div', { class: 'row-tail', text: u.in_hours !== undefined ? '还有 ' + u.in_hours + ' 小时' : '' })
        ]));
      });
    } else {
      upCard.appendChild(h('div', { class: 'empty', text: '没有排表中的例程' }));
    }
    box.appendChild(upCard);

    // 最近运行
    var runs = pick(state, 'engine.runs', []);
    if (runs.length) {
      var runCard = h('div', { class: 'card' }, [
        h('div', { class: 'card-head' }, [h('div', { class: 'card-title', text: '最近运行' })])
      ]);
      runs.slice(0, 5).forEach(function (r) {
        var cls = r.status === 'success' ? 'ok' : (r.status === 'failed' ? 'bad' : 'warn');
        var label = { success: '成功', partial: '部分完成', failed: '失败', cancelled: '取消' }[r.status] || r.status;
        runCard.appendChild(h('div', { class: 'row' }, [
          h('div', { class: 'row-time', text: (r.started || '').slice(5, 16) }),
          h('div', { class: 'row-main', text: r.routine || '' }),
          h('span', { class: 'tag ' + cls, text: label }),
          h('div', { class: 'row-tail', text: r.ok + '/' + r.total })
        ]));
      });
      box.appendChild(runCard);
    }
  }

  // ── 例程 ─────────────────────────────────────────────
  function renderRoutines() {
    var box = document.getElementById('p-routines');
    clear(box);
    var list = pick(state, 'engine.routines', []);
    if (!list.length) {
      box.appendChild(h('div', { class: 'card' }, [
        h('div', { class: 'empty', text: '还没有例程，先在云端跑一次 seed' })
      ]));
      return;
    }
    var wrap = h('div', { class: 'card', style: 'padding:6px 0' });
    list.forEach(function (r) {
      var rate = r.rate;
      var barCls = rate === null || rate === undefined ? '' :
        (rate >= 85 ? 'ok' : (rate >= 60 ? 'warn' : 'bad'));
      var steps = (r.steps || []).map(function (s) {
        return h('span', { class: 'chip', text: s });
      });
      wrap.appendChild(h('div', { class: 'routine' }, [
        h('div', { class: 'r-top' }, [
          h('div', { class: 'r-name', text: r.name }),
          h('span', { class: 'tag ' + (r.enabled ? '' : 'off'), text: r.enabled ? '启用' : '停用' })
        ]),
        h('div', { class: 'r-desc', text: r.desc || '' }),
        h('div', { class: 'r-meta' }, [
          h('span', { text: r.schedule_text || '手动' }),
          h('span', { text: (r.steps || []).length + ' 步' }),
          h('span', { text: rate === null || rate === undefined ? '未运行' : '近 ' + r.runs + ' 次 · ' + rate + '%' })
        ]),
        h('div', { class: 'bar ' + barCls }, [
          h('i', { style: 'width:' + (rate || 0) + '%' })
        ]),
        h('div', { class: 'r-steps' }, steps)
      ]));
      wrap.appendChild(h('div', { style: 'height:1px;background:var(--line);margin:0 14px' }));
    });
    box.appendChild(wrap);
  }

  // ── 能力 ─────────────────────────────────────────────
  var capIndex = [];
  function renderCaps() {
    var box = document.getElementById('p-caps');
    clear(box);

    var input = h('input', {
      class: 'search', placeholder: '搜索能力名称、用途或方法名',
      oninput: function () { filterCaps(this.value); }
    });
    box.appendChild(input);

    // 状态图例：26 个灰点不加说明会被误读成「坏了」
    var counts = { ok: 0, fail: 0, skip: 0, untested: 0 };
    (state.caps || []).forEach(function (c) { counts[c.status || 'untested'] = (counts[c.status || 'untested'] || 0) + 1; });
    var legend = h('div', { class: 'cap-legend' }, [
      h('span', {}, [h('i', { class: 'dot-sm ok' }), document.createTextNode('可用 ' + counts.ok)]),
      counts.skip ? h('span', {}, [h('i', { class: 'dot-sm skip' }), document.createTextNode('跳过 ' + counts.skip)]) : null,
      counts.fail ? h('span', {}, [h('i', { class: 'dot-sm fail' }), document.createTextNode('失效 ' + counts.fail)]) : null,
      h('span', {}, [h('i', { class: 'dot-sm untested' }), document.createTextNode('未探测 ' + counts.untested)])
    ]);
    box.appendChild(legend);

    var holder = h('div', { id: 'cap-holder' });
    box.appendChild(holder);
    capIndex = [];

    var byCat = {};
    (state.caps || []).forEach(function (c) {
      (byCat[c.category] = byCat[c.category] || []).push(c);
    });

    Object.keys(byCat).forEach(function (cat) {
      holder.appendChild(h('div', { class: 'cap-cat', text: cat + ' · ' + byCat[cat].length }));
      byCat[cat].forEach(function (c) {
        var el = h('div', { class: 'cap' }, [
          h('div', { class: 'cap-dot ' + (c.status || 'untested'), title: '风险 ' + (c.risk || 'low') }),
          h('div', { class: 'cap-name' }, [
            document.createTextNode(c.name),
            h('em', { text: (c.app || '') + ' · ' + (c.desc || '') })
          ]),
          h('span', { class: 'cap-kind ' + (c.kind || ''), text: { read: '只读', write: '写入', navigate: '跳转' }[c.kind] || c.kind })
        ]);
        el.dataset.k = ((c.name || '') + (c.desc || '') + (c.method || '') + (c.app || '')).toLowerCase();
        holder.appendChild(el);
        capIndex.push(el);
      });
    });
  }

  function filterCaps(q) {
    q = (q || '').trim().toLowerCase();
    capIndex.forEach(function (el) {
      el.style.display = (!q || el.dataset.k.indexOf(q) >= 0) ? 'flex' : 'none';
    });
  }

  // ── 顶部同步状态 ──────────────────────────────────────
  function renderMeta() {
    var el = document.getElementById('sync-text');
    var wrap = document.getElementById('sync');
    if (!el) return;
    var t = state.meta || {};
    var src = t.source === 'local' ? '本机实时' : '云端快照';
    var at = t.generated_at || '';
    el.textContent = at ? (src + ' · ' + at) : src;
    if (wrap) wrap.className = 'sync' + (t.source === 'local' ? '' : ' stale');
  }

  // ── 渲染入口 ─────────────────────────────────────────
  function renderAll() {
    renderMeta();
    renderToday();
    renderRoutines();
    renderCaps();
  }

  window.NeoPilotApply = function (patch) {
    if (!patch) return false;
    if (patch.today) state.today = merge(state.today || {}, patch.today);
    if (patch.engine) state.engine = patch.engine;
    if (patch.caps) state.caps = patch.caps;
    state.meta = merge(state.meta || {}, patch.meta || {});
    renderAll();
    return true;
  };

  window.NeoPilotRefresh = function () {
    try {
      if (window.NeoPilotNative && window.NeoPilotNative.getLive) {
        var live = window.NeoPilotNative.getLive();
        if (live) {
          window.NeoPilotApply(JSON.parse(live));
          return true;
        }
      }
    } catch (e) { }
    try {
      if (window.NeoPilotNative && window.NeoPilotNative.getData) {
        var raw = window.NeoPilotNative.getData();
        if (raw) {
          window.NeoPilotApply(JSON.parse(raw));
          return true;
        }
      }
    } catch (e) { }
    return false;
  };

  // 标签切换
  window.NeoPilotTab = function (id, node) {
    document.querySelectorAll('.panel').forEach(function (p) { p.classList.remove('on'); });
    document.querySelectorAll('.tab').forEach(function (t) { t.classList.remove('on'); });
    var panel = document.getElementById('p-' + id);
    if (panel) panel.classList.add('on');
    if (node) node.classList.add('on');
    window.scrollTo(0, 0);
  };

  // ── 启动 ─────────────────────────────────────────────
  function boot() {
    var node = document.getElementById('bootstrap');
    if (node) {
      try {
        var data = JSON.parse(node.textContent);
        state.meta = data.meta || {};
        state.today = data.today || {};
        state.engine = data.engine || {};
        state.caps = data.caps || [];
      } catch (e) { }
    }
    renderAll();
    window.NeoPilotRefresh();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
