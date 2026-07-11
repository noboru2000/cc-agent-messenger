# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Noboru Harada
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

    def test_ingress_dir_creatable_passes(self) -> None:
        # tmp/ doesn't exist yet but its parent is writable -> daemon will create it.
        cfg = _helpers.make_config(self.dir, inbound_event_path=os.path.join(self.dir, "tmp", ".slack_message"))
        checks = dict((n, ok) for n, ok, _ in run_doctor(cfg))
        self.assertTrue(checks["ingress dir writable"])

    def test_kill_switch_reflected(self) -> None:
        def ks_ok() -> bool:
            return dict((n, ok) for n, ok, _ in run_doctor(self.cfg))["kill switch"]

        self.assertTrue(ks_ok())
        killswitch.engage(self.cfg.kill_switch_path)
        self.assertFalse(ks_ok())
        killswitch.disengage(self.cfg.kill_switch_path)
        self.assertTrue(ks_ok())

    def test_slack_ability_all_good(self) -> None:
        rows = run_doctor(self.cfg, check_slack=True, slack=_helpers.FakeSlack())
        got = dict((n, ok) for n, ok, _ in rows)
        for name in ("slack auth", "bot scopes", "channel access", "socket mode"):
            self.assertIn(name, got)
            self.assertTrue(got[name], name)

    def test_missing_reactions_scope_surfaced_not_failed(self) -> None:
        fake = _helpers.FakeSlack(scopes=["chat:write", "chat:write.customize", "app_mentions:read", "groups:history"])
        scope_row = next(r for r in run_doctor(self.cfg, check_slack=True, slack=fake) if r[0] == "bot scopes")
        self.assertTrue(scope_row[1])  # core present -> not a hard fail
        self.assertIn("reactions:write", scope_row[2])  # but it's surfaced

    def test_missing_core_scope_fails(self) -> None:
        fake = _helpers.FakeSlack(scopes=["chat:write.customize", "app_mentions:read", "groups:history"])  # no chat:write
        scope_row = next(r for r in run_doctor(self.cfg, check_slack=True, slack=fake) if r[0] == "bot scopes")
        self.assertFalse(scope_row[1])
        self.assertIn("chat:write", scope_row[2])

    def test_missing_groups_history_fails(self) -> None:
        fake = _helpers.FakeSlack(scopes=["chat:write", "chat:write.customize", "app_mentions:read"])
        scope_row = next(r for r in run_doctor(self.cfg, check_slack=True, slack=fake) if r[0] == "bot scopes")
        self.assertFalse(scope_row[1])
        self.assertIn("groups:history", scope_row[2])

    def test_missing_customize_scope_fails(self) -> None:
        fake = _helpers.FakeSlack(scopes=["chat:write", "app_mentions:read", "groups:history"])
        scope_row = next(r for r in run_doctor(self.cfg, check_slack=True, slack=fake) if r[0] == "bot scopes")
        self.assertFalse(scope_row[1])
        self.assertIn("chat:write.customize", scope_row[2])

    def test_not_in_channel_fails(self) -> None:
        fake = _helpers.FakeSlack(is_member=False)
        got = dict((n, ok) for n, ok, _ in run_doctor(self.cfg, check_slack=True, slack=fake))
        self.assertFalse(got["channel access"])

    def test_auth_failure_short_circuits(self) -> None:
        class Boom(_helpers.FakeSlack):
            def auth_scopes(self):  # noqa: ANN001, ANN201
                raise RuntimeError("invalid_auth")

        rows = run_doctor(self.cfg, check_slack=True, slack=Boom())
        got = dict((n, ok) for n, ok, _ in rows)
        self.assertFalse(got["slack auth"])
        self.assertNotIn("bot scopes", got)  # stopped after auth

    def test_live_receipt_posts_and_reacts(self) -> None:
        fake = _helpers.FakeSlack()
        rows = run_doctor(self.cfg, check_slack=True, live=True, slack=fake)
        got = dict((n, ok) for n, ok, _ in rows)
        self.assertTrue(got["live receipt 👀→✅"])
        # one probe post + the exact receipt sequence: add 👀, remove 👀, add ✅.
        self.assertEqual(len(fake.calls), 1)
        kinds = [(action, name) for action, _ch, _ts, name in fake.reactions]
        self.assertEqual(kinds, [("add", "eyes"), ("remove", "eyes"), ("add", "white_check_mark")])

    def test_live_implies_slack_via_cli_path(self) -> None:
        # live=True must trigger the slack probes too (cmd_doctor passes
        # check_slack=args.slack or args.live).
        rows = run_doctor(self.cfg, check_slack=True, live=True, slack=_helpers.FakeSlack())
        names = [n for n, _, _ in rows]
        self.assertIn("slack auth", names)
        self.assertIn("live receipt 👀→✅", names)

    def test_live_skipped_when_killswitch_engaged(self) -> None:
        killswitch.engage(self.cfg.kill_switch_path)
        try:
            fake = _helpers.FakeSlack()
            row = next(r for r in run_doctor(self.cfg, check_slack=True, live=True, slack=fake) if r[0] == "live receipt 👀→✅")
            self.assertFalse(row[1])
            self.assertIn("kill switch", row[2])
            self.assertEqual(fake.calls, [])  # nothing posted while halted
        finally:
            killswitch.disengage(self.cfg.kill_switch_path)

    def test_live_skipped_when_auth_fails(self) -> None:
        class Boom(_helpers.FakeSlack):
            def auth_scopes(self):  # noqa: ANN001, ANN201
                raise RuntimeError("invalid_auth")

        row = next(r for r in run_doctor(self.cfg, check_slack=True, live=True, slack=Boom()) if r[0] == "live receipt 👀→✅")
        self.assertFalse(row[1])
        self.assertIn("skipped", row[2])


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
