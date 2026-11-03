"""Each `cem.toml` against the Python it describes.

This is the test that keeps the template honest, and it is the one worth
copying into a real CEM: without it the manifest is a description of a design
nobody is building, and it drifts silently because nothing reads it in CI.

It runs against two manifests: the repo root's, which a tool reads, and the
annotated one beside the bushing example, which the docs point at. The second
is documentation, and documentation nothing checks goes stale.
"""

from __future__ import annotations

import dataclasses
import importlib
import inspect
import json
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from bushing_sdf.bushing import PARAM_FIELDS as BUSHING_PARAM_FIELDS
from bushing_sdf.parameters import BushingParameters

from widget_sdf.parameters import WidgetParameters
from widget_sdf.sdm.assembly import PARAM_FIELDS as STARTER_PARAM_FIELDS

ROOT = Path(__file__).resolve().parents[1]
PREFIX_TYPE = {"d_": "float", "n_": "int", "b_": "bool", "s_": "str", "a_": "array"}


@dataclass(frozen=True)
class Case:
    """One manifest, the dataclass it describes and what the `.sdm` ships."""

    manifest: Path
    params_cls: type
    param_fields: dict[str, Any]

    @property
    def cem(self) -> dict[str, Any]:
        return tomllib.loads(self.manifest.read_text())["cem"]


CASES = {
    "template": Case(ROOT / "cem.toml", WidgetParameters, STARTER_PARAM_FIELDS),
    "bushing": Case(
        ROOT / "examples" / "bushing_sdf" / "cem.toml", BushingParameters, BUSHING_PARAM_FIELDS
    ),
}


@pytest.fixture(params=sorted(CASES))
def case(request: pytest.FixtureRequest) -> Case:
    return CASES[request.param]


def test_the_manifests_are_not_empty() -> None:
    """Every check below loops over a manifest; an empty one passes them all."""
    for c in CASES.values():
        assert len(c.cem["params"]) >= 4
        assert len(c.cem["constraints"]) >= 1


def test_every_declared_param_exists_on_the_dataclass(case: Case) -> None:
    fields = {f.name for f in dataclasses.fields(case.params_cls)}
    missing = sorted(set(case.cem["params"]) - fields)
    assert not missing, f"cem.toml declares params that do not exist: {missing}"


def test_every_dataclass_field_is_declared(case: Case) -> None:
    """The direction that catches the real failure: someone adds a param and
    the manifest silently stops describing the design."""
    fields = {f.name for f in dataclasses.fields(case.params_cls)}
    undeclared = sorted(fields - set(case.cem["params"]))
    assert not undeclared, f"parameters.py has params cem.toml never mentions: {undeclared}"


def test_declared_defaults_match_the_dataclass(case: Case) -> None:
    for name, spec in case.cem["params"].items():
        actual = getattr(case.params_cls(), name)
        assert spec.get("default") == actual, (
            f"{name}: cem.toml says {spec.get('default')}, dataclass says {actual}"
        )


def test_the_prefix_matches_the_declared_type(case: Case) -> None:
    """The prefix IS the type here, so a mismatch actively misleads."""
    for name, spec in case.cem["params"].items():
        assert spec["type"] == PREFIX_TYPE[name[:2]], name


def test_every_default_sits_inside_its_own_bounds(case: Case) -> None:
    checked = 0
    for name, spec in case.cem["params"].items():
        if "bounds" not in spec:
            continue
        lo, hi = spec["bounds"]
        assert lo <= spec["default"] <= hi, name
        checked += 1
    assert checked >= 4


def test_derived_values_are_not_declared_as_params(case: Case) -> None:
    """Shipping a derived value as a free param is what severs it from its
    inputs: the hexafoil bug."""
    cls = case.params_cls
    derived = {n for n in dir(cls) if isinstance(getattr(cls, n, None), property)}
    assert derived, "the example has no derived value to protect"
    leaked = sorted(derived & set(case.cem["params"]))
    assert not leaked, f"derived values declared as free params: {leaked}"
    assert not sorted(derived & set(case.param_fields)), "derived value shipped in the .sdm"


def test_every_declared_constraint_is_actually_enforced(case: Case) -> None:
    """The manifest is what a tool reads; validate() is what runs.

    Without this, the two drift and the manifest starts describing rules
    nothing checks. Each constraint's name must appear in a validate()
    message, which is why those messages are prefixed with the name.
    """
    src = inspect.getsource(case.params_cls.validate)
    for c in case.cem["constraints"]:
        assert c["name"] in src, (
            f"cem.toml declares constraint {c['name']!r} that validate() never "
            "enforces: a rule nothing checks is not a rule"
        )


def test_every_constraint_carries_its_reason(case: Case) -> None:
    """A constraint whose `why` lives only in someone's head gets relaxed by
    the next person who finds it inconvenient."""
    for c in case.cem["constraints"]:
        assert c.get("why"), f"{c['name']} has no `why`"


def test_the_entry_point_resolves(case: Case) -> None:
    """cem.toml is read without importing, but the string still has to be
    right: nothing else checks it, so this does."""
    mod_name, _, attr = case.cem["entry_point"].partition(":")
    assert callable(getattr(importlib.import_module(mod_name), attr))


def test_emitted_bounds_match_the_manifest(case: Case) -> None:
    """A viewer builds its control from the DOCUMENT, not from `cem.toml`.

    A param emitted with ``bounds: null`` has no range to slide between and
    renders as a control you cannot move, while the manifest cheerfully
    declares a range nothing can offer.
    """
    assert case.param_fields
    for field, (_unit, bounds) in case.param_fields.items():
        declared = case.cem["params"][field].get("bounds")
        assert declared is not None, f"{field} declares no bounds in cem.toml"
        assert list(bounds) == list(declared), (
            f"{field}: the part emits {list(bounds)}, cem.toml declares "
            f"{list(declared)}. A tool would offer the wrong range."
        )


def test_emitted_units_match_the_manifest(case: Case) -> None:
    assert case.param_fields
    for field, (unit, _b) in case.param_fields.items():
        declared = case.cem["params"][field].get("unit")
        assert unit == declared, (
            f"{field}: the part emits unit {unit!r}, cem.toml says {declared!r}"
        )


def test_emits_is_the_field_name_without_its_prefix(case: Case) -> None:
    emitted = 0
    for name, spec in case.cem["params"].items():
        if "emits" in spec:
            assert spec["emits"] == name.split("_", 1)[1], name
            emitted += 1
    assert emitted >= 4


def test_a_drifted_manifest_is_caught(tmp_path: Path) -> None:
    """The oracle can fail: a manifest whose default disagrees with the
    dataclass must trip the same comparison the tests above make."""
    c = CASES["template"]
    drifted = tomllib.loads(c.manifest.read_text().replace("default = 40.0", "default = 41.0"))[
        "cem"
    ]
    mismatches = [
        n for n, s in drifted["params"].items() if s.get("default") != getattr(c.params_cls(), n)
    ]
    assert mismatches == ["d_length"]


def test_cem_name_is_the_name_the_cli_builds_by_default(tmp_path: Path) -> None:
    """`scripts/rename.py` sets `cem.toml`'s name and the CLI's default
    `--name` to the same `<thing>`; the pair has to agree for the template too,
    or a renamed CEM's manifest and its emitted part would carry two names."""
    from widget_sdf.sdm.cli import main

    out = tmp_path / "default.sdm"
    assert main(["--out", str(out)]) == 0
    assert json.loads(out.read_text())["name"] == CASES["template"].cem["name"]


def test_the_bushing_manifest_names_the_part_it_builds() -> None:
    from bushing_sdf.bushing import build_bushing_part

    assert CASES["bushing"].cem["name"] == build_bushing_part().name
