"""The flanged bushing: SDF trees, the `.sdm` params, and the entry point.

This is the worked example of a full CEM: a tube, a bore, a flange and a bolt
circle, with every kind of declaration `cem.toml` supports. Its annotated
manifest is `cem.toml` beside this file, and `tests/test_example_bushing.py`
holds it to the same drift checks as the template's own.

WHY ONE FUNCTION PER FEATURE rather than one that builds everything: these are
the units a reviewer reads and a test pins. A single `build_tree()` is fine
until the first time someone needs the flange alone.

`capped_cylinder` takes `h` as a HALF-height. `_cylinder()` below takes a full
length and halves it in one place, so the factor of two lives once instead of
at every call site.
"""

from __future__ import annotations

import math
from typing import Any

from software_defined_matter import (
    MaterialRegion,
    Param,
    Part,
    sdf_op,
    sdf_primitive,
    sdf_transform,
)

from bushing_sdf.parameters import BushingParameters

__all__ = [
    "MATERIAL_ID",
    "MATERIAL_NAME",
    "PARAM_FIELDS",
    "body_tree",
    "bolt_circle_tree",
    "bore_tree",
    "build_bushing_part",
    "flange_tree",
    "tube_tree",
]


def _cylinder(*, radius: float, length: float, z_center: float) -> dict[str, Any]:
    """A z-axis cylinder of FULL `length`, centred at `z_center`.

    The one place the half-height convention is applied. `capped_cylinder`
    takes `h` as a half-height, and getting that wrong is silent: the part is
    simply twice as long as intended, which looks like a design error rather
    than a units error.
    """
    return sdf_transform(
        "translate",
        sdf_primitive("capped_cylinder", r=radius, h=length / 2.0),
        t=[0.0, 0.0, z_center],
    )


def tube_tree(p: BushingParameters) -> dict[str, Any]:
    """The outer tube, solid. The bore is cut in `body_tree`, not here."""
    return _cylinder(radius=p.d_outer_radius, length=p.d_length, z_center=p.d_length / 2.0)


def bore_tree(p: BushingParameters) -> dict[str, Any]:
    """The through-bore, overshooting both ends.

    A cut that stops exactly at a face leaves a coincident surface, and a
    coincident surface is a coin flip for every downstream mesher.
    """
    overshoot = 4.0 * p.d_voxel_size_mm
    return _cylinder(
        radius=p.d_bore_radius, length=p.d_length + 2.0 * overshoot, z_center=p.d_length / 2.0
    )


def flange_tree(p: BushingParameters) -> dict[str, Any]:
    """The flange disc at z = 0, with its bolt circle removed."""
    disc = _cylinder(
        radius=p.d_flange_radius, length=p.d_flange_thickness, z_center=p.d_flange_thickness / 2.0
    )
    holes = bolt_circle_tree(p)
    return sdf_op("subtract", [disc, holes]) if holes is not None else disc


def bolt_circle_tree(p: BushingParameters) -> dict[str, Any] | None:
    """Union of the bolt holes, or None when there are none.

    Returns None rather than an empty union: `sdf_op("union", [])` is a node
    whose meaning depends on the evaluator's identity element, and the two
    plausible answers (+inf and -inf) differ by the whole part. The schema also
    refuses it: `children` has `minItems: 1`.
    """
    if p.n_bolt_holes <= 0:
        return None
    overshoot = 4.0 * p.d_voxel_size_mm
    holes = []
    for i in range(p.n_bolt_holes):
        theta = i * p.d_bolt_angular_pitch
        holes.append(
            sdf_transform(
                "translate",
                sdf_primitive(
                    "capped_cylinder",
                    r=p.d_bolt_hole_radius,
                    h=(p.d_flange_thickness + overshoot) / 2.0,
                ),
                t=[
                    p.d_bolt_circle_radius * math.cos(theta),
                    p.d_bolt_circle_radius * math.sin(theta),
                    p.d_flange_thickness / 2.0,
                ],
            )
        )
    return holes[0] if len(holes) == 1 else sdf_op("union", holes)


def body_tree(p: BushingParameters) -> dict[str, Any]:
    """The whole bushing: tube and flange unioned, then the bore cut THROUGH both.

    Subtract-last is the point. Cutting the bore inside `tube_tree` and then
    unioning the flange over it re-fills the bore where the flange overlaps.
    The part looks right in a section through the tube and is solid where it
    matters. A cut that must pass through several features belongs at the level
    where all of them are present.
    """
    solid = sdf_op("union", [tube_tree(p), flange_tree(p)])
    return sdf_op("subtract", [solid, bore_tree(p)])


MATERIAL_ID = 1
MATERIAL_NAME = "nylon12_sls"

#: The fields that ship in the `.sdm` as params. Derived values are NOT here:
#: they are recomputed from these, and shipping them as free params is what
#: severs a derived value from its inputs (the hexafoil bug:
#: schema 0.2 cannot express a param expression, so a derived param written as
#: a free one desyncs the moment a slider moves).
#: field -> unit, and the units must come from sdm-core's schema enum
#: ("mm", "count", "rad", "deg", "ratio", "N", "MPa", ...). An empty string is
#: REFUSED by the schema, which is easy to hit and reads as an unrelated
#: validation dump. Written out per field rather than inferred from the prefix
#: because `d_` is a float, not a millimetre: an angle is `d_` too.
#: field -> (unit, (lo, hi)). Mirrors `cem.toml`; a test asserts they agree.
#:
#: BOUNDS ARE NOT OPTIONAL, and omitting them is a silent failure that only
#: shows up in a tool. A viewer builds its control from what the DOCUMENT says,
#: not from `cem.toml`, so a param emitted with `bounds: null` has no range to
#: slide between and renders as a control nothing can move. Declaring a range
#: in the manifest and leaving it out here means the manifest describes a
#: control nothing can offer.
PARAM_FIELDS = {
    "n_bolt_holes": ("count", (0, 24)),
    "d_outer_radius": ("mm", (4.0, 60.0)),
    "d_wall_thickness": ("mm", (0.8, 20.0)),
    "d_length": ("mm", (5.0, 200.0)),
    "d_flange_radius": ("mm", (5.0, 100.0)),
    "d_flange_thickness": ("mm", (1.0, 30.0)),
    "d_bolt_hole_radius": ("mm", (0.5, 10.0)),
    "d_bolt_circle_radius": ("mm", (3.0, 90.0)),
}


def _params_block(p: BushingParameters) -> dict:
    """`.sdm` params. Names lose the type prefix: `cem.toml` records that
    mapping under `emits`, so a consumer can join the two without guessing."""
    return {
        f.split("_", 1)[1]: Param(
            name=f.split("_", 1)[1],
            value=float(getattr(p, f)),
            free=False,
            bounds=bounds,
            unit=unit,
        )
        for f, (unit, bounds) in PARAM_FIELDS.items()
    }


def build_bushing_part(params: BushingParameters | None = None, *, name: str = "bushing") -> Part:
    """Build the bushing as a single-material `Part`.

    Validates FIRST and raises on failure. A CEM that emits geometry from
    invalid parameters produces a plausible-looking part that violates its own
    design rules, and nothing downstream can tell.
    """
    params = params or BushingParameters()
    errors = params.validate()
    if errors:
        raise ValueError("invalid bushing parameters:\n  " + "\n  ".join(errors))

    lo, hi = params.bbox()
    return Part(
        name=name,
        params=_params_block(params),
        materials=[
            MaterialRegion(
                material_id=MATERIAL_ID,
                name=MATERIAL_NAME,
                sdf_tree=body_tree(params),
            )
        ],
        metadata={"bbox": [lo, hi], "units": "mm"},
    )
