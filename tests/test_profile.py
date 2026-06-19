from __future__ import annotations

import os
import unittest

import _helpers  # noqa: F401
from claude_messenger.profile import load_profile, match_command, split_for_slack

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_EXAMPLE = os.path.join(_ROOT, "src", "claude_messenger", "assets", "profile.example.json")


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
