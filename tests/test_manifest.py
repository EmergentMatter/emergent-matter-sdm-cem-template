"""`cem.toml` against the Python it describes.

This is the test that keeps the template honest, and it is the one worth
copying into a real CEM: without it the manifest is a description of a design
nobody is building, and it drifts silently because nothing reads it in CI.
"""

from __future__ import annotations

import dataclasses
import tomllib
from pathlib import Path

import pytest

from widget_sdf.parameters import WidgetParameters
from widget_sdf.sdm.assembly import PARAM_FIELDS

ROOT = Path(__file__).resolve().parents[1]
CEM = tomllib.loads((ROOT / "cem.toml").read_text())["cem"]
PREFIX_TYPE = {"d_": "float", "n_": "int", "b_": "bool", "s_": "str", "a_": "array"}


def test_every_declared_param_exists_on_the_dataclass() -> None:
    fields = {f.name for f in dataclasses.fields(WidgetParameters)}
    missing = sorted(set(CEM["params"]) - fields)
    assert not missing, f"cem.toml declares params that do not exist: {missing}"


def test_every_dataclass_field_is_declared() -> None:
    """The direction that catches the real failure: someone adds a param and
    the manifest silently stops describing the design."""
    fields = {f.name for f in dataclasses.fields(WidgetParameters)}
    undeclared = sorted(fields - set(CEM["params"]))
    assert not undeclared, f"parameters.py has params cem.toml never mentions: {undeclared}"


@pytest.mark.parametrize("name", sorted(CEM["params"]))
def test_declared_defaults_match_the_dataclass(name: str) -> None:
    declared = CEM["params"][name].get("default")
    actual = getattr(WidgetParameters(), name)
    assert declared == actual, f"{name}: cem.toml says {declared}, dataclass says {actual}"


@pytest.mark.parametrize("name", sorted(CEM["params"]))
def test_the_prefix_matches_the_declared_type(name: str) -> None:
    """The prefix IS the type here, so a mismatch actively misleads."""
    assert CEM["params"][name]["type"] == PREFIX_TYPE[name[:2]]


@pytest.mark.parametrize("name", sorted(CEM["params"]))
def test_every_default_sits_inside_its_own_bounds(name: str) -> None:
    spec = CEM["params"][name]
    if "bounds" not in spec:
        pytest.skip("no bounds declared")
    lo, hi = spec["bounds"]
    assert lo <= spec["default"] <= hi


def test_derived_values_are_not_declared_as_params() -> None:
    """Shipping a derived value as a free param is what severs it from its
    inputs: the hexafoil bug."""
    derived = {
        n for n in dir(WidgetParameters) if isinstance(getattr(WidgetParameters, n, None), property)
    }
    leaked = sorted(derived & set(CEM["params"]))
    assert not leaked, f"derived values declared as free params: {leaked}"
    assert not sorted(derived & set(PARAM_FIELDS)), "derived value shipped in the .sdm"


def test_every_declared_constraint_is_actually_enforced() -> None:
    """The manifest is what a tool reads; validate() is what runs.

    Without this, the two drift and the manifest starts describing rules
    nothing checks. Each constraint's name must appear in a validate()
    message, which is why those messages are prefixed with the name.
    """
    import inspect

    src = inspect.getsource(WidgetParameters.validate)
    for c in CEM["constraints"]:
        assert c["name"] in src, (
            f"cem.toml declares constraint {c['name']!r} that validate() never "
            "enforces: a rule nothing checks is not a rule"
        )


def test_every_constraint_carries_its_reason() -> None:
    """A constraint whose `why` lives only in someone's head gets relaxed by
    the next person who finds it inconvenient."""
    for c in CEM["constraints"]:
        assert c.get("why"), f"{c['name']} has no `why`"


def test_the_entry_point_resolves() -> None:
    """cem.toml is read without importing, but the string still has to be
    right: nothing else checks it, so this does."""
    import importlib

    mod_name, _, attr = CEM["entry_point"].partition(":")
    assert callable(getattr(importlib.import_module(mod_name), attr))


def test_emitted_bounds_match_the_manifest() -> None:
    """A viewer builds its control from the DOCUMENT, not from `cem.toml`.

    A param emitted with ``bounds: null`` has no range to slide between and
    renders as a control you cannot move, while the manifest cheerfully
    declares a range nothing can offer.
    """
    for field, (_unit, bounds) in PARAM_FIELDS.items():
        declared = CEM["params"][field].get("bounds")
        assert declared is not None, f"{field} declares no bounds in cem.toml"
        assert list(bounds) == list(declared), (
            f"{field}: assembly.py emits {list(bounds)}, cem.toml declares "
            f"{list(declared)}. A tool would offer the wrong range."
        )


def test_emitted_units_match_the_manifest() -> None:
    for field, (unit, _b) in PARAM_FIELDS.items():
        declared = CEM["params"][field].get("unit")
        assert unit == declared, (
            f"{field}: assembly.py emits unit {unit!r}, cem.toml says {declared!r}"
        )
