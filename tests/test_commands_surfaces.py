# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Noboru Harada
from __future__ import annotations

import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout

import _helpers
from cc_agent_messenger import cli, commands, heartbeat, ingress, killswitch, monitors, sendapi


class RoutePolicyTests(unittest.TestCase):
    def test_route_for(self) -> None:
        self.assertEqual(commands.route_for("help"), "daemon")
        self.assertEqual(commands.route_for("watch"), "both")
        self.assertEqual(commands.route_for("keepalive"), "both")
        self.assertEqual(commands.route_for("away"), "both")
        self.assertEqual(commands.route_for("back"), "both")
        self.assertEqual(commands.route_for("explain_status"), "agent")
        self.assertEqual(commands.route_for("health_check"), "agent")
        self.assertEqual(commands.route_for("system_doctor"), "agent")
        self.assertEqual(commands.route_for(None), "agent")
        self.assertEqual(commands.route_for("nope"), "agent")


class IpcWatchKeepaliveTests(unittest.TestCase):
    def _ctx(self):
        ctx = _helpers.make_ctx(_helpers.make_config(tempfile.mkdtemp()))
        ctx.monitors = monitors.MonitorScheduler([])
        ctx.heartbeat = heartbeat.HeartbeatScheduler()
        return ctx

    def test_watch_register_then_list(self) -> None:
        ctx = self._ctx()
        self.assertEqual(sendapi.dispatch({"op": "watch", "text": 'gpu every:15m "GPU温度"'}, ctx)["status"], "ok")
        listing = sendapi.dispatch({"op": "watch", "text": "list"}, ctx)
        self.assertEqual(listing["status"], "ok")
        self.assertIn("gpu", listing["summary"])

    def test_keepalive_set_then_status(self) -> None:
        ctx = self._ctx()
        setr = sendapi.dispatch({"op": "keepalive", "text": 'MR:10m "状況"'}, ctx)
        self.assertEqual(setr["status"], "ok")
        self.assertIn("10m", setr["summary"])
        status = sendapi.dispatch({"op": "keepalive", "text": ""}, ctx)  # read-only query
        self.assertIn("10m", status["summary"])

    def test_killswitch_halts_registration(self) -> None:
        ctx = self._ctx()
        killswitch.engage(ctx.cfg.kill_switch_path)
        self.assertEqual(sendapi.dispatch({"op": "watch", "text": "gpu off"}, ctx)["status"], "halted")
        self.assertEqual(sendapi.dispatch({"op": "keepalive", "text": "off"}, ctx)["status"], "halted")

    def test_monitors_unavailable_when_no_scheduler(self) -> None:
        ctx = _helpers.make_ctx(_helpers.make_config(tempfile.mkdtemp()))  # monitors/heartbeat = None
        self.assertEqual(sendapi.dispatch({"op": "watch", "text": "list"}, ctx)["status"], "failed")
        self.assertEqual(sendapi.dispatch({"op": "keepalive", "text": ""}, ctx)["status"], "failed")


class DaemonAnswerHelpTests(unittest.TestCase):
    def test_help_answered_by_daemon_not_forwarded(self) -> None:
        ctx = _helpers.make_ctx(_helpers.make_config(tempfile.mkdtemp()))
        ev = ingress._ingest(
            ctx, source="mention", channel_id="C_PRIVATE", user_id="U_OWNER",
            text="!help", ts="1.1", thread_ts="1.1", trigger="help", args={},
        )
        self.assertIsNone(ev)  # not appended / not forwarded to the agent
        self.assertTrue(ctx.slack.calls)  # the daemon posted the reply directly
        self.assertIn("使えるコマンド", ctx.slack.calls[0]["text"])
        self.assertFalse(os.path.exists(ctx.cfg.inbound_event_path))  # nothing written to ingress


class CommandsCliTests(unittest.TestCase):
    def test_parse_watch_keepalive(self) -> None:
        a = cli.build_parser().parse_args(["watch", "gpu", "every:15m"])
        self.assertIs(a.func, cli.cmd_watch)
        self.assertEqual(a.args, ["gpu", "every:15m"])
        b = cli.build_parser().parse_args(["keepalive", "MR:10m"])
        self.assertIs(b.func, cli.cmd_keepalive)

    def test_commands_output_route_and_all(self) -> None:
        args = cli.build_parser().parse_args(["commands", "--route", "--all"])
        buf = io.StringIO()
        with redirect_stdout(buf):
            cli.cmd_commands(args)
        out = buf.getvalue()
        self.assertIn("!watch [both]", out)
        self.assertIn("!help [daemon]", out)
        self.assertIn("CLI", out)
        self.assertIn("keepalive", out)


if __name__ == "__main__":
    unittest.main()
