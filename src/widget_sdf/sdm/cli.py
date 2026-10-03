"""`python -m widget_sdf.sdm.cli --out part.sdm --set d_outer_radius=14`

Both flags are required by the viewer's `/reemit` contract. `--set` alone
500s inside a subprocess, and the error surfaces nowhere useful.
"""

from __future__ import annotations

import argparse
import dataclasses
import sys
from pathlib import Path
from typing import Any

from widget_sdf.parameters import WidgetParameters
from widget_sdf.sdm.assembly import build_widget_part
from widget_sdf.sdm.harness import save_sdm

__all__ = ["main"]


def _coerce(field_name: str, raw: str) -> bool | int | float | str:
    """Cast by the prefix, which IS the type in this codebase.

    An `n_` field parses through float FIRST. The `.sdm` stores every param
    value as a JSON number, so an integer round-trips as `8.0`; a viewer reads
    that and hands it straight back on re-emit, and `int("8.0")` raises. The
    failure reads "expects a whole number, got '8.0'", which looks like a whole
    number and sends you looking in the wrong place. A genuinely non-integral
    value is still refused.
    """
    if field_name.startswith("n_"):
        value = float(raw)
        if value != int(value):
            raise ValueError(f"{raw} is not a whole number")
        return int(value)
    if field_name.startswith("b_"):
        return raw.lower() in ("1", "true", "yes")
    if field_name.startswith("s_"):
        return raw
    return float(raw)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build the widget as a .sdm")
    ap.add_argument("--out", required=True, type=Path, help="output .sdm path")
    ap.add_argument(
        "--set",
        action="append",
        default=[],
        metavar="NAME=VALUE",
        help="override a parameter; repeatable",
    )
    ap.add_argument("--name", default="widget")
    args = ap.parse_args(argv)

    # Accept BOTH the field name and the name the param carries in the .sdm.
    #
    # The document strips the type prefix, so `n_bolt_holes` ships as
    # `bolt_holes` and `cem.toml` records that under `emits`. A viewer reads
    # the emitted name and passes THAT back on re-emit, so a CLI that only
    # knows the field name refuses every rebuild a viewer sends:
    #
    #   error: unknown parameter 'bolt_holes': did you mean 'n_bolt_holes'?
    #
    # Having --out and --set is necessary but not sufficient. The names have to
    # agree in both directions, and `emits` is the mapping that says so.
    known = {f.name for f in dataclasses.fields(WidgetParameters)}
    emitted: dict[str, str] = {}
    for f in known:
        alias = f.split("_", 1)[1]
        if alias in emitted:
            raise AssertionError(
                f"two fields emit the same name {alias!r}: {emitted[alias]!r} "
                f"and {f!r}. The .sdm could not tell them apart."
            )
        emitted[alias] = f

    overrides: dict[str, Any] = {}
    for item in args.set:
        if "=" not in item:
            ap.error(f"--set expects NAME=VALUE, got {item!r}")
        key, raw = item.split("=", 1)
        key = emitted.get(key, key)  # accept the emitted name too
        if key not in known:
            # Naming the near-misses turns a typo into a one-line fix instead
            # of a silently-ignored override that changes nothing.
            near = sorted(k for k in known if k.split("_", 1)[-1] == key.split("_", 1)[-1])
            ap.error(
                f"unknown parameter {key!r}" + (f": did you mean {near[0]!r}?" if near else "")
            )
        try:
            overrides[key] = _coerce(key, raw)
        except ValueError:
            kind = "whole number" if key.startswith("n_") else "number"
            ap.error(f"{key!r} expects a {kind}, got {raw!r}")

    params = dataclasses.replace(WidgetParameters(), **overrides)
    errors = params.validate()
    if errors:
        # Non-zero exit AND a named cause on STDERR. A viewer's re-emit reads
        # proc.stderr to explain a failure and DISCARDS stdout, so printing the
        # reason to stdout surfaces in the browser as "authoring failed:" with
        # nothing after it. The reason was there the whole time, on the wrong
        # stream.
        print("failed: invalid parameters:\n  " + "\n  ".join(errors), file=sys.stderr, flush=True)
        return 2

    # Record the arguments ACTUALLY used, not sys.argv: main() is called
    # in-process by the tests, where sys.argv is pytest's command line.
    recorded = [sys.argv[0]] + (list(argv) if argv is not None else sys.argv[1:])
    path = save_sdm(
        build_widget_part(params, name=args.name),
        args.name,
        out=args.out,
        argv=recorded,
    )
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
