# Design regions: keep in, keep out, optional

A part that a later tool may change (a topology optimizer, a lightweighting pass, a
fabrication check) needs to say where it may and may not be changed. Only the CEM
knows that for sure: it placed the bearing seat, the bolt pads, the screwdriver
reach. A tool that is told by hand, with coordinates copied out of the CEM, goes
stale the first time a parameter moves, and nothing fails when it does.

So a CEM that knows these regions writes them into its part, next to the geometry.

## The three kinds

| Kind | Meaning | Examples |
|---|---|---|
| `keep_in` | Must stay solid | bearing seats, bolt pads, bore walls, sealing faces |
| `keep_out` | Never material | tool and fastener reach, clearance to a mating part, cable paths |
| `optional` | Material may be added here if it helps | room for a rib or gusset beyond the current shape |

Space a region does not mention follows the part: material that is there may be
removed, empty space stays empty.

When regions overlap:

1. **Keep out wins.** A clearance is physical.
2. **Keep in** applies where the part or an optional region is; it does not create
   material outside both.
3. **Optional** extends where material may be, so a tool's design space is the part,
   plus optional regions, minus keep-outs.

## Where it lives

In the part's `metadata`, under `design_regions`. The SDM schema keeps `metadata`
free-form, so this needs no sdm-core change and a tool that does not know the block
ignores it.

```json
"metadata": {
  "design_regions": {
    "version": 1,
    "keep_in":  [{"name": "bolt pad 1", "why": "solid under the screw head", "sdf_tree": {}}],
    "keep_out": [{"name": "driver reach, left wall screw", "why": "screwdriver from the front", "sdf_tree": {}}],
    "optional": [{"name": "above the plate", "why": "ribs may be added here", "sdf_tree": {}}]
  }
}
```

- `sdf_tree` is an ordinary SDF tree, the same kind as a material's, negative
  inside. Build it with the same `software_defined_matter` builders the part uses.
- Write its dimensions as parameter references, exactly as the part's own trees do,
  so the region moves with the part when a parameter changes. A region built from
  literal numbers is the hand-copied coordinate this convention exists to remove.
- `name` reads in a viewer and in a tool's log. `why` is the design reason: what a
  later engineer needs before deciding a region may go.
- Any kind may be absent or empty. A part with nothing to protect writes no block.

## Writing it from a CEM

In the part builder, after the materials:

```python
md = dict(part.metadata or {})
md["design_regions"] = {
    "version": 1,
    "keep_in": [
        {"name": "bolt pad 1", "why": "solid under the screw head", "sdf_tree": pad_tree(params, 0)},
    ],
    "keep_out": [
        {"name": "driver reach", "why": "screwdriver from the front", "sdf_tree": reach_tree(params)},
    ],
}
part.metadata = md
```

Build each region tree in `sdm/trees_*.py` beside the geometry it protects, from the
same parameters, and give it a field assertion in `tests/test_build.py` like any
other tree: evaluate it at a point you know is inside and one you know is outside.

## What checks it

`scripts/check_contract.py` checks the block's shape when a part has one: a known
version and kinds, a non-empty `name` and `why` on every entry, names unique within
a kind, a tree on every entry, and every parameter reference in a tree naming a
parameter the part declares. Whether a region sits where you meant it is a field
assertion's job, as for any tree.
