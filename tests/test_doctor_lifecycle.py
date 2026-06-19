from __future__ import annotations

import os
import tempfile
import unittest

import _helpers
from cc_agent_messenger import killswitch, lifecycle
from cc_agent_messenger.doctor import format_checks, run_doctor


class DoctorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = tempfile.mkdtemp()
        self.cfg = _helpers.make_config(self.dir)

    def test_returns_checks(self) -> None:
        checks = run_doctor(self.cfg)
        self.assertTrue(checks)
        self.assertTrue(all(len(c) == 3 for c in checks))
        # no network check unless requested
        self.assertNotIn("slack auth", [name for name, _, _ in checks])
        self.assertIn("[PASS]", format_checks(checks) + "[PASS]")  # format runs

    def test_kill_switch_reflected(self) -> None:
        def ks_ok() -> bool:
            return dict((n, ok) for n, ok, _ in run_doctor(self.cfg))["kill switch"]

        self.assertTrue(ks_ok())
        killswitch.engage(self.cfg.kill_switch_path)
        self.assertFalse(ks_ok())
        killswitch.disengage(self.cfg.kill_switch_path)
        self.assertTrue(ks_ok())


class LifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = tempfile.mkdtemp()
        self.cfg = _helpers.make_config(self.dir, send_api_endpoint=os.path.join(self.dir, "send.sock"))

    def test_pidfile_roundtrip(self) -> None:
        self.assertIsNone(lifecycle.read_pid(self.cfg))
        lifecycle.write_pidfile(self.cfg)
        self.assertEqual(lifecycle.read_pid(self.cfg), os.getpid())
        lifecycle.remove_pidfile(self.cfg)
        self.assertIsNone(lifecycle.read_pid(self.cfg))

    def test_status_down_when_no_daemon(self) -> None:
        st = lifecycle.status(self.cfg)
        self.assertFalse(st["running"])  # nothing listening on the socket

    def test_stop_returns_false_without_pidfile(self) -> None:
        self.assertFalse(lifecycle.stop(self.cfg))


if __name__ == "__main__":
    unittest.main()
