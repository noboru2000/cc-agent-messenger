# Architecture

`claude-messenger` bridges a Slack channel to AI coding agents running on your Mac,
as **complete message turns** (not live terminal mirroring). It is two halves: a
Python daemon/CLI, and a Claude Code skill the live session runs.

## The C0 loop (the proven core)

```text
Slack channel ──► resident bot (Bolt + Socket Mode)
                    │ ingress: authorize (NN4) + match command + tag `trigger`
                    ▼
              tmp/.slack_message  (append-only JSONL, one event per line)
                    │
                    ▼  tail -f Monitor in the live VS Code Claude Code session
              live session wakes, interprets, composes a reply
                    │
                    ▼  claude-messenger send (Unix-socket send API)
              egress chokepoint ──► bot chat.postMessage (@owner) ──► your phone
```

- **Inbound (ingress):** Slack events (`app_mention`, thread `message`,
  `slash_commands`, `block_actions`, `reaction_added`) are authorized to the single
  owner + channel, matched to a command `trigger`, and appended as one JSONL line.
- **Wake:** the live session's `tail -f` Monitor delivers the appended line as an
  event and wakes the otherwise-idle session.
- **Outbound (egress):** the live session replies via `claude-messenger send`,
  which goes through the **egress chokepoint** in the daemon.

## The egress chokepoint (every outbound post)

In strict order; failing any stage stops the send:

1. **Kill switch (NN6)** — if engaged, return `halted`.
2. **Destination authorization (NN4)** — the target must be the allowed channel
   (or a configured agent channel); never a free-form channel.
3. **Outbound filter (NN10)** — apply the profile + reply rule (concise; split
   overly long messages into coherent chunks).
4. **Audit (NN6/NN7)** — record the action (timestamp, actor, destination,
   correlation id, outcome) with truncated payloads.
5. **Post** — `chat.postMessage` as the bot, prepending the owner `@mention`.

The Slack **bot token lives only in the daemon**; the reply CLI and the live
session never see it. Posting under the **bot identity** (distinct from the owner)
is what makes the owner `@mention` generate a phone push — Slack suppresses
notifications for your own messages.

## Four input surfaces (command interpretation)

Most deterministic first: **slash commands** → **Block Kit buttons / select menus**
→ **emoji reactions** → **free-text `@mention`**. Free text uses a bot
deterministic fast-path; on no match, the live session interprets it (LLM
fallback) and maps it to the **closed set of command handlers**, asking a short
1/2 disambiguation when ambiguous. A `strict` mode refuses unmatched free text.
The effective command set stays closed; destructive actions remain gated by NN5.

## C0 vs C1, and multiple agents

- **C0 (live window):** the reply comes from the already-open Claude Code session,
  with live working-memory context. Claude-Code-specific; session-bound (NN13).
- **C1 (headless spawn-per-turn):** the daemon runs the agent CLI headlessly
  (`claude -p` / `codex exec` / `copilot -p`), captures the turn, and replies.
  Tool-agnostic; the only path for Codex/Copilot (separate from their GUI tabs).
- **Routing:** one dedicated Slack channel per agent; the daemon resolves the
  agent by `channel_id` and dispatches to C0 (append to that agent's ingress file)
  or C1 (spawn + reply through the chokepoint).

## Security model

Single trusted operator (NN4); local-only Unix-socket transport (`0600`); Socket
Mode (no public URL); kill switch (NN6); append-only audit with rotation (NN7);
closed effective command set + NN5 approval for dangerous actions; secrets
local-only (NN8). Hands-free auto-reply is a conscious allowlist grant. See
[../SECURITY.md](../SECURITY.md).

## Components (`src/claude_messenger/`)

`config` · `models` · `profile` (command matcher + split) · `authz` · `killswitch`
· `audit` · `slackclient` (bot-token holder) · `context` · `egress` (chokepoint) ·
`sendapi` (Unix-socket server) · `ingress` (4 surfaces) · `daemon` (Bolt wiring) ·
`ipcclient` · `lifecycle` (pidfile/status/stop) · `doctor` · `cli` · `commands`
(registry + i18n) · `agentrunner` + `router` + `multiagent` (C1 routing).
