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

The part is a flanged bushing. It is deliberately boring: what this repo
teaches is the **shape of a CEM**, not the shape of a part. It builds, it
validates, and its tests pass, so you can tell whether your first change
broke something.

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
   every import and manifest reference that names either, renames the repo
   slug everywhere `pyproject.toml` and `ci.yml` carry it, and resets the
   release history (step 2, below). `<thing>` becomes a Python package
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
3. **Wire up release control for your CEM.** `.github/workflows/version.yml`
   needs no repo secret: `emergent-matter-sdm-core` resolves from the org's
   package index, not a private-sibling checkout. Adjust
   `.github/CODEOWNERS` if this CEM has different owners than the
   template's default.
4. **Rewrite `parameters.py`.** This is the design. Declared fields, derived
   `@property`, and `validate()`: see the rules below.
5. **Rewrite `sdm/trees_*.py`.** One function per feature.
6. **Update `cem.toml`** to match. `tests/test_manifest.py` fails until it does,
   in both directions.
7. **Rewrite `tests/test_build.py`'s field assertions** for your geometry. Keep
   the *style*: points whose answers you know by hand.

## The rules this template encodes

### One Part per physical part; an Assembly places them

A `Part` is one physically inseparable object: what comes off the printer,
the machine or the shelf as one piece. It may hold several materials if it is
made as one. Anything that can be separated (fastened, bonded, pressed in,
dropped in place) is its own `Part`, and an `Assembly` places it; assemblies
nest. The bushing is one piece, so this CEM emits one `Part`. For a product
of several pieces, `write_assembly` in `sdm/assembly.py` writes
`parts/<name>.sdm` per part plus `<name>.sdm`, with relative, sha256-pinned
references, and `tests/test_assembly.py` is the pattern for checking it.

### Top-down: every dimension has one owner, and here it is the CEM

The `.sdm` is this CEM's output: reviewed, never edited, and never
overridden in the file. A change goes into the CEM and the `.sdm` is
regenerated. Each generated document records what produced it under
`metadata.source` (see `source_metadata`). A parent CEM that composes child
CEMs owns the dimensions they share (an air gap, a bolt circle, a shaft
diameter) and passes them down; a child reads them and never redeclares
them. sdm-core's Assembly params and instance overrides are for designs
authored directly as `.sdm` with no CEM, so `write_assembly` writes neither.

The full text and the reasons for both rules are on the docs hub's
[concepts](https://github.com/EmergentMatter/emergent-matter-sdm/blob/main/docs/concepts.md)
page.

### Derived values are `@property`. Never a field.

`d_bore_radius` is `d_outer_radius - d_wall_thickness`. Write it down as a
field and it becomes a second source of truth that nothing keeps in sync:
which is exactly how a param edit produces geometry that violates the model
with nothing reporting a problem. This is not hypothetical: it is
the hexafoil bug,
where derived params were flattened into free params at authoring time and
the viewer faithfully rendered the inconsistent state.

Corollary, enforced by `test_derived_values_are_not_declared_as_params`: a
derived value must not ship in the `.sdm` as a free param either.

### `validate()` returns a list. It does not raise.

An optimizer or a coder agent should see every problem at once, not fix five
things in five round trips. `build_*_part()` is what raises.

### The interesting constraints are not bounds

Per-param bounds cannot express `d_wall_thickness < d_outer_radius`, an
ordering like `tube < bolt_circle < flange`, or a floor on a *derived* value
like `d_flange_ligament` (which depends on `n_bolt_holes`). Those go in
`validate()` **and** in `cem.toml`'s `[[cem.constraints]]`, each with a `why`:
a constraint whose reason lives only in someone's head gets relaxed by the
next person who finds it inconvenient.

`test_every_declared_constraint_is_actually_enforced` is what stops the two
from drifting.

### `cem.toml` is the machine-readable surface

Every param with its type, default, unit, coupling `role`, bounds, and the
name it `emits` as in the `.sdm`. It is read **without importing anything**:
the MCP server's `read_cem` parses it and never resolves `entry_point`. Keep it
that way: the moment reading a manifest runs code, "list the CEMs I have"
becomes a supply-chain question.

What each `role` costs to change is documented once, in `cem.toml`'s own
header comment; this file doesn't repeat it.

### The CLI takes `--out` **and** `--set`, and the document says so

The viewer's `/reemit` contract requires both. A CEM with only `--set` fails
inside a subprocess, where the error is easy to lose entirely.

The document also **declares** them, as `metadata.generator.accepts`. A tool
cannot tell from the recorded argv which flags a CLI understands, and without
the declaration its only option is to write edited values into the `.sdm` and
hope the generator reads its own output. `harness.py` stamps the declaration
and `check_contract.py` fails without it.

`harness.py` stamps `metadata.generator` with the argv and cwd that produced
the file. Without it the `.sdm` can be rendered and never re-derived.

**Read [`docs/traps.md`](docs/traps.md) before writing geometry.** It is the
list of mistakes this stack lets you make that produce a document that
builds, validates, and is wrong.

## Tests

```bash
uv run pytest
uv run python scripts/check_contract.py
```

**A green test suite is not a working CEM.** It means your CEM is internally
consistent. It does not mean a tool can drive it: bounds can be missing, the
CLI can reject the very name the document emits, an integer can arrive as
`8.0`, errors can go to the wrong stream, and the recorded generator can fail
to reproduce its own document. Every one of those is invisible from inside the
CEM and shows up as a broken or unmovable control in a viewer.

`scripts/check_contract.py` drives your CLI as a SUBPROCESS, the way a tool
does, and checks all of it without a browser. It reads the entry point from
`pyproject.toml`, so it copies into any CEM unchanged.

`test_manifest.py` is the one worth copying verbatim into a real CEM. Without
it the manifest describes a design nobody is building, and it drifts silently
because nothing else reads it.

## Documentation

| Page | What it covers |
|---|---|
| [`docs/traps.md`](docs/traps.md) | The mistakes this stack lets you make that produce a document that builds, validates, and is wrong |
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
