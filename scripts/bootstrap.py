#!/usr/bin/env python3
"""One command from a fresh clone to a working, tested CEM.

    python3 scripts/bootstrap.py

Fetches Python, syncs from the package index, and runs the test suite.

Stdlib only, and it must stay that way. It runs before the environment exists,
on whatever Python is on the machine, so nothing here may use syntax newer
than 3.8.

If it fails, run `python3 scripts/doctor.py`, which explains rather than acts.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path


def root():
    return str(Path(__file__).resolve().parent.parent)


def console_script(here):
    """The console-script name `pyproject.toml`'s `[project.scripts]`
    installs, read with a regex rather than `tomllib`: this script has to
    run on the Python 3.9 macOS ships, and `tomllib` needs 3.11+. A
    hardcoded name here would go stale silently the moment someone renames
    `[project.scripts]`'s key without knowing this file also names it,
    since nothing else checks that this hint still matches what got
    installed.
    """
    text = (Path(here) / "pyproject.toml").read_text()
    match = re.search(r"(?m)^\[project\.scripts\]\s*\n(\S+)\s*=", text)
    return match.group(1) if match else "widget-build"


def run(cmd, cwd=None):
    print("  $ " + " ".join(cmd))
    return subprocess.run(cmd, cwd=cwd).returncode


def main(argv: list[str] | None = None) -> int:
    here = root()
    print("\nBootstrapping a CEM workspace")
    print("  this repo : " + here + "\n")

    if not shutil.which("uv"):
        print(
            "error: uv is not installed. It manages the Python version and the venv.",
            file=sys.stderr,
        )
        print("  curl -LsSf https://astral.sh/uv/install.sh | sh", file=sys.stderr)
        return 1

    if not shutil.which("git"):
        print("error: git is not installed.", file=sys.stderr)
        return 1

    print("1. python")
    run(["uv", "python", "install", "3.13"])

    print("\n2. sync")
    if run(["uv", "sync"], cwd=here) != 0:
        print("\n  Sync failed. Run `python3 scripts/doctor.py` for the reason.")
        return 1

    print("\n3. tests")
    if run(["uv", "run", "pytest", "-q"], cwd=here) != 0:
        print("\n  Tests failed on a fresh clone. That is a bug in this repo,")
        print("  not in your setup. Please open an issue with the output above.")
        return 1

    print("\n4. tool contract")
    if run(["uv", "run", "python", "scripts/check_contract.py"], cwd=here) != 0:
        print("\n  The contract check failed on a fresh clone. That is a bug in")
        print("  this repo, not in your setup. Please open an issue.")
        return 1

    script = console_script(here)
    print("\nReady. Next:")
    print("  uv run " + script + " --out output/first.sdm")
    print("  uv run " + script + " --out output/wide.sdm --set d_length=200")
    print("\nThen read docs/traps.md before writing your own geometry: it is")
    print("the list of things that pass validation and are still wrong.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
