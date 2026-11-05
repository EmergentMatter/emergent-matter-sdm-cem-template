"""The CEM's own `cem.toml` against the Python it describes.

This is the test that keeps the template honest, and it is the one worth
copying into a real CEM: without it the manifest is a description of a design
nobody is building, and it drifts silently because nothing reads it in CI.

It depends on the CEM's own package and nothing else, so it survives deleting
`examples/`. The checks live in `manifest_checks.py`; the floors here are the
ones any real CEM can meet (a CEM may be small, with no derived value and no
constraint).
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from manifest_checks import CHECKS, Case, default_mismatches

from widget_sdf.parameters import WidgetParameters
from widget_sdf.sdm.assembly import PARAM_FIELDS

ROOT = Path(__file__).resolve().parents[1]
CASE = Case(ROOT / "cem.toml", WidgetParameters, PARAM_FIELDS)


@pytest.mark.parametrize("check", sorted(CHECKS))
def test_the_manifest_agrees_with_the_code(check: str) -> None:
    CHECKS[check](CASE)


def test_a_drifted_manifest_is_caught() -> None:
    """The oracle can fail: change the first declared param's default in the
    parsed manifest and exactly that name is reported."""
    cem = copy.deepcopy(CASE.cem)
    first = next(iter(cem["params"]))
    assert default_mismatches(cem, WidgetParameters) == []

    cem["params"][first]["default"] = "not the dataclass default"

    assert default_mismatches(cem, WidgetParameters) == [first]


def test_a_manifest_with_a_missing_field_is_caught() -> None:
    cem = copy.deepcopy(CASE.cem)
    removed = next(iter(cem["params"]))
    del cem["params"][removed]
    declared = set(cem["params"])
    import dataclasses

    fields = {f.name for f in dataclasses.fields(WidgetParameters)}
    assert fields - declared == {removed}


def test_cem_name_is_the_name_the_cli_builds_by_default(tmp_path: Path) -> None:
    """`scripts/rename.py` sets `cem.toml`'s name and the CLI's default
    `--name` to the same `<thing>`; the pair has to agree for the template too,
    or a renamed CEM's manifest and its emitted part would carry two names."""
    from widget_sdf.sdm.cli import main

    out = tmp_path / "default.sdm"
    assert main(["--out", str(out)]) == 0
    assert json.loads(out.read_text())["name"] == CASE.cem["name"]
