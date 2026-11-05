"""Every dimension is free, an input, or driven, and nothing dangles.

The check itself lives in sdm-core (`software_defined_matter.dimension_audit`),
so every CEM runs the same one; this file only points it at this CEM's part and
its declared dimensions. Copy it into a real CEM and change the two imports.

- free: declared in cem.toml with `bounds`; an optimizer may move it.
- input: declared with a `source` (requirement, bought part, standard, process
  limit, parent assembly); fixed unless `tradeable = true`.
- driven: computed from the others (`@property`); never declared.

The audit fails on a number typed into the shape code, a declared dimension
that moves nothing, a length with a typed-in offset, and a declaration missing
its origin, source or bounds. It prints which dimensions are driving.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from software_defined_matter.dimension_audit import assert_dimensions

from widget_sdf.parameters import WidgetParameters
from widget_sdf.sdm.assembly import build_widget_part

ROOT = Path(__file__).resolve().parents[1]


def _declared(path: Path) -> dict:
    return tomllib.loads(path.read_text())["cem"]["params"]


def test_every_dimension_is_free_input_or_driven() -> None:
    report = assert_dimensions(build_widget_part, WidgetParameters(), _declared(ROOT / "cem.toml"))
    print("driving:", report.driving, "| optimizer may move:", report.optimizable)
