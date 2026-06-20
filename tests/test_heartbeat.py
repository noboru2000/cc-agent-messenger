# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Noboru Harada
from __future__ import annotations

import unittest

import _helpers  # noqa: F401  (sets up sys.path)
from cc_agent_messenger import heartbeat as hb


class ParseIntervalTests(unittest.TestCase):
    def test_keywords_and_units(self) -> None:
        self.assertEqual(hb.parse_interval("MR:10m"), 600)
        self.assertEqual(hb.parse_interval("every:5m"), 300)
        self.assertEqual(hb.parse_interval("10m"), 600)
        self.assertEqual(hb.parse_interval("2h"), 7200)

    def test_floor_and_misses(self) -> None:
        self.assertEqual(hb.parse_interval("5s"), hb.MIN_INTERVAL)  # clamped up
        self.assertIsNone(hb.parse_interval("off"))
        self.assertIsNone(hb.parse_interval("hello"))
        self.assertIsNone(hb.parse_interval(""))


class ApplyModeTests(unittest.TestCase):
    def test_away_on(self) -> None:
        st = hb.apply_mode(hb.KeepAliveState(), "away", '!away MR:1m "progress & blockers"', now=100.0)
        self.assertTrue(st.enabled)
        self.assertTrue(st.away)
        self.assertEqual(st.interval_s, 60)
        self.assertEqual(st.content, "progress & blockers")
        self.assertEqual(st.last_activity, 100.0)

    def test_keepalive_off_disables(self) -> None:
        st = hb.KeepAliveState(enabled=True, away=True)
        hb.apply_mode(st, "keepalive", "!keepalive off", now=0.0)
        self.assertFalse(st.enabled)

    def test_back_exits(self) -> None:
        st = hb.KeepAliveState(enabled=True, away=True)
        hb.apply_mode(st, "back", "!back", now=0.0)
        self.assertFalse(st.away)
        self.assertFalse(st.enabled)


class DueTests(unittest.TestCase):
    def test_disabled_never_due(self) -> None:
        self.assertFalse(hb.due(hb.KeepAliveState(enabled=False, interval_s=60), now=10_000))

    def test_reset_on_activity(self) -> None:
        st = hb.KeepAliveState(enabled=True, interval_s=60, last_activity=0.0, last_tick=0.0)
        self.assertFalse(hb.due(st, now=59))
        self.assertTrue(hb.due(st, now=60))
        st.last_activity = 65.0  # a real message restarts the timer
        self.assertFalse(hb.due(st, now=120))  # only 55s of silence
        self.assertTrue(hb.due(st, now=126))   # 61s of silence


class SchedulerTests(unittest.TestCase):
    def test_due_events_and_tick(self) -> None:
        sched = hb.HeartbeatScheduler()
        sched.apply_mode("C1", "away", "!away MR:1m", now=0.0)
        self.assertEqual(sched.due_events(now=59), [])
        events = sched.due_events(now=60, owner_user_id="U_OWNER")
        self.assertEqual(len(events), 1)
        ev = events[0]
        self.assertEqual(ev.trigger, "keep_alive")
        self.assertEqual(ev.source, "timer")
        self.assertEqual(ev.channel_id, "C1")
        self.assertTrue(ev.args["away"])
        # tick restarts the timer -> not due again immediately
        self.assertEqual(sched.due_events(now=61), [])

    def test_note_activity_restarts(self) -> None:
        sched = hb.HeartbeatScheduler()
        sched.apply_mode("C1", "keepalive", "!keepalive MR:1m", now=0.0)
        sched.note_activity("C1", now=50.0)
        self.assertEqual(sched.due_events(now=100), [])   # 50s since activity
        self.assertEqual(len(sched.due_events(now=111)), 1)  # 61s since activity

    def test_unknown_channel_activity_is_noop(self) -> None:
        sched = hb.HeartbeatScheduler()
        sched.note_activity("C_NONE", now=1.0)  # no state created -> nothing due
        self.assertEqual(sched.due_events(now=10_000), [])


if __name__ == "__main__":
    unittest.main()
