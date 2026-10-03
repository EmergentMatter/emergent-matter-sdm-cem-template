"""Compose the trees into one `Part`. This is the CEM's entry point.

`cem.toml` names `widget_sdf.sdm.assembly:build_widget_part` as `entry_point`,
so this signature is a contract: params in (or None for defaults), `Part` out.
"""

from __future__ import annotations

from software_defined_matter import MaterialRegion, Param, Part

from widget_sdf.parameters import WidgetParameters
from widget_sdf.sdm.trees_body import body_tree

__all__ = ["MATERIAL_ID", "MATERIAL_NAME", "PARAM_FIELDS", "build_widget_part"]

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


def _params_block(p: WidgetParameters) -> dict:
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


def build_widget_part(params: WidgetParameters | None = None, *, name: str = "widget") -> Part:
    """Build the widget as a single-material `Part`.

    Validates FIRST and raises on failure. A CEM that emits geometry from
    invalid parameters produces a plausible-looking part that violates its own
    design rules, and nothing downstream can tell.
    """
    params = params or WidgetParameters()
    errors = params.validate()
    if errors:
        raise ValueError("invalid widget parameters:\n  " + "\n  ".join(errors))

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
