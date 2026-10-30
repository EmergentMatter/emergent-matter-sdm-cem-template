"""Every number in the part comes from a parameter, and every parameter says
where it comes from.

Parametric modelling is the point of a CEM: change a requirement, rerun, and
every dimension that depends on it moves. That only holds if nothing is
positioned or sized by a number typed into the shape code. Such a number looks
fine in review (the part is the right size today) and is silently wrong the
first time an input changes, because nothing ties it to anything.

Three checks, copied into every CEM made from this template:

1. Every declared parameter names its `source` in `cem.toml` (a requirement, a
   bought part, a standard, a process limit, a reasoned choice, or a tool
   setting). A number with no source is a guess nobody can check.
2. No number in the emitted trees stays put when each float parameter is
   changed on its own: such a number is typed into the code, not computed from
   the inputs. Plain constants (0, 1/2, 1, 2 and angles of whole 15 degree
   steps, which come from counts) are allowed.
3. Scale every length parameter together and every length in the part scales
   exactly with them: a number that does not is a parameter plus a typed-in
   offset (`outer_radius + 1.3`), which reads as parametric and is not.
"""

from __future__ import annotations

import dataclasses
import math
import re
import tomllib
from pathlib import Path
from typing import Any

from widget_sdf.parameters import WidgetParameters
from widget_sdf.sdm.assembly import build_widget_part

ROOT = Path(__file__).resolve().parents[1]
CEM = tomllib.loads((ROOT / "cem.toml").read_text())["cem"]

#: The kinds of source a parameter may name (cem.toml explains each).
SOURCE = re.compile(
    r"^(requirement:\S+|part:[^:\s]+:\S+|standard:.+|process:[^:\s]+:\S+|choice: .+|tool: .+)"
)
#: A `choice` has to say why in at least this many words.
N_REASON_WORDS = 5
#: How much a float parameter is scaled for a comparison build.
D_SCALE = 1.07
#: Numbers that may appear in a tree without coming from a parameter.
PLAIN = (0.0, 0.5, 1.0, 2.0)

Numbers = list[tuple[str, Any]]


def test_every_param_names_its_source() -> None:
    missing = [n for n, spec in CEM["params"].items() if not spec.get("source")]
    assert not missing, (
        f"cem.toml params with no `source`: {missing}. Say where each number "
        "comes from: a requirement, a bought part, a standard, a process limit, "
        "or `choice: <why>`."
    )
    bad = [n for n, spec in CEM["params"].items() if not SOURCE.match(spec["source"])]
    assert not bad, f"`source` not one of the kinds cem.toml lists: {bad}"


def test_a_choice_says_why() -> None:
    thin = [
        n
        for n, spec in CEM["params"].items()
        if spec["source"].startswith("choice:") and len(spec["source"].split()) - 1 < N_REASON_WORDS
    ]
    assert not thin, f"`choice` sources with no real reason: {thin}"


def _numbers(tree: Any, where: str = "") -> Numbers:
    """Every number in a tree with its place, plus every place's shape (keys
    or length), so two trees can be lined up."""
    out: Numbers = []
    if isinstance(tree, dict):
        out.append((f"{where}{{}}", tuple(sorted(tree))))
        for k in sorted(tree):
            out += _numbers(tree[k], f"{where}/{k}")
    elif isinstance(tree, (list, tuple)):
        out.append((f"{where}[]", len(tree)))
        for i, v in enumerate(tree):
            out += _numbers(v, f"{where}/{i}")
    elif isinstance(tree, (int, float)) and not isinstance(tree, bool):
        out.append((where, float(tree)))
    return out


def _plain(x: float) -> bool:
    if any(math.isclose(abs(x), c, abs_tol=1e-12) for c in PLAIN):
        return True
    steps = x / (math.pi / 12)  # whole 15 degree steps: an angle set by a count
    return math.isclose(steps, round(steps), abs_tol=1e-9)


def _trees(p: WidgetParameters) -> list[Any]:
    return [m.sdf_tree for m in build_widget_part(p).materials]


def _scaled(base: WidgetParameters, names: list[str], k: float) -> WidgetParameters:
    return dataclasses.replace(base, **{n: getattr(base, n) * k for n in names})


def _floats(p: WidgetParameters) -> list[str]:
    return [f.name for f in dataclasses.fields(p) if isinstance(getattr(p, f.name), float)]


def _lined_up(a: Numbers, b: Numbers) -> list[tuple[str, float, float]]:
    assert [w for w, _ in a] == [w for w, _ in b], (
        "the tree changed shape when only float parameters changed; a float "
        "parameter should size and place features, not add or remove them"
    )
    return [(w, va, vb) for (w, va), (_, vb) in zip(a, b, strict=True) if isinstance(va, float)]


def test_no_number_is_typed_into_the_shapes() -> None:
    """Each float parameter is changed on its own; a number that moves for
    none of them is typed in."""
    base = WidgetParameters()
    a = _numbers(_trees(base))
    moved: set[str] = set()
    for name in _floats(base):
        for w, va, vb in _lined_up(a, _numbers(_trees(_scaled(base, [name], D_SCALE)))):
            if va != vb:
                moved.add(w)
    typed = [(w, v) for w, v in a if isinstance(v, float) and w not in moved and not _plain(v)]
    assert not typed, (
        "numbers typed into the shape code, not computed from parameters "
        "(no parameter moves them): "
        + "; ".join(f"{v:g} at {w}" for w, v in typed[:12])
        + ". Make each a parameter with a `source` in cem.toml, or compute it "
        "from the ones it depends on."
    )


def test_no_length_is_offset_by_a_typed_number() -> None:
    """Scale every length parameter (unit mm) together and every length in the
    part must scale exactly with them; an angle or a count does not move. A
    number that does neither mixes a parameter with a typed-in length
    (`outer_radius + 1.3`), which reads as parametric and is not."""
    base = WidgetParameters()
    lengths = [n for n in _floats(base) if CEM["params"].get(n, {}).get("unit") == "mm"]
    pairs = _lined_up(_numbers(_trees(base)), _numbers(_trees(_scaled(base, lengths, D_SCALE))))
    mixed = [
        (w, va, vb)
        for w, va, vb in pairs
        if not math.isclose(vb, va, rel_tol=1e-9, abs_tol=1e-12)
        and not math.isclose(vb, D_SCALE * va, rel_tol=1e-9, abs_tol=1e-12)
    ]
    assert not mixed, (
        f"lengths that did not scale with the length parameters (all scaled by "
        f"{D_SCALE}): "
        + "; ".join(f"{va:g} -> {vb:g} at {w}" for w, va, vb in mixed[:12])
        + ". Something typed in is being added to a parameter: make it a "
        "parameter with a `source`."
    )
