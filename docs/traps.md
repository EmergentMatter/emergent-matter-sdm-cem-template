# Traps

The mistakes this stack lets you make. Each one produces a document that
builds, validates, and is wrong, so none of them are caught by the checks that
exist by default.

They share one shape: **the loud check does not cover the thing that breaks.**
The schema validates structure. It catches a malformed document and misses a
well-formed one describing the wrong part. Plan your tests around that.

Everything here is permanent: a convention, a units boundary, a property of an
algorithm. Nobody is going to fix any of it, because none of it is broken.

A defect that somebody *could* fix does not belong here. Written down, it
outlives the fix and goes stale in every repository copied from this one, and
nothing fails when it does. File it against the repository that owns it and
link the issue instead.

For setting up, see the README. For the conventions to follow while editing,
see `CLAUDE.md`.

## Getting set up

Covered in the README, and `scripts/doctor.py` diagnoses a broken environment
and prints the fix. The failure worth knowing about names the wrong culprit:
an old interpreter surfaces inside the materials package as a `zip()`
`TypeError`.


## Writing geometry

**Op names are an enum.** `union`, `subtract`, `intersect`, `smooth_*`,
`softmin_*`, `swept_min*`. The natural-reading `difference` fails the `oneOf`
and the error names every part of the node except the wrong one.

**A param reference is `{"$ref": name}`**, built by `make_param_ref`. Writing
`{"param": name}` reaches the semantic checker and fails with
`unrecognised leaf`, pointing at the leaf rather than the shape you meant.

**Transform keyword names are `t`, `s`, `angle`, `R`, and `c`/`l`.** A wrong
key is refused by validation and the message names it.

**Half-height conventions are silent when wrong.** `capped_cylinder(h, r)` and
`extrusion(h)` both take `h` as a HALF-height. Passing a full length builds a
part twice as long and validates perfectly. Apply the factor of two in ONE
helper, not at every call site.

**`round_box` rounds all twelve edges,** not the four vertical ones. For a
plate you want a 2D rounded rectangle extruded, which is a different tree
entirely. `examples/plate_sdf/` is the worked version, with the field checks
that catch getting it wrong.

Both rounding primitives treat the radius the same way: the solid ends at the
half-extent you give, and the radius is carved out of it.

**An empty union is refused** (`children` has `minItems: 1`), and it is also
meaningless: its identity element could be positive or negative infinity, and
those differ by the whole part. Return `None` and let the caller decide.

**Subtract last.** A cut that must pass through several features belongs at the
level where all of them are present. Cutting inside one feature and then
unioning another over it silently re-fills the cut.

**Overshoot your cuts.** A hole that stops exactly at a face leaves a
coincident surface, which is a coin flip for every downstream mesher.

**Every param needs a unit from the schema's enum.** An empty string is
refused, and the error lists the enum.

## The CLI contract, which is more than two flags

Everything here was found by pointing a real viewer at a real part. All of it
passes every test a CEM can run on its own.

**`--out` and `--set` are necessary, not sufficient.** With both present and
working, the viewer still failed every parameter change with a 500.

**Accept the name the `.sdm` EMITS, not just the field name.** The document
strips the type prefix, so `n_bolt_holes` ships as `bolt_holes`, and
`cem.toml` records that under `emits`. The viewer reads the emitted name and
hands *that* back on re-emit, so a CLI that only knows the field name refuses
every rebuild:

    error: unknown parameter 'bolt_holes' -- did you mean 'n_bolt_holes'?

`emits` is the join key. Both spellings should work.

**An int param arrives as a float.** The `.sdm` stores every value as a JSON
number, so an integer round-trips as `6.0`. `int("6.0")` raises, and the error
complains about a whole number that visibly is one. Parse through `float`
first, then reject a genuinely non-integral value.

**The viewer EXECUTES your generator command.** `metadata.generator` records
the argv and cwd that produced the file, and re-emit runs it. So the recorded
command must still work from that directory, and the consent gate has to
approve it first, or you get `reemit_refused_untrusted` and a 500 with nothing
useful in the browser. Approve from a terminal:

    uv run python -c "from web_sdm_tool import trust; trust.approve('<key>')"

The key comes from `trust.judge(path, generator)`. The viewer may also offer
to approve in the app; the terminal recipe works either way.

The key is a hash of `{argv, cwd}`. **Both.** So it changes when you edit the
recorded command *and* when you move the CEM on disk. Renaming the directory
invalidates an approval that was working a minute ago, and the refusal looks
identical to never having approved at all.

**Declare the flags the CLI takes.** A tool driving your CEM cannot tell from
the recorded argv whether it accepts `--out` and `--set`. Undeclared, the
tool's only option is to write edited values into your `.sdm` and re-run the
command as recorded, which works only if the generator reads its own output.
One that does not rebuilds from its defaults and throws the edit away, and
nothing errors: the panel shows the new value and the geometry is the old
geometry.

```python
part.metadata["generator"] = {
    "argv": [...],
    "cwd": str(Path.cwd()),
    "accepts": ["--out", "--set"],
}
```

Both together or neither — `--set` without `--out` would have the generator
write over the source file mid-rebuild. `harness.py` stamps this for you and
`check_contract.py` fails without it.

Prefer the flags even if your CEM does read its own `.sdm`: they keep the
generator a pure function of its arguments rather than of its own previous
output, and a failed build cannot leave the `.sdm` holding params that
disagree with the geometry beside them.

**`--set` has to DO something.** Accepting the flag is not honouring it. A
generator whose values come from a frozen dataclass constructed with no
arguments parses every `--set` and applies none — and the "accepts the emitted
name" and "accepts the field name" checks both pass while it does.
`check_contract.py` nudges a real param and reads the value back.

**Re-emit re-runs your whole authoring command.** So record the command that
does the minimum producing a `.sdm`, and keep the authoring-only work behind
flags you leave off that recording: meshing and export, field sampling and
self-checks, optimisation, any solver call. Record
`metadata.generator.argv` without them.

Two properties follow, and `scripts/check_contract.py` checks both: the replay
has to be fast enough to sit under a slider, and it must write nothing but its
`--out`. A generator that meshes writes beside its script regardless of
`--out`, which corrupts the working tree on every release. The reasoning is in
that script's docstring, beside the budget it enforces.

## Materials

**Property names are terse symbols, not words.** `rho`, `E`, `sigma_y`, `nu`,
`UTS`. `get(mat, "density")` raises `KeyError`.

**The catalogue is SI; geometry is millimetres.** Density arrives in kg/m³ and
modulus in Pa, while your part is in mm. Convert once, at the boundary, and
never again downstream. A 1000x slip here passes every structural test, every
validation, and every geometry check, and reports a 3 m steel truss weighing 59
tonnes. Pin the converted value in a test against a number a human recognises,
like 7.85 g/cm³.

**Never hard-code a material property.** Two repos in this org currently size
parts against a stiffness the catalogue had already corrected. Read it.

## Objectives and metrics

**`volume` and `mass` are voxel integrals with a resolution floor.** They
refuse when cells cannot resolve the thinnest feature, and cap at 192 cells per
axis. For anything large and slender, roughly a span over 576 mm with
centimetre features, they are unavailable by construction. Compute the quantity
analytically instead. The refusal is loud and well worded, which is the right
behaviour, but it will surprise you.

**Round-trip through disk after saving.** `save` validates, but loading the
file back also catches anything the writer does on the way out.

## If you add an optimiser

**Everything inside a `jit` trace is abstract,** including values built from
constants. A helper that calls `float()` works standalone and raises
`ConcretizationTypeError` inside the trace, with the traceback pointing at
whatever created the tracer rather than at the conversion. Compute concrete
values outside and close over them.

**A quadratic penalty approaches feasibility from outside.** Ramping the
penalty therefore buys feasibility by adding material every round, and the last
iterate is often the worst one. Keep the best feasible iterate. In the truss
CEM this was worth 24%.

**Name a ratio so it says whether the safety factor is in it.** "Buckling
ratio" and "buckling utilisation" differ by exactly the safety factor, and one
label for both is how a margin gets read as twice what it is.

**Do not infer provenance.** `radii is not None` means radii were supplied, not
that they were optimised. A uniform array is not a solved design, and a reader
of the emitted file cannot tell the difference unless you record it.

## Testing

**Evaluate the field, do not just build it.** Every trap above produces a
document that validates. Pick points whose signed distance you can compute by
hand: on an axis the field equals minus the radius, on a surface it is zero, a
known distance outside it is that distance.

**Derive your expected values carefully.** While writing the truss CEM a field
check "failed" at a point that turned out to have a member running through it.
The code was right and the hand-calculation was wrong. That is still the test
working: it forced someone to look.

**Copy `tests/test_manifest.py` verbatim.** It checks `cem.toml` against the
Python in both directions and asserts every declared constraint can actually
fire. Nothing else reads the manifest, so without it the manifest drifts into
describing a design nobody is building. It transferred between two unrelated
CEMs with only name substitutions.

**Test the degenerate cases inside your bounds.** Zero holes and one hole are
both legal, both meaningful, and both divide by zero in the obvious
implementation of a pitch.

## Known gaps, tracked elsewhere

Two things about this stack are defects rather than conventions, and both are
known. Neither is a rule to learn.

- The viewer and sdm-core have drifted, so a checkout of both at their default
  branches cannot render.
- Re-emit replays the recorded generator synchronously, so a slow command
  freezes the viewer rather than merely being slow, and from the browser that
  is indistinguishable from a parameter being ignored.

Before adding anything here, check it against the current sdm-core. Several
entries that used to live in this file described behaviour that has since been
fixed, and a workaround outlives its fix silently. If somebody could fix it, it
is an issue, not a trap.
