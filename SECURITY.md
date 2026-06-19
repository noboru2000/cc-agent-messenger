# Security Policy

`claude-messenger` lets Slack messages drive AI coding agents that can run
commands. Treat it as a **remote-code-execution-adjacent** tool and operate it
accordingly.

## Threat model & assumptions

- **Single trusted operator.** Only the configured owner Slack user ID, in the
  configured private channel, may drive the agent (NN4). Messages from any other
  identity or channel are ignored.
- **Trusted machine + network.** Run only on a machine and network you control.
- **Local-only transport.** The send API is a Unix domain socket (`0600`); no
  public URL or inbound port (Slack Socket Mode is an outbound WebSocket).

## Token handling

- The Slack bot token (`xoxb-…`) and app token (`xapp-…`) live **only** in your
  local `.claude-messenger/config.toml` (gitignored) and inside the daemon. They
  are **never** committed and never sent to the reply CLI or the live session.
- The shipped templates contain placeholders only.

## Hands-free auto-reply is a conscious risk

Making replies hands-free requires adding an allow-rule (e.g.
`Bash(claude-messenger send:*)`) to your `.claude/settings.json`, which grants
**auto-execution** of the reply command without a per-call prompt. This is a
deliberate trade-off you accept. The tool **prints** the rule; it never grants it
for you.

## Controls

- **Closed command set** for the common path; free text is mapped to the same
  closed handler set, and destructive/irreversible actions require explicit
  in-Slack approval (NN5).
- **Kill switch** (`claude-messenger kill on`) halts all inbound/outbound at once.
- **Audit log** records every inbound and outbound action (rotated, retention-
  bounded, payloads truncated).
- **Headless agents (C1)** run commands — confine each per its tool's controls
  (Codex sandbox/approval, Claude permission mode, Copilot tool permissions); do
  not rely on permissive defaults.

## Reporting a vulnerability

Please report security issues privately to the maintainer (open a minimal,
non-public report via the repository's security advisory feature, or contact the
maintainer directly) rather than filing a public issue. We will acknowledge and
respond as soon as practical.

## No warranty

Provided "as is", without warranty of any kind (see [LICENSE](LICENSE)). You are
responsible for how you deploy and operate it.
