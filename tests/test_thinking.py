# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Noboru Harada
from __future__ import annotations

import tempfile
import unittest

import _helpers
from cc_agent_messenger import thinking
from cc_agent_messenger.egress import handle_send
from cc_agent_messenger.models import STATUS_POSTED, SendRequest


class ThinkingTrackerTests(unittest.TestCase):
    def test_record_resolve_is_one_shot(self) -> None:
        t = thinking.ThinkingTracker()
        t.record("c", "CH", "9.9")
        self.assertEqual(t.resolve("c"), ("CH", "9.9"))
        self.assertIsNone(t.resolve("c"))  # popped on first resolve

    def test_record_ignores_empty(self) -> None:
        t = thinking.ThinkingTracker()
        t.record("", "CH", "9.9")
        t.record("c", "CH", "")
        self.assertIsNone(t.resolve("c"))


class ThinkingFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = tempfile.mkdtemp()

    def _ctx(self, **cfg_overrides: object):
        cfg = _helpers.make_config(self.dir, **cfg_overrides)
        slack = _helpers.FakeSlack()
        ctx = _helpers.make_ctx(cfg, slack)
        ctx.thinking = thinking.ThinkingTracker()
        return ctx, slack

    def test_placeholder_posted_with_owner_mention_when_enabled(self) -> None:
        ctx, slack = self._ctx(thinking_ack=True)
        thinking.on_receipt(ctx, ctx.cfg.allowed_slack_channel_id, "100.1", "CID")
        self.assertEqual(len(slack.calls), 1)
        self.assertIn(f"<@{ctx.cfg.owner_slack_user_id}>", slack.calls[0]["text"])
        self.assertEqual(slack.calls[0]["thread_ts"], "100.1")

    def test_reply_morphs_placeholder_in_place(self) -> None:
        ctx, slack = self._ctx(thinking_ack=True)
        thinking.on_receipt(ctx, ctx.cfg.allowed_slack_channel_id, "100.1", "CID")
        placeholder_ts = slack.calls[0]  # the post; its ts was recorded
        res = handle_send(
            SendRequest(text="ready", correlation_id="CID", mention_owner=False, channel_id=ctx.cfg.allowed_slack_channel_id),
            ctx,
        )
        self.assertEqual(res.status, STATUS_POSTED)
        self.assertEqual(len(slack.calls), 1)  # no *new* post — just the placeholder
        self.assertEqual(len(slack.updates), 1)  # reply edited in place
        self.assertEqual(slack.updates[0]["text"], "ready")
        del placeholder_ts

    def test_disabled_posts_normally(self) -> None:
        ctx, slack = self._ctx()  # thinking_ack defaults False
        thinking.on_receipt(ctx, ctx.cfg.allowed_slack_channel_id, "100.1", "CID")
        self.assertEqual(slack.calls, [])  # no placeholder
        handle_send(
            SendRequest(text="ready", correlation_id="CID", mention_owner=False, channel_id=ctx.cfg.allowed_slack_channel_id),
            ctx,
        )
        self.assertEqual(len(slack.calls), 1)  # normal post
        self.assertEqual(slack.updates, [])  # no edit

    def test_no_placeholder_reply_posts_normally(self) -> None:
        # enabled, but no on_receipt ran for this correlation id (e.g. a proactive
        # message) -> egress just posts.
        ctx, slack = self._ctx(thinking_ack=True)
        handle_send(
            SendRequest(text="hi", correlation_id="OTHER", mention_owner=False, channel_id=ctx.cfg.allowed_slack_channel_id),
            ctx,
        )
        self.assertEqual(len(slack.calls), 1)
        self.assertEqual(slack.updates, [])

    def test_post_failure_is_swallowed(self) -> None:
        cfg = _helpers.make_config(self.dir, thinking_ack=True)
        slack = _helpers.FakeSlack(raise_exc=RuntimeError("boom"))
        ctx = _helpers.make_ctx(cfg, slack)
        ctx.thinking = thinking.ThinkingTracker()
        thinking.on_receipt(ctx, cfg.allowed_slack_channel_id, "", "CID")  # must not raise
        self.assertIsNone(thinking.resolve(ctx, "CID"))  # nothing recorded


if __name__ == "__main__":
    unittest.main()
