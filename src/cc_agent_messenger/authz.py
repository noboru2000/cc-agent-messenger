# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Noboru Harada
"""Owner/channel authorization (NN4).

See ``docs/DETAILED_DESIGN.md`` §7.2. Only the configured owner in the configured
private channel may drive the agents; everything else is denied.
"""

from __future__ import annotations

from .config import Config


def is_authorized(user_id: str, channel_id: str, cfg: Config) -> bool:
    """True only for the configured owner in the configured allowed channel."""

    return user_id == cfg.owner_slack_user_id and channel_id == cfg.allowed_slack_channel_id


def is_allowed_destination(channel_id: str, cfg: Config, extra_channels: tuple[str, ...] = ()) -> bool:
    """True when the post targets the allowed channel or a configured agent channel."""

    return channel_id == cfg.allowed_slack_channel_id or channel_id in extra_channels
