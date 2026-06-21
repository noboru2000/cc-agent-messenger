# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Noboru Harada
"""Local configuration loading and validation.

Configuration is local-only; real tokens and host paths live under
``.cc-agent-messenger/`` and are never committed (NN8).
"""

from __future__ import annotations

import dataclasses
import os
import tomllib
from dataclasses import dataclass

DEFAULT_CONFIG_PATH = ".cc-agent-messenger/config.toml"
CONFIG_PATH_ENV = "CC_AGENT_MESSENGER_CONFIG"

# Keys with no default; load_config raises if any is missing.
_REQUIRED = (
    "slack_bot_token",
    "slack_app_token",
    "owner_slack_user_id",
    "allowed_slack_channel_id",
    "profile_path",
    "audit_log_dir",
    "kill_switch_path",
    "send_api_endpoint",
    "inbound_event_path",
)


@dataclass(frozen=True)
class Config:
    slack_bot_token: str
    slack_app_token: str
    owner_slack_user_id: str
    allowed_slack_channel_id: str
    profile_path: str
    audit_log_dir: str
    kill_switch_path: str
    send_api_endpoint: str
    inbound_event_path: str
    default_agent: str = "claude"
    interpretation_mode: str = "flexible"  # "flexible" | "strict" (§2.6)
    max_chunk_chars: int = 3900
    audit_retention_days: int = 30
    # Instant "thinking…" ack: the daemon posts a placeholder the moment a command
    # is received (pushing the owner immediately), then the reply edits it in place
    # via chat.update — one message goes "🤔 …" → the final answer. Opt-in.
    thinking_ack: bool = False
    thinking_text: str = "🤔 …"


class ConfigError(ValueError):
    """Raised when configuration is missing or invalid."""


def _coerce(name: str, value: object, target_type: type) -> object:
    if target_type is int and not isinstance(value, bool):
        try:
            return int(value)  # type: ignore[arg-type]
        except (TypeError, ValueError) as exc:
            raise ConfigError(f"config key '{name}' must be an int, got {value!r}") from exc
    return value


def load_config(path: str | None = None) -> Config:
    """Load configuration from a TOML file, then apply uppercase env overrides.

    Each field may be overridden by an env var named like the field in uppercase
    (e.g. ``SLACK_BOT_TOKEN``). Raises ``ConfigError`` if a required key is absent.
    """

    cfg_path = path or os.environ.get(CONFIG_PATH_ENV, DEFAULT_CONFIG_PATH)
    data: dict[str, object] = {}
    if os.path.exists(cfg_path):
        with open(cfg_path, "rb") as handle:
            data = tomllib.load(handle)

    fields = {f.name: f for f in dataclasses.fields(Config)}
    values: dict[str, object] = {}
    missing: list[str] = []
    for name, field_def in fields.items():
        env_value = os.environ.get(name.upper())
        if env_value is not None:
            raw: object = env_value
        elif name in data:
            raw = data[name]
        elif field_def.default is not dataclasses.MISSING:
            raw = field_def.default
        else:
            missing.append(name)
            continue
        target_type = type(field_def.default) if field_def.default is not dataclasses.MISSING else str
        values[name] = _coerce(name, raw, target_type)

    if missing:
        raise ConfigError(f"missing required config keys: {', '.join(sorted(missing))}")

    cfg = Config(**values)  # type: ignore[arg-type]
    if cfg.interpretation_mode not in ("flexible", "strict"):
        raise ConfigError(f"interpretation_mode must be 'flexible' or 'strict', got {cfg.interpretation_mode!r}")
    return cfg
