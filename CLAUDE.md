# CLAUDE.md

Guidance for agent sessions working in a CEM scaffolded from this template.

## Code standard

Follow [STYLE.md](STYLE.md) at the repo root for all code, comments, tests,
and docs. It is the org standard and wins over habit. Pull request
descriptions follow
[.github/PULL_REQUEST_TEMPLATE.md](.github/PULL_REQUEST_TEMPLATE.md).

Two standards, and they answer different questions. `STYLE.md` governs **how**
to write: naming, docstrings, typing, tests, and the writing rules, including
no em dashes. The docs hub's
[documentation standard](https://github.com/EmergentMatter/emergent-matter-sdm/blob/main/docs/documentation-standard.md)
governs **where** a piece of documentation belongs, and what should not be
written down at all: no manual file indexes, no counts, no plans, no history
inside a document, and no explanation kept in two places. Check both before
adding a doc, a section, or a comment that explains something rather than
does it. When in doubt, check the standard before inventing a pattern.

That second one earns its keep here more than in most repos. This template is
copied into every new CEM, so a paragraph that goes stale here goes stale in
every one of them, and nothing fails when it does.

Read `README.md` first: it is the rules, and this file is the working
practice on top of them.

Some files here are delivered by the shared
[`actions`](https://github.com/EmergentMatter/actions) templates and kept
current by its sync tooling: `LICENSE`, `NOTICE`, `STYLE.md`,
`CONTRIBUTING.md`, `SECURITY.md`, `SUPPORT.md`, `CODE_OF_CONDUCT.md`,
`ruff-base.toml`, `scripts/changeset.py`, and most of `.github/`. Never edit
one here, not even for a typo: a local change is indistinguishable from
staleness to a three-way sync, which has to arbitrate the difference. Change
the template instead.

## What a CEM is, and what it is not

A **computational engineering model** (CEM) turns **parameters into
geometry**. It owns the design: the numbers, the relationships between them,
and the rules about what combinations are valid. See the
[glossary](https://github.com/EmergentMatter/emergent-matter-sdm/blob/main/docs/glossary.md)
for this and every other ecosystem term, and
[concepts](https://github.com/EmergentMatter/emergent-matter-sdm/blob/main/docs/concepts.md)
for where a CEM sits in the wider pipeline.

It is **not** a renderer, a mesher, a solver, or an optimizer. Those consume a
CEM's output. If you are about to add one here, you are in the wrong repo:
`sdm-core` evaluates and emits, the SDM web viewer renders, the MCP server exposes the
geometry to an agent.

## The order of operations, and why it is not negotiable

1. `parameters.py`: declare, derive, validate
2. `cem.toml`: declare the same surface, machine-readably
3. `sdm/trees_*.py`: parameters to **signed distance field** (SDF) trees
4. `tests/test_build.py`: evaluate the field at points you can check by hand

Doing 3 before 1 produces geometry with the numbers inline, and then the
parameters get "extracted" later by reading the tree: at which point the
derived relationships are already lost, because a tree records `9.0`, not
`outer_radius - wall_thickness`.

## One file per physical part, and one owner per dimension

Before writing geometry, list the physical pieces. Each separable piece is
its own `Part` and its own file; never pack separate bodies into one Part's
material regions. Place them with `write_assembly`. The CEM owns every
dimension: change it here and regenerate, never edit or override a value in
the `.sdm`. When this CEM composes other CEMs, it owns the dimensions they
share and passes them down; a child never redeclares them. README's "One
Part per physical part" and "Top-down" sections are the rules.

## Never store a derived value

`d_bore_radius` is `@property`. So is anything computed from declared fields.

README's "Derived values are `@property`. Never a field." section has the
full story, the hexafoil bug; the rule it forces is: **a wrong CEM does not
crash, it produces a plausible part**, because nothing errors when a derived
value quietly disagrees with the inputs it's supposed to track.

Two tests hold the line, and both matter:
`test_derived_values_are_not_declared_as_params` (not in `cem.toml`, not in the
`.sdm`) and the manifest/dataclass drift checks in `test_manifest.py`.

## Verify by evaluating, never by validating

`verify()` returning `schema_ok: True` means the JSON is shaped right. It
says nothing about whether the geometry is what you meant. Every trap in
[`docs/traps.md`](docs/traps.md) validated cleanly while writing this
template.

So: after any change to a tree builder, **evaluate the field** at points whose
sign you know. `tests/test_build.py` is the pattern. It is cheap (JAX traces
once per module) and it is the only thing that distinguishes "it built" from
"it built the right thing".

## Adding a parameter: the full checklist

Miss any step and the failure is silent:

1. Field on the dataclass, prefixed by type (`d_` float, `n_` int, `b_` bool,
   `s_` str, `a_` array), with a docstring.
2. `[cem.params.<name>]` in `cem.toml`: type matching the prefix, default
   matching the field, `unit`, `role`, bounds if they are real.
3. `PARAM_FIELDS` in `sdm/assembly.py` **if** it should ship in the `.sdm`,
   with a unit from sdm-core's schema enum (`mm`, `count`, `rad`, `deg`,
   `ratio`, `N`, `MPa`, ...). An empty string is REFUSED, and the error reads
   as an unrelated validation dump.
4. A rule in `validate()` if any combination involving it is invalid, plus a
   `[[cem.constraints]]` entry with a `why`.
5. A field assertion in `test_build.py` if it changes the shape.

`test_manifest.py` catches 1-vs-2 in both directions. Nothing catches a missing
step 4 except you.

## Units

The `.sdm` is millimetres. `parameters.py` should be too, and say so in every
docstring. `d_` means *float*, not *millimetre*: angles are `d_` as well,
which is why `PARAM_FIELDS` carries an explicit unit per field instead of
inferring one from the prefix.

## Tests

```bash
uv run pytest
```

No visible windows, no GPU, no network. A CEM's tests should run in under a
second plus the JAX import.
