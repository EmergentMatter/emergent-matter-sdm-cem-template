# Changelog

<!-- towncrier release notes start -->

## 1.0.1 (2026-10-30)

### Patch

- `scripts/rename.py` now computes every rewrite and runs every check before writing anything, so a bad `[project].name` or `ci.yml` `package-name:` stops it with the tree untouched instead of leaving a half-renamed copy. (rename-all-or-nothing)
- A .sdm built inside the repo no longer records absolute paths in its generator, so it re-emits on any machine; one built outside the repo records the absolute project root and warns.
- `scripts/rename.py` now renames the root package in `uv.lock`, so a CEM made from the template passes `uv sync --locked` in its first CI run.


## 1.0.0 (2026-10-03)

### Major

- Open Source Launch
