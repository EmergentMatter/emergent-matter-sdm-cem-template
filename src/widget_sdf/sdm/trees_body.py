"""SDF trees for the widget.

WHY A FUNCTION PER FEATURE rather than one that builds everything: these are
the units a reviewer reads and a test pins. The block is one feature; a part
with more adds a function each, and a cut that must pass through several
belongs at the level where all of them are present (subtract last).

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

PRIMITIVE KWARGS ARE UNVALIDATED THE SAME WAY. `round_box` takes `b`, the
HALF-extents, and `r`; `capped_cylinder` takes `h` as a half-height too. A
full length where a half is wanted is silent and builds a part twice the size.
Here the factor of two is applied once, in `body_tree`.

Both traps have the same shape: the loud check (the schema) does not cover the
thing that breaks, and the thing that breaks reports without saying where. Run
the built .sdm through an actual evaluation before believing it. `tests/
test_build.py` is that check, and it is the reason it exists.
"""

from __future__ import annotations

from typing import Any

from software_defined_matter import sdf_primitive, sdf_transform

from widget_sdf.parameters import WidgetParameters

__all__ = ["body_tree"]


def body_tree(p: WidgetParameters) -> dict[str, Any]:
    """The rounded block, standing on z = 0 and centred on x and y.

    `round_box` keeps its half-extents `b` as the outer size and carves the
    radius out of them, so the block is exactly length x width x height.
    """
    return sdf_transform(
        "translate",
        sdf_primitive(
            "round_box",
            b=[p.d_length / 2.0, p.d_width / 2.0, p.d_height / 2.0],
            r=p.d_edge_radius,
        ),
        t=[0.0, 0.0, p.d_height / 2.0],
    )
