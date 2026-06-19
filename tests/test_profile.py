from __future__ import annotations

import os
import unittest

import _helpers  # noqa: F401
from cc_agent_messenger.profile import (
    CommandRule,
    Profile,
    load_profile,
    match_command,
    split_for_slack,
    strip_command_prefix,
)

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_EXAMPLE = os.path.join(_ROOT, "src", "cc_agent_messenger", "assets", "profile.example.json")


class MatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.profile = load_profile(_EXAMPLE)

    def test_each_command_phrase(self) -> None:
        cases = {
            "生きてますか？": "health_check",
            "最新の状況を説明して": "explain_status",
            "不具合があれば報告して": "report_issues",
            "結果が出ていれば報告して": "report_results",
            "次に何をすべきか選択肢をあげて": "propose_options",
            "処理を継続": "continue",
        }
        for text, expected in cases.items():
            self.assertEqual(match_command(text, self.profile).trigger, expected, text)

    def test_select_option_index(self) -> None:
        match = match_command("2番でお願い", self.profile)
        self.assertEqual(match.trigger, "select_option")
        self.assertEqual(match.args.get("index"), 2)

    def test_unmatched_returns_none(self) -> None:
        self.assertIsNone(match_command("全く関係ない雑談", self.profile).trigger)

    def test_default_prefix_is_bang(self) -> None:
        self.assertEqual(self.profile.command_prefix, "!")

    def test_bang_resolves_each_command_exactly(self) -> None:
        cases = {
            "!help": "help",
            "!health": "health_check",
            "!status": "explain_status",
            "!issues": "report_issues",
            "!results": "report_results",
            "!options": "propose_options",
            "!continue": "continue",
            "!doctor": "system_doctor",
        }
        for text, expected in cases.items():
            self.assertEqual(match_command(text, self.profile).trigger, expected, text)

    def test_bang_select_carries_index(self) -> None:
        match = match_command("!select 2", self.profile)
        self.assertEqual(match.trigger, "select_option")
        self.assertEqual(match.args.get("index"), 2)

    def test_bang_unknown_token_falls_through(self) -> None:
        # "!chat …" is not a command; it flows on as free text (trigger None here).
        self.assertIsNone(match_command("!chat about something", self.profile).trigger)

    def test_configurable_prefix(self) -> None:
        profile = Profile(
            version=1,
            commands=[CommandRule("explain_status", ["status"]), CommandRule("select_option", ["select"], takes_index=True)],
            command_prefix="$",
        )
        self.assertEqual(match_command("$status", profile).trigger, "explain_status")
        self.assertEqual(match_command("$select 3", profile).args.get("index"), 3)

    def test_strip_command_prefix(self) -> None:
        self.assertEqual(strip_command_prefix("!status", "!"), ("status", True))
        self.assertEqual(strip_command_prefix("  !status", "!"), ("status", True))
        self.assertEqual(strip_command_prefix("状況", "!"), ("状況", False))
        self.assertEqual(strip_command_prefix("!status", ""), ("!status", False))


class SplitTests(unittest.TestCase):
    def test_short_is_single_chunk(self) -> None:
        self.assertEqual(split_for_slack("hello", 100), ["hello"])

    def test_long_splits_under_limit(self) -> None:
        text = "\n\n".join("x" * 40 for _ in range(10))  # 10 paragraphs
        chunks = split_for_slack(text, 100)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(c) <= 100 for c in chunks))

    def test_single_oversize_paragraph_hard_split(self) -> None:
        chunks = split_for_slack("y" * 250, 100)
        self.assertEqual(len(chunks), 3)
        self.assertTrue(all(len(c) <= 100 for c in chunks))
        self.assertEqual("".join(chunks), "y" * 250)


if __name__ == "__main__":
    unittest.main()
