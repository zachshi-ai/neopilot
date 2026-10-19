"""NeoPilot 命令行入口."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import brief as brief_mod, catalog, engine, presets, probe as probe_mod, render, snapshot as snap_mod
from .store import Store


def _out(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _need(store: Store) -> None:
    if not store.exists():
        store.init()


def cmd_init(args, store: Store) -> int:
    store.init()
    print(f"已初始化：{store.home}")
    return 0


def cmd_seed(args, store: Store) -> int:
    _need(store)
    n = 0
    for r in presets.all_presets():
        path = store.routines_dir / f"{r['id']}.json"
        if path.exists() and not args.force:
            continue
        store.save_routine(dict(r))
        n += 1
    print(f"写入 {n} 个例程（跳过已存在 {len(presets.all_presets()) - n} 个）")
    return 0


def cmd_routines(args, store: Store) -> int:
    _need(store)
    rs = store.routines()
    if args.json:
        _out(rs)
        return 0
    if not rs:
        print("还没有例程，先跑 init --seed")
        return 0
    print(f"{'ID':<18}{'状态':<6}{'时间表':<16}名称")
    print("-" * 64)
    for r in rs:
        st = "启用" if r.get("enabled") else "停用"
        print(f"{r['id']:<18}{st:<6}{r.get('schedule_text',''):<16}{r['name']}")
    return 0


def cmd_show(args, store: Store) -> int:
    _need(store)
    r = store.load_routine(args.id)
    if args.json:
        _out(r)
        return 0
    print(f"{r['name']}  ({r['id']})")
    print(f"  时间表：{r.get('schedule_text') or '手动'}")
    print(f"  说明：  {r.get('desc')}")
    print(f"  状态：  {'启用' if r.get('enabled') else '停用'}")
    print("  步骤：")
    for i, s in enumerate(r["steps"], 1):
        must = "必过" if s.get("must", True) else "可跳"
        print(f"    {i}. [{must}] {s.get('label')}  →  {s['cap']}")
    return 0


def cmd_toggle(args, store: Store, on: bool) -> int:
    _need(store)
    r = store.load_routine(args.id)
    r["enabled"] = on
    store.save_routine(r)
    print(f"{r['name']} 已{'启用' if on else '停用'}")
    return 0


def cmd_run(args, store: Store) -> int:
    _need(store)
    r = store.load_routine(args.id)
    extra = {}
    for kv in args.ctx or []:
        k, _, v = kv.partition("=")
        extra[k if k.startswith("$") else "$" + k] = v
    run = engine.start_run(store, r, ctx_extra=extra, trigger=args.trigger)
    if args.json:
        _out(run)
    else:
        print(f"▶ 开始运行 {r['name']}")
        print(f"  run_id: {run['run_id']}")
        print(f"  共 {len(run['steps'])} 步，第一步：")
        s = engine.next_step(run)
        print(json.dumps({"step": s["id"], "cap": s["cap"], "params": s["params"]},
                         ensure_ascii=False, indent=2))
    return 0


def cmd_next(args, store: Store) -> int:
    _need(store)
    run = store.find_run(args.run_id)
    s = engine.next_step(run)
    if s is None:
        _out({"done": True, "status": run.get("status")})
    else:
        _out({"done": False, "run_id": run["run_id"], "step": s["id"],
              "cap": s["cap"], "label": s["label"], "params": s["params"],
              "attempt": s.get("attempt", 0)})
    return 0


def cmd_report(args, store: Store) -> int:
    _need(store)
    run = store.find_run(args.run_id)
    data = None
    if args.data:
        data = json.loads(args.data)
    run = engine.report_step(store, run, args.step, args.status,
                             data=data, error=args.error, ms=args.ms)
    if args.json:
        _out(run)
        return 0
    print(f"· {args.step} → {args.status}")
    remain = engine.next_step(run)
    if remain is None:
        print(f"  运行结束：{run['status']}（{sum(1 for s in run['steps'] if s['status']=='ok')}/{len(run['steps'])} 步成功）")
    else:
        print(f"  下一 步：{remain['label']} → {remain['cap']}")
    return 0


def cmd_status(args, store: Store) -> int:
    _need(store)
    run = store.find_run(args.run_id)
    if args.json:
        _out(run)
        return 0
    print(f"{run['routine_name']}  {run['run_id']}")
    print(f"  状态：{run['status']}   触发：{run.get('trigger')}")
    for s in run["steps"]:
        mark = {"ok": "✓", "fail": "✗", "retry": "↻", "skipped": "–", "pending": "·"}.get(s["status"], "?")
        print(f"  {mark} {s['label']:<16} {s['cap']:<44} {s['status']}")
    return 0


def cmd_runs(args, store: Store) -> int:
    _need(store)
    runs = store.runs(limit=args.limit)
    if args.json:
        _out(runs)
        return 0
    if not runs:
        print("还没有运行记录")
        return 0
    for r in runs:
        ok = sum(1 for s in r["steps"] if s["status"] == "ok")
        print(f"{(r.get('started_at') or '')[:19].replace('T',' ')}  "
              f"{r['routine_name']:<12} {r['status']:<8} {ok}/{len(r['steps'])}  {r['run_id']}")
    return 0


def cmd_cancel(args, store: Store) -> int:
    _need(store)
    run = store.find_run(args.run_id)
    run = engine.cancel_run(store, run, args.reason or "")
    print(f"已取消 {run['run_id']}（{run['status']}）")
    return 0


def cmd_due(args, store: Store) -> int:
    _need(store)
    items = engine.due_routines(store, window_min=args.window)
    if args.json:
        _out(items)
        return 0
    if not items:
        print(f"过去 {args.window} 分钟内没有到点的例程")
        return 0
    for d in items:
        flag = "  [缺配置 " + ",".join(d["missing"]) + "]" if d["blocked"] else ""
        print(f"{d['hit_at']}  {d['name']}{flag}  已滞后 {d['lag_min']} 分钟")
    return 0


def cmd_tick(args, store: Store) -> int:
    _need(store)
    res = engine.tick(store, window_min=args.window, skip_blocked=not args.force)
    if args.claim:
        queue = engine.work_queue(store)
        _out({"started": res, "queue": queue})
        return 0
    if args.json:
        _out(res)
        return 0
    if not res:
        print("本轮无事可做")
        return 0
    for r in res:
        if r.get("started"):
            print(f"▶ 已启动 {r['name']}（{r['hit_at']}） run_id={r['run_id']}")
        else:
            print(f"– 跳过   {r['name']}：{r.get('reason', '')}")
    return 0


def cmd_crontab(args, store: Store) -> int:
    for line in engine.crontab_lines(store, python_bin=args.python, entry=args.entry):
        print(line)
    return 0


def cmd_work(args, store: Store) -> int:
    _need(store)
    items = engine.work_queue(store)
    if args.json:
        _out(items)
        return 0
    if not items:
        print("没有待执行的步骤")
        return 0
    for it in items:
        print(f"[{it['routine_name']}] {it['label']}  →  {it['cap']}")
        print(f"    run={it['run_id']}  step={it['step']}  参数={it['params']}")
    print()
    print("执行后回填：neopilot.py report <run_id> <step> --status ok --data '{...}'")
    return 0


def cmd_audit(args, store: Store) -> int:
    _need(store)
    rows = store.audits(limit=args.limit)
    if args.json:
        _out(rows)
        return 0
    if not rows:
        print("还没有写操作记录")
        return 0
    for r in rows:
        status = r.get("status")
        mark = "✓" if status == "ok" else ("–" if status == "skip" else "✗")
        print(f"{mark} {r.get('at')}  {r.get('name', '')}  {r.get('method')}  "
              f"[{r.get('risk')}]  {r.get('params')}")
    return 0


def cmd_probe(args, store: Store) -> int:
    _need(store)
    if args.queue:
        items = probe_mod.pending(store, max_age_days=args.max_age)
        if args.json:
            _out(items)
            return 0
        if not items:
            print("所有只读能力都是新鲜的，无需探测")
            return 0
        for it in items:
            print(f"{it['method']:<48}{it['name']}")
        print()
        print("回填：neopilot.py probe --report <method>=ok|fail|skip [--note ...]")
        return 0

    if args.report:
        ok = 0
        for pair in args.report:
            method, _, status = pair.partition("=")
            probe_mod.report(store, method.strip(), status.strip() or "ok", args.note or "")
            ok += 1
        print(f"已记录 {ok} 条探测结果")
        return 0

    counts = probe_mod.summary(store)
    if args.json:
        _out(counts)
        return 0
    print("能力探测状态")
    for k in ("ok", "fail", "skip", "untested"):
        print(f"  {k:<10}{counts.get(k, 0)}")
    return 0


def cmd_brief(args, store: Store) -> int:
    _need(store)
    run = store.find_run(args.run_id)
    text = brief_mod.brief(run)
    if args.json:
        _out({"run_id": run["run_id"], "routine": run["routine"],
              "status": run["status"], "brief": text})
    else:
        print(text)
    return 0


def cmd_snapshot(args, store: Store) -> int:
    _need(store)
    path = Path(args.out) if args.out else (store.data_dir / "app_snapshot.json")
    snap_mod.write(store, path)
    if args.json:
        print(path.read_text(encoding="utf-8"))
    else:
        print(f"{path}  ({path.stat().st_size} B)")
    return 0


def cmd_dashboard(args, store: Store) -> int:
    _need(store)
    path = Path(args.out) if args.out else store.out_dir / "dashboard.html"
    render.write(store, path)
    print(path)
    return 0


def cmd_upcoming(args, store: Store) -> int:
    _need(store)
    ups = engine.upcoming(store, limit=args.limit)
    if args.json:
        _out(ups)
        return 0
    if not ups:
        print("没有排表中的例程")
        return 0
    for u in ups:
        flag = "  [缺配置]" if u.get("blocked") else ""
        print(f"{u['at']}  {u['name']}{flag}  （{u['in_hours']} 小时后）")
    return 0


def cmd_doctor(args, store: Store) -> int:
    problems = []
    info = {}
    if not store.exists():
        problems.append("未初始化：先跑 neopilot init")
    rs = store.routines() if store.exists() else []
    info["routine_count"] = len(rs)
    for r in rs:
        for s in r.get("steps", []):
            if not catalog.exists(s["cap"]):
                problems.append(f"{r['id']} 引用未知能力 {s['cap']}")
        if r.get("schedule") and len(r["schedule"].split()) != 5:
            problems.append(f"{r['id']} 的 cron 表达式不是 5 段")
    crons = [r for r in rs if r.get("schedule")]
    info["scheduled"] = len(crons)
    for r in crons:
        nxt = engine.next_occurrence(r["schedule"])
        if nxt is None:
            problems.append(f"{r['id']} 在 8 天内不会触发")
    info["capabilities"] = catalog.stats()["total"]
    info["runs"] = len(store.runs(limit=500)) if store.exists() else 0
    info["storage"] = store.usage()["human"] if store.exists() else "0 B"
    if args.json:
        _out({"ok": not problems, "problems": problems, "info": info})
    else:
        print("引擎体检")
        for k, v in info.items():
            print(f"  {k:<14}{v}")
        print()
        if problems:
            print("发现 %d 个问题：" % len(problems))
            for p in problems:
                print("  ✗ " + p)
        else:
            print("✓ 未发现结构性问题")
    return 0 if not problems else 1


def cmd_prune(args, store: Store) -> int:
    n = store.prune_runs(keep=args.keep)
    print(f"清掉 {n} 条旧运行记录")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="neopilot", description="STEPX Neo 个人自动化中枢")
    p.add_argument("--home", help="状态目录，默认 ./.neopilot")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="初始化状态目录").set_defaults(func=cmd_init)

    sp = sub.add_parser("seed", help="写入预置例程")
    sp.add_argument("--force", action="store_true")
    sp.set_defaults(func=cmd_seed)

    sp = sub.add_parser("routines", help="列出例程")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_routines)

    sp = sub.add_parser("show", help="查看例程细节")
    sp.add_argument("id")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_show)

    sp = sub.add_parser("enable", help="启用例程")
    sp.add_argument("id")
    sp.set_defaults(func=lambda a, s: cmd_toggle(a, s, True))

    sp = sub.add_parser("disable", help="停用例程")
    sp.add_argument("id")
    sp.set_defaults(func=lambda a, s: cmd_toggle(a, s, False))

    sp = sub.add_parser("run", help="启动一次运行")
    sp.add_argument("id")
    sp.add_argument("--json", action="store_true")
    sp.add_argument("--trigger", default="manual")
    sp.add_argument("--ctx", nargs="*", help="模板变量，如 city=示例市")
    sp.set_defaults(func=cmd_run)

    sp = sub.add_parser("next", help="取下一步")
    sp.add_argument("run_id")
    sp.set_defaults(func=cmd_next)

    sp = sub.add_parser("report", help="回填某一步的结果")
    sp.add_argument("run_id")
    sp.add_argument("step")
    sp.add_argument("--status", required=True, choices=["ok", "fail", "skip"])
    sp.add_argument("--data")
    sp.add_argument("--error")
    sp.add_argument("--ms", type=int)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_report)

    sp = sub.add_parser("status", help="查看运行状态")
    sp.add_argument("run_id")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_status)

    sp = sub.add_parser("runs", help="列出运行记录")
    sp.add_argument("--limit", type=int, default=20)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_runs)

    sp = sub.add_parser("cancel", help="取消运行")
    sp.add_argument("run_id")
    sp.add_argument("--reason")
    sp.set_defaults(func=cmd_cancel)

    sp = sub.add_parser("due", help="看过往窗口内有没有到点的例程")
    sp.add_argument("--window", type=int, default=15)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_due)

    sp = sub.add_parser("tick", help="启动所有到点且未跑的例程")
    sp.add_argument("--window", type=int, default=15)
    sp.add_argument("--force", action="store_true", help="缺配置也强行启动")
    sp.add_argument("--claim", action="store_true", help="启动后直接输出待执行队列")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_tick)

    sp = sub.add_parser("crontab", help="输出可直接安装的 crontab 行")
    sp.add_argument("--python", default="python3")
    sp.add_argument("--entry", default="neopilot.py")
    sp.set_defaults(func=cmd_crontab)

    sp = sub.add_parser("work", help="列出所有未完成运行的待执行步骤")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_work)

    sp = sub.add_parser("audit", help="查看写操作审计")
    sp.add_argument("--limit", type=int, default=30)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_audit)

    sp = sub.add_parser("probe", help="能力可用性探测")
    sp.add_argument("--queue", action="store_true", help="列出待探测的能力")
    sp.add_argument("--report", nargs="*", help="回填探测结果，如 method=ok")
    sp.add_argument("--note", help="附注")
    sp.add_argument("--max-age", type=int, default=7, help="结果有效天数")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_probe)

    sp = sub.add_parser("brief", help="把运行结果翻译成人话")
    sp.add_argument("run_id")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_brief)

    sp = sub.add_parser("snapshot", help="生成给 App 消费的快照 JSON")
    sp.add_argument("-o", "--out")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_snapshot)

    sp = sub.add_parser("dashboard", help="生成驾驶舱 HTML")
    sp.add_argument("-o", "--out")
    sp.set_defaults(func=cmd_dashboard)

    sp = sub.add_parser("upcoming", help="接下来要跑的例程")
    sp.add_argument("--limit", type=int, default=8)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_upcoming)

    sp = sub.add_parser("doctor", help="引擎体检")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_doctor)

    sp = sub.add_parser("prune", help="清理旧运行记录")
    sp.add_argument("--keep", type=int, default=200)
    sp.set_defaults(func=cmd_prune)

    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    store = Store(Path(args.home) if args.home else None)
    return args.func(args, store)


if __name__ == "__main__":
    sys.exit(main())
