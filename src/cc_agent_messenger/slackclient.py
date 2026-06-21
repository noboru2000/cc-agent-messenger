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

    def update(self, channel_id: str, ts: str, text: str, options: list[str] | None = None) -> None:
        """Edit an existing message in place (``chat.update``) — used to morph a
        "thinking…" placeholder into the final reply (see ``thinking.py``)."""

        kwargs: dict[str, object] = {"channel": channel_id, "ts": ts, "text": text}
        if options:
            kwargs["blocks"] = _build_button_blocks(text, options)
        self._client.chat_update(**kwargs)

    def add_reaction(self, channel_id: str, timestamp: str, name: str) -> None:
        """Add an emoji reaction to a message (needs the ``reactions:write`` scope)."""

        self._client.reactions_add(channel=channel_id, timestamp=timestamp, name=name)

    def remove_reaction(self, channel_id: str, timestamp: str, name: str) -> None:
        """Remove an emoji reaction the bot previously added."""

        self._client.reactions_remove(channel=channel_id, timestamp=timestamp, name=name)

    def is_socket_mode_live(self) -> bool:
        """Best-effort liveness: the bot token authenticates against Slack."""

        try:
            return bool(self._client.auth_test().get("ok"))
        except Exception:  # pragma: no cover - network dependent
            return False

    # --- Capability probes (used by `doctor --slack`; see doctor.py) ----------
    # These let the diagnostics verify what the *installed* bot can actually do,
    # without ever handing the token back to the caller.

    def auth_scopes(self) -> tuple[dict[str, str], list[str]]:
        """Return ``(identity, granted_bot_scopes)`` for capability diagnostics.

        ``identity`` carries only non-secret fields (bot user, team, url). The
        granted scopes come from the ``x-oauth-scopes`` response header — the one
        place Slack reports what the installed token actually holds (so a missing
        ``reactions:write`` shows up here). Raises on auth/network failure.
        """

        resp = self._client.auth_test()
        data = resp.data if isinstance(resp.data, dict) else {}
        identity = {
            "user_id": str(data.get("user_id", "")),
            "user": str(data.get("user", "")),
            "team": str(data.get("team", "")),
            "url": str(data.get("url", "")),
        }
        raw = ""
        for key, value in (resp.headers or {}).items():
            if key.lower() == "x-oauth-scopes":
                raw = value or ""
                break
        scopes = [s.strip() for s in raw.split(",") if s.strip()]
        return identity, scopes

    def channel_membership(self, channel_id: str) -> tuple[bool, str]:
        """Return ``(bot_is_member, "#name")`` for the channel. Raises on API error
        (e.g. ``channel_not_found`` / missing ``groups:read``)."""

        resp = self._client.conversations_info(channel=channel_id)
        ch = resp.data.get("channel", {}) if isinstance(resp.data, dict) else {}
        name = ch.get("name") or channel_id
        return bool(ch.get("is_member")), f"#{name}"

    def socket_mode_reachable(self) -> tuple[bool, str]:
        """Verify the app-level token + Socket Mode via ``apps.connections.open``.

        Uses the ``xapp-`` app-level token (held in cfg, never returned). Mints a
        WSS endpoint but does not connect — read-only and non-disruptive to a
        running daemon. Raises on API error (e.g. Socket Mode disabled, bad token).
        """

        from slack_sdk import WebClient

        client = WebClient(token=self._cfg.slack_app_token)
        resp = client.apps_connections_open()
        ok = bool(resp.data.get("ok")) if isinstance(resp.data, dict) else False
        return ok, "Socket Mode connection mint ok"
