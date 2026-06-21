# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Noboru Harada
"""Per-thread C1 session store (resume tokens).

Maps ``(agent_name, thread_ts)`` to a resume token so a headless C1 agent keeps
context across turns *within a Slack thread*. Persisted as JSON next to the other
local state under ``.cc-agent-messenger/`` (gitignored). No new config key — the
path is derived from ``profile_path``'s directory.

Token semantics differ per adapter: for ``claude`` it is the ``session_id`` the CLI
returns (captured after the first turn); other adapters may pre-generate their own.
"""

from __future__ import annotations

import json
import os
import threading

from .config import Config

_LOCK = threading.Lock()
_FILENAME = "sessions.json"


def store_path(cfg: Config) -> str:
    base = os.path.dirname(cfg.profile_path) or "."
    return os.path.join(base, _FILENAME)


def _key(agent_name: str, thread_ts: str | None) -> str:
    return f"{agent_name}::{thread_ts or '-'}"


def _load(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def get_session(cfg: Config, agent_name: str, thread_ts: str | None) -> str | None:
    """Return the stored resume token for this agent+thread, or None."""

    with _LOCK:
        return _load(store_path(cfg)).get(_key(agent_name, thread_ts))


def set_session(cfg: Config, agent_name: str, thread_ts: str | None, token: str | None) -> None:
    """Persist the resume token for this agent+thread (no-op if token is falsy)."""

    if not token:
        return
    path = store_path(cfg)
    with _LOCK:
        data = _load(path)
        data[_key(agent_name, thread_ts)] = token
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(data, handle)
        os.replace(tmp, path)  # atomic
