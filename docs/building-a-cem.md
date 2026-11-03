# Building a CEM

What to change after `scripts/rename.py`, in what order, and the rules a CEM
follows. [`traps.md`](traps.md) lists the mistakes this stack lets you make
that still build and validate; [`CLAUDE.md`](../CLAUDE.md) is the working
practice on top of both.

## What to change, in order

1. **Wire up release control for your CEM.** `.github/workflows/version.yml`
   needs no repo secret: `emergent-matter-sdm-core` resolves from the org's
   package index, not a private-sibling checkout. Adjust
   `.github/CODEOWNERS` if this CEM has different owners than the
   template's default.
2. **Rewrite `parameters.py`.** This is the design. Declared fields, derived
   `@property`, and `validate()`: see the rules below.
3. **Rewrite `sdm/trees_*.py`.** One function per feature.
4. **Update `cem.toml`** to match. `tests/test_manifest.py` fails until it does,
   in both directions.
5. **Rewrite `tests/test_build.py`'s field assertions** for your geometry. Keep
   the *style*: points whose answers you know by hand.

## The rules a CEM follows

### Derived values are `@property`. Never a field.

`d_half_min_side` is `min(d_length, d_width, d_height) / 2`. Write it down as a
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

Per-param bounds cannot express `d_edge_radius < d_half_min_side`, a limit
on a *derived* value. The bushing example adds an ordering like
`tube < bolt_circle < flange` and a floor on `d_flange_ligament` (which depends
on `n_bolt_holes`). Those go in
`validate()` **and** in `cem.toml`'s `[[cem.constraints]]`, each with a `why`:
a constraint whose reason lives only in someone's head gets relaxed by the
next person who finds it inconvenient.

`test_every_declared_constraint_is_actually_enforced` is what stops the two
from drifting.

### `cem.toml` is the machine-readable surface

Every param with its type, default, unit, coupling `role`, bounds, and the
name it `emits` as in the `.sdm`. It is read **without importing anything**:
`sdm-sidecar cem show` parses it and never resolves `entry_point`. Keep it
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

`harness.py` stamps `metadata.generator` with the command that produced the
file, as `uv run --frozen <script> ...` with a `cwd` relative to the `.sdm`, so
the file re-emits on any machine. Without it the `.sdm` can be rendered and never re-derived.

**Read [`docs/traps.md`](docs/traps.md) before writing geometry.** It is the
list of mistakes this stack lets you make that produce a document that
builds, validates, and is wrong.
