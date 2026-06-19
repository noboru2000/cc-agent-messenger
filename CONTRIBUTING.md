# Contributing

Thanks for your interest. This is a small, **security-sensitive** tool maintained
by one person, so the workflow favors agreeing on an approach before code lands.
Please keep changes small and reviewable, and add or update tests for every
behavior change.

## Reporting bugs

Open a **Bug report** issue (the blank issue option is disabled — pick a template).
Include the version (`cc-agent-messenger --version`), install method, OS/Python,
and steps to reproduce.

- **Security vulnerabilities** do **not** go in public issues. Report them
  privately via a [Security Advisory](https://github.com/noboru2000/cc-agent-messenger/security/advisories/new)
  or email the maintainer — see [SECURITY.md](SECURITY.md).
- **Redact secrets.** Never paste Slack tokens (`xoxb-…`, `xapp-…`), IDs, or
  `.cc-agent-messenger/config.toml` contents.

## Questions & usage help

Use [Discussions](https://github.com/noboru2000/cc-agent-messenger/discussions),
not the issue tracker — the tracker is for actionable bugs and feature requests.

## Proposing changes (pull requests)

1. **Discuss first.** For anything non-trivial, open a **Feature request** issue or
   a Discussion so we agree on the approach before you invest in a PR. Trivial
   fixes (typos, small doc fixes, obvious bugs) can go straight to a PR.
2. **Branch & PR.** Work on a branch; open a PR against `main` and fill in the PR
   template. Link the issue/discussion (`Closes #NN`).
3. **Keep it small and focused.** Split large changes into multiple PRs.
4. **Tests + CI.** Add/adjust tests; `uv run pytest` must pass (CI runs it).
5. **Review & merge.** The maintainer reviews; PRs are **squash-merged**, so the PR
   title becomes the commit — make it a good Conventional Commit (below).
6. By contributing you agree your contribution is licensed under the project's
   [MIT License](LICENSE).

## Development setup

    git clone https://github.com/noboru2000/cc-agent-messenger
    cd cc-agent-messenger
    uv sync --extra dev
    uv run pytest

The test suite runs offline (Slack is mocked). You can also run it without `uv`:

    PYTHONPATH=src python -m unittest discover -s tests

## Commit messages

Use [Conventional Commits](https://www.conventionalcommits.org/): a `type(scope):`
prefix and an imperative summary. Common types: `feat`, `fix`, `docs`, `refactor`,
`test`, `chore`, `ci`. Examples:

    feat(commands): add the `!` command prefix
    fix(ingress): avoid double-ingestion of bot-mentioned thread replies
    docs(setup): add the update/upgrade section

## Code guidelines

- Type-annotate public functions; avoid OS-specific assumptions and hard-coded
  machine paths (use config).
- Never commit secrets or host-specific values — keep them under
  `.cc-agent-messenger/` (gitignored).
- Keep the security model intact (see [SECURITY.md](SECURITY.md)): single
  operator, authorization, kill switch, audit, local-only token handling.
- The inbound command set is a **closed allowlist**; destructive/irreversible
  actions stay behind explicit in-Slack approval (NN5).

## Labels (maintainer reference)

`bug`, `enhancement`, `docs`, `question`, `security`, `needs-triage`,
`good first issue`, `wontfix`, `duplicate`.
