from __future__ import annotations

import os
import tempfile
import unittest

import _helpers  # noqa: F401  (sets up sys.path)
from claude_messenger.config import ConfigError, load_config

_MINIMAL_TOML = """
slack_bot_token = "xoxb-x"
slack_app_token = "xapp-x"
owner_slack_user_id = "U1"
allowed_slack_channel_id = "C1"
profile_path = "p.json"
audit_log_dir = "audit"
kill_switch_path = "K"
send_api_endpoint = "/tmp/s.sock"
inbound_event_path = "tmp/.slack_message"
max_chunk_chars = 1234
"""


class ConfigTests(unittest.TestCase):
    def _write(self, text: str) -> str:
        fd, path = tempfile.mkstemp(suffix=".toml")
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        self.addCleanup(os.remove, path)
        return path

    def test_load_from_toml(self) -> None:
        cfg = load_config(self._write(_MINIMAL_TOML))
        self.assertEqual(cfg.owner_slack_user_id, "U1")
        self.assertEqual(cfg.max_chunk_chars, 1234)  # int coercion
        self.assertEqual(cfg.interpretation_mode, "flexible")  # default

    def test_missing_required_raises(self) -> None:
        with self.assertRaises(ConfigError):
            load_config(self._write('slack_bot_token = "only"\n'))

    def test_env_override(self) -> None:
        path = self._write(_MINIMAL_TOML)
        os.environ["OWNER_SLACK_USER_ID"] = "U_ENV"
        self.addCleanup(os.environ.pop, "OWNER_SLACK_USER_ID", None)
        cfg = load_config(path)
        self.assertEqual(cfg.owner_slack_user_id, "U_ENV")

    def test_invalid_interpretation_mode_raises(self) -> None:
        with self.assertRaises(ConfigError):
            load_config(self._write(_MINIMAL_TOML + 'interpretation_mode = "loose"\n'))


if __name__ == "__main__":
    unittest.main()
