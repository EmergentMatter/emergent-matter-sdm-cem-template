#!/usr/bin/env python3
"""Run this CEM's build CLI with plain Python: no `uv`, no installed package.

    python scripts/build.py --out output/part.sdm --set <name>=<value>

The recorded generator of a `.sdm` names this file when the part was built
where `uv` is absent (a hosted workspace). It puts `src/` on the import path,
then calls the entry point `[project.scripts]` declares, so it needs no edit
when `rename.py` renames the package.

The first script in `[project.scripts]` is the one it runs.
"""

from __future__ import annotations

import importlib
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def entry_point() -> tuple[str, str]:
    """`(module, function)` of the first console script in pyproject."""
    with (ROOT / "pyproject.toml").open("rb") as fh:
        scripts = tomllib.load(fh).get("project", {}).get("scripts", {})
    if not scripts:
        raise SystemExit("pyproject declares no [project.scripts]; nothing to run")
    module, _, func = next(iter(scripts.values())).partition(":")
    return module, func or "main"


def main(argv: list[str] | None = None) -> int:
    sys.path.insert(0, str(ROOT / "src"))
    module, func = entry_point()
    result = getattr(importlib.import_module(module), func)(
        list(sys.argv[1:] if argv is None else argv)
    )
    return result if isinstance(result, int) else 0


if __name__ == "__main__":
    raise SystemExit(main())
