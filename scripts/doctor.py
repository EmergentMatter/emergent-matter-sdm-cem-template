#!/usr/bin/env python3
"""Diagnose a CEM setup and say exactly what to do about it.

Stdlib only, and it must stay that way: this script has to run BEFORE the
environment exists, which is precisely when the environment is broken. It also
has to run on whatever Python the user happens to have, including the 3.9 that
ships with macOS, so nothing here may use syntax newer than 3.8.

Run it whenever something does not work:

    python3 scripts/doctor.py

Every check prints what it found, and every failure prints the fix rather than
just the symptom. The failures below are the real ones, in the order people
hit them.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

MIN_PYTHON = (3, 13)

OK = "  ok   "
BAD = " FAIL  "
WARN = " warn  "

_n_fail = 0


def report(b_ok, s_label, s_detail="", s_fix=""):
    global _n_fail
    tag = OK if b_ok else BAD
    if not b_ok:
        _n_fail += 1
    print(tag + s_label + (("  " + s_detail) if s_detail else ""))
    if not b_ok and s_fix:
        for line in s_fix.strip().splitlines():
            print("         " + line.strip())
    return b_ok


def repo_root():
    return str(Path(__file__).resolve().parent.parent)


def console_script(root):
    """The console-script name `pyproject.toml`'s `[project.scripts]`
    installs, read with a regex rather than `tomllib`: this script has to
    run on the Python 3.9 macOS ships, and `tomllib` needs 3.11+. See the
    identical helper in `bootstrap.py` for why a hardcoded name here would
    go stale silently.
    """
    text = (Path(root) / "pyproject.toml").read_text()
    match = re.search(r"(?m)^\[project\.scripts\]\s*\n(\S+)\s*=", text)
    return match.group(1) if match else "widget-build"


def check_uv():
    path = shutil.which("uv")
    return report(
        bool(path),
        "uv installed",
        path or "",
        "Install it:\n"
        "  curl -LsSf https://astral.sh/uv/install.sh | sh\n"
        "uv manages the Python version and the venv. Do not use pip here.",
    )


def check_python_available():
    """The interpreter uv will USE, which is not the one running this script.

    Worth separating: this script deliberately runs on old Python, so its own
    version proves nothing about whether the project can be built.
    """
    if not shutil.which("uv"):
        return False
    try:
        out = subprocess.run(
            ["uv", "python", "list", "--only-installed"],
            capture_output=True,
            text=True,
            timeout=60,
        ).stdout
    except Exception as exc:  # pragma: no cover - environment dependent
        return report(False, "a Python 3.13+ is available to uv", str(exc))

    b_found = any(
        (".".join(tok.split("-")[1].split(".")[:2]) >= "3.13")
        for tok in out.split()
        if tok.startswith("cpython-")
    )
    return report(
        b_found,
        "a Python 3.13+ is available to uv",
        "" if b_found else "none found",
        "Fetch one:\n"
        "  uv python install 3.13\n"
        "3.13 is required by sdm-core. On an older interpreter the failure "
        "surfaces inside the materials package as\n"
        "  TypeError: zip() takes no keyword arguments\n"
        "which looks like a bug in materials and is not.",
    )


def check_sync():
    root = repo_root()
    b_venv = (Path(root) / ".venv").is_dir()
    return report(
        b_venv,
        "project synced (.venv exists)",
        "",
        "Run:  uv sync",
    )


def check_imports():
    root = repo_root()
    if not (Path(root) / ".venv").is_dir():
        return False
    code = (
        "import software_defined_matter as s, emergent_matter_materials as m; "
        # getattr, not a direct attribute: the constant's NAME varies between
        # sdm-core versions, and a doctor that reports "broken install" because
        # an attribute moved is worse than no doctor at all. What matters here
        # is that both packages import.
        "v = getattr(s, 'LATEST_SCHEMA_VERSION', None) or getattr(s, 'SCHEMA_VERSION', '?'); "
        "print(v, len(m.list_materials()))"
    )
    try:
        proc = subprocess.run(
            ["uv", "run", "python", "-c", code],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=300,
        )
    except Exception as exc:  # pragma: no cover
        return report(False, "sdm-core and materials import", str(exc))

    b_ok = proc.returncode == 0
    detail = proc.stdout.strip() if b_ok else proc.stderr.strip().splitlines()[-1:]
    return report(
        b_ok,
        "sdm-core and materials import",
        ("schema " + proc.stdout.split()[0] + ", " + proc.stdout.split()[1] + " materials")
        if b_ok
        else str(detail),
        "Try:  uv sync --reinstall",
    )


def main(argv: list[str] | None = None) -> int:
    print()
    print("EmergentMatter CEM setup check")
    print("  repo   " + repo_root())
    print(f"  python running this script: {sys.version_info[0]}.{sys.version_info[1]}")
    print()

    check_uv()
    check_python_available()
    print()
    check_sync()
    check_imports()

    print()
    if _n_fail == 0:
        print("Everything checks out. Try:")
        print("  uv run pytest")
        print("  uv run " + console_script(repo_root()) + " --out output/first.sdm")
        return 0
    print(f"{_n_fail} check(s) failed. Fix them top to bottom: later ones depend on")
    print("earlier ones, so the first failure is usually the only real problem.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
