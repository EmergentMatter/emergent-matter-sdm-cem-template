"""The parameter model: derived values, and the constraints validate() owns."""

from __future__ import annotations

import dataclasses
import math

import pytest

from widget_sdf.parameters import WidgetParameters


def test_defaults_are_valid() -> None:
    """A template whose defaults do not build teaches the wrong first move."""
    assert WidgetParameters().validate() == []


def test_derived_values_follow_their_inputs() -> None:
    """The property, not a stored field: this is the rule the template exists
    to demonstrate, so it gets a test rather than only a comment."""
    p = dataclasses.replace(WidgetParameters(), d_outer_radius=20.0, d_wall_thickness=5.0)
    assert p.d_bore_radius == 15.0
    assert (
        not hasattr(type(p), "__dataclass_fields__")
        or "d_bore_radius" not in type(p).__dataclass_fields__
    ), "d_bore_radius must be derived, never a field: two sources of truth"


def test_bolt_pitch_closes_the_circle() -> None:
    p = WidgetParameters()
    assert p.n_bolt_holes * p.d_bolt_angular_pitch == pytest.approx(2 * math.pi)


def test_too_many_holes_is_a_perforation() -> None:
    """The constraint that cannot be a bound: it depends on a derived value
    which depends on n_bolt_holes."""
    errs = dataclasses.replace(WidgetParameters(), n_bolt_holes=24).validate()
    assert any("flange_ligament_floor" in e for e in errs), errs


def test_a_wall_thicker_than_the_radius_leaves_no_bore() -> None:
    errs = dataclasses.replace(WidgetParameters(), d_wall_thickness=99.0).validate()
    assert any("wall_thickness_below_outer_radius" in e for e in errs), errs


def test_validate_reports_every_problem_at_once() -> None:
    """Not one exception at a time: an optimizer or an agent should see the
    whole picture, not fix five things in five round trips."""
    errs = dataclasses.replace(
        WidgetParameters(),
        d_wall_thickness=99.0,
        d_flange_radius=1.0,
    ).validate()
    assert len(errs) >= 2, errs


def test_the_bbox_contains_the_part() -> None:
    p = WidgetParameters()
    lo, hi = p.bbox()
    assert lo[0] <= -max(p.d_outer_radius, p.d_flange_radius)
    assert hi[2] >= p.d_length
