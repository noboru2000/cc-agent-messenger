# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/), and this project adheres to
semantic versioning.

## [Unreleased]

### Added
- Initial scaffold of the portable package extracted from the verified C0 loop.
- Resident Slack bot daemon (Bolt + Socket Mode) with a single egress chokepoint:
  kill switch → destination authorization → outbound filter/split → audit → post.
- Unix-domain-socket send API + unified CLI:
  `init`, `daemon`, `send`, `ping`, `status`, `stop`, `kill`, `doctor`.
- Claude Code skill, config/profile templates, and the `init` scaffolder.
- Multi-agent C1 skeleton (`AgentRunner`, `Router`) — Claude/Codex/Copilot C1
  PoC-verified; daemon wiring is a later increment.
