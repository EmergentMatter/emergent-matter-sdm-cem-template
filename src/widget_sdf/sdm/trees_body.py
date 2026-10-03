"""SDF trees for the widget, one function per feature.

WHY ONE FUNCTION PER FEATURE rather than one that builds everything: these are
the units a reviewer reads, a test pins, and a future per-leaf grid bakes. A
single `build_tree()` that returns the whole part is fine until the first time
someone needs the flange alone, and then it is a refactor under pressure.

Every function takes `WidgetParameters` and returns a tree. None of them read
globals, and none of them mutate anything.

THE OP NAME IS AN ENUM AND THE ERROR DOES NOT SAY SO. The schema admits
`union`, `subtract`, `intersect`, `smooth_union`, `smooth_subtract`,
`smooth_intersect`, `softmin_many`, `softmin_chunked`, `swept_min`,
`swept_min_zyz`, and nothing else. Write the natural-reading `difference` and
the `oneOf` branch simply fails to match, so validation reports
`Unevaluated properties are not allowed ('children', 'op', 'type' were
unexpected)` and dumps the whole tree. That message names every part of the
node except the one that is wrong. Check the op name first.

AND THE TRANSFORM KEYS ARE NOT VALIDATED AT ALL. `params` is typed as a bare
object in the schema, so a transform can be perfectly schema-valid and still
fail to evaluate: `translate` wants `t=`, and passing the natural-reading
`offset=` validates, saves, loads, and then dies inside the evaluator with a
bare `KeyError: 't'` and no node named. The keys are `t` (translate), `s`
(scale), `angle` (rotate_x/y/z), `R` (rotate_matrix), `c`/`l` (repeat).

PRIMITIVE KWARGS ARE UNVALIDATED THE SAME WAY, and `capped_cylinder` carries a
semantic trap on top: its signature is `(p, h, r)` where **h is HALF-height**.
So `radius=`/`height=` raises `TypeError: unexpected keyword argument`, which is
at least loud. But `h=full_length` is silent and builds a part twice as long as
intended. `_cylinder()` below takes a full length and halves it in one place, so
the factor-of-two lives once instead of at seven call sites.

Both traps have the same shape: the loud check (the schema) does not cover the
thing that breaks, and the thing that breaks reports without saying where. Run
the built .sdm through an actual evaluation before believing it. `tests/
test_build.py` is that check, and it is the reason it exists.
"""

from __future__ import annotations

import math
from typing import Any

from software_defined_matter import sdf_op, sdf_primitive, sdf_transform

from widget_sdf.parameters import WidgetParameters

__all__ = ["tube_tree", "bore_tree", "flange_tree", "bolt_circle_tree", "body_tree"]


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


def tube_tree(p: WidgetParameters) -> dict[str, Any]:
    """The outer tube, solid. The bore is cut in `body_tree`, not here."""
    return _cylinder(radius=p.d_outer_radius, length=p.d_length, z_center=p.d_length / 2.0)


def bore_tree(p: WidgetParameters) -> dict[str, Any]:
    """The through-bore, overshooting both ends.

    A cut that stops exactly at a face leaves a coincident surface, and a
    coincident surface is a coin flip for every downstream mesher.
    """
    overshoot = 4.0 * p.d_voxel_size_mm
    return _cylinder(
        radius=p.d_bore_radius, length=p.d_length + 2.0 * overshoot, z_center=p.d_length / 2.0
    )


def flange_tree(p: WidgetParameters) -> dict[str, Any]:
    """The flange disc at z = 0, with its bolt circle removed."""
    disc = _cylinder(
        radius=p.d_flange_radius, length=p.d_flange_thickness, z_center=p.d_flange_thickness / 2.0
    )
    holes = bolt_circle_tree(p)
    return sdf_op("subtract", [disc, holes]) if holes is not None else disc


def bolt_circle_tree(p: WidgetParameters) -> dict[str, Any] | None:
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


def body_tree(p: WidgetParameters) -> dict[str, Any]:
    """The whole widget: tube and flange unioned, then the bore cut THROUGH both.

    Subtract-last is the point. Cutting the bore inside `tube_tree` and then
    unioning the flange over it re-fills the bore where the flange overlaps.
    The part looks right in a section through the tube and is solid where it
    matters. A cut that must pass through several features belongs at the level
    where all of them are present.
    """
    solid = sdf_op("union", [tube_tree(p), flange_tree(p)])
    return sdf_op("subtract", [solid, bore_tree(p)])
