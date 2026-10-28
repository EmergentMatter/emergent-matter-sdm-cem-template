#!/usr/bin/env python3
"""Turn this template into a real CEM.

    python3 scripts/rename.py <thing> [--company <company-name>]

Performs README's "Use it" step 1, mechanically: renames the package
directory and fixes every import and manifest reference that names it,
renames the repo slug everywhere `pyproject.toml` and `ci.yml` carry it,
renames the console-script key, renames the root package in `uv.lock` (so
`uv sync --locked` still passes), and resets the release history (step 2).

WHY A SCRIPT AND NOT A PARAGRAPH. This rename procedure used to be prose in
README, and every review round found another location it forgot: cem.toml's
entry_point, the imports in tests/, examples/ (it sits on pytest's
pythonpath too), then the repo slug pyproject.toml and ci.yml separately
carry. Prose that has to be kept in step with the code by a human re-reading
it stays wrong for exactly as long as nobody notices. This script IS the
procedure, so there is one copy instead of three, and
tests/test_rename_checklist.py drives it against a throwaway copy the same
way a person drives it for real.

Stdlib only, and it must stay that way: this runs before the environment
exists, on whatever Python the user has, so nothing here may use syntax
newer than 3.8. No `tomllib` (3.11+), no third-party imports -- see
bootstrap.py and doctor.py for the same constraint and the same reason.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

OLD_PACKAGE = "widget_sdf"
OLD_SCRIPT = "widget-build"
OLD_SLUG = "emergent-matter-sdm-cem-template"

#: The organization half of a renamed CEM's repo slug. EmergentMatter's
#: own CEMs are `emergent-matter-cem-<thing>`, so that is the default; a
#: fork of this template anywhere else passes --company and gets its own.
#: The template is a template, so the slug it writes cannot be one company's
#: name baked in past the point anyone can change it.
DEFAULT_COMPANY = "emergent-matter"

#: The version a renamed CEM starts at, in `pyproject.toml` and in `uv.lock`.
FIRST_VERSION = "0.1.0"

#: Directories whose *.py files get the package-name rename. examples/ sits
#: on pyproject.toml's pytest pythonpath and is exercised by its own test,
#: on the same footing as src/ and tests/.
PACKAGE_DIRS = ("src", "tests", "examples")


def _fail(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)


def _valid_thing(thing: str) -> bool:
    """`thing` becomes `<thing>_sdf` (a Python package, so it has to be a
    valid identifier), `<thing>-build` (a console-script key), and
    `<company>-cem-<thing>` (a repo slug). Lowercase snake_case
    satisfies a Python identifier and reads fine hyphen-joined in the other
    two, so it is the one shape that works everywhere it gets used."""
    return bool(re.fullmatch(r"[a-z][a-z0-9_]*", thing)) and f"{thing}_sdf".isidentifier()


def _valid_company(company: str) -> bool:
    """`company` is the organization half of the repo slug
    (`<company>-cem-<thing>`), so it has to read as slug segments:
    lowercase alphanumerics joined by single hyphens. Anything else
    produces a slug GitHub would reject, and the rename is the wrong
    place to discover that."""
    return bool(re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", company))


def _normalized(name: str) -> str:
    """The spelling `uv.lock` records a package under: lowercase, with every
    run of `-`, `_` and `.` collapsed to one `-` (PEP 503)."""
    return re.sub(r"[-_.]+", "-", name).lower()


def _replace_token(text: str, old: str, new: str) -> str:
    """`text` with every `old` that stands alone as a name replaced by `new`.
    An `old` with a name character (`[A-Za-z0-9_-]`) on either side is part of
    a longer name and is left alone, which is what makes the replacement
    idempotent: `my_widget_sdf`, written by a first run for thing `my_widget`,
    is not `widget_sdf` again on a rerun."""
    return re.sub(r"(?<![A-Za-z0-9_-])" + re.escape(old) + r"(?![A-Za-z0-9_-])", new, text)


#: ci.yml's `package-name:` line, with the value in group 2 and the line's
#: trailing whitespace, `\r` included, in group 3 so a rewrite keeps it.
_PACKAGE_NAME_LINE = re.compile(r"(?m)^([ \t]*package-name:[ \t]*)(\S+)([ \t]*\r?)$")


def _relock_root(lock_text: str, new_slug: str) -> str:
    """`uv.lock` with its root package entry renamed to `new_slug` at
    `FIRST_VERSION`, the only two lines `uv lock` changes after this rename.
    An entry already named `new_slug` at `FIRST_VERSION` is accepted and comes
    back unchanged, so a rerun after a failed write finishes the rename.
    Raises `ValueError` when there is not exactly one root entry under either
    name, or the renamed one is at another version, so a lock this cannot
    rewrite stops the rename before anything is written."""
    old_name = re.escape(_normalized(OLD_SLUG))
    new_name = re.escape(_normalized(new_slug))
    # `\r?\n` and a lock read with its line endings intact: a Windows checkout
    # may have turned them into CRLF, which uv accepts.
    pattern = re.compile(
        r'(?m)^(\[\[package\]\]\r?\nname = )"(' + old_name + "|" + new_name + r')"(\r?\n)'
        r'version = "([^"]*)"(\r?\n)(source = \{ editable = "\." \}\r?)$'
    )
    entries = pattern.findall(lock_text)
    if len(entries) != 1:
        raise ValueError(
            f"uv.lock does not have exactly one root package entry named {OLD_SLUG!r} "
            f"or {_normalized(new_slug)!r}"
        )
    _, name, _, version, _, _ = entries[0]
    if name != _normalized(OLD_SLUG) and version != FIRST_VERSION:
        raise ValueError(
            f"uv.lock's root package entry is already named {name!r}, but at version "
            f"{version!r} rather than {FIRST_VERSION!r}"
        )
    return pattern.sub(
        lambda m: (
            f'{m.group(1)}"{_normalized(new_slug)}"{m.group(3)}'
            f'version = "{FIRST_VERSION}"{m.group(5)}{m.group(6)}'
        ),
        lock_text,
    )


def _write_atomic(path: Path, text: str) -> None:
    """Replace `path` with `text` in one step: the new content goes to a
    sibling file first and is moved over the old one, so the file is either
    entirely old or entirely new. A disk error leaves a stray `.rename-tmp`
    file at worst, never a truncated source file."""
    tmp = path.with_name(path.name + ".rename-tmp")
    try:
        tmp.write_bytes(text.encode("utf-8"))
        shutil.copymode(path, tmp)
        tmp.replace(path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def _read(path: Path) -> str:
    """`path` decoded as UTF-8, line endings untouched. A file that is not
    UTF-8 raises `UnicodeDecodeError`, a `ValueError`."""
    return path.read_bytes().decode("utf-8")


def _plan_rewrites(new_package: str, new_script: str, new_slug: str) -> dict[Path, str]:
    """The new contents of every file the rename rewrites, keyed by path,
    with nothing written. Raises `ValueError` (or `OSError` for an
    unreadable file) when the tree is not one this script can rename, so
    the caller stops before any file has changed.

    Every rewrite is idempotent: run over a tree a previous run with the same
    arguments has already partly or fully written, it produces what a single
    run would have. That is what lets a rerun finish a rename a disk error
    interrupted.

    Files are read and written as UTF-8 bytes, never through `read_text()`,
    so neither the platform's locale encoding nor newline translation
    touches them: a CRLF file stays CRLF, and non-ASCII text survives."""
    if new_package != OLD_PACKAGE and (ROOT / "src" / new_package).exists():
        raise ValueError(
            f"src/{new_package}/ already exists, so src/{OLD_PACKAGE}/ cannot move there"
        )

    rewrites: dict[Path, str] = {}

    for sub in PACKAGE_DIRS:
        for path in (ROOT / sub).rglob("*.py"):
            text = _read(path)
            new_text = _replace_token(text, OLD_PACKAGE, new_package)
            new_text = _replace_token(new_text, OLD_SCRIPT, new_script)  # cli.py's SCRIPT
            if new_text != text:
                rewrites[path] = new_text

    cem_toml = ROOT / "cem.toml"
    rewrites[cem_toml] = _replace_token(_read(cem_toml), OLD_PACKAGE, new_package)

    # ---- pyproject.toml: package, console script, repo slug, version ----
    pyproject = ROOT / "pyproject.toml"
    text = _read(pyproject)
    text = _replace_token(text, OLD_PACKAGE, new_package)  # packages=, version_files, script
    text = _replace_token(text, OLD_SCRIPT, new_script)  # [project.scripts] key
    text = _replace_token(text, OLD_SLUG, new_slug)  # [project].name, [project.urls]
    text, n_versions = re.subn(
        r'(?m)^version = "[^"\r\n]*"(\r?)$', rf'version = "{FIRST_VERSION}"\g<1>', text, count=1
    )
    if n_versions != 1:
        raise ValueError("could not find [project].version in pyproject.toml")
    rewrites[pyproject] = text

    # [project].name has to be the slug the replace above just wrote. The
    # lock's root entry and ci.yml's package-name are renamed to the same
    # slug, so a name that is anything else leaves the three disagreeing. On
    # a rerun the name is already the new slug; a name that is a different
    # slug means a previous run was given different arguments, and this one
    # is refused rather than mixing the two.
    project_table = text.split("\n[", 1)[0]  # up to [project.scripts]/[project.urls]
    name_match = re.search(r'(?m)^name = "([^"]+)"', project_table)
    if not name_match:
        raise ValueError("could not find [project].name in pyproject.toml")
    project_name = name_match.group(1)
    if project_name != new_slug:
        raise ValueError(
            f"pyproject.toml's [project].name is {project_name!r}, neither the template's "
            f"{OLD_SLUG!r} nor {new_slug!r}, so it cannot be renamed to {new_slug!r}"
        )

    # ---- ci.yml: the rest of the repo slug -------------------------------
    # package-name == [project].name is the invariant that actually breaks
    # something (build's verify-wheel step) rather than just reading wrong,
    # so the line is found, checked against the slug it should hold, and
    # rewritten explicitly instead of trusted to survive the blanket replace.
    # It may already hold the new slug, from a previous run that wrote ci.yml.
    ci_yml = ROOT / ".github" / "workflows" / "ci.yml"
    ci_old = _read(ci_yml)
    package_names = [m.group(2) for m in _PACKAGE_NAME_LINE.finditer(ci_old)]
    if package_names not in ([OLD_SLUG], [new_slug]):
        raise ValueError(
            f"ci.yml must have exactly one package-name: line, set to {OLD_SLUG!r} "
            f"or {new_slug!r}; found {package_names!r}"
        )
    ci_text, n_subs = _PACKAGE_NAME_LINE.subn(
        lambda m: f"{m.group(1)}{project_name}{m.group(3)}",
        _replace_token(ci_old, OLD_SLUG, new_slug),
    )
    assert n_subs == 1
    rewrites[ci_yml] = ci_text

    # ---- uv.lock: the root package, so `uv sync --locked` still passes ----
    lock_path = ROOT / "uv.lock"
    try:
        rewrites[lock_path] = _relock_root(_read(lock_path), new_slug)
    except ValueError as exc:
        raise ValueError(f"cannot rename the root package in uv.lock: {exc}") from exc

    return rewrites


def _already_renamed() -> bool:
    return not (ROOT / "src" / OLD_PACKAGE).is_dir()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "")
    ap.add_argument("thing", help="short CEM name, e.g. 'gear' for src/gear_sdf/")
    ap.add_argument(
        "--company",
        default=DEFAULT_COMPANY,
        help=(
            "organization half of the repo slug, as in <company>-cem-<thing> (default: %(default)s)"
        ),
    )
    args = ap.parse_args(argv)
    thing = args.thing
    company = args.company

    if not _valid_thing(thing):
        _fail(
            f"{thing!r} will not work: it becomes a Python package name "
            "(<thing>_sdf), so it needs to be lowercase snake_case -- "
            "letters, digits, underscores, starting with a letter"
        )
        return 1

    if not _valid_company(company):
        _fail(
            f"{company!r} will not work as the organization half of the "
            "repo slug: it needs to be lowercase alphanumerics joined by "
            "single hyphens, e.g. 'emergent-matter'"
        )
        return 1

    if _already_renamed():
        _fail(
            f"src/{OLD_PACKAGE}/ does not exist, so this repo looks already "
            "renamed. Refusing to run again rather than half-applying a "
            "second rename on top of the first."
        )
        return 1

    new_package = f"{thing}_sdf"
    new_script = f"{thing}-build"
    new_slug = f"{company}-cem-{thing}"

    # Everything that can fail on the tree's contents happens here, before
    # a single file changes: every input is read and every new file is
    # computed in memory, and every check runs against those results.
    try:
        rewrites = _plan_rewrites(new_package, new_script, new_slug)
    except (OSError, ValueError) as exc:
        _fail(str(exc))
        return 1

    # ---- the writes -------------------------------------------------------
    # Each file is replaced whole (see _write_atomic), so none is ever left
    # half-written, and every rewrite is idempotent (see _plan_rewrites). The
    # src/ move goes last, because it is what flips _already_renamed(): a
    # failure anywhere up to and including the move leaves src/ in place, so
    # a rerun with the same arguments is accepted and finishes the job.
    # pyproject.toml goes first, so once anything has been written its
    # [project].name names this run's slug and a rerun with different
    # arguments is refused instead of mixing two renames.
    pyproject = ROOT / "pyproject.toml"
    _write_atomic(pyproject, rewrites.pop(pyproject))
    for path, text in rewrites.items():
        _write_atomic(path, text)
    if new_package != OLD_PACKAGE:
        (ROOT / "src" / OLD_PACKAGE).rename(ROOT / "src" / new_package)

    # ---- release history reset -------------------------------------------
    for fragment in (ROOT / "changelog.d").glob("*.md"):
        fragment.unlink()

    print(f"package  : {OLD_PACKAGE} -> {new_package}")
    print(f"script   : {OLD_SCRIPT} -> {new_script}")
    print(f"repo slug: {OLD_SLUG} -> {new_slug}")
    print("release  : [project].version -> 0.1.0, changelog.d/ emptied")

    # A rename happens once. Leaving this script behind invites a second
    # run over a tree it would immediately refuse (see _already_renamed
    # above), so it has nothing left to do and every reason to stop being
    # something a future reader has to wonder about.
    self_path = Path(__file__).resolve()
    self_path.unlink()
    print(f"\nRemoved {self_path.relative_to(ROOT)}: its one job is done.")

    # tests/test_rename_checklist.py exists to drive THIS script against a
    # throwaway copy; once the script is gone, every one of its tests fails
    # trying to invoke a file that no longer exists, so a child CEM's first
    # `pytest` run would start red for a reason that has nothing to do with
    # the CEM's own code. It goes with rename.py, for the same reason.
    checklist_path = ROOT / "tests" / "test_rename_checklist.py"
    if checklist_path.exists():
        checklist_path.unlink()
        print(f"Removed {checklist_path.relative_to(ROOT)}: nothing left for it to drive.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
