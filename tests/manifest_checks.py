"""Checks that a `cem.toml` agrees with the Python it describes.

Shared by `test_manifest.py` (the CEM's own manifest) and the example tests
that hold an example's annotated manifest to the same rules. The CEM's own
checks use floors any real CEM can meet; an example passes `strict=True` for
the stricter ones that keep its loops from passing on nothing.
"""

from __future__ import annotations

import dataclasses
import importlib
import inspect
import tomllib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PREFIX_TYPE = {"d_": "float", "n_": "int", "b_": "bool", "s_": "str", "a_": "array"}


@dataclass(frozen=True)
class Case:
    """One manifest, the dataclass it describes and what the `.sdm` ships."""

    manifest: Path
    params_cls: type
    param_fields: dict[str, Any]
    strict: bool = False

    @property
    def cem(self) -> dict[str, Any]:
        return tomllib.loads(self.manifest.read_text())["cem"]


def default_mismatches(cem: dict[str, Any], params_cls: type) -> list[str]:
    """Declared params whose manifest default differs from the dataclass's."""
    instance = params_cls()
    return [
        name
        for name, spec in cem["params"].items()
        if spec.get("default") != getattr(instance, name)
    ]


def declared_params_exist(case: Case) -> None:
    fields = {f.name for f in dataclasses.fields(case.params_cls)}
    missing = sorted(set(case.cem["params"]) - fields)
    assert not missing, f"cem.toml declares params that do not exist: {missing}"
    assert case.cem["params"], "cem.toml declares no params"


def every_field_is_declared(case: Case) -> None:
    """The direction that catches the real failure: someone adds a param and
    the manifest silently stops describing the design."""
    fields = {f.name for f in dataclasses.fields(case.params_cls)}
    undeclared = sorted(fields - set(case.cem["params"]))
    assert not undeclared, f"parameters.py has params cem.toml never mentions: {undeclared}"


def defaults_match_the_dataclass(case: Case) -> None:
    assert default_mismatches(case.cem, case.params_cls) == []


def prefix_matches_the_type(case: Case) -> None:
    """The prefix IS the type here, so a mismatch actively misleads."""
    for name, spec in case.cem["params"].items():
        assert spec["type"] == PREFIX_TYPE[name[:2]], name


def defaults_sit_inside_their_bounds(case: Case) -> None:
    checked = 0
    for name, spec in case.cem["params"].items():
        if "bounds" not in spec:
            continue
        lo, hi = spec["bounds"]
        assert lo <= spec["default"] <= hi, name
        checked += 1
    if case.strict:
        assert checked >= 4


def derived_values_are_not_declared(case: Case) -> None:
    """Shipping a derived value as a free param is what severs it from its
    inputs: the hexafoil bug."""
    cls = case.params_cls
    derived = {n for n in dir(cls) if isinstance(getattr(cls, n, None), property)}
    if case.strict:
        assert derived, "the example has no derived value to protect"
    leaked = sorted(derived & set(case.cem["params"]))
    assert not leaked, f"derived values declared as free params: {leaked}"
    assert not sorted(derived & set(case.param_fields)), "derived value shipped in the .sdm"


def declared_constraints_are_enforced(case: Case) -> None:
    """The manifest is what a tool reads; validate() is what runs.

    Each constraint's name must appear in `validate()`, which is why its
    messages are prefixed with the name. A CEM may have no constraints."""
    constraints = case.cem.get("constraints", [])
    if case.strict:
        assert constraints
    src = inspect.getsource(case.params_cls.validate)
    for c in constraints:
        assert c["name"] in src, (
            f"cem.toml declares constraint {c['name']!r} that validate() never "
            "enforces: a rule nothing checks is not a rule"
        )


def every_constraint_carries_its_reason(case: Case) -> None:
    for c in case.cem.get("constraints", []):
        assert c.get("why"), f"{c['name']} has no `why`"


def entry_point_resolves(case: Case) -> None:
    """cem.toml is read without importing, but the string still has to be
    right: nothing else checks it, so this does."""
    mod_name, _, attr = case.cem["entry_point"].partition(":")
    assert callable(getattr(importlib.import_module(mod_name), attr))


def emitted_bounds_match(case: Case) -> None:
    """A viewer builds its control from the DOCUMENT, not from `cem.toml`: a
    param emitted without bounds has no range to slide between."""
    assert case.param_fields
    for field, (_unit, bounds) in case.param_fields.items():
        declared = case.cem["params"][field].get("bounds")
        assert declared is not None, f"{field} declares no bounds in cem.toml"
        assert list(bounds) == list(declared), (
            f"{field}: the part emits {list(bounds)}, cem.toml declares "
            f"{list(declared)}. A tool would offer the wrong range."
        )


def emitted_units_match(case: Case) -> None:
    assert case.param_fields
    for field, (unit, _b) in case.param_fields.items():
        declared = case.cem["params"][field].get("unit")
        assert unit == declared, (
            f"{field}: the part emits unit {unit!r}, cem.toml says {declared!r}"
        )


def emits_is_the_name_without_its_prefix(case: Case) -> None:
    emitted = 0
    for name, spec in case.cem["params"].items():
        if "emits" in spec:
            assert spec["emits"] == name.split("_", 1)[1], name
            emitted += 1
    if case.strict:
        assert emitted >= 4


CHECKS: dict[str, Callable[[Case], None]] = {
    fn.__name__: fn
    for fn in (
        declared_params_exist,
        every_field_is_declared,
        defaults_match_the_dataclass,
        prefix_matches_the_type,
        defaults_sit_inside_their_bounds,
        derived_values_are_not_declared,
        declared_constraints_are_enforced,
        every_constraint_carries_its_reason,
        entry_point_resolves,
        emitted_bounds_match,
        emitted_units_match,
        emits_is_the_name_without_its_prefix,
    )
}
