"""The geometry checker refuses arcs and rounds faked with straight segments.

They build, validate and look round from far away; up close, and in every
export, they are rows of flat strips.
"""

from __future__ import annotations

import importlib.util
import math
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_geometry.py"


def _run(doc: dict, capsys) -> tuple[int, str]:
    spec = importlib.util.spec_from_file_location("check_geometry", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod._check_curves(doc)
    return mod._failures, capsys.readouterr().out


def _part(vertices, exceptions=None) -> dict:
    meta = {"geometry_exceptions": exceptions} if exceptions else {}
    poly = {"type": "primitive", "kind": "polygon_2d", "params": {"vertices": vertices}}
    return {"materials": [{"sdf_tree": {"kind": "2d_to_3d", "children": [poly]}}], "metadata": meta}


def _slot_with_sampled_ends(n_per_end: int) -> list[list[float]]:
    """A 40 x 10 slot outline whose round ends are sampled into segments."""
    pts = []
    for cx, a0 in ((20.0, -90.0), (-20.0, 90.0)):
        for k in range(n_per_end + 1):
            a = math.radians(a0 + 180.0 * k / n_per_end)
            pts.append([cx + 5 * math.cos(a), 5 * math.sin(a)])
    return pts


def test_a_round_end_drawn_as_segments_fails(capsys):
    n, out = _run(_part(_slot_with_sampled_ends(12)), capsys)
    assert n == 1
    assert "uneven_capsule_2d" in out


def test_a_spline_fed_a_sampled_curve_fails(capsys):
    pts = [[math.cos(t / 10), math.sin(t / 10)] for t in range(63)]
    doc = {
        "materials": [{"sdf_tree": {"kind": "bspline_2d", "params": {"control_points": pts}}}],
        "metadata": {},
    }
    n, out = _run(doc, capsys)
    assert n == 1 and "63 control points" in out
    few = {
        "materials": [{"sdf_tree": {"kind": "bspline_2d", "params": {"control_points": pts[::8]}}}],
        "metadata": {},
    }
    assert _run(few, capsys)[0] == 0


def test_a_plain_polygon_passes(capsys):
    hexagon = [[math.cos(math.radians(60 * k)), math.sin(math.radians(60 * k))] for k in range(6)]
    l_shape = [[0, 0], [10, 0], [10, 3], [3, 3], [3, 10], [0, 10]]
    assert _run(_part(hexagon), capsys)[0] == 0
    assert _run(_part(l_shape), capsys)[0] == 0


def test_a_declared_exception_passes(capsys):
    doc = _part(_slot_with_sampled_ends(12), {"arcs": "imported vendor outline, sampled"})
    assert _run(doc, capsys)[0] == 0
