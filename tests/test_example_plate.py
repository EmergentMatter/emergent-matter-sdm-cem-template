"""The second example: builds, validates, and EVALUATES the field.

`examples/plate_sdf/` exists to demonstrate one trap the flanged bushing
cannot: `round_box` and `rounded_box_2d` disagree about what the radius does,
and both validate either way. These checks are what would catch getting it
backwards, which produces a plate more than twice its stated thickness.
"""

from __future__ import annotations

import dataclasses

import pytest
from plate_sdf.plate import PlateParameters, build_plate_part
from software_defined_matter import validate


@pytest.fixture(scope="module")
def part():
    return build_plate_part()


@pytest.fixture(scope="module")
def field(part):
    import jax.numpy as jnp
    from software_defined_matter.sdf.compile import make_sdf_closure

    closure = make_sdf_closure(part.materials[0].sdf_tree, part)
    free = jnp.asarray(closure.binding.initial_free_vector())
    return lambda p: float(closure(jnp.asarray(p), free))


def test_it_builds_and_validates(part):
    validate(part)


def test_the_plate_is_solid_between_the_holes(field):
    p = PlateParameters()
    assert field([0.0, p.d_width / 4.0, p.d_thickness / 2.0]) < 0.0


def test_the_top_face_is_where_the_thickness_SAYS(field):
    """THE point of this example. `round_box` subtracts its radius and
    `rounded_box_2d` does not; getting it backwards on a 6 mm plate with an
    8 mm corner radius silently builds a 16 mm plate that validates."""
    p = PlateParameters()
    d_y = p.d_width / 4.0
    assert field([0.0, d_y, p.d_thickness - 0.1]) < 0.0, "should still be solid"
    assert field([0.0, d_y, p.d_thickness + 0.1]) > 0.0, "should have ended"


def test_the_bottom_face_sits_on_z_zero(field):
    p = PlateParameters()
    assert field([0.0, p.d_width / 4.0, 0.1]) < 0.0
    assert field([0.0, p.d_width / 4.0, -0.1]) > 0.0


def test_a_hole_is_actually_a_hole(field):
    p = PlateParameters()
    assert field([p.hole_centres()[0], 0.0, p.d_thickness / 2.0]) > 0.0


def test_the_holes_go_all_the_way_through(field):
    """A cut that stops at a face leaves a coincident surface, which is a coin
    flip for every downstream mesher."""
    p = PlateParameters()
    d_x = p.hole_centres()[0]
    for d_z in (0.01, p.d_thickness / 2.0, p.d_thickness - 0.01):
        assert field([d_x, 0.0, d_z]) > 0.0, f"blocked at z={d_z}"


def test_the_corners_are_rounded_in_PLAN_not_in_section(field):
    """`round_box` rounds all twelve edges; a plate wants only the four
    vertical ones. A point just inside a long edge, at mid-thickness, must be
    solid: on a pillow it would already be outside."""
    p = PlateParameters()
    assert field([0.0, p.d_width / 2.0 - 0.2, p.d_thickness / 2.0]) < 0.0
    assert field([0.0, p.d_width / 2.0 + 0.2, p.d_thickness / 2.0]) > 0.0


def test_one_hole_is_centred_not_inset():
    assert dataclasses.replace(PlateParameters(), n_bolt_holes=1).hole_centres() == [0.0]


def test_zero_holes_does_not_divide_by_zero():
    p = dataclasses.replace(PlateParameters(), n_bolt_holes=0)
    assert p.hole_centres() == [] and p.d_hole_pitch == 0.0


def test_invalid_parameters_raise_rather_than_emit():
    p = dataclasses.replace(PlateParameters(), n_bolt_holes=24)
    with pytest.raises(ValueError, match="ligament_floor"):
        build_plate_part(p)
