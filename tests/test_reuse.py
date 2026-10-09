"""The geometry checker refuses the same part saved as two files.

Two copies are two parts that nothing ties together: a change to one misses
the other. One file, placed by several instances, is one part.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_geometry.py"
PART = {"kind": "part", "materials": [{"name": "pla", "sdf_tree": {"type": "primitive", "kind": "sphere", "params": {"r": 2.0}}}]}


def _checker():
    spec = importlib.util.spec_from_file_location("check_geometry", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _write(path: Path, doc: dict) -> Path:
    path.write_text(json.dumps(doc))
    return path


def test_one_file_reused_passes(tmp_path, capsys):
    mod = _checker()
    a = _write(tmp_path / "pin.sdm", {**PART, "name": "pin"})
    b = _write(tmp_path / "plate.sdm", {**PART, "name": "plate", "materials": [{**PART["materials"][0], "name": "steel"}]})
    mod._check_reuse([a, b])
    assert mod._failures == 0, capsys.readouterr().out


def test_the_same_part_under_two_names_fails(tmp_path, capsys):
    mod = _checker()
    a = _write(tmp_path / "pin.sdm", {**PART, "name": "pin"})
    b = _write(tmp_path / "pin_copy.sdm", {**PART, "name": "pin_copy", "metadata": {"note": "copied"}})
    mod._check_reuse([a, b])
    out = capsys.readouterr().out
    assert mod._failures == 1
    assert "pin.sdm = pin_copy.sdm" in out
