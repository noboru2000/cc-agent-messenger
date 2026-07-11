# Architecture

`cc-agent-messenger` bridges a Slack channel to AI coding agents running on your Mac,
as **complete message turns** (not live terminal mirroring). It is two halves: a
Python daemon/CLI, and a Claude Code skill the live session runs.

## The C0 loop (the proven core)

```text
Slack channel ──► resident bot (Bolt + Socket Mode)
                    │ ingress: authorize (NN4) + match command + tag `trigger`
                    ▼
              .cc-agent-messenger/tmp/.slack_message  (append-only JSONL, one event per line)
                    │
                    ▼  tail -f Monitor in the live VS Code Claude Code session
              live session wakes, interprets, composes a reply
                    │
                    ▼  cc-agent-messenger send (Unix-socket send API)
              egress chokepoint ──► bot chat.postMessage (@owner) ──► your phone
```

- **Inbound (ingress):** Slack events (`app_mention`, thread `message`, a
  top-level `message` containing this app's bot-ID mention, `slash_commands`,
  `block_actions`, `reaction_added`) are authorized to the single owner + channel,
  matched to a command `trigger`, and appended as one JSONL line. Slack clients
  may encode the same visible mention as the bot user ID (`<@U…>`) or bot ID
  (`<@B…>`): the former stays on `app_mention`; the latter is accepted from the
  `message` surface so mobile commands are not silently lost (P14).
- **Wake:** the live session's `tail -f` Monitor delivers the appended line as an
  event and wakes the otherwise-idle session.
- **Outbound (egress):** the live session replies via `cc-agent-messenger send`,
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

### Mention delivery and deduplication

Slack's event type, not the client UI, determines the ingress path. A bot-user-ID
mention (`<@U…>`) is handled only by `app_mention`; the parallel `message` is
rejected. A bot-ID mention (`<@B…>`) is handled by `message`, including at top
level, because Slack does not emit `app_mention` for that representation. Plain
top-level messages remain rejected. The bot ID used for comparison comes from
Bolt's authorization context and is never accepted from message content as a
trusted identity. Owner/channel authorization is still applied after routing.

For private channels, `groups:history` is a required bot-token scope because it
enables the `message.groups` event used by thread replies and mobile bot-ID
mentions. `doctor --slack` verifies the granted scope. Slack does not expose the
app's Event Subscriptions configuration through the installed bot/app tokens, so
the required `message.groups` subscription remains an explicit preflight check in
the setup guide; the outbound `--live` probe cannot prove inbound event delivery.

## C0 vs C1, and multiple agents

- **C0 (resident interactive session):** the reply comes from an already-open
  Claude Code session that watches the ingress JSONL file. That session may run in
  a VS Code window or in the interactive `claude` CLI; the transport and semantics
  are identical. It retains live working-memory context and can send proactive
  updates, but it must remain running and keep its Monitor armed. C0 is
  Claude-Code-specific and session-bound (NN13); the daemon never spawns it.
- **C1 (headless spawn-per-turn):** the daemon runs the agent CLI headlessly
  (`claude -p` / `codex exec` / `copilot -p`), captures the turn, and replies.
  It persists only a resumable session ID per Slack thread, not a resident
  interactive process. Tool-agnostic; the only path for Codex/Copilot (separate
  from their GUI tabs).
- **Routing:** one dedicated Slack channel per agent; the daemon resolves the
  agent by `channel_id` and dispatches to C0 (append to that agent's ingress file)
  or C1 (spawn + reply through the chokepoint).

| Property | C0 | C1 |
| --- | --- | --- |
| Agent lifetime | One resident interactive session | One headless process per Slack turn |
| Who starts the agent | Owner starts `claude` / opens VS Code | Daemon starts the configured CLI |
| Context | Live session working memory | Resumed per Slack thread by stored session ID |
| Ingress | JSONL file + persistent Monitor | Direct daemon dispatch |
| Supported agents | Claude Code | Claude Code, Codex, GitHub Copilot |
| Best fit | Ongoing development, experiments, monitoring | On-demand turns without an open console |
| Configuration | Default single-channel path; optional `integration = "c0"` routing | Explicit `[[agent]]` with `integration = "c1"` |

Installing v0.6 does not convert C0 to C1. Without a C1 `[[agent]]` entry, the
existing daemon → ingress file → resident Claude session flow remains unchanged.

## Security model

Single trusted operator (NN4); local-only Unix-socket transport (`0600`); Socket
Mode (no public URL); kill switch (NN6); append-only audit with rotation (NN7);
closed effective command set + NN5 approval for dangerous actions; secrets
local-only (NN8). Hands-free auto-reply is a conscious allowlist grant. See
[../SECURITY.md](../SECURITY.md).

## Components (`src/cc_agent_messenger/`)

`config` · `models` · `profile` (command matcher + split) · `authz` · `killswitch`
· `audit` · `slackclient` (bot-token holder) · `context` · `egress` (chokepoint) ·
`sendapi` (Unix-socket server) · `ingress` (4 surfaces) · `daemon` (Bolt wiring) ·
`ipcclient` · `lifecycle` (pidfile/status/stop) · `doctor` · `cli` · `commands`
(registry + i18n) · `agentrunner` + `router` + `multiagent` (C1 routing).

## Layout & extensibility

### Why `src/cc_agent_messenger/` (the "src layout")

Standard PyPA layout: the importable package is `cc_agent_messenger`; tests run
against the *installed* package (catching packaging bugs a flat layout hides), and
the package boundary is unambiguous. (`cc-agent-messenger` is the distribution / repo
name; `cc_agent_messenger` — underscore — is the import name, since Python packages
cannot contain hyphens.) Keep it; do not flatten modules directly under `src/`.

### Two orthogonal plugin axes

- **AI agent** (Claude / Codex / Copilot) — **already abstracted**: `agentrunner`
  + `router` + `multiagent` (channel → agent; C0 live / C1 headless).
- **Messaging transport** (Slack / LINE / Teams) — Slack-only today; to be
  abstracted behind a `Transport` interface **when a second transport is added**.

### Future: transport abstraction (`core` + `transports/`)

Planned structure once a second messaging tool (e.g. LINE / Teams) lands:

```text
src/cc_agent_messenger/
├── core/          # transport-agnostic: egress chokepoint, profile/commands,
│                  #   authz, killswitch, audit, send API + CLI, the agent layer
└── transports/
    ├── base.py    # the Transport interface
    ├── slack/     # Bolt + Socket Mode ingress / chat.postMessage egress / tokens
    ├── line/      # (future) Messaging API webhook / push
    └── teams/     # (future) Bot Framework
```

```python
class Transport(Protocol):
    def start(self, on_event: Callable[[InboundEvent], None]) -> None: ...  # receive → normalize → core
    def post(self, channel: str, text: str, *, thread=None, options=None, identity=None) -> str: ...
    def is_live(self) -> bool: ...
```

- `egress.handle_send` would call `transport.post(...)` (the **chokepoint stays in
  core**); the daemon's Bolt wiring becomes the Slack transport's `start()`.
- Today the Slack specifics are localized in `slackclient`, `daemon.build_app`, and
  `ingress` (the four surfaces) — the seam to lift out later.
- **Timing:** introduce the interface with the *second* implementation (avoid
  abstracting against a single case / speculative generality).
