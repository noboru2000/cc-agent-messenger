# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Noboru Harada
from __future__ import annotations

import io
import os
import tempfile
import threading
import unittest
from contextlib import redirect_stdout
from unittest import mock

import _helpers
from cc_agent_messenger import cli, sendapi


class UninstallTests(unittest.TestCase):
    def test_strip_gitignore_block(self) -> None:
        gi = "node_modules/\n*.log\n\n# cc-agent-messenger\n.cc-agent-messenger/\ntmp/\n*.sock\n"
        stripped = cli.strip_gitignore_block(gi)
        self.assertNotIn("# cc-agent-messenger", stripped)
        self.assertNotIn(".cc-agent-messenger/", stripped)
        self.assertIn("node_modules/", stripped)
        # idempotent: no block -> unchanged
        self.assertEqual(cli.strip_gitignore_block("a\nb\n"), "a\nb\n")

    def _scaffold(self) -> str:
        d = tempfile.mkdtemp()
        os.makedirs(os.path.join(d, ".claude", "skills", "cc-agent-messenger"))
        open(os.path.join(d, ".claude", "skills", "cc-agent-messenger", "SKILL.md"), "w").close()
        os.makedirs(os.path.join(d, ".cc-agent-messenger"))
        open(os.path.join(d, ".cc-agent-messenger", "config.toml"), "w").close()
        with open(os.path.join(d, ".gitignore"), "w", encoding="utf-8") as h:
            h.write("keep/\n\n# cc-agent-messenger\n.cc-agent-messenger/\ntmp/\n*.sock\n")
        return d

    def test_uninstall_keeps_config(self) -> None:
        d = self._scaffold()
        with redirect_stdout(io.StringIO()):
            cli.main(["uninstall", "--dir", d])
        self.assertFalse(os.path.exists(os.path.join(d, ".claude", "skills", "cc-agent-messenger")))
        self.assertTrue(os.path.isdir(os.path.join(d, ".cc-agent-messenger")))  # kept
        gi = open(os.path.join(d, ".gitignore"), encoding="utf-8").read()
        self.assertNotIn("# cc-agent-messenger", gi)
        self.assertIn("keep/", gi)

    def test_uninstall_purge_removes_config(self) -> None:
        d = self._scaffold()
        with redirect_stdout(io.StringIO()):
            cli.main(["uninstall", "--dir", d, "--purge"])
        self.assertFalse(os.path.isdir(os.path.join(d, ".cc-agent-messenger")))


class InitUpgradeTests(unittest.TestCase):
    def test_reinit_preserves_config_and_refreshes_skill(self) -> None:
        d = tempfile.mkdtemp()
        with redirect_stdout(io.StringIO()):
            cli.main(["init", "--dir", d])
        config = os.path.join(d, ".cc-agent-messenger", "config.toml")
        skill = os.path.join(d, ".claude", "skills", "cc-agent-messenger", "SKILL.md")
        # simulate a configured repo + a stale skill
        with open(config, "w", encoding="utf-8") as h:
            h.write('slack_bot_token = "xoxb-REAL"\n[[agent]]\nname = "stable-id"\ndisplay_name = "Project Claude"\n')
        open(skill, "w").close()  # truncate -> "stale"
        # re-run init (the upgrade path)
        with redirect_stdout(io.StringIO()):
            cli.main(["init", "--dir", d])
        self.assertIn("xoxb-REAL", open(config, encoding="utf-8").read())  # tokens preserved
        self.assertIn('display_name = "Project Claude"', open(config, encoding="utf-8").read())
        self.assertGreater(os.path.getsize(skill), 0)  # skill refreshed

    def test_refresh_profile_backs_up_and_regenerates(self) -> None:
        d = tempfile.mkdtemp()
        with redirect_stdout(io.StringIO()):
            cli.main(["init", "--dir", d])
        profile = os.path.join(d, ".cc-agent-messenger", "profile.json")
        with open(profile, "w", encoding="utf-8") as h:
            h.write('{"version": 1, "commands": [], "slash_map": {"/status": "explain_status"}}')
        with redirect_stdout(io.StringIO()):
            cli.main(["init", "--dir", d, "--refresh-profile"])
        self.assertTrue(os.path.exists(profile + ".bak"))  # old profile backed up
        import json

        self.assertIn("command_prefix", json.load(open(profile, encoding="utf-8")))


class GitignoreTests(unittest.TestCase):
    def _gitignore(self, d: str) -> str:
        return open(os.path.join(d, ".gitignore"), encoding="utf-8").read()

    def test_init_writes_current_block(self) -> None:
        d = tempfile.mkdtemp()
        with redirect_stdout(io.StringIO()):
            cli.main(["init", "--dir", d])
        gi = self._gitignore(d)
        self.assertIn(".cc-agent-messenger/", gi)
        self.assertIn(".claude/skills/cc-agent-messenger/", gi)
        self.assertNotIn("tmp/", gi)  # inbound now lives under .cc-agent-messenger/
        self.assertNotIn("*.sock", gi)
        self.assertEqual(gi.count("# cc-agent-messenger"), 1)

    def test_reinit_preserves_legacy_block(self) -> None:
        d = tempfile.mkdtemp()
        with open(os.path.join(d, ".gitignore"), "w", encoding="utf-8") as h:
            h.write("keep/\n\n# cc-agent-messenger\n.cc-agent-messenger/\ntmp/\n*.sock\n")
        with redirect_stdout(io.StringIO()):
            cli.main(["init", "--dir", d])
        gi = self._gitignore(d)
        self.assertEqual(gi.count("# cc-agent-messenger"), 1)  # single block, no dupe
        self.assertIn(".claude/skills/cc-agent-messenger/", gi)  # skill entry added
        self.assertIn("tmp/", gi)  # legacy entries kept (config may still use them)
        self.assertIn("*.sock", gi)
        self.assertIn("keep/", gi)  # unrelated entries preserved

    def test_init_is_idempotent(self) -> None:
        d = tempfile.mkdtemp()
        with redirect_stdout(io.StringIO()):
            cli.main(["init", "--dir", d])
        first = self._gitignore(d)
        with redirect_stdout(io.StringIO()):
            cli.main(["init", "--dir", d])
        self.assertEqual(first, self._gitignore(d))  # no churn on re-run


class BuildRequestTests(unittest.TestCase):
    def _args(self, argv: list[str]):
        return cli.build_parser().parse_args(argv)

    def test_build_send_request(self) -> None:
        req = cli.build_send_request(self._args(["send", "--text", "hi", "--thread", "1.1", "--correlation-id", "c1"]))
        self.assertEqual(req["op"], "send")
        self.assertEqual(req["text"], "hi")
        self.assertEqual(req["thread_ts"], "1.1")
        self.assertEqual(req["correlation_id"], "c1")
        self.assertTrue(req["mention_owner"])

    def test_no_mention_and_options(self) -> None:
        req = cli.build_send_request(self._args(["send", "--text", "x", "--no-mention", "--options", "1: A", "2: B"]))
        self.assertFalse(req["mention_owner"])
        self.assertEqual(req["options"], ["1: A", "2: B"])


class CliRoundTripTests(unittest.TestCase):
    def _serve(self):
        ctx = _helpers.make_ctx(_helpers.make_config(tempfile.mkdtemp()))
        stop, ready = threading.Event(), threading.Event()
        thread = threading.Thread(target=sendapi.serve, args=(ctx, stop, ready), daemon=True)
        thread.start()
        self.assertTrue(ready.wait(3))
        self.addCleanup(lambda: (stop.set(), thread.join(3)))
        return ctx

    def test_ping_via_cli(self) -> None:
        ctx = self._serve()
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = cli.main(["ping", "--endpoint", ctx.cfg.send_api_endpoint])
        self.assertEqual(code, 0)
        self.assertIn("alive", buf.getvalue())

    def test_send_via_cli(self) -> None:
        ctx = self._serve()
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = cli.main(["send", "--text", "hi", "--no-mention", "--endpoint", ctx.cfg.send_api_endpoint])
        self.assertEqual(code, 0)
        self.assertIn("posted", buf.getvalue())


class RestartTests(unittest.TestCase):
    def test_parses_to_cmd_restart(self) -> None:
        args = cli.build_parser().parse_args(["restart"])
        self.assertIs(args.func, cli.cmd_restart)
        self.assertTrue(args.ingress)  # ingress on by default

    def test_restart_stops_then_starts_daemon(self) -> None:
        args = cli.build_parser().parse_args(["restart"])
        with mock.patch.object(cli, "load_config", return_value=object()), \
             mock.patch.object(cli.lifecycle, "stop", return_value=True) as stop, \
             mock.patch("cc_agent_messenger.daemon.run") as run, \
             mock.patch("time.sleep"):
            with redirect_stdout(io.StringIO()):
                code = cli.cmd_restart(args)
        stop.assert_called_once()
        run.assert_called_once()
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
