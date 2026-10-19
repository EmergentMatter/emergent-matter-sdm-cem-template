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
  * One file per physical part, reused. A part used in several places is
    one file placed by several instances, so changing it changes it
    everywhere. The same part saved under two names is two parts that
    nothing ties together: a change to one silently misses the other, and
    parts ordered from one may not fit where the other is used.
  * An assembly says how it goes together (``metadata.assembly_process``, see
    docs/assembly-process.md): every instance installed once, in order, from a
    direction, and listed in the file in that build order so the tree reads
    as the build. Without it nothing downstream can explode or sequence the
    assembly, and the knowledge of how to build it lives nowhere.
  * Names read from the assembly down to the detail. Each instance names what
    it is first, then the detail (``screw_m2x6_clampring_1``, not
    ``clampring_1_screw``): an instance of a part starts with the first word
    of its part file's name. The full name is the ids from the top down
    (``hand_mech_crank_driven_thumb``), so a person reads where a part lives
    and what it is without opening the tree (sdm-core ADR 0009).

  * Curves are curves. An arc or round drawn as a polygon of short straight
    segments is a row of flat strips: it renders faceted, exports faceted,
    and prints or cuts faceted, and its radius cannot be measured. sdm-core
    has the exact shapes: circle_2d, rounded_box_2d, uneven_capsule_2d (a
    slot with round ends), and the round modifier on a sharp polygon. A
    bspline_2d is smooth from a handful of control points; sdm-core samples
    it into 16 straight pieces per control point, so one fed hundreds of
    sampled points is no smoother and makes the part many times slower to
    evaluate (a hand's fin went from under a minute to over twenty to mesh).
  * Every part file carries what its parts-list line needs and the geometry
    cannot give (``metadata.bom``, see docs/bom.md). A bought part names its
    vendor and the vendor's part number; a made part says how it is made.
    Without them a parts list is a list of file names, and someone retypes
    every vendor and process by hand, from memory, again for every build.
    Quantities are not written: they are counted from the instances. A
    missing price is reported, not failed: a price nobody quoted is worse
    than none.

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
OK, BAD, NOTE = "  ok   ", " FAIL  ", "  note "
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


def note(s_label: str) -> None:
    """Worth knowing, not a failure."""
    print(NOTE + s_label)


#: What a parts-list quantity may be counted in (docs/bom.md).
BOM_UNITS = ("each", "mm", "m", "in", "ft", "mm^2", "m^2", "in^2", "ft^2", "g", "kg", "ml", "l")
#: How a part is made (docs/bom.md). One spelling each, so a parts list can be
#: sorted and counted by process; anything else is "Other: <what it is>".
FABRICATION_METHODS = (
    "Purchased",
    "FDM",
    "SLS",
    "MJF",
    "SLA",
    "DLP",
    "Metal AM",
    "Machined",
    "Turned",
    "Laser cut",
    "Waterjet cut",
    "Sheet metal",
    "Cast",
    "Moulded",
    "Cut from stock",
    "Hand made",
)
BOM_TEXT = (
    "part_number",
    "vendor",
    "vendor_part_number",
    "url",
    "fabrication",
    "notes",
    "currency",
    "material",
)


#: An outline fakes a curve when this many corners in a row each turn by a
#: small angle (between the two below, degrees): a polygon's real corners
#: turn sharply, a sampled arc turns a little at every vertex.
N_FAKE_ARC_RUN = 4
D_FAKE_ARC_MIN_DEG = 1.0
D_FAKE_ARC_MAX_DEG = 35.0


#: A bspline_2d with more control points than this was fed a sampled curve.
N_SPLINE_MAX_POINTS = 24


def _heavy_splines(materials) -> list[int]:
    """Control-point counts of bspline_2d outlines with more than N_SPLINE_MAX_POINTS."""
    out = []

    def walk(node):
        if isinstance(node, dict):
            if node.get("kind") == "bspline_2d":
                cp = (node.get("params") or {}).get("control_points") or []
                if len(cp) > N_SPLINE_MAX_POINTS:
                    out.append(len(cp))
            for x in node.values():
                walk(x)
        elif isinstance(node, list):
            for x in node:
                walk(x)

    walk(materials)
    return out


def _fake_arcs(materials) -> int:
    """How many polygon_2d outlines run several gently turning corners in a row."""
    import math

    found = []

    def walk(node):
        if isinstance(node, dict):
            if node.get("kind") == "polygon_2d":
                v = (node.get("params") or {}).get("vertices") or node.get("vertices")
                if isinstance(v, list) and len(v) > N_FAKE_ARC_RUN:
                    found.append(v)
            for x in node.values():
                walk(x)
        elif isinstance(node, list):
            for x in node:
                walk(x)

    walk(materials)
    n_fake = 0
    for v in found:
        run = best = 0
        for i in range(len(v)):
            a, b, c = v[i - 1], v[i], v[(i + 1) % len(v)]
            t1 = math.atan2(b[1] - a[1], b[0] - a[0])
            t2 = math.atan2(c[1] - b[1], c[0] - b[0])
            turn = math.degrees(abs((t2 - t1 + math.pi) % (2 * math.pi) - math.pi))
            run = run + 1 if D_FAKE_ARC_MIN_DEG < turn < D_FAKE_ARC_MAX_DEG else 0
            best = max(best, run)
        n_fake += best >= N_FAKE_ARC_RUN
    return n_fake


def _check_curves(doc: dict) -> None:
    """Rounds and arcs are exact shapes, not polygons of short segments."""
    exceptions = (doc.get("metadata") or {}).get("geometry_exceptions") or {}
    n = _fake_arcs(doc.get("materials"))
    if n and isinstance(exceptions, dict) and exceptions.get("arcs"):
        check(True, "curves drawn as segments, declared", exceptions["arcs"])
        return
    check(
        n == 0,
        "curves are curves (no arc or round faked with straight segments)",
        f"{n} polygon_2d outline{'s' if n > 1 else ''} with runs of short segments: use circle_2d, "
        "rounded_box_2d, uneven_capsule_2d, or the round modifier"
        if n
        else "",
    )
    heavy = _heavy_splines(doc.get("materials"))
    check(
        not heavy,
        f"splines are smooth from a few control points (at most {N_SPLINE_MAX_POINTS})",
        f"bspline_2d with {', '.join(map(str, heavy))} control points: a sampled curve, "
        "faceted and slow; use exact shapes, or a spline through a handful of points"
        if heavy
        else "",
    )


def _check_bom(doc: dict) -> None:
    """The part carries what its parts-list line needs (docs/bom.md)."""
    import re

    meta = doc.get("metadata") or {}
    exceptions = meta.get("geometry_exceptions") or {}
    bom = meta.get("bom")
    if bom is not None and not isinstance(bom, dict):
        check(False, "metadata.bom is an object", type(bom).__name__)
        return
    bom = bom or {}
    bad = [k for k in BOM_TEXT if k in bom and not (isinstance(bom[k], str) and bom[k].strip())]

    def number(v) -> bool:
        return isinstance(v, (int, float)) and not isinstance(v, bool)

    price = bom.get("unit_price")
    if price is not None and not (number(price) and price >= 0):
        bad.append("unit_price (a number, 0 or more)")
    qty = bom.get("quantity")
    if qty is not None and not (number(qty) and qty > 0):
        bad.append("quantity (a number above 0)")
    if "unit" in bom and bom["unit"] not in BOM_UNITS:
        bad.append(f"unit ({bom['unit']!r}: one of {', '.join(BOM_UNITS)})")
    rev = bom.get("revision") or (meta.get("source") or {}).get("revision")
    x_y_z = r"[1-9]\d*\.[1-9]\d*\.[1-9]\d*"
    if rev is not None and not (isinstance(rev, str) and re.fullmatch(x_y_z, rev)):
        bad.append(f"revision ({rev!r}: x.y.z, each from 1)")
    check(not bad, "metadata.bom fields are well formed", ", ".join(bad))
    if isinstance(exceptions, dict) and exceptions.get("bom"):
        check(True, "parts-list facts excused", exceptions["bom"])
        return
    bought = meta.get("bought")
    if bought is not None and not isinstance(bought, bool):
        check(False, "metadata.bought is true or false", repr(bought))
        return
    if bought:
        missing = [k for k in ("vendor", "vendor_part_number") if not bom.get(k)]
        check(
            not missing,
            "bought part names its vendor and the vendor's part number",
            "missing metadata.bom." + ", ".join(missing) if missing else "",
        )
        if price is None:
            note("no unit_price yet (left empty rather than guessed)")
    else:
        check(
            bool(bom.get("fabrication")),
            "made part says how it is made",
            "" if bom.get("fabrication") else "missing metadata.bom.fabrication (SLS, FDM, ...)",
        )
    fab = bom.get("fabrication")
    if fab:
        ok = fab in FABRICATION_METHODS or (
            isinstance(fab, str) and fab.startswith("Other: ") and len(fab) > 7
        )
        near = next(
            (
                m
                for m in FABRICATION_METHODS
                if isinstance(fab, str) and m.lower() == fab.strip().lower()
            ),
            None,
        )
        check(
            ok,
            "fabrication is one of the listed methods (or 'Other: ...')",
            ""
            if ok
            else (
                f"{fab!r}: write {near!r}"
                if near
                else f"{fab!r} is not in the list ({', '.join(FABRICATION_METHODS)}); "
                "use 'Other: <what it is>' for anything new"
            ),
        )


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
    _check_names(path, doc)
    _check_process(doc, ids)
    for target in dict.fromkeys(targets):
        check_file(target, seen)


def _check_reuse(paths) -> None:
    """No two files define the same thing (apart from name and metadata)."""
    groups: dict[str, list[Path]] = {}
    for path in paths:
        try:
            doc = json.loads(Path(path).read_text())
        except (OSError, ValueError):
            continue
        body = {k: v for k, v in doc.items() if k not in ("name", "metadata")}
        groups.setdefault(json.dumps(body, sort_keys=True), []).append(Path(path))
    copies = [g for g in groups.values() if len(g) > 1]
    print("\nreuse")
    check(
        not copies,
        "each part is one file, reused by instances",
        "; ".join(" = ".join(p.name for p in g) for g in copies)
        + (": keep one file and point every instance at it" if copies else ""),
    )


def _check_names(path: Path, doc: dict) -> None:
    """Each instance of a part starts with what the part is (sdm-core ADR 0009)."""
    wrong = []
    for inst in doc.get("instances", []):
        rel = (inst.get("part_ref") or {}).get("path", "")
        target = path.parent / rel
        try:
            if _is_assembly(json.loads(target.read_text())):
                continue  # a sub-assembly's id is its short name
        except (OSError, ValueError):
            continue
        kind = Path(rel).stem.split("_")[0]
        iid = inst.get("id", "")
        if iid != kind and not iid.startswith(kind + "_"):
            wrong.append(f"{iid} (places {Path(rel).stem}: start it {kind}_)")
    check(
        not wrong,
        "names say what each part is first, then the detail",
        ", ".join(wrong[:4]) + (f" and {len(wrong) - 4} more" if len(wrong) > 4 else ""),
    )


#: What sort of work a build step is (docs/assembly-process.md).
STEP_KINDS = ("place", "screw", "heat_set", "press", "glue", "snap", "solder", "other")


def _check_process(doc: dict, ids: list) -> None:
    """The assembly says how it goes together (docs/assembly-process.md)."""
    meta = doc.get("metadata") or {}
    proc = meta.get("assembly_process")
    if proc is None:
        reason = (meta.get("geometry_exceptions") or {}).get("assembly_process")
        if reason:
            check(True, "no build sequence, declared", reason)
        else:
            check(
                False,
                "says how it goes together (metadata.assembly_process)",
                "missing: see docs/assembly-process.md",
            )
        return
    problems = []
    known = set(ids)
    placed = dict.fromkeys(proc.get("base") or [], "base")
    problems += [f"base names {i!r}, not an instance" for i in placed if i not in known]
    mated = {str(m.get("child", "")).split(".")[0] for m in doc.get("mates") or []}
    earlier: set = set()
    for n, step in enumerate(proc.get("steps") or []):
        sid = step.get("id") or f"step {n + 1}"
        for i in step.get("instances") or []:
            if i not in known:
                problems.append(f"{sid}: {i!r} is not an instance")
            elif i in placed:
                problems.append(f"{sid}: {i!r} already installed by {placed[i]!r}")
            else:
                placed[i] = sid
        d = step.get("direction")
        ok_dir = (
            isinstance(d, list)
            and len(d) == 3
            and any(isinstance(v, (int, float)) and v for v in d)
        )
        if not ok_dir and not (d is None and set(step.get("instances") or []) <= mated):
            problems.append(f"{sid}: no usable direction")
        t = step.get("travel")
        if t is not None and not (isinstance(t, (int, float)) and t > 0):
            problems.append(f"{sid}: travel must be a positive number of mm")
        r = step.get("rotate")
        if r is not None and not (
            isinstance(r, dict)
            and isinstance(r.get("axis"), list)
            and isinstance(r.get("angle_deg"), (int, float))
        ):
            problems.append(f"{sid}: rotate needs an axis and an angle_deg")
        after = step.get("after")
        if after is not None:
            if not isinstance(after, list):
                problems.append(f"{sid}: after must be a list of step ids")
            else:
                problems += [
                    f"{sid}: after names {a!r}, not an earlier step"
                    for a in after
                    if a not in earlier
                ]
        m = step.get("minutes")
        if m is not None and not (isinstance(m, (int, float)) and m > 0):
            problems.append(f"{sid}: minutes must be a positive number")
        if step.get("kind") not in (None, *STEP_KINDS):
            problems.append(f"{sid}: kind must be one of {', '.join(STEP_KINDS)}")
        earlier.add(sid)
    if proc.get("minutes_source") not in (None, "estimate", "measured"):
        problems.append('minutes_source must be "estimate" or "measured"')
    problems += [f"{i!r} is never installed and is not in base" for i in ids if i not in placed]
    # The tree reads as the build: instances listed base first, then step by
    # step. Only judged once the steps themselves add up.
    if not problems:
        order = list(proc.get("base") or [])
        order += [i for s in proc.get("steps") or [] for i in s.get("instances") or []]
        if ids != order:
            first = next(k for k in range(len(ids)) if ids[k] != order[k])
            problems.append(
                "instances are not listed in build order "
                f"(position {first + 1} is {ids[first]!r}, the build has {order[first]!r} there)"
            )
    check(
        not problems,
        "says how it goes together (metadata.assembly_process)",
        "; ".join(problems[:4]) + (" ..." if len(problems) > 4 else ""),
    )


def _check_part(path: Path, doc: dict) -> None:
    import numpy as np
    from software_defined_matter.io import load_part
    from software_defined_matter.sdf.compile import make_sdf_closure

    exceptions = (doc.get("metadata") or {}).get("geometry_exceptions") or {}
    _check_bom(doc)
    _check_curves(doc)

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
        _check_reuse(sorted(seen))
    print(f"\n{'All checks passed.' if not _failures else f'{_failures} check(s) failed.'}")
    return 1 if _failures else 0


if __name__ == "__main__":
    sys.exit(main())
