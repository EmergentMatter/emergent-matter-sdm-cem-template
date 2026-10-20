"""check_contract.py's design_regions check (docs/design-regions.md)."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _checker():
    spec = importlib.util.spec_from_file_location(
        "check_contract", ROOT / "scripts" / "check_contract.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _doc(regions: dict) -> dict:
    return {"params": {"plate_thickness": {"value": 9.0}}, "metadata": {"design_regions": regions}}


def _tree(ref: str = "plate_thickness") -> dict:
    return {"type": "primitive", "kind": "box", "params": {"b": [1.0, 1.0, {"$ref": ref}]}}


def test_a_complete_block_passes():
    cc = _checker()
    cc._fails.clear()
    cc._check_design_regions(
        _doc({"version": 1, "keep_in": [{"name": "pad", "why": "screw head", "sdf_tree": _tree()}]})
    )
    assert cc._fails == []


def test_missing_why_unknown_kind_and_undeclared_param_fail():
    cc = _checker()
    cc._fails.clear()
    cc._check_design_regions(
        _doc(
            {
                "version": 1,
                "keep_inn": [],
                "keep_out": [{"name": "reach", "sdf_tree": _tree("no_such_param")}],
            }
        )
    )
    assert "design_regions has only keep_in, keep_out, optional" in cc._fails
    assert "design_regions entries are complete" in cc._fails
