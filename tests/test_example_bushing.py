"""The flanged bushing example: build it, evaluate its field, and check its
parameter model.

The template's own part is a rounded block (see `test_build.py`). The bushing
is kept as the worked example of a full CEM, and these are its tests: the
field evaluated at points whose answers are known by hand, the derived values,
and the constraints `validate()` owns. Its manifest is held to the same drift
checks as the template's in `test_manifest.py`.
"""

from __future__ import annotations

import dataclasses
import math

import pytest
from bushing_sdf.bushing import build_bushing_part
from bushing_sdf.parameters import BushingParameters


@pytest.fixture(scope="module")
def part():
    return build_bushing_part()


@pytest.fixture(scope="module")
def field(part):
    """The compiled field. Module-scoped: the first call pays a JAX trace.

    `make_sdf_closure(tree, part)` returns `fn(points, free_vec)`; the second
    argument is the free-param vector, and None is correct while every param
    is `free=False`.
    """
    import jax.numpy as jnp
    from software_defined_matter.sdf.compile import make_sdf_closure

    fn = make_sdf_closure(part.materials[0].sdf_tree, part)

    def f(*points):
        return [float(v) for v in fn(jnp.asarray(points, dtype=float), None)]

    return f


def test_it_builds(part) -> None:
    assert part.name == "bushing"
    assert len(part.materials) == 1
    assert part.metadata["units"] == "mm"


def test_it_validates_against_the_schema(part, tmp_path) -> None:
    """Necessary, and demonstrably not sufficient (see this module's docstring)."""
    from software_defined_matter import load, save

    p = tmp_path / "bushing.sdm"
    save(part, p)
    assert load(p, b_validate_schema=True) is not None


def test_invalid_parameters_do_not_produce_geometry() -> None:
    """A CEM that emits from invalid params makes a plausible-looking part that
    violates its own design rules, and nothing downstream can tell."""
    bad = dataclasses.replace(BushingParameters(), n_bolt_holes=24)
    with pytest.raises(ValueError, match="flange_ligament_floor"):
        build_bushing_part(bad)


# ── the field, at points whose answers are known by hand ───────────────────


def test_the_tube_wall_is_solid(field) -> None:
    p = BushingParameters()
    r_mid = (p.d_bore_radius + p.d_outer_radius) / 2.0
    assert field([r_mid, 0.0, p.d_length * 0.75])[0] < 0.0


def test_the_bore_is_open_all_the_way_through(field) -> None:
    """The regression guard for subtract-last.

    Cut the bore inside `tube_tree` and union the flange over it and the bore
    fills in where the flange overlaps: a blocked bushing that still sections
    correctly through the tube.
    """
    p = BushingParameters()
    # fmt: off
    for z in (p.d_flange_thickness * 0.5,          # inside the flange
              p.d_flange_thickness + 1.0,          # just past it
              p.d_length * 0.5, p.d_length * 0.9):  # up the tube
        # fmt: on
        assert field([0.0, 0.0, z])[0] > 0.0, f"bore is blocked at z={z}"


def test_the_flange_is_solid_between_its_holes(field) -> None:
    import math

    p = BushingParameters()
    mid = p.d_bolt_angular_pitch / 2.0  # halfway between two holes
    x = p.d_bolt_circle_radius * math.cos(mid)
    y = p.d_bolt_circle_radius * math.sin(mid)
    assert field([x, y, p.d_flange_thickness / 2.0])[0] < 0.0


def test_each_bolt_hole_is_actually_a_hole(field) -> None:
    """All of them, not just the first. An off-by-one in the angular sweep
    leaves one hole on top of another and the count still looks right."""
    import math

    p = BushingParameters()
    for i in range(p.n_bolt_holes):
        th = i * p.d_bolt_angular_pitch
        x = p.d_bolt_circle_radius * math.cos(th)
        y = p.d_bolt_circle_radius * math.sin(th)
        d = field([x, y, p.d_flange_thickness / 2.0])[0]
        assert d > 0.0, f"hole {i} at angle {math.degrees(th):.0f} deg is solid"


def test_outside_the_envelope_is_empty(field) -> None:
    p = BushingParameters()
    assert field([0.0, 0.0, p.d_length + 10.0])[0] > 0.0
    assert field([p.d_flange_radius + 10.0, 0.0, 1.0])[0] > 0.0


def test_the_part_is_not_twice_as_long_as_declared(field) -> None:
    """The half-height trap. `h=d_length` instead of `h=d_length/2` builds a
    part of exactly double the length and nothing else complains."""
    p = BushingParameters()
    r_mid = (p.d_bore_radius + p.d_outer_radius) / 2.0
    assert field([r_mid, 0.0, p.d_length * 1.5])[0] > 0.0, (
        "there is material well past the declared length"
    )


def test_a_bolt_count_of_zero_leaves_a_plain_flange(field) -> None:
    """`sdf_op("union", [])` is refused by the schema (minItems 1) and its
    meaning depends on the evaluator's identity element, so the builder returns
    None instead and the caller skips the subtract."""
    import jax.numpy as jnp
    from software_defined_matter.sdf.compile import make_sdf_closure

    p = dataclasses.replace(BushingParameters(), n_bolt_holes=0)
    part = build_bushing_part(p)
    fn = make_sdf_closure(part.materials[0].sdf_tree, part)
    d = fn(
        jnp.asarray([[p.d_bolt_circle_radius, 0.0, p.d_flange_thickness / 2.0]], dtype=float), None
    )
    assert float(d[0]) < 0.0, "the bolt circle should be gone"


# ── the parameter model ───────────────────────────────────────────────────


def test_defaults_are_valid() -> None:
    """A template whose defaults do not build teaches the wrong first move."""
    assert BushingParameters().validate() == []


def test_derived_values_follow_their_inputs() -> None:
    """The property, not a stored field: this is the rule the template exists
    to demonstrate, so it gets a test rather than only a comment."""
    p = dataclasses.replace(BushingParameters(), d_outer_radius=20.0, d_wall_thickness=5.0)
    assert p.d_bore_radius == 15.0
    assert (
        not hasattr(type(p), "__dataclass_fields__")
        or "d_bore_radius" not in type(p).__dataclass_fields__
    ), "d_bore_radius must be derived, never a field: two sources of truth"


def test_bolt_pitch_closes_the_circle() -> None:
    p = BushingParameters()
    assert p.n_bolt_holes * p.d_bolt_angular_pitch == pytest.approx(2 * math.pi)


def test_too_many_holes_is_a_perforation() -> None:
    """The constraint that cannot be a bound: it depends on a derived value
    which depends on n_bolt_holes."""
    errs = dataclasses.replace(BushingParameters(), n_bolt_holes=24).validate()
    assert any("flange_ligament_floor" in e for e in errs), errs


def test_a_wall_thicker_than_the_radius_leaves_no_bore() -> None:
    errs = dataclasses.replace(BushingParameters(), d_wall_thickness=99.0).validate()
    assert any("wall_thickness_below_outer_radius" in e for e in errs), errs


def test_validate_reports_every_problem_at_once() -> None:
    """Not one exception at a time: an optimizer or an agent should see the
    whole picture, not fix five things in five round trips."""
    errs = dataclasses.replace(
        BushingParameters(),
        d_wall_thickness=99.0,
        d_flange_radius=1.0,
    ).validate()
    assert len(errs) >= 2, errs


def test_the_bbox_contains_the_part() -> None:
    p = BushingParameters()
    lo, hi = p.bbox()
    assert lo[0] <= -max(p.d_outer_radius, p.d_flange_radius)
    assert hi[2] >= p.d_length
