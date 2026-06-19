# Releasing

Maintainer runbook. Releases are cut from `main`; publishing to PyPI is automated
by [`.github/workflows/release.yml`](.github/workflows/release.yml) (PyPI Trusted
Publishing / OIDC — no stored token) when a **GitHub Release** is published.

## One-time setup (before the first release)

1. **Configure the PyPI Trusted Publisher.** On <https://pypi.org> → *Your projects*
   → *Publishing* → add a **pending publisher** (the project doesn't exist yet):
   - PyPI Project Name: `cc-agent-messenger`
   - Owner: `noboru2000`
   - Repository: `cc-agent-messenger`
   - Workflow: `release.yml`
   - Environment: `pypi`
2. *(Optional, recommended)* create a GitHub **Environment** named `pypi` with
   protection rules (required reviewer, etc.).
3. *(Optional dry run)* configure the same on <https://test.pypi.org>, temporarily
   set `repository-url: https://test.pypi.org/legacy/` on the publish step, cut a
   pre-release, then `pip install -i https://test.pypi.org/simple/ cc-agent-messenger`.

## Cut a release (vX.Y.Z)

1. **Version** (single source = `pyproject.toml`):

       uv version X.Y.Z

2. **Changelog**: move `## [Unreleased]` → `## [X.Y.Z] - YYYY-MM-DD`, add a fresh
   `## [Unreleased]`, and update the compare links at the bottom.
3. **Verify locally**:

       uv run pytest
       rm -rf dist && uv build && uvx twine check dist/*

4. **Commit & push**, then wait for CI (Python 3.11–3.13) to pass on `main`:

       git commit -am "chore(release): vX.Y.Z"
       git push

5. **Publish the GitHub Release** — this creates the tag `vX.Y.Z` and triggers the
   PyPI publish workflow:

       gh release create vX.Y.Z --title "vX.Y.Z" --notes "See CHANGELOG.md"

   The workflow verifies the tag matches `[project].version`, builds the sdist +
   wheel, and publishes to PyPI via Trusted Publishing.
6. **Verify on PyPI**:

       uv tool upgrade cc-agent-messenger && cc-agent-messenger --version
       # https://pypi.org/project/cc-agent-messenger/

## Notes

- The git tag (`vX.Y.Z`) **must** match `[project].version` (`X.Y.Z`); the release
  workflow enforces this and fails otherwise.
- **Publishing to PyPI makes the source public** (the sdist bundles `src/` +
  `docs/`), regardless of the GitHub repository's visibility.
- Pre-1.0 SemVer: bump **minor** (`0.X.0`) for features / breaking changes, **patch**
  (`0.x.Y`) for fixes.
