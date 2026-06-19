# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Noboru Harada
"""Thin wrapper around the Slack Web API for egress (the bot identity holder).

See ``docs/DETAILED_DESIGN.md`` §7.5. The bot token lives only here (P3/NN8);
callers never receive it. ``slack_sdk`` is imported lazily so the rest of the
package (and its unit tests) can run without the dependency installed.
"""

from __future__ import annotations

from .config import Config


def _build_button_blocks(text: str, options: list[str]) -> list[dict[str, object]]:
    """Render a section + one Block Kit button per option (§2.6 surface 2)."""

    elements = [
        {
            "type": "button",
            "text": {"type": "plain_text", "text": option[:75], "emoji": True},
            # value carries the trigger grammar, e.g. "select_option:2".
            "value": f"select_option:{index + 1}",
            "action_id": f"opt_{index + 1}",
        }
        for index, option in enumerate(options)
    ]
    return [
        {"type": "section", "text": {"type": "mrkdwn", "text": text}},
        {"type": "actions", "elements": elements},
    ]


class SlackEgress:
    """Posts outbound Slack messages as the project bot."""

    def __init__(self, cfg: Config) -> None:
        try:
            from slack_sdk import WebClient
        except ImportError as exc:  # pragma: no cover - depends on environment
            raise RuntimeError(
                "slack_sdk is required to post to Slack; run 'uv sync'"
            ) from exc
        self._cfg = cfg
        self._client = WebClient(token=cfg.slack_bot_token)

    def post(
        self,
        channel_id: str,
        text: str,
        thread_ts: str | None,
        options: list[str] | None = None,
    ) -> str:
        """Post a message and return its Slack timestamp (``ts``)."""

        kwargs: dict[str, object] = {"channel": channel_id, "text": text}
        if thread_ts:
            kwargs["thread_ts"] = thread_ts
        if options:
            kwargs["blocks"] = _build_button_blocks(text, options)
        response = self._client.chat_postMessage(**kwargs)
        return str(response["ts"])

    def is_socket_mode_live(self) -> bool:
        """Best-effort liveness: the bot token authenticates against Slack."""

        try:
            return bool(self._client.auth_test().get("ok"))
        except Exception:  # pragma: no cover - network dependent
            return False
