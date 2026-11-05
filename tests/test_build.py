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
    argument is the free-param vector. None is accepted here because the trees
    embed their numbers and read no free param; a re-emit through the CLI is
    what changes the geometry.
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


def _params_without_a_control(params) -> list[str]:
    """Params the Scene pane would show no slider for: it builds one from each
    FREE param's bounds, and drops the rest."""
    return sorted(
        name
        for name, p in params.items()
        if not p.free or p.bounds is None or not p.bounds[0] < p.bounds[1]
    )


def test_it_ships_every_design_param_free_with_a_range(part) -> None:
    assert sorted(part.params) == ["edge_radius", "height", "length", "width"]
    assert _params_without_a_control(part.params) == []


def test_a_param_shipped_not_free_is_reported() -> None:
    from software_defined_matter import Param

    params = {
        "a": Param(name="a", value=1.0, free=True, bounds=(0.0, 2.0)),
        "b": Param(name="b", value=1.0, free=False, bounds=(0.0, 2.0)),
        "c": Param(name="c", value=1.0, free=True),
    }
    assert _params_without_a_control(params) == ["b", "c"]


def test_a_rebuild_with_set_keeps_every_param_free(tmp_path) -> None:
    import json

    from widget_sdf.sdm.cli import main

    out = tmp_path / "p.sdm"
    assert main(["--out", str(out), "--set", "length=50"]) == 0
    params = json.loads(out.read_text())["params"]
    assert params["length"]["value"] == 50
    assert [n for n, p in params.items() if not p["free"] or not p["bounds"]] == []


def test_invalid_parameters_do_not_produce_geometry() -> None:
    """A CEM that emits from invalid params makes a plausible-looking part that
    violates its own design rules, and nothing downstream can tell."""
    bad = dataclasses.replace(WidgetParameters(), d_edge_radius=15.0)
    with pytest.raises(ValueError, match="edge_radius_below_half_smallest_side"):
        build_widget_part(bad)


# ── the field, at points whose answers are known by hand ───────────────────


def test_the_centre_is_solid(field) -> None:
    p = WidgetParameters()
    assert field([0.0, 0.0, p.d_height / 2.0])[0] < 0.0


def test_the_block_is_exactly_as_long_as_declared(field) -> None:
    """The half-extent trap. `b=d_length` instead of `b=d_length/2` builds a
    block of exactly double the size and nothing else complains."""
    p = WidgetParameters()
    z = p.d_height / 2.0
    assert field([p.d_length / 2.0 - 0.2, 0.0, z])[0] < 0.0, "should still be solid"
    assert field([p.d_length / 2.0 + 0.2, 0.0, z])[0] > 0.0, "should have ended"


def test_the_block_is_as_wide_and_as_tall_as_declared(field) -> None:
    p = WidgetParameters()
    assert field([0.0, p.d_width / 2.0 - 0.2, p.d_height / 2.0])[0] < 0.0
    assert field([0.0, p.d_width / 2.0 + 0.2, p.d_height / 2.0])[0] > 0.0
    assert field([0.0, 0.0, p.d_height - 0.2])[0] < 0.0
    assert field([0.0, 0.0, p.d_height + 0.2])[0] > 0.0


def test_the_block_stands_on_z_zero(field) -> None:
    assert field([0.0, 0.0, 0.2])[0] < 0.0
    assert field([0.0, 0.0, -0.2])[0] > 0.0


def test_the_edges_are_rounded(field) -> None:
    """A corner point just inside the sharp envelope is outside the rounded
    block; with the radius at 0 the same point is solid."""
    p = WidgetParameters()
    corner = [p.d_length / 2.0 - 0.1, p.d_width / 2.0 - 0.1, p.d_height - 0.1]
    assert field(corner)[0] > 0.0
    sharp = build_widget_part(dataclasses.replace(p, d_edge_radius=0.0))
    import jax.numpy as jnp
    from software_defined_matter.sdf.compile import make_sdf_closure

    fn = make_sdf_closure(sharp.materials[0].sdf_tree, sharp)
    assert float(fn(jnp.asarray([corner], dtype=float), None)[0]) < 0.0
