#!/usr/bin/env python3
"""Turn this template into a real CEM.

    python3 scripts/rename.py <thing> [--company <company-name>]

Performs README's "Use it" step 1, mechanically: renames the package
directory and fixes every import and manifest reference that names it,
renames the repo slug everywhere `pyproject.toml` and `ci.yml` carry it,
renames the console-script key, and resets the release history (step 2).

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

    # ---- the package rename ---------------------------------------------
    (ROOT / "src" / OLD_PACKAGE).rename(ROOT / "src" / new_package)

    for sub in PACKAGE_DIRS:
        for path in (ROOT / sub).rglob("*.py"):
            text = path.read_text()
            if OLD_PACKAGE in text:
                path.write_text(text.replace(OLD_PACKAGE, new_package))

    cem_toml = ROOT / "cem.toml"
    cem_toml.write_text(cem_toml.read_text().replace(OLD_PACKAGE, new_package))

    # ---- pyproject.toml: package, console script, repo slug, version ----
    pyproject = ROOT / "pyproject.toml"
    text = pyproject.read_text()
    text = text.replace(OLD_PACKAGE, new_package)  # packages=, version_files, script value
    text = text.replace(OLD_SCRIPT, new_script)  # [project.scripts] key
    text = text.replace(OLD_SLUG, new_slug)  # [project].name, [project.urls]
    text = re.sub(r'(?m)^version = ".*"$', 'version = "0.1.0"', text, count=1)
    pyproject.write_text(text)

    # ---- ci.yml: the rest of the repo slug -------------------------------
    ci_yml = ROOT / ".github" / "workflows" / "ci.yml"
    ci_text = ci_yml.read_text().replace(OLD_SLUG, new_slug)

    # package-name == [project].name is the invariant that actually breaks
    # something (build's verify-wheel step) rather than just reading wrong,
    # so it is re-derived and enforced here instead of trusted to have
    # survived the blanket slug replace above unchanged.
    project_table = text.split("\n[", 1)[0]  # up to [project.scripts]/[project.urls]
    name_match = re.search(r'(?m)^name = "([^"]+)"', project_table)
    if not name_match:
        _fail("could not find [project].name in the rewritten pyproject.toml")
        return 1
    project_name = name_match.group(1)

    ci_text, n_subs = re.subn(
        r"(?m)^(\s*package-name:\s*)\S+\s*$", rf"\g<1>{project_name}", ci_text
    )
    if n_subs != 1:
        _fail("ci.yml's package-name: line was not found (or matched more than once)")
        return 1
    ci_yml.write_text(ci_text)

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
