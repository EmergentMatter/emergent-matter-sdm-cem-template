# How an assembly says it goes together

Every assembly a CEM writes carries its build sequence: which instances go
in, in what order, from which direction, with what tool. The CEM writes it,
because only the CEM knows the design intent; a viewer reads it to explode
the assembly and play the build. `scripts/check_geometry.py` fails an
assembly that has none, or whose steps do not add up.

## Where it lives

In an assembly `.sdm`, under `metadata.assembly_process`. The SDM schema
keeps `metadata` free-form, so this needs no sdm-core change, and tools that
do not know it ignore it. Only assemblies carry it: a part can go in many ways
in many contexts, but within one assembly its way in is fixed.

Each assembly describes only its own instances. A sub-assembly is built by
its own process and installed into its parent as one unit, in a step of the
parent. A viewer plays one assembly at a time: its own steps, with its
sub-assemblies arriving finished; the sub-assembly's own build is played by
picking the sub-assembly.

## Build the tree the way the thing is built

Structure the assembly the way it would come together on an assembly line,
so that reading the tree top to bottom walks through the build:

- **A sub-assembly is a station.** Group parts into a sub-assembly when they
  are built up together off the main line and then installed as one unit
  (a finger with its pins and covers, a stator with its coils). Do not group
  by part type ("all the screws") or by file convenience; group by when and
  where they go together. Nest as deep as the real build nests.
- **List instances in build order.** In every assembly, `base` first, then
  each step's instances in step order. The tree then reads as the build, and
  a viewer playing the steps and a person scrolling the tree see the same
  sequence. The checker fails an assembly whose instances are out of build
  order, and says which order it expected.
- **Fasteners go with what they fasten.** A screw is installed in the step
  that installs (or closes) the part it holds, not in a pile at the end,
  unless the real build really does fasten everything last.

## Shape

```json
"assembly_process": {
  "version": 1,
  "base": ["frame"],
  "steps": [
    {
      "id": "bearings",
      "name": "Press the bearings into the frame",
      "instances": ["bearing_lower", "bearing_upper"],
      "direction": [0, 0, 1],
      "travel": 25.0,
      "rotate": null,
      "tool": "Arbor press, bearing driver Ø42",
      "fasteners": [],
      "notes": "Outer race only; support the frame bore."
    },
    {
      "id": "lid",
      "name": "Screw the lid down",
      "instances": ["lid", "lid_screw_0", "lid_screw_1"],
      "direction": [0, 0, -1],
      "travel": 40.0,
      "tool": "2.5 mm hex key, 1.2 N·m",
      "fasteners": ["lid_screw_0", "lid_screw_1"]
    }
  ]
}
```

| Key | Meaning |
|---|---|
| `base` | Instances already in place before step one (the part everything is built onto). Optional. |
| `steps` | In build order. |
| `id` | Unique within this assembly. |
| `name` | One line, imperative, for the person building it. |
| `instances` | Instance ids of THIS assembly that this step installs. A sub-assembly's id installs the whole unit. |
| `direction` | Unit vector in this assembly's frame: the way the parts MOVE to reach their place. They start `travel` mm back along it. |
| `travel` | Approach distance in mm: how far back the parts start, and how far they sit out in the exploded view. Optional; the viewer uses the parts' size along `direction` if missing. |
| `rotate` | Optional twist while going in (screw in, bayonet, twist-lock): `{"axis": [x, y, z], "angle_deg": 90}`, about the axis through the parts' centre. |
| `tool` | Free text: tool, fixture, torque. Optional. |
| `fasteners` | Which of `instances` are fasteners, so a viewer can show them after what they hold. Optional. |
| `notes` | Free text for the person building it. Optional. |

`direction` may be left out for a part that is mated (sdm-core `mates`): the
viewer then uses the +Z axis of the mate's child port, which is where a
prismatic mate already slides. State it explicitly whenever the two differ.

## What a viewer does with it

- **Explode**: a slider moves each step's parts out along `-direction` by up to
  `travel`, later steps along the same direction further out, so a stack
  separates in order.
- **Build sequence**: Previous / Next / Play, for the assembly picked. Parts
  not yet installed are hidden; the current step's parts slide (and twist)
  in from their start; the step's name, tool, fasteners and notes are shown.

## What the checker refuses

Instances listed out of build order, an instance id that does not exist, an
instance installed twice, an instance never installed and not in `base`, a
step with no usable `direction` (and no
mate to take one from), a `travel` that is not a positive number, a `rotate`
without an axis and an angle. An assembly that genuinely has no meaningful
sequence (a single fixed weldment, say) says so in
`metadata.geometry_exceptions.assembly_process` with a reason.

## Why it is metadata, and why per assembly

`metadata` is free-form in the SDM schema, so a CEM can write this today and
every other tool ignores it. A part can be installed many ways in many
contexts; only the assembly that places it knows which one applies, so the
sequence lives with the instances it orders, and a sub-assembly carries its
own.
