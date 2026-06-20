# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Noboru Harada
from __future__ import annotations

import os
import tempfile
import unittest

import _helpers  # noqa: F401  (sets up sys.path)
from cc_agent_messenger import monitors

_CONFIG = """
[[monitor]]
id = "gpu"
every = "5m"
items = "GPU util, mem, temp, latest loss"
probe = "ssh gpu01 nvidia-smi"
alert = ["temperature.gpu > 85", "loss is NaN"]

[[monitor]]
id = "disk"
every = "1h"
items = "disk free"
enabled = false
"""


class LoadTests(unittest.TestCase):
    def test_load_monitors(self) -> None:
        path = os.path.join(tempfile.mkdtemp(), "config.toml")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(_CONFIG)
        jobs = {j.id: j for j in monitors.load_monitors(path)}
        self.assertEqual(jobs["gpu"].interval_s, 300)
        self.assertEqual(jobs["gpu"].probe, "ssh gpu01 nvidia-smi")
        self.assertEqual(jobs["gpu"].alert, ["temperature.gpu > 85", "loss is NaN"])
        self.assertTrue(jobs["gpu"].enabled)
        self.assertEqual(jobs["disk"].interval_s, 3600)
        self.assertFalse(jobs["disk"].enabled)

    def test_load_missing_returns_empty(self) -> None:
        self.assertEqual(monitors.load_monitors("/nonexistent/config.toml"), [])

    def test_load_skips_entry_without_id(self) -> None:
        # a [[monitor]] missing `id` must be skipped, not crash the daemon
        path = os.path.join(tempfile.mkdtemp(), "config.toml")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write('[[monitor]]\nevery = "5m"\nitems = "x"\n\n[[monitor]]\nid = "ok"\nevery = "1m"\n')
        jobs = monitors.load_monitors(path)
        self.assertEqual([j.id for j in jobs], ["ok"])


class SchedulerTests(unittest.TestCase):
    def _sched(self) -> monitors.MonitorScheduler:
        return monitors.MonitorScheduler([monitors.MonitorJob(id="gpu", interval_s=300, items="x")])

    def test_fixed_cadence_not_reset_by_activity(self) -> None:
        sched = self._sched()
        self.assertEqual(sched.due_events(now=299, channel_id="C1"), [])
        events = sched.due_events(now=300, channel_id="C1", owner_user_id="U")
        self.assertEqual(len(events), 1)
        ev = events[0]
        self.assertEqual(ev.trigger, "monitor_tick")
        self.assertEqual(ev.args["job_id"], "gpu")
        self.assertEqual(ev.channel_id, "C1")
        # tick advanced last_tick; next not due until +interval (fixed cadence)
        self.assertEqual(sched.due_events(now=599, channel_id="C1"), [])
        self.assertEqual(len(sched.due_events(now=600, channel_id="C1")), 1)

    def test_disabled_job_never_fires(self) -> None:
        sched = monitors.MonitorScheduler([monitors.MonitorJob(id="d", interval_s=60, enabled=False)])
        self.assertEqual(sched.due_events(now=10_000, channel_id="C1"), [])


class ApplyWatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.sched = monitors.MonitorScheduler([monitors.MonitorJob(id="gpu", interval_s=300, items="metrics")])

    def test_list(self) -> None:
        out = monitors.apply_watch(self.sched, "!watch list", now=0)
        self.assertIn("gpu", out)
        self.assertIn("ON", out)

    def test_off_then_on(self) -> None:
        monitors.apply_watch(self.sched, "!watch gpu off", now=0)
        self.assertFalse(self.sched.jobs["gpu"].enabled)
        monitors.apply_watch(self.sched, "!watch gpu on", now=10)
        self.assertTrue(self.sched.jobs["gpu"].enabled)

    def test_define_new_job(self) -> None:
        out = monitors.apply_watch(self.sched, '!watch disk every:10m "disk free on gpu01"', now=0)
        self.assertIn("disk", out)
        job = self.sched.jobs["disk"]
        self.assertEqual(job.interval_s, 600)
        self.assertEqual(job.items, "disk free on gpu01")
        self.assertTrue(job.enabled)

    def test_unknown_off(self) -> None:
        out = monitors.apply_watch(self.sched, "!watch nope off", now=0)
        self.assertIn("unknown", out)

    def test_off_inside_quoted_items_does_not_disable(self) -> None:
        monitors.apply_watch(self.sched, '!watch gpu every:5m "alert then back off"', now=0)
        self.assertTrue(self.sched.jobs["gpu"].enabled)  # the "off" in items must not toggle
        self.assertEqual(self.sched.jobs["gpu"].items, "alert then back off")

    def test_define_preserves_items_on_interval_only_update(self) -> None:
        monitors.apply_watch(self.sched, "!watch gpu every:10m", now=0)
        self.assertEqual(self.sched.jobs["gpu"].interval_s, 600)
        self.assertEqual(self.sched.jobs["gpu"].items, "metrics")  # unchanged

    def test_interval_clamped_and_minute_summary(self) -> None:
        monitors.apply_watch(self.sched, "!watch quick every:5s", now=0)
        self.assertEqual(self.sched.jobs["quick"].interval_s, 30)  # clamped to MIN
        self.assertIn("every 1m", monitors.apply_watch(self.sched, "!watch list", now=0))

    def test_is_structured(self) -> None:
        self.assertTrue(monitors.is_structured("!watch gpu off"))
        self.assertTrue(monitors.is_structured("watch list"))
        self.assertFalse(monitors.is_structured("GPUを5分ごとに監視して"))


class NoteMonitorsHookTests(unittest.TestCase):
    def setUp(self) -> None:
        from cc_agent_messenger import ingress

        self.ingress = ingress
        self.cfg = _helpers.make_config(tempfile.mkdtemp())
        self.ctx = _helpers.make_ctx(self.cfg)
        self.ctx.monitors = monitors.MonitorScheduler([monitors.MonitorJob(id="gpu", interval_s=300, items="m")])

    def test_none_scheduler_is_noop(self) -> None:
        ctx = _helpers.make_ctx(self.cfg)  # monitors=None
        self.ingress._note_monitors(ctx, "watch", "!watch gpu off")  # must not raise

    def test_structured_watch_applies(self) -> None:
        self.ingress._note_monitors(self.ctx, "watch", "!watch gpu off")
        self.assertFalse(self.ctx.monitors.jobs["gpu"].enabled)

    def test_natural_language_watch_does_not_apply(self) -> None:
        self.ingress._note_monitors(self.ctx, "watch", "GPUを5分ごとに監視して")
        self.assertTrue(self.ctx.monitors.jobs["gpu"].enabled)  # unchanged
        self.assertNotIn("GPUを5分ごとに監視して", self.ctx.monitors.jobs)  # no junk job


if __name__ == "__main__":
    unittest.main()
