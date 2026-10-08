#!/usr/bin/env python3
"""Check that a CEM's geometry is built the way every CEM builds it.

    uv run python scripts/check_geometry.py               # this CEM's own part
    uv run python scripts/check_geometry.py out/x.sdm ...  # any .sdm, part or assembly

WHY THIS EXISTS. Three CEMs built in the same week, each by a capable agent,
produced three different kinds of file: one described its parts as sdm-core
shapes, one carried a home-made primitive and voxel grids, and one designed in
a B-rep kernel and sampled the result onto grids with dozens of parts packed
into a single part. Every file built, validated, and opened in a viewer. Nothing
said which was right, so the next agent copied whichever it found first.

The rules this enforces, and what breaks without each:

  * Every material compiles to a field from sdm-core's own node types. A
    primitive that only exists in one repository makes a file that nothing
    else can evaluate.
  * No ``raster_field`` in designed geometry. A sampled grid is a picture of a
    part, not the part: edges round off to the grid pitch, holes come out
    polygonal, thin walls smear, a radius cannot be measured, the parameters
    no longer drive the shape, and the file is megabytes per part. A grid is
    for MEASURED data (a scan), never for something this CEM designed.
  * One physical part per part file. Several bodies packed into one part
    cannot be named, coloured, hidden, measured, or clearance-checked on their
    own, and any change to one re-meshes them all. Several parts make an
    assembly: one part file each, placed by instances.
  * An assembly's references resolve, and a pinned ``content_hash`` matches
    the bytes on disk. A stale hash means the part changed after the assembly
    was written and the assembly no longer describes what is on disk.

A real exception (a scanned surface, a print-in-place mechanism that is one
part but several bodies) is declared in the part's own metadata with a reason,
so the exception is visible in the file rather than in someone's memory::

    "metadata": {"geometry_exceptions": {"raster": "CT scan of the casting",
                                         "bodies": "print-in-place hinge"}}

The body count samples the field on a grid, so it is a check, not a proof:
bodies closer together than the sample pitch read as one, and a feature
thinner than the pitch can read as a break. The pitch is printed with the
result; a surprising count is a reason to look, not a verdict.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OK, BAD = "  ok   ", " FAIL  "
#: Body-count sample pitch, mm: the finer of this and the part's longest side
#: over N_BODY_MIN_CELLS. Fine enough that a printed wall does not read as a
#: break; a wall thinner than this can.
D_BODY_PITCH = 0.25
N_BODY_MIN_CELLS = 200
#: Most grid points sampled for one part; past it the pitch grows, and says so.
N_BODY_MAX_POINTS = 120_000_000
#: Points per field call, to bound memory on large grids.
N_CHUNK = 500_000

_failures = 0


def check(b_ok: bool, s_label: str, s_detail: str = "") -> bool:
    global _failures
    print((OK if b_ok else BAD) + s_label + (f"  {s_detail}" if s_detail else ""))
    _failures += not b_ok
    return b_ok


def _walk(node, found: list[str]) -> None:
    """Collect every node kind in an SDF tree (JSON form)."""
    if isinstance(node, dict):
        kind = node.get("kind")
        if isinstance(kind, str):
            found.append(kind)
        for v in node.values():
            _walk(v, found)
    elif isinstance(node, list):
        for v in node:
            _walk(v, found)


def _is_assembly(doc: dict) -> bool:
    return doc.get("kind") == "assembly" or "instances" in doc


def check_file(path: Path, seen: set[Path]) -> None:
    path = path.resolve()
    if path in seen:
        return
    seen.add(path)
    try:
        doc = json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        check(False, f"{path.name} reads as JSON", str(exc))
        return
    print(f"\n{path.name} ({'assembly' if _is_assembly(doc) else 'part'})")
    if _is_assembly(doc):
        _check_assembly(path, doc, seen)
    else:
        _check_part(path, doc)


def _check_assembly(path: Path, doc: dict, seen: set[Path]) -> None:
    ids = [inst.get("id") for inst in doc.get("instances", [])]
    check(len(ids) == len(set(ids)), "instance ids are unique")
    targets = []
    for inst in doc.get("instances", []):
        ref = inst.get("part_ref", {})
        target = (path.parent / ref.get("path", "")).resolve()
        if not check(target.is_file(), f"{inst.get('id')} -> {ref.get('path')} exists"):
            continue
        pinned = ref.get("content_hash")
        if pinned:
            actual = "sha256:" + hashlib.sha256(target.read_bytes()).hexdigest()
            check(
                actual == pinned,
                f"{inst.get('id')} -> {ref.get('path')} matches its pinned hash",
                "" if actual == pinned else "the part changed after this assembly was written",
            )
        targets.append(target)
    for target in dict.fromkeys(targets):
        check_file(target, seen)


def _check_part(path: Path, doc: dict) -> None:
    import numpy as np
    from software_defined_matter.io import load_part
    from software_defined_matter.sdf.compile import make_sdf_closure

    exceptions = (doc.get("metadata") or {}).get("geometry_exceptions") or {}

    kinds: list[str] = []
    _walk(doc.get("materials"), kinds)
    n_raster = kinds.count("raster_field")
    if n_raster and exceptions.get("raster"):
        check(True, "sampled grids declared as measured data", exceptions["raster"])
    else:
        check(
            n_raster == 0,
            "no raster_field (designed parts are shapes, not sampled grids)",
            f"{n_raster} found" if n_raster else "",
        )

    try:
        part = load_part(path)
    except Exception as exc:  # the loader's own message is the useful part
        check(False, "loads and validates with sdm-core", f"{type(exc).__name__}: {exc}")
        return
    check(True, "loads and validates with sdm-core")

    fields = []
    for region in part.materials:
        try:
            fn = make_sdf_closure(region.sdf_tree, part)
            fn(np.zeros((1, 3), dtype=np.float32))
            fields.append((region, fn))
            check(True, f"{region.name} compiles to a field")
        except Exception as exc:
            check(False, f"{region.name} compiles to a field", f"{type(exc).__name__}: {exc}")
    if len(fields) != len(part.materials) or not fields:
        return

    n, pitch = _count_bodies(part, fields)
    if n == 1:
        check(True, "one physical body", f"sampled at {pitch:.2f} mm")
    elif n > 1 and exceptions.get("bodies"):
        check(True, f"{n} bodies, declared as one part", exceptions["bodies"])
    else:
        check(
            False,
            "one physical body",
            f"{n} separate bodies at a {pitch:.2f} mm sample: "
            "make each its own part file in an assembly"
            if n
            else "the part is empty",
        )


def _count_bodies(part, fields) -> tuple[int, float]:
    """Connected solids in the union of every material, from a grid sample."""
    import numpy as np
    from scipy import ndimage
    from software_defined_matter.grid_sampling import material_bbox

    lo, hi = np.full(3, np.inf), np.full(3, -np.inf)
    for region, _ in fields:
        try:
            b = material_bbox(region, part)
            lo, hi = np.minimum(lo, b.min_pt), np.maximum(hi, b.max_pt)
        except Exception:
            box = np.asarray(part.metadata.get("bbox"), dtype=float)
            lo, hi = np.minimum(lo, box[0]), np.maximum(hi, box[1])
    # A part's declared box can be its whole assembly's; shrink to the solid
    # first so the fine pass resolves the part, not empty space around it.
    inside, _, axes = _sample(fields, lo, hi, 64)
    if not inside.any():
        return 0, 0.0
    idx = np.argwhere(inside)
    cell = axes[0][1] - axes[0][0]
    lo = np.array([axes[a][idx[:, a].min()] for a in range(3)]) - cell
    hi = np.array([axes[a][idx[:, a].max()] for a in range(3)]) + cell
    pitch = min(D_BODY_PITCH, float(np.max(hi - lo)) / N_BODY_MIN_CELLS)
    while np.prod((hi - lo) / pitch + 3) > N_BODY_MAX_POINTS:
        pitch *= 1.25
    inside, pitch, _ = _sample(fields, lo, hi, float(np.max(hi - lo)) / pitch)
    _, n = ndimage.label(inside)
    return int(n), pitch


def _sample(fields, lo, hi, n_cells):
    """Inside/outside of the union of fields on a grid with n_cells along the
    longest side. Evaluated a slab at a time so memory stays bounded."""
    import numpy as np

    pitch = float(np.max(hi - lo)) / n_cells
    axes = [np.arange(lo[a] - pitch, hi[a] + 2 * pitch, pitch) for a in range(3)]
    shape = tuple(len(a) for a in axes)
    inside = np.zeros(shape, dtype=bool)
    gx, gy = np.meshgrid(axes[0], axes[1], indexing="ij")
    n_slab = max(1, N_CHUNK // gx.size)
    for k0 in range(0, shape[2], n_slab):
        zs = axes[2][k0 : k0 + n_slab]
        pts = np.empty(gx.shape + (len(zs), 3), dtype=np.float32)
        pts[..., 0] = gx[..., None]
        pts[..., 1] = gy[..., None]
        pts[..., 2] = zs
        pts = pts.reshape(-1, 3)
        slab = np.zeros(len(pts), dtype=bool)
        for _, fn in fields:
            for i in range(0, len(pts), N_CHUNK):
                slab[i : i + N_CHUNK] |= np.asarray(fn(pts[i : i + N_CHUNK])) < 0
        inside[:, :, k0 : k0 + len(zs)] = slab.reshape(shape[0], shape[1], len(zs))
    return inside, pitch, axes


def _own_part_file(tmp: Path) -> Path:
    """Build this CEM's default part through its declared entry point."""
    import importlib

    from software_defined_matter.io import save

    manifest = tomllib.loads((ROOT / "cem.toml").read_text())["cem"]
    module, func = manifest["entry_point"].split(":")
    part = getattr(importlib.import_module(module), func)()
    out = tmp / f"{part.name}.sdm"
    save(part, out)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument(
        "files",
        nargs="*",
        type=Path,
        help=".sdm files to check (default: this CEM's own part)",
    )
    args = ap.parse_args(argv)
    print("\nCEM geometry standard")
    seen: set[Path] = set()
    with tempfile.TemporaryDirectory() as tmp:
        for f in args.files or [_own_part_file(Path(tmp))]:
            check_file(f, seen)
    print(f"\n{'All checks passed.' if not _failures else f'{_failures} check(s) failed.'}")
    return 1 if _failures else 0


if __name__ == "__main__":
    sys.exit(main())
