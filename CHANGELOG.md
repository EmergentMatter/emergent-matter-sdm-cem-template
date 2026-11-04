# Changelog

<!-- towncrier release notes start -->

## 1.1.1 (2026-11-04)

### Patch

- `CLAUDE.md` now tells the coding agent how to work where there is no `uv` and no network: run the package CLI and `pytest` directly and install nothing; build only in this project's own package, never a second one; never write a `.sdm` by hand; report a failed build with its output; and leave `git add`, `git commit` and `git config` to the environment when it saves the work. (agent-guidance-hosted)


## 1.1.0 (2026-11-03)

### Minor

- The template's own part is now a rounded block (`d_length`, `d_width`, `d_height`, `d_edge_radius`) instead of a flanged bushing, so a new project opens on a neutral shape. The bushing moved to `examples/bushing_sdf/` with its own annotated `cem.toml` and tests, and `scripts/rename.py` replaces `README.md` with a short project README. (neutral-starter-part)

### Patch

- `scripts/rename.py` now computes every rewrite and runs every check before writing anything, so a bad `[project].name` or `ci.yml` `package-name:` stops it with the tree untouched instead of leaving a half-renamed copy. (rename-all-or-nothing)
- The README's steps and rules moved to `docs/building-a-cem.md`, which survives `scripts/rename.py`, so `CLAUDE.md` and the generated README point at it. The rename now removes an example whose package name it would collide with, refuses names with a leading, trailing or doubled underscore, keeps a CRLF README's line endings, and prints the next steps. Manifest checks moved to `tests/manifest_checks.py` so the CEM's own `test_manifest.py` no longer depends on the examples. (rename-keeps-the-docs)
- `scripts/rename.py` now also renames the dataclass and part builder, sets `cem.toml`'s `[cem].name` and the CLI's default `--name` to `<thing>`, and takes `--offline` (no network, no `uv`; the lockfile is rewritten as text). `CLAUDE.md` tells the coding agent to build parts through the CEM's parameters and CLI. (rename-project-identity)
- Two rename tests no longer spell out the template's own version; they read it from `pyproject.toml`, so a release that bumps the version no longer breaks them. (rename-tests-read-the-version)
- A .sdm built inside the repo no longer records absolute paths in its generator, so it re-emits on any machine; one built outside the repo records the absolute project root and warns.
- `scripts/rename.py` now renames the root package in `uv.lock`, so a CEM made from the template passes `uv sync --locked` in its first CI run.


## 1.0.0 (2026-10-03)

### Major

- Open Source Launch
