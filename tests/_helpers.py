# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Noboru Harada
"""Shared test helpers. Importing this also puts ``src/`` and ``scripts/`` on the
path so the suite runs under both ``pytest`` and ``python -m unittest``.
"""

from __future__ import annotations

import itertools
import os
import pathlib
import sys

_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "src"))

from cc_agent_messenger.config import Config  # noqa: E402
from cc_agent_messenger.context import AppContext  # noqa: E402
from cc_agent_messenger.profile import CommandRule, Profile  # noqa: E402

_SOCK_COUNTER = itertools.count()


class FakeSlack:
    """Duck-typed stand-in for SlackEgress (no network, no slack_sdk)."""

    def __init__(
        self,
        ts_seq: list[str] | None = None,
        raise_exc: Exception | None = None,
        live: bool = True,
        scopes: list[str] | None = None,
        identity: dict[str, str] | None = None,
        is_member: bool = True,
        socket_ok: bool = True,
    ) -> None:
        self.calls: list[dict[str, object]] = []
        self.reactions: list[tuple[str, str, str, str]] = []
        self._ts = iter(ts_seq or [f"{i}.{i}" for i in range(1, 20)])
        self._raise = raise_exc
        self._live = live
        # Capability-probe defaults: a healthy, fully-scoped bot.
        self._scopes = list(scopes) if scopes is not None else [
            "chat:write", "app_mentions:read", "groups:history",
            "groups:read", "reactions:read", "reactions:write", "commands",
        ]
        self._identity = identity or {"user": "testbot", "user_id": "U_BOT", "team": "T_TEST", "url": "https://example.test"}
        self._is_member = is_member
        self._socket_ok = socket_ok

    def post(self, channel_id: str, text: str, thread_ts: str | None, options: list[str] | None = None) -> str:
        self.calls.append({"channel_id": channel_id, "text": text, "thread_ts": thread_ts, "options": options})
        if self._raise is not None:
            raise self._raise
        return next(self._ts)

    def add_reaction(self, channel_id: str, timestamp: str, name: str) -> None:
        self.reactions.append(("add", channel_id, timestamp, name))

    def remove_reaction(self, channel_id: str, timestamp: str, name: str) -> None:
        self.reactions.append(("remove", channel_id, timestamp, name))

    def is_socket_mode_live(self) -> bool:
        return self._live

    def auth_scopes(self) -> tuple[dict[str, str], list[str]]:
        return dict(self._identity), list(self._scopes)

    def channel_membership(self, channel_id: str) -> tuple[bool, str]:
        return self._is_member, "#test"

    def socket_mode_reachable(self) -> tuple[bool, str]:
        return self._socket_ok, "Socket Mode connection mint ok"


def make_config(tmpdir: str, **overrides: object) -> Config:
    # AF_UNIX paths are length-limited; keep the socket short under /tmp.
    sock = f"/tmp/aism_{os.getpid()}_{next(_SOCK_COUNTER)}.sock"
    values: dict[str, object] = {
        "slack_bot_token": "xoxb-test",
        "slack_app_token": "xapp-test",
        "owner_slack_user_id": "U_OWNER",
        "allowed_slack_channel_id": "C_PRIVATE",
        "profile_path": os.path.join(tmpdir, "profile.json"),
        "audit_log_dir": os.path.join(tmpdir, "audit"),
        "kill_switch_path": os.path.join(tmpdir, "KILL_SWITCH"),
        "send_api_endpoint": sock,
        "inbound_event_path": os.path.join(tmpdir, "slack_message"),
    }
    values.update(overrides)
    return Config(**values)  # type: ignore[arg-type]


def make_profile() -> Profile:
    return Profile(
        version=1,
        commands=[
            CommandRule("explain_status", ["状況", "status"]),
            CommandRule("select_option", ["番", "選択"], takes_index=True),
            CommandRule("continue", ["継続", "continue"]),
        ],
        max_chunk_chars=3900,
    )


def make_ctx(cfg: Config, slack: object | None = None) -> AppContext:
    return AppContext(cfg=cfg, profile=make_profile(), slack=slack or FakeSlack())
