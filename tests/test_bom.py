"""The geometry checker holds part files to carrying their parts-list facts.

A bought part with no vendor, or a made part with no process, builds and
validates; only the parts list comes out empty. Caught here instead.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_geometry.py"


def _run(meta: dict, capsys) -> tuple[int, str]:
    spec = importlib.util.spec_from_file_location("check_geometry", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod._check_bom({"metadata": meta})
    return mod._failures, capsys.readouterr().out


def test_bought_part_with_vendor_passes_and_notes_missing_price(capsys):
    bom = {"vendor": "McMaster-Carr", "vendor_part_number": "94459A120"}
    n, out = _run({"bought": True, "bom": bom}, capsys)
    assert n == 0, out
    assert "no unit_price" in out


def test_bought_part_without_vendor_fails(capsys):
    n, out = _run({"bought": True, "description": "Heat-set insert M2, McMaster 94459A120"}, capsys)
    assert n == 1
    assert "vendor, vendor_part_number" in out


def test_made_part_needs_its_process(capsys):
    assert _run({"bought": False}, capsys)[0] == 1
    assert _run({"bought": False, "bom": {"fabrication": "SLS"}}, capsys)[0] == 0


def test_a_part_with_no_bought_flag_counts_as_made(capsys):
    assert _run({}, capsys)[0] == 1


def test_malformed_fields_fail(capsys):
    bom = {
        "fabrication": "FDM",
        "unit": "feet",
        "unit_price": -1,
        "revision": "1.0.2",
        "quantity": 0,
    }
    n, out = _run({"bom": bom}, capsys)
    assert n == 1
    for word in ("unit", "unit_price", "revision", "quantity"):
        assert word in out


def test_stock_cut_to_size(capsys):
    meta = {
        "bought": True,
        "bom": {
            "vendor": "McMaster-Carr",
            "vendor_part_number": "8633K51",
            "unit": "ft^2",
            "quantity": 0.02,
            "unit_price": 41.5,
            "revision": "1.1.1",
        },
    }
    assert _run(meta, capsys)[0] == 0


def test_declared_exception_excuses_missing_facts(capsys):
    meta = {"bought": True, "geometry_exceptions": {"bom": "salvaged from the old hand; no vendor"}}
    assert _run(meta, capsys)[0] == 0


def test_fabrication_is_one_of_the_listed_methods(capsys):
    assert _run({"bom": {"fabrication": "SLS"}}, capsys)[0] == 0
    assert _run({"bom": {"fabrication": "Other: EDM"}}, capsys)[0] == 0
    n, out = _run({"bom": {"fabrication": "sls"}}, capsys)
    assert n == 1 and "write 'SLS'" in out
    n, out = _run({"bom": {"fabrication": "3D printed"}}, capsys)
    assert n == 1 and "Other:" in out
    assert (
        _run(
            {
                "bought": True,
                "bom": {"vendor": "V", "vendor_part_number": "1", "fabrication": "Purchased"},
            },
            capsys,
        )[0]
        == 0
    )
