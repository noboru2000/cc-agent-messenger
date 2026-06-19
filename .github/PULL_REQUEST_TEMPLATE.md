<!--
Thanks for contributing! This is a small, security-sensitive tool.
For anything non-trivial, please open an issue / discussion FIRST so the
approach is agreed before review. PRs are squash-merged.
-->

## Summary

<!-- What does this change and why? Keep PRs small and reviewable. -->

## Linked issue / discussion

<!-- Required for non-trivial changes. e.g. Closes #123 -->
Closes #

## Type

<!-- Conventional Commits — the PR title should match (e.g. `fix: …`, `feat: …`). -->
- [ ] `fix` — bug fix
- [ ] `feat` — new feature
- [ ] `docs` — documentation only
- [ ] `refactor` / `test` / `chore` — internal change

## Security impact

<!-- Does this touch authorization (NN4), kill switch, audit, token handling,
     the closed command set, or run new commands? If yes, explain. -->
- [ ] This change does **not** weaken the security model (SECURITY.md).

## Checklist

- [ ] The PR title follows Conventional Commits.
- [ ] For a non-trivial change, it was discussed in an issue / discussion first.
- [ ] Tests added or updated for every behavior change.
- [ ] `uv run pytest` passes locally.
- [ ] No secrets, tokens, or host-specific paths are committed.
- [ ] Docs updated (README / SETUP / USAGE / CHANGELOG) where relevant.
- [ ] The change is small and focused (split large changes into multiple PRs).
