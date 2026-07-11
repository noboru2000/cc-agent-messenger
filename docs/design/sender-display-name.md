# Repository-owned Slack sender names — detailed design

## Configuration contract

The default, un-routed C0 channel uses the existing top-level `default_agent` as
its Slack display name. Each routed agent has a stable internal `name` and an
optional presentation-only `display_name`:

```toml
default_agent = "ULBC Mac"

[[agent]]
name = "claude-headless"
display_name = "ULBC Claude"
integration = "c1"
kind = "claude"
channel_id = "C…"
cli = "claude -p"
```

If `display_name` is absent or empty, the effective display name is `name`.
Changing `display_name` must not change routing, audit/session keys, or the stored
C1 resume session. Agent names should therefore remain stable and unique.

The Slack App's display/mention name is a separate workspace-level setting. For
example, an owner may mention `@MacMessenger` while that App posts a routed reply
whose author label is `ULBC Claude`. Configured authorship does not create another
Slack user, change invitations, or change the mention token in inbound events.

## Resolution and trust boundary

The egress chokepoint resolves the effective name from the authorized destination:

1. If the destination matches a configured agent channel, use that agent's
   effective display name.
2. Otherwise, for the authorized default channel, use `default_agent`.
3. Reject unauthorized destinations before resolving or posting.

`SendRequest`, the local send API, CLI arguments, Slack message text, and inbound
events do not carry a username. This prevents an owner message or local caller
from impersonating an arbitrary name. All fresh posts, including split chunks,
buttons, proactive sends, doctor probes, and thinking placeholders, use the
resolved/default configured name. `chat.update` retains the placeholder's original
authorship.

## Slack capability and failure behavior

`SlackEgress.post` passes the resolved value as `username` to `chat.postMessage`.
Slack Apps require both `chat:write` and `chat:write.customize`. The latter is a
required `doctor --slack` scope in v0.7. Missing scope is a preflight failure; a
post rejected by Slack follows the existing audited `STATUS_FAILED` path. The app
does not silently fall back to its global Slack display name because that would
make per-repository attribution unreliable.

Slack reference: [`chat.postMessage`](https://docs.slack.dev/reference/methods/chat.postMessage/)
documents the `username` argument; [`chat:write.customize`](https://docs.slack.dev/reference/scopes/chat.write.customize/)
is the required Bot Token Scope.

## Upgrade and `init`

`cc-agent-messenger init` continues to preserve an existing `config.toml`; it must
never overwrite tokens, host paths, agent routes, or presentation names. It
refreshes the packaged skill and config example. Existing configurations need no
schema rewrite because `display_name` is optional. Operators add
`chat:write.customize`, reinstall the Slack App, then set `default_agent` and any
agent `display_name` values before restarting the daemon.

## Tests

Tests cover config parsing and fallback, stable agent names, default C0 and routed
C0/C1 resolution, Slack `username` forwarding, split/button posts, required scope
diagnostics, and preservation of existing config during `init`.
