<a id="readme-top"></a>

# emergent-matter-sdm-cem-template

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-033388.svg)](LICENSE)
[![Python 3.13+](https://img.shields.io/badge/python-3.13+-0055FF.svg)](https://www.python.org/downloads/)
[![Built with sdm-core](https://img.shields.io/badge/built%20with-sdm--core-033388.svg)](https://github.com/EmergentMatter/emergent-matter-sdm-core)
[![uv](https://img.shields.io/badge/packaged%20with-uv-DE5FE9.svg)](https://docs.astral.sh/uv/)

Template for a Software Defined Matter **computational engineering model** (CEM): a
repo that turns parameters into geometry as a **signed distance field** (SDF)
tree, using [`sdm-core`](https://github.com/EmergentMatter/emergent-matter-sdm-core)
to standardize the result into an `.sdm` file. Both terms, and the full
pipeline this repo is the first step of, are in the docs hub:
[glossary](https://github.com/EmergentMatter/emergent-matter-sdm/blob/main/docs/glossary.md),
[concepts](https://github.com/EmergentMatter/emergent-matter-sdm/blob/main/docs/concepts.md).

The part is a rounded block. It is deliberately boring: what this repo
teaches is the **shape of a CEM**, not the shape of a part. It builds, it
validates, and its tests pass, so you can tell whether your first change
broke something. A fuller worked CEM, a flanged bushing with a bolt circle,
an integer parameter and five constraints, is in
[`examples/bushing_sdf/`](examples/bushing_sdf/), with an annotated
`cem.toml` of its own.

## Install

```bash
uv sync
```

resolves this CEM's dependencies from an index, the same as any other Python
project.

### Development install

Working on `sdm-core` itself, alongside this CEM, needs an editable install
instead of the published package. Don't hand-edit `[tool.uv.sources]` for
that: run `python3 scripts/em-dev.py` (synced from the `actions` templates)
with `emergent-matter-sdm-core` cloned beside this repo. It builds a
separate, git-ignored `.venv-local` from this repo's own lockfile with the
sibling installed editable on top, so `pyproject.toml`, `uv.lock`, and the
regular `.venv` stay exactly as committed. `python3 scripts/em-dev.py off`
reverts to the published package; `python3 scripts/em-dev.py status` shows
local vs. published per package.

**Python 3.13+**, a floor that comes from `sdm-core`. On an older interpreter
the failure appears deep inside the materials package as
`TypeError: zip() takes no keyword arguments`, which looks like a bug in
materials and is a version mismatch. macOS ships 3.9.

## Use it

```bash
gh repo create <org>/<company-name>-cem-<thing> --private \
  --template EmergentMatter/emergent-matter-sdm-cem-template
cd <company-name>-cem-<thing>
python3 scripts/bootstrap.py
```

`bootstrap.py` fetches Python 3.13, syncs from the package index, runs the
test suite, and finishes by checking that a tool can actually drive the
result. One command, fresh clone to working. See Install above for what
it's setting up and why.

**If anything goes wrong:** `python3 scripts/doctor.py`. It prints the fix, not
the symptom. Both scripts are stdlib only and run on old Python, because they
have to work *before* the environment exists.

Then, in this order:

1. **Rename the template to your CEM: `python3 scripts/rename.py <thing>`.**
   Renames `src/widget_sdf/` and the console script `widget-build`, fixes
   every import and manifest reference that names either, renames the
   parameters class and the part builder, sets `cem.toml`'s `[cem].name` and
   the CLI's default `--name` to `<thing>`, renames the repo slug everywhere
   `pyproject.toml` and `ci.yml` carry it, renames the root package in
   `uv.lock` so `uv sync --locked` still passes, resets the release history
   (step 2, below), and **replaces this README** with a short one for your
   CEM (the steps and rules that were here are in
   [`docs/building-a-cem.md`](docs/building-a-cem.md), which stays). If
   `<thing>_sdf` is the name of an example under `examples/`, that example
   and its test file are removed. `<thing>` becomes a Python package
   name, so it has to be lowercase snake_case. The new repo slug is
   `<company-name>-cem-<thing>`, where `<company-name>` defaults to
   `emergent-matter`; forking this template outside Emergent Matter,
   pass `--company <company-name>` to get your own. The script refuses a bad
   `<thing>` and refuses to run a second time against an already-renamed
   repo, rather than half-applying either; see its own docstring for why
   this is a script and not a paragraph, and
   `tests/test_rename_checklist.py` for what it's proven to do. It removes
   itself, and that test file, once it succeeds.
2. **Release history is already reset.** The script above set
   `[project].version` back to `0.1.0` and emptied `changelog.d/`: the
   template's own notes describe changes to the template, not to your CEM.
3. **Everything after the rename** is in
   [`docs/building-a-cem.md`](docs/building-a-cem.md): wiring up release
   control, rewriting `parameters.py`, the trees, `cem.toml` and the build
   test, and the rules a CEM follows. The script prints this list when it
   finishes.

## Tests

```bash
uv run pytest
uv run python scripts/check_contract.py
```

**A green test suite is not a working CEM.** It means your CEM is internally
consistent. It does not mean a tool can drive it: bounds can be missing, a
param can ship without `free=True` (the Scene is empty), the CLI can reject the very name the document emits, an integer can arrive as
`8.0`, errors can go to the wrong stream, and the recorded generator can fail
to reproduce its own document. Every one of those is invisible from inside the
CEM and shows up as a broken or unmovable control in a viewer.

`scripts/check_contract.py` drives your CLI as a SUBPROCESS, the way a tool
does, and checks all of it without a browser. It reads the entry point from
`pyproject.toml`, so it copies into any CEM unchanged.

`test_manifest.py` is the one worth copying verbatim into a real CEM. Without
it the manifest describes a design nobody is building, and it drifts silently
because nothing else reads it.

`test_dimensions.py` holds the other line: every dimension is free (declared
with bounds; an optimizer may move it), an input (declared with its source;
fixed unless tradeable), or driven (computed from the others), and nothing
dangles. It calls sdm-core's dimension audit, which fails on a number typed
into the shape code, a declared dimension that moves nothing, and a length
with a typed-in offset. See CLAUDE.md, "Every dimension is free, an input, or
driven", for the full rules.

## Documentation

| Page | What it covers |
|---|---|
| [`docs/traps.md`](docs/traps.md) | The mistakes this stack lets you make that produce a document that builds, validates, and is wrong |
| [`examples/bushing_sdf/`](examples/bushing_sdf/) | A full worked CEM with an annotated `cem.toml`: roles, `emits`, bounds, constraints |
| [`examples/plate_sdf/`](examples/plate_sdf/) | A rounded plate, and the rounding trap |
| [STYLE.md](STYLE.md) / [CONTRIBUTING.md](CONTRIBUTING.md) | House style and how a change ships |

Those pages document this template. For the wider SDM ecosystem and the
other repositories in it, see
[`emergent-matter-sdm`](https://github.com/EmergentMatter/emergent-matter-sdm).

## Built with

| | |
|---|---|
| [`sdm-core`](https://github.com/EmergentMatter/emergent-matter-sdm-core) | The only runtime dependency; `sdm/trees_*.py` builds `.sdm` documents through its SDF DSL |
| [uv](https://docs.astral.sh/uv/) | Packaging and the locked dev environment |
| [hatchling](https://hatch.pypa.io/) | Build backend |

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for how a change ships: the
changeset a pull request needs, what counts as major, minor, or patch,
and how a release is cut. [STYLE.md](STYLE.md) is the house style for
code, tests, and docs, and it wins over habit.

By participating you agree to the
[Code of Conduct](CODE_OF_CONDUCT.md).

## Support

Questions and usage help go to
[Discussions](https://github.com/EmergentMatter/emergent-matter-sdm/discussions);
bugs and feature requests go to
[Issues](https://github.com/EmergentMatter/emergent-matter-sdm-cem-template/issues).
See [SUPPORT.md](SUPPORT.md) for what is and is not supported.

For security reports, do not open a public issue. Follow
[SECURITY.md](SECURITY.md).

## License

Apache-2.0. See [`LICENSE`](LICENSE) and [`NOTICE`](NOTICE).

<p align="right">(<a href="#readme-top">back to top</a>)</p>
