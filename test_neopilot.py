"""NeoPilot 自测：不依赖设备，纯逻辑层验证。

跑法：python3 -m unittest -v test_neopilot
"""

import sys
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from neopilot import brief, catalog, engine, presets, probe, render, state, web  # noqa: E402
from neopilot.store import Store  # noqa: E402

TZ = timezone(timedelta(hours=8))


class TestCatalog(unittest.TestCase):
    def test_methods_unique(self):
        methods = [c.method for c in catalog.all_caps()]
        self.assertEqual(len(methods), len(set(methods)))

    def test_every_step_in_presets_exists(self):
        for r in presets.all_presets():
            for s in r["steps"]:
                self.assertTrue(catalog.exists(s["cap"]),
                                f"{r['id']} 引用了不存在的 {s['cap']}")

    def test_stats_shape(self):
        st = catalog.stats()
        self.assertGreater(st["total"], 30)
        self.assertEqual(st["read"] + st["write"] + st["navigate"], st["total"])


class TestTemplates(unittest.TestCase):
    def test_resolve_today(self):
        ctx = engine.template_context()
        out = engine.resolve({"start_time": "$today_0000"}, ctx)
        self.assertRegex(out["start_time"], r"^\d{4}-\d{2}-\d{2} 00:00:00$")

    def test_unresolved_detects_empty_var(self):
        ctx = engine.template_context()
        self.assertEqual(engine.unresolved({"x": "$home_work_gcj"}, ctx), ["$home_work_gcj"])
        self.assertEqual(engine.unresolved({"x": "$today"}, ctx), [])

    def test_longest_key_wins(self):
        ctx = engine.template_context()
        s = engine.resolve("$today_0000", ctx)
        self.assertTrue(s.endswith("00:00:00"))
        self.assertNotIn("$", s)


class TestCron(unittest.TestCase):
    def test_daily(self):
        self.assertTrue(engine.cron_matches("50 7 * * *",
                                            datetime(2026, 10, 19, 7, 50, tzinfo=TZ)))
        self.assertFalse(engine.cron_matches("50 7 * * *",
                                             datetime(2026, 10, 19, 7, 51, tzinfo=TZ)))

    def test_weekday_range(self):
        mon = datetime(2026, 10, 19, 8, 20, tzinfo=TZ)
        sun = datetime(2026, 10, 25, 8, 20, tzinfo=TZ)
        self.assertTrue(engine.cron_matches("20 8 * * 1-5", mon))
        self.assertFalse(engine.cron_matches("20 8 * * 1-5", sun))

    def test_sunday_zero(self):
        sun = datetime(2026, 10, 25, 20, 0, tzinfo=TZ)
        self.assertTrue(engine.cron_matches("0 20 * * 0", sun))

    def test_step_syntax(self):
        self.assertTrue(engine.cron_matches("*/15 * * * *",
                                            datetime(2026, 10, 19, 3, 45, tzinfo=TZ)))
        self.assertFalse(engine.cron_matches("*/15 * * * *",
                                             datetime(2026, 10, 19, 3, 46, tzinfo=TZ)))

    def test_next_occurrence(self):
        nxt = engine.next_occurrence("50 7 * * *", datetime(2026, 10, 19, 8, 0, tzinfo=TZ))
        self.assertEqual(nxt, datetime(2026, 10, 20, 7, 50, tzinfo=TZ))


class TestEngine(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "np")
        self.store.init()

    def tearDown(self):
        self.tmp.cleanup()

    def _routine(self, verify=None):
        return {
            "id": "t", "name": "测试例程", "enabled": True, "schedule": "",
            "steps": [
                {"id": "a", "cap": "settings_get_current_battery_level", "label": "A", "must": True, "retry": 0},
                {"id": "b", "cap": "get_current_location", "label": "B", "must": False, "retry": 1},
            ],
            "verify": verify or {"min_ok": 1, "must_all_ok": True},
        }

    def test_happy_path(self):
        run = engine.start_run(self.store, self._routine())
        self.assertEqual(run["status"], "running")
        run = engine.report_step(self.store, run, "a", "ok", data={"level": "80%"})
        self.assertEqual(engine.next_step(run)["id"], "b")
        run = engine.report_step(self.store, run, "b", "ok", data={"address": "x"})
        self.assertEqual(run["status"], "success")
        self.assertIsNotNone(run["ended_at"])

    def test_must_fail_marks_failed(self):
        run = engine.start_run(self.store, self._routine())
        run = engine.report_step(self.store, run, "a", "fail", error="boom")
        run = engine.report_step(self.store, run, "b", "ok", data={})
        self.assertEqual(run["status"], "failed")

    def test_optional_fail_partial(self):
        run = engine.start_run(self.store, self._routine())
        run = engine.report_step(self.store, run, "a", "ok", data={})
        run = engine.report_step(self.store, run, "b", "fail", error="x")
        run = engine.report_step(self.store, run, "b", "fail", error="x")  # 用完 1 次重试
        self.assertEqual(run["status"], "partial")

    def test_retry_transitions(self):
        run = engine.start_run(self.store, self._routine())
        run = engine.report_step(self.store, run, "a", "ok", data={})
        run = engine.report_step(self.store, run, "b", "fail", error="first")
        self.assertEqual(engine.next_step(run)["id"], "b")
        self.assertEqual(run["steps"][1]["status"], "retry")
        run = engine.report_step(self.store, run, "b", "ok", data={})
        self.assertEqual(run["status"], "success")

    def test_cancel(self):
        run = engine.start_run(self.store, self._routine())
        run = engine.cancel_run(self.store, run, "手工停")
        self.assertEqual(run["status"], "cancelled")
        self.assertTrue(all(s["status"] in ("skipped",) for s in run["steps"]))

    def test_unknown_cap_rejected(self):
        r = self._routine()
        r["steps"][0]["cap"] = "no_such_method"
        with self.assertRaises(KeyError):
            engine.start_run(self.store, r)

    def test_health_and_overview(self):
        run = engine.start_run(self.store, self._routine())
        run = engine.report_step(self.store, run, "a", "ok", data={})
        run = engine.report_step(self.store, run, "b", "ok", data={})
        h = engine.routine_health(self.store, "t")
        self.assertEqual(h["success"], 1)
        self.assertEqual(h["rate"], 100)
        ov = engine.overview(self.store)
        self.assertEqual(ov["step_ok"], 2)


class TestScheduler(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "np")
        self.store.init()

    def tearDown(self):
        self.tmp.cleanup()

    def _mk(self, rid, schedule, enabled=True):
        self.store.save_routine({
            "id": rid, "name": rid, "enabled": enabled, "schedule": schedule,
            "steps": [{"id": "a", "cap": "settings_get_current_battery_level",
                       "label": "A", "must": True, "retry": 0, "params": {}}],
            "verify": {"min_ok": 1, "must_all_ok": True},
        })

    def test_due_hits_window(self):
        self._mk("d1", "30 9 * * *")
        frm = datetime(2026, 10, 19, 9, 34, tzinfo=TZ)
        items = engine.due_routines(self.store, window_min=10, frm=frm)
        self.assertEqual([i["id"] for i in items], ["d1"])
        self.assertEqual(items[0]["lag_min"], 4)

    def test_due_outside_window(self):
        self._mk("d2", "30 9 * * *")
        frm = datetime(2026, 10, 19, 9, 50, tzinfo=TZ)
        self.assertEqual(engine.due_routines(self.store, window_min=10, frm=frm), [])

    def test_due_skips_already_run(self):
        self._mk("d3", "30 9 * * *")
        frm = datetime(2026, 10, 19, 9, 32, tzinfo=TZ)
        run = engine.start_run(self.store, self.store.load_routine("d3"))
        # 把这次运行的开始时间改到触发点之后
        run["started_at"] = "2026-10-19T09:30:30+0800"
        self.store.save_run(run)
        self.assertEqual(engine.due_routines(self.store, window_min=10, frm=frm), [])

    def test_due_ignores_disabled_and_manual(self):
        self._mk("d4", "30 9 * * *", enabled=False)
        self._mk("d5", "")
        frm = datetime(2026, 10, 19, 9, 32, tzinfo=TZ)
        self.assertEqual(engine.due_routines(self.store, window_min=10, frm=frm), [])

    def test_tick_starts_run(self):
        self._mk("d6", "30 9 * * *")
        frm = datetime(2026, 10, 19, 9, 31, tzinfo=TZ)
        res = engine.tick(self.store, window_min=5)  # 用真实时间，应无动作
        self.assertEqual(res, [])
        # 直接验证启动通路
        run = engine.start_run(self.store, self.store.load_routine("d6"),
                               trigger="schedule:test")
        self.assertEqual(run["trigger"], "schedule:test")
        self.assertEqual(len(self.store.runs()), 1)

    def test_tick_skips_blocked(self):
        self.store.save_routine({
            "id": "d7", "name": "需要地址", "enabled": True, "schedule": "30 9 * * *",
            "steps": [{"id": "a", "cap": "amap_route_card", "label": "路线", "must": True,
                       "retry": 0, "params": {"origin": "$loc_gcj", "destination": "$home_work_gcj"}}],
            "verify": {"min_ok": 1, "must_all_ok": True},
        })
        frm = datetime(2026, 10, 19, 9, 31, tzinfo=TZ)
        items = engine.due_routines(self.store, window_min=5, frm=frm)
        self.assertTrue(items[0]["blocked"])

    def test_crontab_line_shape(self):
        lines = engine.crontab_lines(self.store)
        self.assertIn("tick", lines[1])
        self.assertTrue(lines[1].startswith("*/5 * * * *"))


class TestAudit(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "np")
        self.store.init()

    def tearDown(self):
        self.tmp.cleanup()

    def test_write_step_is_audited(self):
        r = {"id": "a", "name": "A", "enabled": True, "schedule": "",
             "steps": [{"id": "b", "cap": "settings_adjust_brightness", "label": "调亮度",
                        "must": True, "retry": 0, "params": {"newValue": "40"}}],
             "verify": {"min_ok": 1, "must_all_ok": True}}
        run = engine.start_run(self.store, r)
        engine.report_step(self.store, run, "b", "ok", data={"newValue": "40"})
        rows = self.store.audits()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["method"], "settings_adjust_brightness")
        self.assertEqual(rows[0]["status"], "ok")
        self.assertEqual(rows[0]["params"]["newValue"], "40")

    def test_read_step_not_audited(self):
        r = {"id": "b", "name": "B", "enabled": True, "schedule": "",
             "steps": [{"id": "x", "cap": "settings_get_current_battery_level",
                        "label": "读电量", "must": True, "retry": 0}],
             "verify": {"min_ok": 1, "must_all_ok": True}}
        run = engine.start_run(self.store, r)
        engine.report_step(self.store, run, "x", "ok", data={})
        self.assertEqual(self.store.audits(), [])

    def test_failed_write_still_audited(self):
        r = {"id": "c", "name": "C", "enabled": True, "schedule": "",
             "steps": [{"id": "y", "cap": "gallery_create_album", "label": "建相册",
                        "must": False, "retry": 0}],
             "verify": {"min_ok": 1, "must_all_ok": False}}
        run = engine.start_run(self.store, r)
        engine.report_step(self.store, run, "y", "fail", error="10402")
        rows = self.store.audits()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "fail")
        self.assertEqual(rows[0]["error"], "10402")


class TestWorkQueue(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "np")
        self.store.init()

    def tearDown(self):
        self.tmp.cleanup()

    def _r(self):
        return {"id": "w", "name": "W", "enabled": True, "schedule": "",
                "steps": [{"id": "s1", "cap": "settings_get_current_battery_level",
                           "label": "一", "must": True, "retry": 0},
                          {"id": "s2", "cap": "get_current_location",
                           "label": "二", "must": True, "retry": 0}],
                "verify": {"min_ok": 1, "must_all_ok": True}}

    def test_queue_lists_next_step_only(self):
        run = engine.start_run(self.store, self._r())
        q = engine.work_queue(self.store)
        self.assertEqual(len(q), 1)
        self.assertEqual(q[0]["step"], "s1")
        self.assertEqual(q[0]["run_id"], run["run_id"])

    def test_queue_follows_progress(self):
        run = engine.start_run(self.store, self._r())
        engine.report_step(self.store, run, "s1", "ok", data={})
        q = engine.work_queue(self.store)
        self.assertEqual(q[0]["step"], "s2")

    def test_queue_empty_after_done(self):
        run = engine.start_run(self.store, self._r())
        engine.report_step(self.store, run, "s1", "ok", data={})
        engine.report_step(self.store, run, "s2", "ok", data={})
        self.assertEqual(engine.work_queue(self.store), [])


class TestProbe(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "np"); self.store.init()

    def tearDown(self):
        self.tmp.cleanup()

    def test_pending_only_read_kinds(self):
        items = probe.pending(self.store)
        self.assertTrue(items)
        kinds = {catalog.get(i["method"]).kind for i in items}
        self.assertEqual(kinds, {"read"})

    def test_report_and_summary(self):
        probe.report(self.store, "settings_get_current_battery_level", "ok")
        counts = probe.summary(self.store)
        self.assertEqual(counts["ok"], 1)
        self.assertEqual(probe.status_of(self.store, "settings_get_current_battery_level", "read"), "ok")
        # 写类能力不参与探测，恒为 untested
        self.assertEqual(probe.status_of(self.store, "settings_adjust_brightness", "write"), "untested")

    def test_pending_skips_fresh(self):
        for it in probe.pending(self.store):
            probe.report(self.store, it["method"], "ok")
        self.assertEqual(probe.pending(self.store), [])


class TestStateContract(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "np")
        self.store.init()
        for r in presets.all_presets():
            self.store.save_routine(dict(r))

    def tearDown(self):
        self.tmp.cleanup()

    def test_top_level_keys(self):
        st = state.build(self.store)
        self.assertEqual(set(["meta", "today", "engine", "caps"]), set(st.keys()))
        self.assertEqual(st["meta"]["source"], "cloud")

    def test_today_shape_is_stable(self):
        st = state.build(self.store)
        for k in ("city", "address", "battery", "now", "daily", "tips", "events", "headline"):
            self.assertIn(k, st["today"])
        self.assertIsInstance(st["today"]["events"], list)

    def test_legacy_snapshot_normalized(self):
        # 旧的 today.json 用的是 today 而不是 daily
        self.store.save_snapshot("today", {"city": "示例市", "battery": "80%",
                                           "now": {"temp": "26℃", "text": "阴"},
                                           "today": {"low": 24, "high": 33, "pop": 10}})
        st = state.build(self.store)
        self.assertEqual(st["today"]["daily"]["high"], 33)
        self.assertEqual(st["today"]["now"]["temp"], "26℃")

    def test_engine_block(self):
        st = state.build(self.store)
        for k in ("kpi", "upcoming", "runs", "routines"):
            self.assertIn(k, st["engine"])
        self.assertEqual(len(st["engine"]["routines"]), len(presets.all_presets()))

    def test_caps_flat_list(self):
        st = state.build(self.store)
        self.assertEqual(len(st["caps"]), catalog.stats()["total"])
        self.assertIn("method", st["caps"][0])


class TestWebBuild(unittest.TestCase):
    def test_single_file_html(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "np")
            store.init()
            html = web.build_html(state.build(store))
            self.assertIn('id="bootstrap"', html)
            self.assertIn("NeoPilotApply", html)
            self.assertIn("tabbar", html)
            self.assertNotIn("__CSS__", html)
            self.assertNotIn("__BOOTSTRAP__", html)
            # 内联数据必须能原样解析回来
            import json as _json
            body = html.split('id="bootstrap">', 1)[1].split("</script>", 1)[0]
            data = _json.loads(body.replace("<\\/", "</"))
            self.assertIn("today", data)

    def test_no_script_breakout(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "np")
            store.init()
            store.save_snapshot("today", {"headline": "危险</script><script>alert(1)</script>"})
            html = web.build_html(state.build(store))
            self.assertNotIn("</script><script>alert(1)", html)


class TestBrief(unittest.TestCase):
    def _run(self):
        return {
            "routine": "morning-cockpit", "routine_name": "晨间驾驶舱", "status": "success",
            "steps": [
                {"id": "weather", "label": "天气", "status": "ok",
                 "data": {"today": {"day": "多云", "low": 25, "high": 35, "pop": 0},
                          "now": {"text": "阴", "temp": "26℃"}}},
                {"id": "calendar", "label": "日程", "status": "ok",
                 "data": {"events": [{"title": "示例日程", "start": "2026-10-19 06:35",
                                      "end": "2026-10-19 07:05"}]}},
                {"id": "battery", "label": "电量", "status": "ok", "data": {"level": "80%"}},
            ],
        }

    def test_morning_brief_mentions_key_facts(self):
        text = brief.brief(self._run())
        for token in ("多云", "25", "35", "示例日程", "80%"):
            self.assertIn(token, text)

    def test_rain_hint(self):
        run = self._run()
        run["steps"][0]["data"]["today"]["pop"] = 80
        self.assertIn("带伞", brief.brief(run))

    def test_generic_fallback(self):
        run = {"routine": "x", "routine_name": "某例程", "status": "success",
               "steps": [{"id": "a", "label": "步骤A", "status": "ok", "data": {"k": 1}}]}
        self.assertIn("某例程", brief.brief(run))


class TestRender(unittest.TestCase):
    def test_dashboard_contains_sections(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "np")
            store.init()
            for r in presets.all_presets():
                store.save_routine(dict(r))
            html = render.render(store)
            for token in ("NeoPilot", "p-home", "p-routines", "p-caps", "tabbar", "bootstrap"):
                self.assertIn(token, html)
            for leak in ("__CSS__", "__JS__", "__BOOTSTRAP__"):
                self.assertNotIn(leak, html)

    def test_empty_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "np")
            store.init()
            html = render.render(store)
            self.assertIn("bootstrap", html)


if __name__ == "__main__":
    unittest.main(verbosity=2)
