# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Noboru Harada
from __future__ import annotations

import tempfile
import unittest

import _helpers
from cc_agent_messenger import egress, receipts
from cc_agent_messenger.models import SendRequest


class ReceiptTests(unittest.TestCase):
    def setUp(self) -> None:
        self.slack = _helpers.FakeSlack()
        self.cfg = _helpers.make_config(tempfile.mkdtemp())
        self.ctx = _helpers.make_ctx(self.cfg, slack=self.slack)
        self.ctx.receipts = receipts.ReceiptTracker()

    def test_receipt_adds_eyes_and_tracks(self) -> None:
        receipts.on_receipt(self.ctx, "C_PRIVATE", "111.1", "cid-1")
        self.assertIn(("add", "C_PRIVATE", "111.1", "eyes"), self.slack.reactions)
        self.assertEqual(self.ctx.receipts.pending["cid-1"], ("C_PRIVATE", "111.1"))

    def test_reply_swaps_to_check(self) -> None:
        receipts.on_receipt(self.ctx, "C_PRIVATE", "111.1", "cid-1")
        self.slack.reactions.clear()
        receipts.on_reply(self.ctx, "cid-1")
        self.assertEqual(
            self.slack.reactions,
            [("remove", "C_PRIVATE", "111.1", "eyes"), ("add", "C_PRIVATE", "111.1", "white_check_mark")],
        )
        self.assertNotIn("cid-1", self.ctx.receipts.pending)  # consumed

    def test_reply_without_receipt_is_noop(self) -> None:
        receipts.on_reply(self.ctx, "unknown")
        self.assertEqual(self.slack.reactions, [])

    def test_send_swaps_receipt_end_to_end(self) -> None:
        # a received command, then the live session's reply via the egress chokepoint
        receipts.on_receipt(self.ctx, "C_PRIVATE", "222.2", "cid-2")
        self.slack.reactions.clear()
        result = egress.handle_send(SendRequest(text="done", thread_ts=None, correlation_id="cid-2"), self.ctx)
        self.assertEqual(result.status, "posted")
        self.assertIn(("remove", "C_PRIVATE", "222.2", "eyes"), self.slack.reactions)
        self.assertIn(("add", "C_PRIVATE", "222.2", "white_check_mark"), self.slack.reactions)

    def test_best_effort_on_reaction_error(self) -> None:
        boom = _helpers.FakeSlack()

        def _raise(*a, **k):
            raise RuntimeError("no reactions:write scope")

        boom.add_reaction = _raise  # type: ignore[assignment]
        ctx = _helpers.make_ctx(self.cfg, slack=boom)
        ctx.receipts = receipts.ReceiptTracker()
        # must not raise even though add_reaction fails
        receipts.on_receipt(ctx, "C_PRIVATE", "333.3", "cid-3")


if __name__ == "__main__":
    unittest.main()
