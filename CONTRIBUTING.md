# Contributing

Thanks for your interest. This is a small, security-sensitive tool; please keep
changes small and reviewable, and add or update tests for every behavior change.

## Development setup

    git clone https://github.com/REPLACE-OWNER/claude-messenger
    cd claude-messenger
    uv sync --extra dev
    uv run pytest

The test suite runs offline (Slack is mocked). You can also run it without `uv`:

    PYTHONPATH=src python -m unittest discover -s tests

## Guidelines

- Type-annotate public functions; avoid OS-specific assumptions and hard-coded
  machine paths (use config).
- Never commit secrets or host-specific values — keep them under
  `.claude-messenger/` (gitignored).
- Keep the security model intact (see [SECURITY.md](SECURITY.md)): single
  operator, authorization, kill switch, audit, local-only token handling.
- Discuss larger changes (e.g. multi-agent wiring, new transports) in an issue
  first.
