"""This CEM's own part meets the geometry standard (scripts/check_geometry.py).

The checker carries the reasons; this only makes a breach fail `pytest`, which
is the one signal an agent reliably stops on.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_geometry.py"


def test_own_part_meets_the_geometry_standard(capsys, monkeypatch):
    spec = importlib.util.spec_from_file_location("check_geometry", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    # A coarse body count keeps the suite fast; the widget has no feature near 1 mm.
    monkeypatch.setattr(mod, "D_BODY_PITCH", 1.0)
    monkeypatch.setattr(mod, "N_BODY_MIN_CELLS", 40)
    assert mod.main([]) == 0, capsys.readouterr().out
