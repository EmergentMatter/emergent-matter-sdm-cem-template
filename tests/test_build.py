"""Build the part and evaluate the field. The test that actually has teeth.

WHY THIS EXISTS AND WHAT IT CAUGHT. Writing this template hit three separate
bugs that the schema validated happily and that only an EVALUATION found:

1. `sdf_op("difference", ...)`: the op name is an enum and `difference` is not
   in it. The `oneOf` branch fails to match, so the error is
   `Unevaluated properties are not allowed ('children', 'op', 'type' were
   unexpected)` plus a dump of the whole tree: a message that names every part
   of the node except the one that is wrong.
2. `sdf_transform("translate", child, offset=[...])`: the transform's `params`
   is a bare object in the schema, so `offset` validates, saves, loads, and then
   dies inside the evaluator as `KeyError: 't'`, with no node named.
3. `sdf_primitive("capped_cylinder", radius=..., height=...)`: wrong kwargs
   (`r`/`h`), and `h` is a HALF-height. The wrong names raise loudly; the wrong
   convention does not, and silently builds a part twice as long.

Every one of those produced a file where `verify()` returned `schema_ok: True`.
A CEM test suite that stops at "it builds and validates" is testing the wrong
thing, so this one asks the field questions with known answers.
"""

from __future__ import annotations

import dataclasses

import pytest

from widget_sdf.parameters import WidgetParameters
from widget_sdf.sdm.assembly import build_widget_part


@pytest.fixture(scope="module")
def part():
    return build_widget_part()


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
    assert part.name == "widget"
    assert len(part.materials) == 1
    assert part.metadata["units"] == "mm"


def test_it_validates_against_the_schema(part, tmp_path) -> None:
    """Necessary, and demonstrably not sufficient (see this module's docstring)."""
    from software_defined_matter import load, save

    p = tmp_path / "widget.sdm"
    save(part, p)
    assert load(p, b_validate_schema=True) is not None


def test_invalid_parameters_do_not_produce_geometry() -> None:
    """A CEM that emits from invalid params makes a plausible-looking part that
    violates its own design rules, and nothing downstream can tell."""
    bad = dataclasses.replace(WidgetParameters(), n_bolt_holes=24)
    with pytest.raises(ValueError, match="flange_ligament_floor"):
        build_widget_part(bad)


# ── the field, at points whose answers are known by hand ───────────────────


def test_the_tube_wall_is_solid(field) -> None:
    p = WidgetParameters()
    r_mid = (p.d_bore_radius + p.d_outer_radius) / 2.0
    assert field([r_mid, 0.0, p.d_length * 0.75])[0] < 0.0


def test_the_bore_is_open_all_the_way_through(field) -> None:
    """The regression guard for subtract-last.

    Cut the bore inside `tube_tree` and union the flange over it and the bore
    fills in where the flange overlaps: a blocked bushing that still sections
    correctly through the tube.
    """
    p = WidgetParameters()
    # fmt: off
    for z in (p.d_flange_thickness * 0.5,          # inside the flange
              p.d_flange_thickness + 1.0,          # just past it
              p.d_length * 0.5, p.d_length * 0.9):  # up the tube
        # fmt: on
        assert field([0.0, 0.0, z])[0] > 0.0, f"bore is blocked at z={z}"


def test_the_flange_is_solid_between_its_holes(field) -> None:
    import math

    p = WidgetParameters()
    mid = p.d_bolt_angular_pitch / 2.0  # halfway between two holes
    x = p.d_bolt_circle_radius * math.cos(mid)
    y = p.d_bolt_circle_radius * math.sin(mid)
    assert field([x, y, p.d_flange_thickness / 2.0])[0] < 0.0


def test_each_bolt_hole_is_actually_a_hole(field) -> None:
    """All of them, not just the first. An off-by-one in the angular sweep
    leaves one hole on top of another and the count still looks right."""
    import math

    p = WidgetParameters()
    for i in range(p.n_bolt_holes):
        th = i * p.d_bolt_angular_pitch
        x = p.d_bolt_circle_radius * math.cos(th)
        y = p.d_bolt_circle_radius * math.sin(th)
        d = field([x, y, p.d_flange_thickness / 2.0])[0]
        assert d > 0.0, f"hole {i} at angle {math.degrees(th):.0f} deg is solid"


def test_outside_the_envelope_is_empty(field) -> None:
    p = WidgetParameters()
    assert field([0.0, 0.0, p.d_length + 10.0])[0] > 0.0
    assert field([p.d_flange_radius + 10.0, 0.0, 1.0])[0] > 0.0


def test_the_part_is_not_twice_as_long_as_declared(field) -> None:
    """The half-height trap. `h=d_length` instead of `h=d_length/2` builds a
    part of exactly double the length and nothing else complains."""
    p = WidgetParameters()
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

    p = dataclasses.replace(WidgetParameters(), n_bolt_holes=0)
    part = build_widget_part(p)
    fn = make_sdf_closure(part.materials[0].sdf_tree, part)
    d = fn(
        jnp.asarray([[p.d_bolt_circle_radius, 0.0, p.d_flange_thickness / 2.0]], dtype=float), None
    )
    assert float(d[0]) < 0.0, "the bolt circle should be gone"
