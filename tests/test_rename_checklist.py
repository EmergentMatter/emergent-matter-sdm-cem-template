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
import difflib
import importlib
import json
import os
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
    dst: Path,
    thing: str = THING,
    company: str | None = None,
    env: dict[str, str] | None = None,
    offline: bool = False,
) -> subprocess.CompletedProcess:
    """`scripts/rename.py`, invoked as a real subprocess the way a person or
    `bootstrap.py` runs it, not by importing and calling its internals.

    `company` left None omits the flag entirely, so the default path is
    what every other test in this file exercises.
    """
    argv = [sys.executable, str(dst / "scripts" / "rename.py"), thing]
    if offline:
        argv.append("--offline")
    if company is not None:
        argv += ["--company", company]
    return subprocess.run(
        argv,
        cwd=dst,
        capture_output=True,
        text=True,
        env=env,
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


@pytest.fixture(scope="module")
def renamed_base(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """One offline-renamed copy, shared by the tests that only read it or copy
    it. Tests that change a copy call `_variant` first."""
    dst = tmp_path_factory.mktemp("base") / "renamed"
    _copy_tree(dst)
    result = _run_rename(dst, offline=True)
    assert result.returncode == 0, result.stderr
    return dst


def _variant(base: Path, tmp_path: Path) -> Path:
    dst = tmp_path / "variant"
    shutil.copytree(base, dst)
    return dst


def _pytest(dst: Path, *args: str) -> subprocess.CompletedProcess:
    """`dst`'s own tests, run as its owner would, with its `src` first on the
    path (the venv's editable install points at the template's own)."""
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *args],
        cwd=dst,
        capture_output=True,
        text=True,
        timeout=600,
        env={**os.environ, "PYTHONPATH": str(dst / "src")},
    )


def _passed(result: subprocess.CompletedProcess) -> None:
    assert result.returncode == 0, result.stdout[-2500:] + result.stderr[-1500:]
    assert " passed" in result.stdout


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

    fields = {f.name for f in dataclasses.fields(parameters.ThingParameters)}
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
        "after the rename: `sdm-sidecar cem show` would fail to read this CEM's entry point"
    )


def test_the_renamed_cli_still_satisfies_the_tool_contract(tmp_path: Path) -> None:
    """The substance of `scripts/check_contract.py`, run in-process against
    the renamed CLI: build, the emitted-name alias, an int-as-float value,
    an unknown param refused, and the recorded generator replaying to the
    same document. A rename that broke any of these would be invisible
    until a viewer, not a test, tried to drive the result."""
    dst, _parameters, _assembly, cli = _renamed_copy(tmp_path)

    out = dst / "out.sdm"
    assert cli.main(["--out", str(out), "--set", "length=50"]) == 0, (
        "the renamed CLI no longer builds: scripts/rename.py missed one of the imports under src/"
    )
    doc = json.loads(out.read_text())
    assert doc["params"]["length"]["value"] == 50

    out2 = dst / "out2.sdm"
    assert cli.main(["--out", str(out2), "--set", "d_height=25.0"]) == 0
    assert json.loads(out2.read_text())["params"]["height"]["value"] == 25

    with pytest.raises(SystemExit):
        cli.main(["--out", str(dst / "bad.sdm"), "--set", "definitely_not_a_param=1"])

    argv = doc["metadata"]["generator"]["argv"]
    assert argv[:4] == ["uv", "run", "--frozen", cli.SCRIPT], (
        f"the recorded generator does not name the renamed script: {argv[:4]}"
    )
    replayed_out = dst / "replay.sdm"
    replay = [*argv[4:], "--out", str(replayed_out)]
    assert cli.main(replay) == 0, "the recorded generator command does not re-run after the rename"
    before = {k: v["value"] for k, v in doc["params"].items()}
    after = {k: v["value"] for k, v in json.loads(replayed_out.read_text())["params"].items()}
    assert before == after, "replaying the recorded command changed the document after the rename"


def _widget_leftovers(tree: Path) -> tuple[int, list[str]]:
    """How many text files were scanned, and which of them still say `widget`
    in any case."""
    scanned = 0
    leftovers = []
    for path in sorted(tree.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        scanned += 1
        rel = str(path.relative_to(tree))
        if "widget" in text.lower():
            leftovers.append(rel)
    return scanned, leftovers


def test_an_offline_rename_leaves_nothing_named_widget(
    tmp_path: Path,
) -> None:
    dst = tmp_path / "renamed"
    _copy_tree(dst)

    result = _run_rename(dst, offline=True)
    assert result.returncode == 0, result.stderr

    scanned, leftovers = _widget_leftovers(dst)
    assert scanned >= 30, "the scan found almost nothing to look at"
    assert leftovers == []


def test_the_readme_is_replaced_by_the_projects_own(tmp_path: Path) -> None:
    dst = tmp_path / "renamed"
    _copy_tree(dst)
    template_readme = (dst / "README.md").read_text()
    assert (
        template_readme.startswith("<a id=")
        and "Template for a Software Defined" in template_readme
    )

    assert _run_rename(dst, thing="gear_box", offline=True).returncode == 0

    readme = (dst / "README.md").read_text()
    assert readme.startswith("# gear_box\n")
    assert "Made from the Emergent Matter CEM template." in readme
    assert "PYTHONPATH=src python -m gear_box_sdf.sdm.cli --out output/part.sdm" in readme
    assert "uv run gear_box-build" in readme
    assert "uv run pytest" in readme and "python -m pytest" in readme
    assert "## Tests" in readme, "ci.yml points at the README's Tests section"
    assert "CLAUDE.md" in readme and "docs/building-a-cem.md" in readme
    assert "Template for a Software Defined" not in readme
    assert len(readme.splitlines()) < 50


def test_a_missing_readme_stops_the_script_before_anything_changes(tmp_path: Path) -> None:
    dst = tmp_path / "renamed"
    _copy_tree(dst)
    (dst / "README.md").unlink()

    _refused_and_untouched(dst, "README.md")


def test_the_widget_scan_can_fail(tmp_path: Path) -> None:
    """The template itself is full of `widget`; the scan must say so."""
    dst = tmp_path / "unrenamed"
    _copy_tree(dst)

    _, leftovers = _widget_leftovers(dst)

    assert "cem.toml" in leftovers
    assert f"src/{OLD_PACKAGE}/parameters.py" in leftovers


def test_an_offline_rename_names_the_cem_and_the_lockfile_after_the_thing(
    tmp_path: Path,
) -> None:
    dst = tmp_path / "renamed"
    _copy_tree(dst)

    assert _run_rename(dst, thing="gear_box", offline=True).returncode == 0

    cem = tomllib.loads((dst / "cem.toml").read_text())["cem"]
    assert cem["name"] == "gear_box"
    assert cem["entry_point"] == "gear_box_sdf.sdm.assembly:build_gear_box_part"
    lock = tomllib.loads((dst / "uv.lock").read_text())
    names = [pkg["name"] for pkg in lock["package"]]
    assert "emergent-matter-cem-gear-box" in names
    assert _normalized_old_slug() not in names
    cli_text = (dst / "src" / "gear_box_sdf" / "sdm" / "cli.py").read_text()
    assert 'default="gear_box"' in cli_text
    assert "class GearBoxParameters" in (dst / "src" / "gear_box_sdf" / "parameters.py").read_text()


def _normalized_old_slug() -> str:
    return OLD_SLUG.replace("_", "-").lower()


def test_an_offline_rename_leaves_a_working_cem_whose_own_tests_pass(renamed_base: Path) -> None:
    _passed(_pytest(renamed_base, "tests"))
    assert not (renamed_base / "tests" / "test_rename_checklist.py").exists()


def _leads_with_uv(text: str, script: str, package: str) -> bool:
    """The documented build lines are both present and `uv run` comes first."""
    uv_line = f"uv run {script} --out"
    fallback = f"PYTHONPATH=src python -m {package}.sdm.cli --out"
    return uv_line in text and fallback in text and text.index(uv_line) < text.index(fallback)


def test_the_documented_build_lines_lead_with_uv_and_the_script_is_real(
    renamed_base: Path,
) -> None:
    """What this proves: CLAUDE.md and the README both give `uv run <script>`
    first and the `PYTHONPATH=src python -m` form as the fallback, and
    `<script>` is a real `[project.scripts]` entry of the renamed package's CLI.
    It does not run `uv` (that needs an index)."""
    scripts = tomllib.loads((renamed_base / "pyproject.toml").read_text())["project"]["scripts"]
    assert scripts == {f"{THING}-build": f"{NEW_PACKAGE}.sdm.cli:main"}
    for name in ("CLAUDE.md", "README.md"):
        text = (renamed_base / name).read_text()
        assert _leads_with_uv(text, f"{THING}-build", NEW_PACKAGE), name


def test_the_ordering_check_can_fail() -> None:
    uv_line = "uv run thing-build --out"
    fallback = "PYTHONPATH=src python -m thing_sdf.sdm.cli --out"
    assert _leads_with_uv(f"{uv_line} x\n{fallback} y", "thing-build", "thing_sdf")
    assert not _leads_with_uv(f"{fallback} y\n{uv_line} x", "thing-build", "thing_sdf")
    assert not _leads_with_uv(f"{uv_line} x", "thing-build", "thing_sdf")


def test_the_fallback_build_line_runs_without_uv_on_the_path(renamed_base: Path) -> None:
    """What this proves: the fallback line's module runs under an interpreter
    that already has the dependencies, with `src` on the path and no `uv` on
    `PATH`. The interpreter here is the test venv's, which has every
    dependency; the line is not shown to work on an interpreter without them."""
    out = renamed_base / "fallback.sdm"
    result = subprocess.run(
        [sys.executable, "-m", f"{NEW_PACKAGE}.sdm.cli", "--out", str(out)],
        cwd=renamed_base,
        capture_output=True,
        text=True,
        env={"PATH": "/nonexistent", "PYTHONPATH": str(renamed_base / "src")},
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(out.read_text())["name"] == THING


def test_the_fallback_build_line_needs_src_on_the_path(renamed_base: Path) -> None:
    """Without `PYTHONPATH=src` the renamed package is not importable, so the
    line's prefix is not decoration."""
    result = subprocess.run(
        [sys.executable, "-m", f"{NEW_PACKAGE}.sdm.cli", "--out", str(renamed_base / "x.sdm")],
        cwd=renamed_base,
        capture_output=True,
        text=True,
        env={"PATH": "/nonexistent"},
    )

    assert result.returncode != 0


@pytest.mark.parametrize("bad", ["Not-A-Thing", "1gear", "gear sdf", "../x"])
def test_an_offline_rename_refuses_a_bad_thing_and_changes_nothing(
    tmp_path: Path, bad: str
) -> None:
    dst = tmp_path / "renamed"
    _copy_tree(dst)
    before = _snapshot(dst)

    result = _run_rename(dst, thing=bad, offline=True)

    assert result.returncode == 1
    assert result.stderr.startswith("error:")
    assert _snapshot(dst) == before


def test_the_offline_flag_does_not_change_what_is_written(tmp_path: Path) -> None:
    plain = tmp_path / "plain"
    offline = tmp_path / "offline"
    _copy_tree(plain)
    _copy_tree(offline)

    assert _run_rename(plain).returncode == 0
    assert _run_rename(offline, offline=True).returncode == 0

    assert _relative_snapshot(plain) == _relative_snapshot(offline)


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


def _root_lock_entry(lock: Path) -> dict:
    packages = tomllib.loads(lock.read_text())["package"]
    roots = [p for p in packages if p.get("source") == {"editable": "."}]
    assert len(roots) == 1
    return roots[0]


def _template_version() -> str:
    """The version the template carries now. A release bumps it, so tests that
    mention the lock's old version read it instead of spelling it out."""
    return tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]


def test_the_lockfile_root_entry_follows_the_rename(tmp_path: Path) -> None:
    """`uv sync --locked`, the first step of every CI job, fails when
    `uv.lock` still names the package the rename replaced, so the lock's root
    entry has to move with `[project].name`."""
    dst = tmp_path / "renamed"
    _copy_tree(dst)
    old_lock = (dst / "uv.lock").read_text()
    old_version = _template_version()

    assert _run_rename(dst).returncode == 0

    project = tomllib.loads((dst / "pyproject.toml").read_text())["project"]
    entry = _root_lock_entry(dst / "uv.lock")
    assert entry["name"] == NEW_SLUG
    assert entry["version"] == project["version"]
    new_lock = (dst / "uv.lock").read_text()
    changed = [
        line
        for line in difflib.unified_diff(
            old_lock.splitlines(), new_lock.splitlines(), lineterm="", n=0
        )
        if line[:1] in "+-" and not line.startswith(("+++", "---"))
    ]
    assert changed == [
        f'-name = "{OLD_SLUG}"',
        f'-version = "{old_version}"',
        f'+name = "{NEW_SLUG}"',
        f'+version = "{project["version"]}"',
    ]


def test_the_lockfile_uses_the_normalised_name_for_an_underscored_thing(tmp_path: Path) -> None:
    dst = tmp_path / "renamed"
    _copy_tree(dst)

    assert _run_rename(dst, thing="my_chair").returncode == 0

    assert _root_lock_entry(dst / "uv.lock")["name"] == "emergent-matter-cem-my-chair"
    assert tomllib.loads((dst / "pyproject.toml").read_text())["project"]["name"] == (
        "emergent-matter-cem-my_chair"
    )


def _entry_block(lock: str) -> str:
    start = lock.index("[[package]]\nname = " + f'"{OLD_SLUG}"')
    end = lock.index("\n[[package]]", start + 1)
    return lock[start:end]


def _damage(lock: str, kind: str) -> str:
    block = _entry_block(lock)
    if kind == "missing":
        return lock.replace(block + "\n", "")
    if kind == "twice":
        return lock + "\n" + block + "\n"
    if kind == "version line gone":
        damaged = lock.replace(block, block.replace(f'version = "{_template_version()}"\n', "", 1))
        assert damaged != lock, "the damage changed nothing"
        return damaged
    if kind == "extra key":
        return lock.replace(block, block.replace("source =", 'extra = "x"\nsource =', 1))
    raise AssertionError(kind)


@pytest.mark.parametrize("kind", ["missing", "twice", "version line gone", "extra key"])
def test_a_lockfile_the_script_cannot_rewrite_stops_it_before_anything_changes(
    tmp_path: Path, kind: str
) -> None:
    dst = tmp_path / "renamed"
    _copy_tree(dst)
    (dst / "uv.lock").write_bytes(_damage((dst / "uv.lock").read_text(), kind).encode())
    before = {p: p.read_bytes() for p in dst.rglob("*") if p.is_file()}

    result = _run_rename(dst)

    assert result.returncode == 1
    assert "uv.lock" in result.stderr
    assert {p: p.read_bytes() for p in dst.rglob("*") if p.is_file()} == before


def test_a_look_alike_package_in_the_lock_is_left_alone(tmp_path: Path) -> None:
    """The entry is found by its name and by being the editable root, so a
    package with a longer name, or one with the same name from an index, is not
    the root and is not rewritten."""
    dst = tmp_path / "renamed"
    _copy_tree(dst)
    lock = (dst / "uv.lock").read_text()
    extra = (
        f'\n[[package]]\nname = "{OLD_SLUG}-extras"\nversion = "1.0.0"\n'
        f'source = {{ editable = "." }}\n\n[[package]]\nname = "{OLD_SLUG}"\n'
        'version = "2.0.0"\nsource = { registry = "https://example.invalid/simple" }\n'
    )
    (dst / "uv.lock").write_text(lock + extra)

    assert _run_rename(dst).returncode == 0

    after = (dst / "uv.lock").read_text()
    assert f'name = "{OLD_SLUG}-extras"' in after
    assert f'name = "{OLD_SLUG}"\nversion = "2.0.0"' in after
    assert f'name = "{NEW_SLUG}"' in after


def _uv() -> str | None:
    uv = shutil.which("uv")
    if uv is None and os.environ.get("CI"):
        pytest.fail("uv is required in CI to check the renamed lockfile")
    if uv is None:
        pytest.skip("uv is not on PATH")
    return uv


@pytest.mark.parametrize(
    ("thing", "company"), [(THING, None), ("my_chair", None), ("ab", "my-co-2")]
)
def test_uv_accepts_the_renamed_lockfile_as_it_stands(
    tmp_path: Path, thing: str, company: str | None
) -> None:
    """The oracle is `uv` itself: a lock that `uv lock --check` accepts is one
    `uv sync --locked` accepts."""
    uv = _uv()
    dst = tmp_path / "renamed"
    _copy_tree(dst)
    assert _run_rename(dst, thing=thing, company=company).returncode == 0

    result = subprocess.run([uv, "lock", "--check"], cwd=dst, capture_output=True, text=True)

    assert result.returncode == 0, result.stderr


def test_the_oracle_can_fail(tmp_path: Path) -> None:
    """Put the template's own lock back after the rename: `uv lock --check`
    must object, or the test above proves nothing."""
    uv = _uv()
    dst = tmp_path / "renamed"
    _copy_tree(dst)
    original = (dst / "uv.lock").read_bytes()
    assert _run_rename(dst).returncode == 0
    (dst / "uv.lock").write_bytes(original)

    result = subprocess.run([uv, "lock", "--check"], cwd=dst, capture_output=True, text=True)

    assert result.returncode != 0


#: Every file the rename rewrites that carries a non-ASCII `─` ruler.
NAME_ONLY = ("scripts/bootstrap.py", "scripts/doctor.py", "CLAUDE.md")

_RULED_FILES = (
    "pyproject.toml",
    "cem.toml",
    f"src/{OLD_PACKAGE}/parameters.py",
    "tests/test_build.py",
)


def test_files_with_windows_line_endings_keep_them_and_their_encoding(tmp_path: Path) -> None:
    """A Windows checkout may have CRLF line endings, and Python's default
    text encoding there is the locale's, not UTF-8. Run under an ASCII
    locale, every rewritten file has to come back CRLF with its `─` rulers
    intact, and the version and package-name, whose regexes must see past
    the `\\r`, still have to be rewritten. That includes the README the
    script writes whole, the name-only files, and the files only the bare
    word `widget` reaches."""
    dst = tmp_path / "renamed"
    _copy_tree(dst)
    rewritten = [
        dst / "pyproject.toml",
        dst / "cem.toml",
        dst / "README.md",
        dst / ".github" / "workflows" / "ci.yml",
        dst / "uv.lock",
        *(dst / name for name in NAME_ONLY),
        *(
            p
            for sub in _PACKAGE_DIRS
            for p in (dst / sub).rglob("*.py")
            if "widget" in p.read_text().lower() and p.name != "test_rename_checklist.py"
        ),
    ]
    only_bare = [
        p
        for p in rewritten
        if p.suffix == ".py" and OLD_PACKAGE not in p.read_text() and "widget" in p.read_text()
    ]
    assert only_bare, "no file is reached by the bare word alone; update the test"
    for path in rewritten:
        path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
    for name in _RULED_FILES:
        assert "─" in (dst / name).read_text(encoding="utf-8"), (
            f"{name} has no ruler; update the test"
        )
    ascii_locale = {**os.environ, "LC_ALL": "C", "PYTHONUTF8": "0", "PYTHONCOERCECLOCALE": "0"}

    result = _run_rename(dst, env=ascii_locale)
    assert result.returncode == 0, result.stderr

    for path in rewritten:
        path = Path(str(path).replace(f"src/{OLD_PACKAGE}", f"src/{NEW_PACKAGE}"))
        after = path.read_bytes()
        assert b"\n" not in after.replace(b"\r\n", b""), f"{path} lost its CRLF line endings"
        assert OLD_PACKAGE.encode() not in after, f"{path} was not rewritten"
        if path.suffix == ".py":
            assert b"widget" not in after.lower(), f"{path} still names widget"
    assert (dst / "README.md").read_bytes().startswith(b"# thing\r\n")
    for name in _RULED_FILES:
        name = name.replace(OLD_PACKAGE, NEW_PACKAGE)
        assert "─" in (dst / name).read_bytes().decode("utf-8"), f"{name} lost its rulers"
    project = tomllib.loads((dst / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert project["version"] == "0.1.0"
    ci_text = (dst / ".github" / "workflows" / "ci.yml").read_bytes().decode("utf-8")
    assert f"          package-name: {NEW_SLUG}\r\n" in ci_text
    assert _root_lock_entry(dst / "uv.lock")["name"] == NEW_SLUG


def test_an_lf_readme_is_replaced_by_an_lf_readme(renamed_base: Path) -> None:
    """The control for the CRLF case: the line endings follow the file."""
    assert b"\r" not in (renamed_base / "README.md").read_bytes()


def _snapshot(tree: Path) -> dict[Path, bytes]:
    return {p: p.read_bytes() for p in tree.rglob("*") if p.is_file()}


def _refused_and_untouched(dst: Path, fragment: str) -> None:
    """Run the rename and require a refusal naming `fragment` that leaves
    every file byte-identical, `src/` unmoved and the script still present."""
    before = _snapshot(dst)

    result = _run_rename(dst)

    assert result.returncode == 1
    assert fragment in result.stderr
    assert _snapshot(dst) == before
    assert (dst / "src" / OLD_PACKAGE).is_dir()
    assert not (dst / "src" / NEW_PACKAGE).exists()


def _edit(dst: Path, relative: str, old: str, new: str) -> None:
    path = dst / relative
    text = path.read_text()
    assert old in text, f"{relative} no longer contains {old!r}; update the test"
    path.write_text(text.replace(old, new, 1))


@pytest.mark.parametrize(
    ("old", "new"),
    [
        (f'name = "{OLD_SLUG}"', f'title = "{OLD_SLUG}"'),
        (f'name = "{OLD_SLUG}"', 'name = "someone-elses-package"'),
    ],
    ids=["name line gone", "name is not the template slug"],
)
def test_a_bad_project_name_stops_the_script_before_anything_changes(
    tmp_path: Path, old: str, new: str
) -> None:
    dst = tmp_path / "renamed"
    _copy_tree(dst)
    _edit(dst, "pyproject.toml", old, new)

    _refused_and_untouched(dst, "[project].name")


@pytest.mark.parametrize("kind", ["missing", "twice", "other value"])
def test_a_bad_ci_package_name_stops_the_script_before_anything_changes(
    tmp_path: Path, kind: str
) -> None:
    dst = tmp_path / "renamed"
    _copy_tree(dst)
    line = f"          package-name: {OLD_SLUG}\n"
    ci = dst / ".github" / "workflows" / "ci.yml"
    text = ci.read_text()
    assert line in text
    damaged = {
        "missing": text.replace(line, ""),
        "twice": text.replace(line, line + line),
        "other value": text.replace(line, "          package-name: something-else\n"),
    }[kind]
    ci.write_text(damaged)

    _refused_and_untouched(dst, "package-name")


def test_an_existing_destination_package_stops_the_script_before_anything_changes(
    tmp_path: Path,
) -> None:
    dst = tmp_path / "renamed"
    _copy_tree(dst)
    (dst / "src" / NEW_PACKAGE).mkdir()
    (dst / "src" / NEW_PACKAGE / "keep.txt").write_text("mine")

    before = _snapshot(dst)
    result = _run_rename(dst)

    assert result.returncode == 1
    assert f"src/{NEW_PACKAGE}/ already exists" in result.stderr
    assert _snapshot(dst) == before
    assert (dst / "src" / OLD_PACKAGE).is_dir()


def test_a_source_file_that_cannot_be_read_stops_the_script_before_anything_changes(
    tmp_path: Path,
) -> None:
    dst = tmp_path / "renamed"
    _copy_tree(dst)
    (dst / "tests" / "bad_bytes.py").write_bytes(b"\xff\xfe not utf-8 \x80")

    before = _snapshot(dst)
    result = _run_rename(dst)

    assert result.returncode == 1
    assert result.stderr.startswith("error:")
    assert _snapshot(dst) == before
    assert (dst / "src" / OLD_PACKAGE).is_dir()


def test_a_successful_rename_leaves_no_temporary_files_behind(tmp_path: Path) -> None:
    dst = tmp_path / "renamed"
    _copy_tree(dst)

    assert _run_rename(dst).returncode == 0

    assert not list(dst.rglob("*.rename-tmp"))


#: Runs `scripts/rename.py`'s main() with one step made to fail the way a
#: disk error would: the uv.lock write, or the src/ move.
_FAILING_DRIVER = """
import importlib.util
import sys
from pathlib import Path

script, fail, argv = sys.argv[1], sys.argv[2], sys.argv[3:]
spec = importlib.util.spec_from_file_location("rename", script)
rename = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rename)
if fail == "uv.lock":
    write = rename._write_atomic

    def _write_atomic(path, text):
        if path.name == "uv.lock":
            raise OSError("injected: disk full")
        write(path, text)

    rename._write_atomic = _write_atomic
else:

    def rename_path(self, target):
        raise OSError("injected: cannot move")

    Path.rename = rename_path
raise SystemExit(rename.main(argv))
"""


def _run_failing_rename(dst: Path, fail: str, thing: str) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            "-c",
            _FAILING_DRIVER,
            str(dst / "scripts" / "rename.py"),
            fail,
            thing,
        ],
        cwd=dst,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "injected" in result.stderr
    assert (dst / "src" / OLD_PACKAGE).is_dir()


def _relative_snapshot(tree: Path) -> dict[Path, bytes]:
    return {p.relative_to(tree): b for p, b in _snapshot(tree).items()}


@pytest.mark.parametrize("thing", [THING, "my_widget"])
@pytest.mark.parametrize("fail", ["uv.lock", "src move"])
def test_a_rerun_after_a_failed_write_finishes_the_rename(
    tmp_path: Path, fail: str, thing: str
) -> None:
    """A disk error part-way through the writes leaves src/ unmoved, so the
    script accepts a rerun; that rerun has to finish with the tree a single
    clean run produces. `my_widget` contains the template's `widget_sdf` and
    `widget-build` once renamed, so a replacement that is not idempotent
    would rename them a second time."""
    clean = tmp_path / "clean"
    _copy_tree(clean)
    assert _run_rename(clean, thing=thing).returncode == 0
    dst = tmp_path / "renamed"
    _copy_tree(dst)

    _run_failing_rename(dst, fail, thing)
    result = _run_rename(dst, thing=thing)

    assert result.returncode == 0, result.stderr
    assert _relative_snapshot(dst) == _relative_snapshot(clean)


def test_a_rerun_with_a_different_name_after_a_failed_write_is_refused(tmp_path: Path) -> None:
    dst = tmp_path / "renamed"
    _copy_tree(dst)
    _run_failing_rename(dst, "uv.lock", THING)
    before = _snapshot(dst)

    result = _run_rename(dst, thing="gear")

    assert result.returncode == 1
    assert "[project].name" in result.stderr
    assert _snapshot(dst) == before


# ── what the renamed repo points at, and what it can lose ─────────────────


def _doc_problems(root: Path) -> tuple[int, list[str]]:
    """How many `docs/*.md` pointers and quoted-section pointers the renamed
    repo's own docs carry, and which of them lead nowhere."""
    files = [
        root / "CLAUDE.md",
        root / "README.md",
        root / "docs" / "traps.md",
        root / "docs" / "building-a-cem.md",
        root / "src" / NEW_PACKAGE / "__init__.py",
    ]
    found = 0
    problems = []
    for path in files:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        for m in re.finditer(r"(?<![\w/.-])docs/[\w-]+\.md", text):
            found += 1
            if not (root / m.group()).is_file():
                problems.append(f"{path.name}: {m.group()} does not exist")
        for m in re.finditer(r'"([^"]+)" section of\s+\[?(docs/[\w-]+\.md)', text):
            found += 1
            target = root / m.group(2)
            headings = (
                [line.lstrip("# ").strip() for line in target.read_text().splitlines()]
                if target.is_file()
                else []
            )
            if m.group(1) not in headings:
                problems.append(f"{path.name}: no section {m.group(1)!r} in {m.group(2)}")
    return found, problems


def test_every_section_the_renamed_docs_point_to_exists(renamed_base: Path) -> None:
    found, problems = _doc_problems(renamed_base)

    assert found >= 6
    assert problems == []
    claude = (renamed_base / "CLAUDE.md").read_text()
    assert "README's" not in claude and "Read `README.md` first" not in claude


def test_a_pointer_to_a_missing_doc_or_section_is_reported(
    renamed_base: Path, tmp_path: Path
) -> None:
    dst = _variant(renamed_base, tmp_path)
    doc = dst / "docs" / "building-a-cem.md"
    doc.write_text(doc.read_text().replace("### Derived values", "### Derived things"))
    _, problems = _doc_problems(dst)
    assert any("Derived values" in p for p in problems)

    doc.unlink()
    _, problems = _doc_problems(dst)
    assert any("does not exist" in p for p in problems)


def test_the_renamed_suite_survives_deleting_the_examples(
    renamed_base: Path, tmp_path: Path
) -> None:
    """The examples say "delete this directory when you start your own CEM",
    and the CEM's own manifest checks must not go with them."""
    dst = _variant(renamed_base, tmp_path)
    example_tests = sorted((dst / "tests").glob("test_example_*.py"))
    assert len(example_tests) == 2
    shutil.rmtree(dst / "examples")
    for path in example_tests:
        path.unlink()

    result = _pytest(dst)

    _passed(result)
    assert "test_manifest.py" in "".join(p.name for p in (dst / "tests").iterdir())


def _plain_box(dst: Path) -> None:
    """Cut the renamed CEM down to a box with no derived value and no
    constraint, the smallest real CEM."""
    package = dst / "src" / NEW_PACKAGE
    (package / "parameters.py").write_text(
        "from __future__ import annotations\n\n"
        "from dataclasses import dataclass\n\n\n"
        "@dataclass(frozen=True)\n"
        "class ThingParameters:\n"
        "    d_length: float = 40.0\n"
        "    d_width: float = 30.0\n"
        "    d_height: float = 20.0\n"
        "    d_voxel_size_mm: float = 0.25\n\n"
        "    def bbox(self):\n"
        "        v = self.d_voxel_size_mm\n"
        "        return (\n"
        "            [-self.d_length / 2 - v, -self.d_width / 2 - v, -v],\n"
        "            [self.d_length / 2 + v, self.d_width / 2 + v, self.d_height + v],\n"
        "        )\n\n"
        "    def validate(self):\n"
        "        return []\n"
    )
    toml = (dst / "cem.toml").read_text()
    toml = re.sub(r"\[cem\.params\.d_edge_radius\].*?(?=\n\[)", "", toml, flags=re.S)
    toml = re.sub(r"\[\[cem\.constraints\]\].*?(?=\n\[\[cem\.objectives)", "", toml, flags=re.S)
    (dst / "cem.toml").write_text(toml)
    assembly = package / "sdm" / "assembly.py"
    assembly.write_text(
        "\n".join(
            line for line in assembly.read_text().splitlines() if '"d_edge_radius"' not in line
        )
        + "\n"
    )
    trees = package / "sdm" / "trees_body.py"
    trees.write_text(trees.read_text().replace("p.d_edge_radius", "0.0"))


def test_the_manifest_checks_pass_for_a_plain_box_with_no_derived_value_and_no_constraint(
    renamed_base: Path, tmp_path: Path
) -> None:
    dst = _variant(renamed_base, tmp_path)
    _plain_box(dst)
    cem = tomllib.loads((dst / "cem.toml").read_text())["cem"]
    assert sorted(cem["params"]) == ["d_height", "d_length", "d_voxel_size_mm", "d_width"]
    assert "constraints" not in cem

    _passed(_pytest(dst, "tests/test_manifest.py"))


def test_the_manifest_checks_pass_after_changing_a_default_in_both_files(
    renamed_base: Path, tmp_path: Path
) -> None:
    dst = _variant(renamed_base, tmp_path)
    params = dst / "src" / NEW_PACKAGE / "parameters.py"
    params.write_text(
        params.read_text().replace("d_length: float = 40.0", "d_length: float = 50.0")
    )
    toml = dst / "cem.toml"
    toml.write_text(toml.read_text().replace("default = 40.0", "default = 50.0", 1))

    _passed(_pytest(dst, "tests/test_manifest.py"))


def test_the_manifest_checks_fail_after_changing_a_default_in_one_file_only(
    renamed_base: Path, tmp_path: Path
) -> None:
    dst = _variant(renamed_base, tmp_path)
    toml = dst / "cem.toml"
    toml.write_text(toml.read_text().replace("default = 40.0", "default = 50.0", 1))

    result = _pytest(dst, "tests/test_manifest.py")

    assert result.returncode != 0
    assert "defaults_match_the_dataclass" in result.stdout


# ── a thing named like an example ─────────────────────────────────────────


@pytest.mark.parametrize(("thing", "other"), [("plate", "bushing"), ("bushing", "plate")])
def test_a_thing_named_like_an_example_removes_only_that_example(
    tmp_path: Path, renamed_base: Path, thing: str, other: str
) -> None:
    """No project name is refused: the example whose package the new name
    would collide with, and its test file, go; the other example stays."""
    assert (renamed_base / "examples" / f"{thing}_sdf").is_dir(), "the control keeps both"
    assert (renamed_base / "tests" / f"test_example_{thing}.py").is_file()
    dst = tmp_path / "renamed"
    _copy_tree(dst)

    result = _run_rename(dst, thing=thing, offline=True)

    assert result.returncode == 0, result.stderr
    assert not (dst / "examples" / f"{thing}_sdf").exists()
    assert not (dst / "tests" / f"test_example_{thing}.py").exists()
    assert (dst / "examples" / f"{other}_sdf").is_dir()
    assert (dst / "tests" / f"test_example_{other}.py").is_file()
    assert (dst / "src" / f"{thing}_sdf" / "parameters.py").is_file()
    _passed(_pytest(dst))


# ── the thing's shape, the flag's wording, what the script prints ─────────


@pytest.mark.parametrize("bad", ["gear_", "gear__box", "_gear", "gear-box", "Gear"])
def test_a_thing_with_a_stray_separator_is_refused_and_changes_nothing(
    tmp_path: Path, bad: str
) -> None:
    dst = tmp_path / "renamed"
    _copy_tree(dst)
    before = _snapshot(dst)

    result = _run_rename(dst, thing=bad, offline=True)

    assert result.returncode == 1
    assert result.stderr.startswith("error:")
    assert _snapshot(dst) == before


@pytest.mark.parametrize("thing", ["x_cem", "p_1", "a1_b2"])
def test_a_thing_that_is_snake_case_with_digits_is_accepted(tmp_path: Path, thing: str) -> None:
    dst = tmp_path / "renamed"
    _copy_tree(dst)

    assert _run_rename(dst, thing=thing, offline=True).returncode == 0
    assert (dst / "src" / f"{thing}_sdf").is_dir()


def test_offline_is_described_in_general_terms() -> None:
    script = ROOT / "scripts" / "rename.py"
    result = subprocess.run(
        [sys.executable, str(script), "--help"], capture_output=True, text=True, timeout=60
    )

    assert result.returncode == 0
    assert "never uses the network or uv" in " ".join(result.stdout.split())
    assert "broker" not in script.read_text().lower()


def test_the_script_prints_where_to_go_next(tmp_path: Path) -> None:
    dst = tmp_path / "renamed"
    _copy_tree(dst)

    result = _run_rename(dst, offline=True)

    assert "docs/building-a-cem.md" in result.stdout
    for step in ("release control", "parameters.py", "trees_*.py", "cem.toml", "test_build.py"):
        assert step in result.stdout
    assert (dst / "docs" / "building-a-cem.md").is_file()


# ── the guidance the coding agent reads ───────────────────────────────────


def _agent_rules_missing(text: str, package: str, script: str) -> list[str]:
    """The rules `CLAUDE.md` must carry for an agent that has no `uv` and no
    network, with the renamed names filled in. Returns the ones it lacks."""
    flat = " ".join(text.split())
    rules = {
        "own package": (
            f"this project's own package, the only directory under `src/`: `src/{package}/`"
        ),
        "no second package": "Never create a second package under `src/`",
        "build into output": f"uv run {script} --out output/part.sdm",
        "direct fallback": f"PYTHONPATH=src python -m {package}.sdm.cli --out output/part.sdm",
        "no uv, deps installed": (
            "If `uv` is not on the machine, the dependencies are already installed"
        ),
        "no installing": "Never try to install anything or fetch `uv`",
        "no hand-written sdm": "Never write a `.sdm` by hand or from a script of your own",
        "report failures": "stop and report the failure with its output",
        "no git commands": (
            "Where there is no `uv`, the work is saved for you each turn: do not run "
            "`git add`, `git commit` or `git config`"
        ),
        "commit when asked locally": "On a local machine, commit only when asked",
        "no sidecar or viewer": "`sdm-sidecar` and the viewer are never needed to build or test",
    }
    return [name for name, phrase in rules.items() if phrase not in flat]


def test_a_renamed_claude_md_carries_the_agent_rules_with_the_new_names(
    renamed_base: Path,
) -> None:
    text = (renamed_base / "CLAUDE.md").read_text()

    assert _agent_rules_missing(text, NEW_PACKAGE, f"{THING}-build") == []
    assert "widget" not in text.lower()


def test_the_agent_rules_check_can_fail(renamed_base: Path) -> None:
    text = (renamed_base / "CLAUDE.md").read_text()

    assert _agent_rules_missing(text, "other_sdf", "other-build") != []
    without = text.replace("`git add`, `git commit` or `git config`", "git")
    assert _agent_rules_missing(without, NEW_PACKAGE, f"{THING}-build") == ["no git commands"]
    # The template's own text names the template's package, not the renamed one.
    stale = (ROOT / "CLAUDE.md").read_text()
    assert "own package" in _agent_rules_missing(stale, NEW_PACKAGE, f"{THING}-build")


def test_the_template_claude_md_carries_the_same_rules_under_the_template_names() -> None:
    text = (ROOT / "CLAUDE.md").read_text()

    assert _agent_rules_missing(text, OLD_PACKAGE, "widget-build") == []


def _bare_pytest_lines(text: str) -> list[int]:
    """Offsets of each `uv run pytest` with no `python -m pytest` within a
    few lines of it: the fallback has to sit beside the uv form."""
    return [
        m.start()
        for m in re.finditer(r"uv run pytest", text)
        if "python -m pytest" not in text[max(0, m.start() - 300) : m.end() + 300]
    ]


def test_every_uv_run_pytest_has_the_fallback_beside_it(renamed_base: Path) -> None:
    seen = 0
    for name in ("CLAUDE.md", "README.md"):
        text = (renamed_base / name).read_text()
        seen += len(re.findall(r"uv run pytest", text))
        assert _bare_pytest_lines(text) == [], name
    assert seen >= 3


def test_the_pytest_fallback_check_can_fail() -> None:
    assert _bare_pytest_lines("```bash\nuv run pytest\n```\n" + "x" * 400) != []
    assert _bare_pytest_lines("uv run pytest, or python -m pytest without uv") == []


def test_the_notes_that_assume_uv_say_they_are_for_a_local_machine(renamed_base: Path) -> None:
    for name in ("docs/traps.md", "docs/building-a-cem.md"):
        text = " ".join((renamed_base / name).read_text().split())
        assert "do not install" in text and "python -m" in text, name


def test_a_renamed_copys_built_part_ships_every_param_free_with_bounds(
    renamed_base: Path,
) -> None:
    """The Scene pane builds its controls from free params only; read the
    `.sdm` the renamed package's CLI writes, the way the viewer does."""
    out = renamed_base / "output" / "free.sdm"
    result = subprocess.run(
        [sys.executable, "-m", f"{NEW_PACKAGE}.sdm.cli", "--out", str(out), "--set", "length=50"],
        cwd=renamed_base,
        capture_output=True,
        text=True,
        env={"PATH": "/nonexistent", "PYTHONPATH": str(renamed_base / "src")},
    )
    assert result.returncode == 0, result.stderr

    params = json.loads(out.read_text())["params"]
    assert sorted(params) == ["edge_radius", "height", "length", "width"]
    assert params["length"]["value"] == 50
    assert [n for n, p in params.items() if p["free"] is not True or not p["bounds"]] == []
