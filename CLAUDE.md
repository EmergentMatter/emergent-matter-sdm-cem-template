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

Read [docs/building-a-cem.md](docs/building-a-cem.md) first: it is the rules,
and this file is the working practice on top of them.

Some files here are delivered by the shared
[`actions`](https://github.com/EmergentMatter/actions) templates and kept
current by its sync tooling: `LICENSE`, `NOTICE`, `STYLE.md`,
`CONTRIBUTING.md`, `SECURITY.md`, `SUPPORT.md`, `CODE_OF_CONDUCT.md`,
`ruff-base.toml`, `scripts/changeset.py`, and most of `.github/`. Never edit
one here, not even for a typo: a local change is indistinguishable from
staleness to a three-way sync, which has to arbitrate the difference. Change
the template instead.

## Building a part

Every part in this repo is built through the CEM.

- Every dimension a person may want to change is a parameter: a field on
  `WidgetParameters` in `src/widget_sdf/parameters.py` and a matching
  `[cem.params.<name>]` entry in `cem.toml`. A number that appears only inside
  a tree builder is not adjustable, and the viewer shows no parameters for it.
- The part lives in this project's own package, the only directory under
  `src/`: `src/widget_sdf/`. Edit the parameters and the tree builders under
  `src/widget_sdf/sdm/`. Never create a second package under `src/`, and never
  write a build script beside them: the build command and Regenerate both use
  this package.
- Build with the package's CLI, into `output/`:
  `uv run widget-build --out output/part.sdm --set <name>=<value>`.
- If `uv` is not on the machine, the dependencies are already installed. Run
  the same CLI directly:
  `PYTHONPATH=src python -m widget_sdf.sdm.cli --out output/part.sdm --set <name>=<value>`
  (drop the `PYTHONPATH=src` prefix where the environment already sets it).
  Never try to install anything or fetch `uv`: no `pip install`, no downloads.
- Where there is no `uv`, the work is saved for you each turn: do not run
  `git add`, `git commit` or `git config`. On a local machine, commit only when
  asked.
- `sdm-sidecar` and the viewer are never needed to build or test: the package
  CLI and pytest are the whole loop.
- Every parameter a person may change ships in the `.sdm` with `free=True`
  (see `PARAM_FIELDS` in `src/widget_sdf/sdm/assembly.py`), or the Scene panel
  shows nothing for it. Only a param `cem.toml` gives the role `tool` or
  `derived`, or no role, may ship fixed.
- After a build, open the part with the `open_part` MCP tool where that tool is
  available, so the person sees it; otherwise tell them its path,
  `output/part.sdm`, and to open that file.
- Never write a `.sdm` by hand or from a script of your own, and never build
  geometry in a standalone script or notebook with fixed values. Only the
  package's CLI makes a `.sdm`. If a build fails, stop and report the failure
  with its output.
- Run `uv run pytest` after a change (`python -m pytest` where there is no
  `uv`). A new parameter follows the checklist under "Adding a parameter"
  below.

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
`min(length, width, height) / 2`.

## Never store a derived value

`d_half_min_side` is `@property`. So is anything computed from declared fields.

The "Derived values are `@property`. Never a field." section of
[docs/building-a-cem.md](docs/building-a-cem.md) has the full story, the
hexafoil bug; the rule it forces is: **a wrong CEM does not crash, it
produces a plausible part**, because nothing errors when a derived value
quietly disagrees with the inputs it's supposed to track.

Two tests hold the line, and both matter:
`test_derived_values_are_not_declared_as_params` (not in `cem.toml`, not in the
`.sdm`) and the manifest/dataclass drift checks in `test_manifest.py`.

## Every dimension is free, an input, or driven. Nothing dangles

Parametric modelling is the point. Change a requirement, rerun, and every
dimension that depends on it must move; a number typed into the shape code
looks right today and is silently wrong the first time an input changes.

Every dimension gets its value exactly one of three ways:

- **Free:** declared in `cem.toml` with `origin = "free"` and `bounds`. The
  designer picked it, it is not set by anything outside the part, and an
  optimizer may move it within its bounds. Early in a design many dimensions
  are free; that is fine, as long as each one says so.
- **Input:** declared with `origin = "input"` and set from outside the part: a
  requirement, a bought part, a standard, a process limit, or a parent
  assembly. Fixed unless marked `tradeable = true`, so an optimizer cannot
  "solve" a design by changing what it was asked to meet.
- **Driven:** computed from other dimensions (`@property`). Never declared.

**Driving is not a label.** A dimension is driving when something else moves
with it, and any of the three can be: a free inset that places a hole, an input
bearing bore that sets a pocket, a driven wall that sets a fillet (a chain).
sdm-core's dimension audit finds which by nudging each declared dimension and
watching what moves. A hand-written label would drift from what the code does.

- **Every declared dimension names its `source`:** `requirement:<id>`,
  `part:<vendor>:<number>`, `standard:<name, clause>`,
  `process:<profile>:<limit>`, `parent:<assembly>:<param>`, `choice: <why>`
  (a reasoned design decision, the usual source of a free one), or
  `tool: <what>`. A number with no source is a guess nobody can check.
- **A process limit is a floor, not a driver.** The wall is sized by its load;
  the minimum wall is the floor under it. Write it as a driven dimension
  (`max(load_sized_wall, min_wall)`) or as a `validate()` rule on a free one,
  not as the wall itself. Declare the floor as an input with
  `role = "derived"`; it is allowed to move no geometry.
- **A number that comes from somewhere else is never retyped.** One home per
  number; everything else points at it. A groove for a spring is driven by
  the spring's width, not by a second copy of it.
- **The AI writes structure, not values.** Every number you type is a guess
  that has to be re-checked forever; every reference you write is one decision,
  checked once. Prefer reading a value to typing it.
- **A bought part is one entry,** and its dimensions are read off it (head
  diameter, thread, width). Swap the part and every dimension that depends on
  it moves together.
- **Rules judge; they never assign.** `validate()` reports how far past a
  limit a value is. It never clamps the value back, which would hide the
  problem.
- **A clearance is applied at exactly one place,** so it is never added twice
  or forgotten once.
- **A clean audit is evidence about what it covers, not about what it does
  not.** It checks that nothing dangles, not that each input points at the
  right thing. `parent:motor:case_radius` is checked for form, not against the
  motor's file. When the tests are green, ask what drives each dimension.
- **Turning literals into parameters must not change the part.** Build and
  hash the output before, wire the parameters in, rebuild, compare hashes.
  Identical output proves the wiring; a part that merely looks right does not.

`tests/test_dimensions.py` holds the line by calling sdm-core's
`assert_dimensions` on this CEM's part and its declared dimensions. The check
lives in sdm-core so every CEM runs the same one; copy the test (it is a few
lines) and point it at your part. It fails on a number no declared dimension
moves (typed in), a declared dimension that moves nothing (unused, unless it
is a limit or a tool setting), a length that does not scale with the rest (a
typed-in offset, `outer_radius + 1.3`), and a declaration missing its origin,
source or bounds. Plain constants (0, 1/2, 1, 2, angles of whole 15 degree
steps from counts) are allowed.

(These rules come from the Parametric Function Table spec,
`emergent-matter-parametric-function-table`, which is retired as a format.
The rules stand.)

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

`examples/bushing_sdf/` is a full worked CEM to copy from, with an annotated
`cem.toml`.

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
6. An `origin` (`free` with `bounds`, or `input`) and a `source` in
   `cem.toml`: the requirement, part, standard, process limit, parent assembly
   or reasoned choice the value comes from. `test_dimensions.py` refuses a
   dimension without them.

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

Without `uv`: `python -m pytest`.

No visible windows, no GPU, no network. A CEM's tests should run in under a
second plus the JAX import.
