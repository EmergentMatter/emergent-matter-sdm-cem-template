"""The parameter model: derived values, and the constraints validate() owns."""

from __future__ import annotations

import dataclasses

from widget_sdf.parameters import WidgetParameters


def test_defaults_are_valid() -> None:
    """A template whose defaults do not build teaches the wrong first move."""
    assert WidgetParameters().validate() == []


def test_derived_values_follow_their_inputs() -> None:
    """The property, not a stored field: this is the rule the template exists
    to demonstrate, so it gets a test rather than only a comment."""
    p = dataclasses.replace(WidgetParameters(), d_height=8.0)
    assert p.d_half_min_side == 4.0
    assert "d_half_min_side" not in {f.name for f in dataclasses.fields(p)}, (
        "d_half_min_side must be derived, never a field: two sources of truth"
    )


def test_an_edge_radius_of_half_the_smallest_side_leaves_no_block() -> None:
    p = WidgetParameters()
    errs = dataclasses.replace(p, d_edge_radius=p.d_half_min_side).validate()
    assert any("edge_radius_below_half_smallest_side" in e for e in errs), errs


def test_an_edge_radius_just_under_the_limit_is_valid() -> None:
    p = WidgetParameters()
    assert dataclasses.replace(p, d_edge_radius=p.d_half_min_side - 0.01).validate() == []


def test_the_limit_follows_the_smallest_side() -> None:
    """A radius that fits the default block does not fit a thinner one."""
    p = dataclasses.replace(WidgetParameters(), d_edge_radius=3.0, d_width=5.0)
    assert p.validate(), "2.5 mm is half the smallest side, so a 3 mm radius must be refused"


def test_validate_reports_every_problem_at_once() -> None:
    """Not one exception at a time: an optimizer or an agent should see the
    whole picture. With one constraint, the check is that it names its cause."""
    errs = dataclasses.replace(WidgetParameters(), d_edge_radius=99.0).validate()
    assert len(errs) == 1 and "99.0" in errs[0], errs


def test_the_bbox_contains_the_part() -> None:
    p = WidgetParameters()
    lo, hi = p.bbox()
    assert lo[0] <= -p.d_length / 2.0 and hi[0] >= p.d_length / 2.0
    assert lo[1] <= -p.d_width / 2.0 and hi[1] >= p.d_width / 2.0
    assert lo[2] <= 0.0 and hi[2] >= p.d_height
