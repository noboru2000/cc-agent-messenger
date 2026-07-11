# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Noboru Harada
from __future__ import annotations

import glob
import json
import os
import tempfile
import unittest

import _helpers
from cc_agent_messenger import ingress, killswitch
from cc_agent_messenger.profile import Profile, CommandRule


def _profile() -> Profile:
    return Profile(
        version=1,
        commands=[
            CommandRule("explain_status", ["状況", "status"]),
            CommandRule("select_option", ["番", "選択"], takes_index=True),
        ],
        slash_map={"/status": "explain_status", "/select": "select_option"},
        reaction_map={"one": {"trigger": "select_option", "args": {"index": 1}}},
        interpretation_mode="flexible",
    )


class EnsureEventFileTests(unittest.TestCase):
    def test_creates_dir_and_empty_file(self) -> None:
        d = tempfile.mkdtemp()
        path = os.path.join(d, "tmp", ".slack_message")
        self.assertFalse(os.path.exists(path))
        ingress.ensure_event_file(path)
        self.assertTrue(os.path.isfile(path))  # tail -F/-f now has a target
        self.assertEqual(os.path.getsize(path), 0)

    def test_preserves_existing_content(self) -> None:
        d = tempfile.mkdtemp()
        path = os.path.join(d, "tmp", ".slack_message")
        ingress.ensure_event_file(path)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write('{"v":1}\n')
        ingress.ensure_event_file(path)  # idempotent — must not truncate
        self.assertEqual(open(path, encoding="utf-8").read(), '{"v":1}\n')


class IngressTests(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = tempfile.mkdtemp()
        self.cfg = _helpers.make_config(self.dir, inbound_event_path=os.path.join(self.dir, "events.jsonl"))
        self.ctx = _helpers.make_ctx(self.cfg)
        self.ctx.profile = _profile()

    def _events(self) -> list[dict]:
        path = self.cfg.inbound_event_path
        if not os.path.exists(path):
            return []
        with open(path, encoding="utf-8") as handle:
            return [json.loads(line) for line in handle.read().splitlines()]

    def _audit(self) -> list[dict]:
        rows: list[dict] = []
        for path in glob.glob(os.path.join(self.cfg.audit_log_dir, "*.jsonl")):
            with open(path, encoding="utf-8") as handle:
                rows.extend(json.loads(line) for line in handle.read().splitlines())
        return rows

    def test_authorized_mention_appends_one_line(self) -> None:
        ev = ingress.handle_mention("C_PRIVATE", "U_OWNER", "<@U_BOT> 最新の状況を説明して", "100.1", "100.1", self.ctx)
        self.assertIsNotNone(ev)
        events = self._events()
        self.assertEqual(len(events), 1)
        row = events[0]
        self.assertEqual(row["source"], "mention")
        self.assertEqual(row["trigger"], "explain_status")
        self.assertEqual(row["text"], "最新の状況を説明して")  # mention stripped
        self.assertTrue(row["correlation_id"])

    def test_unauthorized_user_not_appended(self) -> None:
        ingress.handle_mention("C_PRIVATE", "U_INTRUDER", "<@U_BOT> 状況", "1.1", "1.1", self.ctx)
        self.assertEqual(self._events(), [])
        self.assertEqual(self._audit()[0]["outcome"], "ignored")

    def test_wrong_channel_not_appended(self) -> None:
        ingress.handle_mention("C_OTHER", "U_OWNER", "<@U_BOT> 状況", "1.1", "1.1", self.ctx)
        self.assertEqual(self._events(), [])

    def test_killswitch_blocks_append(self) -> None:
        killswitch.engage(self.cfg.kill_switch_path)
        ingress.handle_mention("C_PRIVATE", "U_OWNER", "<@U_BOT> 状況", "1.1", "1.1", self.ctx)
        self.assertEqual(self._events(), [])

    def test_slash_deterministic_trigger(self) -> None:
        ingress.handle_slash("C_PRIVATE", "U_OWNER", "/select", "2", "trig", self.ctx)
        row = self._events()[0]
        self.assertEqual(row["source"], "slash")
        self.assertEqual(row["trigger"], "select_option")
        self.assertEqual(row["args"]["index"], 2)

    def test_button_action_value_parsed(self) -> None:
        ingress.handle_action("C_PRIVATE", "U_OWNER", "select_option:3", "9.9", "100.1", self.ctx)
        row = self._events()[0]
        self.assertEqual(row["source"], "button")
        self.assertEqual(row["trigger"], "select_option")
        self.assertEqual(row["args"]["index"], 3)

    def test_reaction_mapped(self) -> None:
        ingress.handle_reaction("C_PRIVATE", "U_OWNER", "one", "100.1", self.ctx)
        row = self._events()[0]
        self.assertEqual(row["source"], "reaction")
        self.assertEqual(row["trigger"], "select_option")
        self.assertEqual(row["args"]["index"], 1)

    def test_flexible_unmatched_appends_null_trigger(self) -> None:
        ev = ingress.handle_mention("C_PRIVATE", "U_OWNER", "<@U_BOT> 雑談です", "1.1", "1.1", self.ctx)
        self.assertIsNotNone(ev)
        self.assertIsNone(self._events()[0]["trigger"])

    def test_should_ingest_message_dedup(self) -> None:
        # thread reply, no bot mention -> ingest
        self.assertTrue(ingress.should_ingest_message({"thread_ts": "1.1", "text": "継続"}, "U_BOT", "B_BOT"))
        # bot-mentioned thread reply -> skip (app_mention handles it)
        self.assertFalse(ingress.should_ingest_message({"thread_ts": "1.1", "text": "<@U_BOT> 継続"}, "U_BOT", "B_BOT"))
        # bot-ID mention in a thread has no app_mention counterpart -> ingest
        self.assertTrue(ingress.should_ingest_message({"thread_ts": "1.1", "text": "<@B_BOT> 継続"}, "U_BOT", "B_BOT"))
        # top-level (no thread) -> skip
        self.assertFalse(ingress.should_ingest_message({"text": "継続"}, "U_BOT", "B_BOT"))
        # iOS bot-ID mention arrives only as a top-level message -> ingest
        self.assertTrue(ingress.should_ingest_message({"text": "<@B_BOT> !help"}, "U_BOT", "B_BOT"))
        # desktop bot-user-ID mention remains owned by app_mention
        self.assertFalse(ingress.should_ingest_message({"text": "<@U_BOT> !help"}, "U_BOT", "B_BOT"))
        # a pathological message containing both forms stays on app_mention
        self.assertFalse(ingress.should_ingest_message({"text": "<@U_BOT> <@B_BOT> !help"}, "U_BOT", "B_BOT"))
        # missing/wrong authorization metadata fails closed at top level
        self.assertFalse(ingress.should_ingest_message({"text": "<@B_BOT> !help"}, "U_BOT"))
        self.assertFalse(ingress.should_ingest_message({"text": "<@B_OTHER> !help"}, "U_BOT", "B_BOT"))
        # bot-authored / edits -> skip
        self.assertFalse(ingress.should_ingest_message({"thread_ts": "1.1", "bot_id": "B1"}, "U_BOT", "B_BOT"))
        self.assertFalse(ingress.should_ingest_message({"thread_ts": "1.1", "subtype": "message_changed"}, "U_BOT", "B_BOT"))

    def test_strict_unmatched_refused(self) -> None:
        self.cfg = _helpers.make_config(self.dir, inbound_event_path=os.path.join(self.dir, "events.jsonl"), interpretation_mode="strict")
        self.ctx.cfg = self.cfg
        ev = ingress.handle_mention("C_PRIVATE", "U_OWNER", "<@U_BOT> 雑談です", "1.1", "1.1", self.ctx)
        self.assertIsNone(ev)
        self.assertEqual(self._events(), [])
        self.assertEqual(self._audit()[-1]["outcome"], "refused")


if __name__ == "__main__":
    unittest.main()
