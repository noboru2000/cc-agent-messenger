"""Inbound command matcher + outbound reply rule (the v1 profile).

See ``docs/DETAILED_DESIGN.md`` §7.1 and §8. The profile is the concrete
instantiation of the closed command allowlist (FEASIBILITY_STUDY §3.3.3).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from .models import CommandMatch

# Extracts an option index from phrases like "1番", "選択 2", "option 3".
_INDEX_RE = re.compile(r"(\d+)")


@dataclass(frozen=True)
class CommandRule:
    trigger: str
    patterns: list[str]  # normalized substrings; any contained => match
    takes_index: bool = False


@dataclass(frozen=True)
class Profile:
    version: int
    commands: list[CommandRule]
    slash_map: dict[str, str] = field(default_factory=dict)
    reaction_map: dict[str, dict[str, object]] = field(default_factory=dict)
    interpretation_mode: str = "flexible"
    max_chunk_chars: int = 3900


def _normalize(text: str) -> str:
    return re.sub(r"\s+", "", text).lower()


def match_command(text: str, profile: Profile) -> CommandMatch:
    """Map free text to a command via the bot fast-path (deterministic).

    Returns ``CommandMatch(None, {})`` when nothing matches; the caller decides
    whether to refuse (strict) or pass through for the LLM fallback (flexible).
    """

    norm = _normalize(text)
    if not norm:
        return CommandMatch(None, {})
    for rule in profile.commands:
        for pattern in rule.patterns:
            if _normalize(pattern) in norm:
                args: dict[str, object] = {}
                if rule.takes_index:
                    found = _INDEX_RE.search(text)
                    if found:
                        args["index"] = int(found.group(1))
                return CommandMatch(rule.trigger, args)
    return CommandMatch(None, {})


def split_for_slack(text: str, max_chars: int) -> list[str]:
    """Split ``text`` into coherent chunks each <= ``max_chars`` (§10.3 step 5).

    Splits on paragraph then line then hard boundaries; never returns an empty
    list. Concise replies (the norm) return a single chunk.
    """

    if max_chars <= 0:
        raise ValueError("max_chars must be positive")
    if len(text) <= max_chars:
        return [text]

    chunks: list[str] = []
    current = ""

    def flush() -> None:
        nonlocal current
        if current:
            chunks.append(current)
            current = ""

    for paragraph in text.split("\n\n"):
        piece = paragraph if not current else "\n\n" + paragraph
        if len(current) + len(piece) <= max_chars:
            current += piece
            continue
        flush()
        if len(paragraph) <= max_chars:
            current = paragraph
            continue
        # Paragraph alone exceeds the limit: hard-split it.
        for start in range(0, len(paragraph), max_chars):
            segment = paragraph[start : start + max_chars]
            if len(segment) == max_chars:
                chunks.append(segment)
            else:
                current = segment
    flush()
    return chunks or [text[:max_chars]]


def load_profile(path: str) -> Profile:
    """Load a profile JSON file (see ``configs/profile.example.json``)."""

    with open(path, "rb") as handle:
        data = json.load(handle)
    commands = [
        CommandRule(
            trigger=str(item["trigger"]),
            patterns=[str(p) for p in item.get("patterns", [])],
            takes_index=bool(item.get("takes_index", False)),
        )
        for item in data.get("commands", [])
    ]
    return Profile(
        version=int(data.get("version", 1)),
        commands=commands,
        slash_map={str(k): str(v) for k, v in data.get("slash_map", {}).items()},
        reaction_map=dict(data.get("reaction_map", {})),
        interpretation_mode=str(data.get("interpretation_mode", "flexible")),
        max_chunk_chars=int(data.get("max_chunk_chars", 3900)),
    )
