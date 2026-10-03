"""`scripts/rename.py`, driven as a subprocess against a throwaway copy.

README's "Use it" step 1 used to be prose describing this rename by hand,
and every review round found another location it forgot to mention:
`cem.toml`'s `entry_point`, the imports in `tests/`, `examples/`, then the
repo slug `pyproject.toml` and `ci.yml` separately carry. The procedure is
now `scripts/rename.py` instead, so there is one copy to keep correct
rather than three, and this file drives it exactly the way a person (or
`bootstrap.py`) would: as a subprocess, against a copy of the tree, the same
reason `scripts/check_contract.py` drives the CLI as a subprocess rather
than calling `main()` in-process. It pins the invariant that the result
still holds together: the manifest and the dataclass still agree,
`cem.toml`'s `entry_point` still resolves, `ci.yml`'s `package-name` still
matches `[project].name`, the CLI still satisfies the tool contract, and
the script itself refuses bad input and a second run rather than
half-applying either.
"""

from __future__ import annotations

import dataclasses
import importlib
import json
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]

OLD_PACKAGE = "widget_sdf"
NEW_PACKAGE = "thing_sdf"
OLD_SLUG = "emergent-matter-sdm-cem-template"
NEW_SLUG = "emergent-matter-cem-thing"
THING = "thing"

#: Everywhere the package rename claims to reach. A leftover reference to
#: OLD_PACKAGE in one of these after `scripts/rename.py` runs means it does
#: not actually cover that location.
_PACKAGE_DIRS = ("src", "tests", "examples")
_PACKAGE_TOML_FILES = ("pyproject.toml", "cem.toml")

#: Everywhere the repo-slug rename, a SEPARATE token from the package name
#: above, claims to reach.
_SLUG_FILES = ("pyproject.toml", ".github/workflows/ci.yml")


def _copy_tree(dst: Path) -> None:
    """A working copy of the template, without the generated cruft the
    rename never touches and that would only slow the copy down."""
    shutil.copytree(
        ROOT,
        dst,
        ignore=shutil.ignore_patterns(
            ".git", ".venv", "__pycache__", ".mypy_cache", ".ruff_cache", ".pytest_cache", "output"
        ),
    )


def _run_rename(
    dst: Path, thing: str = THING, company: str | None = None
) -> subprocess.CompletedProcess:
    """`scripts/rename.py`, invoked as a real subprocess the way a person or
    `bootstrap.py` runs it, not by importing and calling its internals.

    `company` left None omits the flag entirely, so the default path is
    what every other test in this file exercises.
    """
    argv = [sys.executable, str(dst / "scripts" / "rename.py"), thing]
    if company is not None:
        argv += ["--company", company]
    return subprocess.run(
        argv,
        cwd=dst,
        capture_output=True,
        text=True,
    )


def _import_renamed(dst: Path) -> tuple[ModuleType, ModuleType, ModuleType]:
    """Import the renamed package fresh, isolated from any NEW_PACKAGE-named
    module a previous run of this file may have left cached."""
    for name in list(sys.modules):
        if name == NEW_PACKAGE or name.startswith(f"{NEW_PACKAGE}."):
            del sys.modules[name]
    sys.path.insert(0, str(dst / "src"))
    try:
        parameters = importlib.import_module(f"{NEW_PACKAGE}.parameters")
        assembly = importlib.import_module(f"{NEW_PACKAGE}.sdm.assembly")
        cli = importlib.import_module(f"{NEW_PACKAGE}.sdm.cli")
        return parameters, assembly, cli
    finally:
        sys.path.remove(str(dst / "src"))


def _renamed_copy(tmp_path: Path) -> tuple[Path, ModuleType, ModuleType, ModuleType]:
    dst = tmp_path / "renamed"
    _copy_tree(dst)
    result = _run_rename(dst)
    assert result.returncode == 0, (
        f"scripts/rename.py failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    parameters, assembly, cli = _import_renamed(dst)
    return dst, parameters, assembly, cli


def test_the_script_refuses_an_invalid_thing_name(tmp_path: Path) -> None:
    """`<thing>` becomes a Python package name (`<thing>_sdf`); fed
    something that can't be, the script has to say so and stop rather than
    write a tree nothing can import."""
    dst = tmp_path / "renamed"
    _copy_tree(dst)

    result = _run_rename(dst, thing="Not An Identifier!")

    assert result.returncode == 1
    assert result.stderr.startswith("error:")
    assert (dst / "src" / OLD_PACKAGE).is_dir(), "an invalid name must not touch the tree at all"


def test_the_default_company_keeps_the_emergentmatter_slug(tmp_path: Path) -> None:
    """Omitting --company has to leave EmergentMatter's own CEMs named the
    way the org already names them: the flag is for forks elsewhere, not a
    new step every EmergentMatter rename now has to remember."""
    dst = tmp_path / "renamed"
    _copy_tree(dst)

    assert _run_rename(dst).returncode == 0

    name = tomllib.loads((dst / "pyproject.toml").read_text())["project"]["name"]
    assert name == NEW_SLUG


def test_the_company_flag_reaches_every_file_the_slug_lives_in(tmp_path: Path) -> None:
    """The point of the flag: a fork outside EmergentMatter gets its own
    slug everywhere the rename writes one. Checking pyproject.toml alone
    would pass on a script that wrote the flag into [project].name and left
    ci.yml naming a company the forker has nothing to do with."""
    dst = tmp_path / "renamed"
    _copy_tree(dst)

    result = _run_rename(dst, company="acme-robotics")
    assert result.returncode == 0, result.stderr

    expected = f"acme-robotics-cem-{THING}"
    name = tomllib.loads((dst / "pyproject.toml").read_text())["project"]["name"]
    assert name == expected

    ci_text = (dst / ".github/workflows/ci.yml").read_text()
    assert expected in ci_text
    assert NEW_SLUG not in ci_text, (
        f"ci.yml still names {NEW_SLUG!r} after a rename that asked for a "
        "different company: --company does not reach every file the slug "
        "lives in. (The sibling checkout paths keep naming "
        "emergent-matter-sdm-core/-materials -- those are EmergentMatter's "
        "own repos and stay that whoever forks this.)"
    )


def test_the_script_refuses_an_invalid_company(tmp_path: Path) -> None:
    """A company that cannot be a slug segment has to be refused up front,
    the same as a bad <thing>: the alternative is a tree written with a
    repo name GitHub will not accept."""
    dst = tmp_path / "renamed"
    _copy_tree(dst)

    result = _run_rename(dst, company="Acme Robotics!")

    assert result.returncode == 1
    assert result.stderr.startswith("error:")
    assert (dst / "src" / OLD_PACKAGE).is_dir(), "an invalid company must not touch the tree at all"


def test_the_script_refuses_to_run_against_an_already_renamed_repo(tmp_path: Path) -> None:
    """A second run over an already-renamed tree is exactly the half-applied
    state a rename script must not produce: refuse it outright instead. The
    script removes itself on success (see the test above), so a literal
    second invocation of the same copy can't happen; this puts a fresh copy
    of the script back to exercise the guard on its own, the scenario it
    actually protects against (a rename script somehow present in a tree
    that has already been renamed)."""
    dst, *_ = _renamed_copy(tmp_path)
    shutil.copy(ROOT / "scripts" / "rename.py", dst / "scripts" / "rename.py")

    result = _run_rename(dst, thing="gear")

    assert result.returncode == 1
    assert result.stderr.startswith("error:")
    assert "already" in result.stderr


def test_the_rename_script_removes_itself_after_a_successful_run(tmp_path: Path) -> None:
    """A child CEM has no use for a script whose only job is the one-time
    move away from the template, and leaving it behind invites the second
    run the test above refuses anyway."""
    dst, *_ = _renamed_copy(tmp_path)
    assert not (dst / "scripts" / "rename.py").exists()


def test_the_rename_script_also_removes_its_own_test_file(tmp_path: Path) -> None:
    """This file's only job is driving `scripts/rename.py` against a
    throwaway copy. Once that script is gone, every test here would fail
    trying to invoke a file that no longer exists, so a child CEM's first
    `pytest` run would start red over a file with nothing left to drive."""
    dst, *_ = _renamed_copy(tmp_path)
    assert not (dst / "tests" / "test_rename_checklist.py").exists()


def test_no_reference_to_the_old_package_name_survives_the_rename(tmp_path: Path) -> None:
    """A leftover here names exactly the location `scripts/rename.py`
    does not actually cover."""
    dst, *_ = _renamed_copy(tmp_path)

    leftovers = []
    for sub in _PACKAGE_DIRS:
        for path in (dst / sub).rglob("*.py"):
            if OLD_PACKAGE in path.read_text():
                leftovers.append(str(path.relative_to(dst)))
    for name in _PACKAGE_TOML_FILES:
        if OLD_PACKAGE in (dst / name).read_text():
            leftovers.append(name)

    assert not leftovers, (
        f"{leftovers} still name {OLD_PACKAGE!r} after the rename: "
        "scripts/rename.py does not actually cover one of these locations"
    )


def test_no_reference_to_the_old_repo_slug_survives_the_rename(tmp_path: Path) -> None:
    """The repo-slug half of the rename. A leftover here names exactly the
    location that was skipped, for a token independent of the package name
    checked above."""
    dst, *_ = _renamed_copy(tmp_path)

    leftovers = [name for name in _SLUG_FILES if OLD_SLUG in (dst / name).read_text()]

    assert not leftovers, (
        f"{leftovers} still name the old repo slug {OLD_SLUG!r} after the "
        "rename: scripts/rename.py does not actually cover one of "
        "pyproject.toml's [project].name/[project.urls] or ci.yml's "
        "working-directory/checkout path/dist-dir/package-name"
    )


def test_ci_yml_package_name_still_matches_project_name_after_the_rename(
    tmp_path: Path,
) -> None:
    """The coupling that actually breaks a CI run rather than just reading
    wrong: `build`'s `verify-wheel` step needs `package-name` to equal
    `[project].name` exactly, because it reads pyproject.toml from a
    checkout `defaults.run.working-directory` doesn't reach."""
    dst, *_ = _renamed_copy(tmp_path)

    project_name = tomllib.loads((dst / "pyproject.toml").read_text())["project"]["name"]
    ci_text = (dst / ".github/workflows/ci.yml").read_text()
    match = re.search(r"package-name:\s*(\S+)", ci_text)
    assert match, "ci.yml no longer has a package-name: line for verify-wheel to read"

    assert match.group(1) == project_name, (
        f"ci.yml's package-name ({match.group(1)!r}) no longer matches "
        f"pyproject.toml's [project].name ({project_name!r}) after the "
        "rename: build's verify-wheel step would look for a wheel uv build "
        "never produces, and fail with nothing pointing back at a renamed "
        "URL as the cause"
    )


def test_manifest_and_dataclass_still_agree_after_the_rename(tmp_path: Path) -> None:
    """`test_manifest.py`'s own invariant, replayed against the renamed
    copy: cem.toml and the dataclass must still describe the same params,
    and cem.toml's entry_point must still resolve to a callable."""
    dst, parameters, _assembly, _cli = _renamed_copy(tmp_path)
    cem = tomllib.loads((dst / "cem.toml").read_text())["cem"]

    fields = {f.name for f in dataclasses.fields(parameters.WidgetParameters)}
    assert set(cem["params"]) == fields, (
        "cem.toml and the dataclass disagree right after a rename that "
        "changed no params: scripts/rename.py left one of them referring "
        "to the old package"
    )

    mod_name, _, attr = cem["entry_point"].partition(":")
    assert mod_name.startswith(NEW_PACKAGE), (
        f"cem.toml's entry_point still reads {cem['entry_point']!r}: "
        "scripts/rename.py does not cover cem.toml's entry_point, so a "
        "fresh CEM ships with a manifest naming a package that no longer "
        "exists"
    )
    entry = getattr(importlib.import_module(mod_name), attr, None)
    assert callable(entry), (
        f"cem.toml's entry_point {cem['entry_point']!r} does not resolve "
        "after the rename: the MCP server's read_cem would fail to build this CEM"
    )


def test_the_renamed_cli_still_satisfies_the_tool_contract(tmp_path: Path) -> None:
    """The substance of `scripts/check_contract.py`, run in-process against
    the renamed CLI: build, the emitted-name alias, an int-as-float value,
    an unknown param refused, and the recorded generator replaying to the
    same document. A rename that broke any of these would be invisible
    until a viewer, not a test, tried to drive the result."""
    dst, _parameters, _assembly, cli = _renamed_copy(tmp_path)

    out = dst / "out.sdm"
    assert cli.main(["--out", str(out), "--set", "outer_radius=14"]) == 0, (
        "the renamed CLI no longer builds: scripts/rename.py missed one of the imports under src/"
    )
    doc = json.loads(out.read_text())
    assert doc["params"]["outer_radius"]["value"] == 14

    out2 = dst / "out2.sdm"
    assert cli.main(["--out", str(out2), "--set", "bolt_holes=8.0"]) == 0
    assert json.loads(out2.read_text())["params"]["bolt_holes"]["value"] == 8

    with pytest.raises(SystemExit):
        cli.main(["--out", str(dst / "bad.sdm"), "--set", "definitely_not_a_param=1"])

    argv = doc["metadata"]["generator"]["argv"]
    replay = list(argv[1:])
    replayed_out = dst / "replay.sdm"
    replay[replay.index("--out") + 1] = str(replayed_out)
    assert cli.main(replay) == 0, "the recorded generator command does not re-run after the rename"
    before = {k: v["value"] for k, v in doc["params"].items()}
    after = {k: v["value"] for k, v in json.loads(replayed_out.read_text())["params"].items()}
    assert before == after, "replaying the recorded command changed the document after the rename"


def test_resetting_release_history_sets_the_version_and_empties_changelog_d(
    tmp_path: Path,
) -> None:
    """The release-history reset half of the script: [project].version goes
    back to 0.1.0, and the template's own fragments must not ship as a new
    CEM's first release notes."""
    dst, *_ = _renamed_copy(tmp_path)

    version = tomllib.loads((dst / "pyproject.toml").read_text())["project"]["version"]
    assert version == "0.1.0", "scripts/rename.py did not reset [project].version to 0.1.0"

    fragments = sorted((dst / "changelog.d").glob("*.md"))
    assert not fragments, f"changelog.d/ still has the template's own notes: {fragments}"
