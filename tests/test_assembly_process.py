"""The geometry checker holds assemblies to saying how they go together.

An assembly that builds and validates but carries no build sequence, or one
that installs a part twice or never, is caught here rather than in a viewer.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_geometry.py"


def _checker():
    spec = importlib.util.spec_from_file_location("check_geometry", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _run_on(doc: dict, capsys) -> tuple[int, str]:
    mod = _checker()
    mod._check_process(doc, [i["id"] for i in doc["instances"]])
    return mod._failures, capsys.readouterr().out


def _assembly(process=None, exceptions=None):
    meta = {}
    if process is not None:
        meta["assembly_process"] = process
    if exceptions:
        meta["geometry_exceptions"] = exceptions
    return {
        "kind": "assembly",
        "instances": [{"id": "frame"}, {"id": "lid"}, {"id": "screw"}],
        "metadata": meta,
    }


GOOD = {
    "version": 1,
    "base": ["frame"],
    "steps": [
        {
            "id": "lid",
            "name": "Fit the lid",
            "instances": ["lid"],
            "direction": [0, 0, -1],
            "travel": 30,
        },
        {
            "id": "screw",
            "name": "Screw it down",
            "instances": ["screw"],
            "direction": [0, 0, -1],
            "rotate": {"axis": [0, 0, 1], "angle_deg": 720},
            "tool": "2.5 mm hex key",
        },
    ],
}


def test_a_complete_sequence_passes(capsys):
    failures, _ = _run_on(_assembly(GOOD), capsys)
    assert failures == 0


def test_an_assembly_without_a_sequence_fails(capsys):
    failures, out = _run_on(_assembly(), capsys)
    assert failures == 1 and "missing" in out


def test_a_declared_exception_passes(capsys):
    failures, _ = _run_on(_assembly(exceptions={"assembly_process": "one welded unit"}), capsys)
    assert failures == 0


def test_twice_never_and_unknown_are_all_named(capsys):
    bad = json.loads(json.dumps(GOOD))
    bad["steps"][1]["instances"] = ["lid", "ghost"]
    failures, out = _run_on(_assembly(bad), capsys)
    assert failures == 1
    assert "already installed" in out and "'ghost'" in out and "'screw' is never installed" in out


def test_instances_out_of_build_order_fail(capsys):
    doc = _assembly(GOOD)
    doc["instances"] = [
        {"id": "screw"},
        {"id": "frame"},
        {"id": "lid"},
    ]  # screw listed before what it holds
    failures, out = _run_on(doc, capsys)
    assert failures == 1 and "build order" in out


def test_dependencies_and_times_pass(capsys):
    doc = json.loads(json.dumps(GOOD))
    doc["steps"][0]["after"] = []
    doc["steps"][1].update({"after": ["lid"], "minutes": 2})
    doc["minutes_source"] = "estimate"
    failures, _ = _run_on(_assembly(doc), capsys)
    assert failures == 0


def test_after_names_only_earlier_steps(capsys):
    doc = json.loads(json.dumps(GOOD))
    doc["steps"][0]["after"] = ["screw"]  # a later step
    doc["steps"][1]["minutes"] = 0
    doc["minutes_source"] = "a hunch"
    failures, out = _run_on(_assembly(doc), capsys)
    assert failures == 1
    assert "not an earlier step" in out and "minutes must be" in out and "minutes_source" in out


def test_names_start_with_what_the_part_is(tmp_path, capsys):
    mod = _checker()
    (tmp_path / "screw_m3x8.sdm").write_text(json.dumps({"name": "screw_m3x8", "materials": []}))
    good = {
        "kind": "assembly",
        "instances": [{"id": "screw_m3x8_lid_0", "part_ref": {"path": "screw_m3x8.sdm"}}],
    }
    bad = {
        "kind": "assembly",
        "instances": [{"id": "lid_0_screw", "part_ref": {"path": "screw_m3x8.sdm"}}],
    }
    mod._check_names(tmp_path / "box.sdm", good)
    assert mod._failures == 0
    mod._check_names(tmp_path / "box.sdm", bad)
    out = capsys.readouterr().out
    assert mod._failures == 1 and "lid_0_screw" in out and "start it screw_" in out


def test_step_kind_is_from_the_list(capsys):
    doc = json.loads(json.dumps(GOOD))
    doc["steps"][0]["kind"] = "place"
    doc["steps"][1]["kind"] = "hammer"
    failures, out = _run_on(_assembly(doc), capsys)
    assert failures == 1 and "kind must be one of" in out
