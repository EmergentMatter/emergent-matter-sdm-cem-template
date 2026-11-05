"""`scripts/check_contract.py`'s rule about which params may ship fixed.

The Scene panel builds its controls from free params only, so a design param
that ships non-free gets none. A param the manifest gives no role, or the role
`tool` or `derived`, may be fixed on purpose.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def contract():
    spec = importlib.util.spec_from_file_location(
        "check_contract", ROOT / "scripts" / "check_contract.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _doc(**free: bool) -> dict:
    return {n: {"value": 1.0, "free": f, "bounds": [0.0, 2.0]} for n, f in free.items()}


MANIFEST = {
    "d_length": {"role": "re-emit", "emits": "length"},
    "d_voxel_size_mm": {"role": "tool"},
    "d_floor": {"role": "derived"},
    "d_plain": {},
}


def test_a_design_param_that_ships_non_free_is_reported(contract) -> None:
    assert contract.design_params_not_free(_doc(length=False), MANIFEST) == ["length"]


def test_a_free_design_param_passes(contract) -> None:
    assert contract.design_params_not_free(_doc(length=True), MANIFEST) == []


def test_a_fixed_tool_derived_or_role_less_param_passes(contract) -> None:
    doc = _doc(d_voxel_size_mm=False, d_floor=False, d_plain=False)
    assert contract.design_params_not_free(doc, MANIFEST) == []


def test_a_param_the_manifest_does_not_declare_passes(contract) -> None:
    assert contract.design_params_not_free(_doc(mystery=False), MANIFEST) == []


def test_the_templates_built_part_passes_against_its_own_manifest(contract, tmp_path) -> None:
    import tomllib

    from widget_sdf.sdm.cli import main

    out = ROOT / "output" / ".free-check" / "p.sdm"
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        assert main(["--out", str(out)]) == 0
        doc = json.loads(out.read_text())["params"]
    finally:
        out.unlink(missing_ok=True)
    manifest = tomllib.loads((ROOT / "cem.toml").read_text())["cem"]["params"]

    assert doc, "the build shipped no params"
    assert contract.design_params_not_free(doc, manifest) == []
    doc["length"]["free"] = False
    assert contract.design_params_not_free(doc, manifest) == ["length"]
