"""Kill switch (NN6).

See ``docs/DETAILED_DESIGN.md`` §7.3. v1 mechanism = presence of a file at the
configured path. Always available without the daemon: the owner can create or
remove the file directly.
"""

from __future__ import annotations

import os


def is_engaged(path: str) -> bool:
    """True when the kill-switch file exists (remote operation is halted)."""

    return os.path.exists(path)


def engage(path: str) -> None:
    """Engage the kill switch by creating the file (idempotent)."""

    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "a", encoding="utf-8"):
        pass


def disengage(path: str) -> None:
    """Disengage the kill switch by removing the file (idempotent)."""

    try:
        os.remove(path)
    except FileNotFoundError:
        pass
