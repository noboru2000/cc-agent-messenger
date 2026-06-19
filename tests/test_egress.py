# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Noboru Harada
from __future__ import annotations

import glob
import json
import os
import tempfile
import unittest

import _helpers
from cc_agent_messenger import killswitch
from cc_agent_messenger.egress import handle_ping, handle_send
from cc_agent_messenger.models import SendRequest


class EgressTests(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = tempfile.mkdtemp()
        self.cfg = _helpers.make_config(self.dir)
        self.slack = _helpers.FakeSlack()
        self.ctx = _helpers.make_ctx(self.cfg, self.slack)

    def _audit_rows(self) -> list[dict]:
        rows: list[dict] = []
        for path in glob.glob(os.path.join(self.cfg.audit_log_dir, "*.jsonl")):
            with open(path, encoding="utf-8") as handle:
                rows.extend(json.loads(line) for line in handle.read().splitlines())
        return rows

    def test_halted_when_killswitch_engaged(self) -> None:
        killswitch.engage(self.cfg.kill_switch_path)
        result = handle_send(SendRequest(text="hi"), self.ctx)
        self.assertEqual(result.status, "halted")
        self.assertEqual(self.slack.calls, [])
        self.assertEqual(self._audit_rows()[0]["outcome"], "halted")

    def test_posts_with_owner_mention(self) -> None:
        result = handle_send(SendRequest(text="done", thread_ts="100.1"), self.ctx)
        self.assertEqual(result.status, "posted")
        self.assertEqual(len(self.slack.calls), 1)
        call = self.slack.calls[0]
        self.assertEqual(call["channel_id"], "C_PRIVATE")
        self.assertEqual(call["thread_ts"], "100.1")
        self.assertTrue(str(call["text"]).startswith("<@U_OWNER> "))

    def test_no_mention(self) -> None:
        handle_send(SendRequest(text="x", mention_owner=False), self.ctx)
        self.assertEqual(self.slack.calls[0]["text"], "x")

    def test_oversize_splits(self) -> None:
        cfg = _helpers.make_config(self.dir, max_chunk_chars=100)
        ctx = _helpers.make_ctx(cfg, self.slack)
        long_text = "z" * 350
        result = handle_send(SendRequest(text=long_text, mention_owner=False), ctx)
        self.assertEqual(result.status, "posted")
        self.assertEqual(len(self.slack.calls), 4)
        self.assertEqual(len(result.message_ts), 4)

    def test_options_render_buttons_single_post(self) -> None:
        handle_send(SendRequest(text="choose", options=["1: A", "2: B"], mention_owner=False), self.ctx)
        self.assertEqual(len(self.slack.calls), 1)
        self.assertEqual(self.slack.calls[0]["options"], ["1: A", "2: B"])

    def test_failed_on_slack_error(self) -> None:
        ctx = _helpers.make_ctx(self.cfg, _helpers.FakeSlack(raise_exc=RuntimeError("boom")))
        result = handle_send(SendRequest(text="x"), ctx)
        self.assertEqual(result.status, "failed")
        self.assertIn("boom", result.reason or "")
        self.assertEqual(self._audit_rows()[-1]["outcome"], "failed")

    def test_ping_alive(self) -> None:
        result = handle_ping(self.ctx)
        self.assertEqual(result.status, "alive")
        self.assertEqual(result.to_wire().get("socket_mode"), True)

    def test_ping_halted_when_killswitch(self) -> None:
        killswitch.engage(self.cfg.kill_switch_path)
        self.assertEqual(handle_ping(self.ctx).status, "halted")


if __name__ == "__main__":
    unittest.main()
