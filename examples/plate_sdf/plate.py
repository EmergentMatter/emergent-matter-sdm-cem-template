"""A rounded mounting plate, and the rounding trap the bushing does not hit.

THE TRAP: `round_box` rounds all TWELVE edges of a cuboid, top and bottom
included, which makes a pillow rather than a plate. A plate has four rounded
VERTICAL corners and sharp faces.

Both primitives produce geometry and both validate, so nothing catches the
wrong one. The shape you want comes from building the profile in 2D and pushing
it through the thickness, which is a different tree entirely.

`extrusion` takes `h` as a HALF-height, the same convention as
`capped_cylinder`. Apply the factor of two in one place.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from software_defined_matter import (
    MaterialRegion,
    Param,
    Part,
    sdf_2d_to_3d,
    sdf_op,
    sdf_primitive,
    sdf_transform,
)

__all__ = [
    "PlateParameters",
    "body_tree",
    "bolt_row_tree",
    "build_plate_part",
]

MATERIAL_ID = 1
MATERIAL_NAME = "aluminum_6061_t6"


@dataclass(frozen=True)
class PlateParameters:
    """The plate's design. Same rules as `WidgetParameters`."""

    n_bolt_holes: int = 4
    d_length: float = 120.0
    d_width: float = 40.0
    d_thickness: float = 6.0
    d_corner_radius: float = 8.0
    d_hole_radius: float = 2.6
    d_edge_inset: float = 10.0
    d_voxel_size_mm: float = 0.4

    @property
    def d_hole_pitch(self) -> float:
        """Zero below two holes, which is legal and must not divide by zero."""
        if self.n_bolt_holes < 2:
            return 0.0
        return (self.d_length - 2.0 * self.d_edge_inset) / (self.n_bolt_holes - 1)

    @property
    def d_ligament(self) -> float:
        """Material between adjacent holes. Infinite when there is none."""
        if self.n_bolt_holes < 2:
            return math.inf
        return self.d_hole_pitch - 2.0 * self.d_hole_radius

    def hole_centres(self) -> list[float]:
        """x positions from the plate centre. One hole is CENTRED, not inset,
        because a lone hole at the inset reads as a bug to anyone who sees it."""
        if self.n_bolt_holes < 1:
            return []
        if self.n_bolt_holes == 1:
            return [0.0]
        d_span = self.d_length - 2.0 * self.d_edge_inset
        return [-d_span / 2.0 + i * self.d_hole_pitch for i in range(self.n_bolt_holes)]

    def validate(self) -> list[str]:
        errs: list[str] = []
        if self.d_corner_radius >= min(self.d_length, self.d_width) / 2.0:
            errs.append(
                f"corner_fits_the_plate: radius {self.d_corner_radius} >= half "
                "the short side; the fillets would meet"
            )
        if 2.0 * self.d_hole_radius >= self.d_width:
            errs.append("hole_fits_the_width: the hole breaks out of both long edges")
        if self.d_ligament < 2.0:
            errs.append(
                f"ligament_floor: only {self.d_ligament:.2f} mm between holes "
                "(floor 2.0); this is a perforation, not a bolt row"
            )
        return errs


def body_tree(p: PlateParameters):
    """A 2D rounded rectangle, extruded. NOT `round_box`: see the module docstring."""
    return sdf_transform(
        "translate",
        sdf_2d_to_3d(
            "extrusion",
            sdf_primitive(
                "rounded_box_2d",
                b=[p.d_length / 2.0, p.d_width / 2.0],
                r=p.d_corner_radius,
            ),
            h=p.d_thickness / 2.0,  # HALF-height
        ),
        t=[0.0, 0.0, p.d_thickness / 2.0],
    )


def bolt_row_tree(p: PlateParameters):
    """Union of the holes, or None. Never an empty union: its identity element
    could be +inf or -inf and those differ by the whole part."""
    centres = p.hole_centres()
    if not centres:
        return None
    # fmt: off
    d_over = 4.0 * p.d_voxel_size_mm      # overshoot: a cut that stops at a
    d_len = p.d_thickness + 2.0 * d_over  # face leaves a coincident surface
    # fmt: on
    holes = [
        sdf_transform(
            "translate",
            sdf_primitive("capped_cylinder", r=p.d_hole_radius, h=d_len / 2.0),
            t=[d_x, 0.0, p.d_thickness / 2.0],
        )
        for d_x in centres
    ]
    return holes[0] if len(holes) == 1 else sdf_op("union", holes)


def build_plate_part(params: PlateParameters | None = None, *, name: str = "plate") -> Part:
    """Validate first, then build. Geometry from invalid parameters is a
    plausible-looking part that violates its own rules."""
    p = params or PlateParameters()
    errors = p.validate()
    if errors:
        raise ValueError("invalid plate parameters:\n  " + "\n  ".join(errors))

    body = body_tree(p)
    holes = bolt_row_tree(p)
    tree = body if holes is None else sdf_op("subtract", [body, holes])

    d_v = p.d_voxel_size_mm
    return Part(
        name=name,
        params={
            "length": Param(name="length", value=p.d_length, unit="mm", bounds=(40.0, 400.0)),
            "width": Param(name="width", value=p.d_width, unit="mm", bounds=(15.0, 200.0)),
            "thickness": Param(
                name="thickness", value=p.d_thickness, unit="mm", bounds=(1.0, 30.0)
            ),
        },
        materials=[MaterialRegion(material_id=MATERIAL_ID, name=MATERIAL_NAME, sdf_tree=tree)],
        metadata={
            "bbox": [
                [-p.d_length / 2.0 - d_v, -p.d_width / 2.0 - d_v, -d_v],
                [p.d_length / 2.0 + d_v, p.d_width / 2.0 + d_v, p.d_thickness + d_v],
            ],
            "units": "mm",
        },
    )
