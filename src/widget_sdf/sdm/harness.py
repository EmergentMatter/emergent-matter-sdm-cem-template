"""Save wrapper: `Part` to a `.sdm` on disk.

Thin on purpose. The one thing it adds over `software_defined_matter.save` is
GENERATOR METADATA: the argv and cwd that produced the file. Downstream, a
viewer's `/reemit` reads exactly that to rebuild the part when a topology param
changes; without it the file is a dead end that can be rendered and never
re-derived.

The record is PORTABLE: no absolute path, and `cwd` relative to the `.sdm`
(the engine resolves it against the file). A `.sdm` is committed and shared,
so a path into one machine's venv fails with "authoring command not found" on
every other machine. The command is `uv run --frozen <script>`, which finds
the project's own venv from `cwd` and runs the script from its locked
dependencies.

The `/reemit` contract is `--out` AND `--set`. A CEM whose CLI takes only
`--set` fails inside a subprocess, where the error is easy to lose.
"""

from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from software_defined_matter import Part

__all__ = [
    "GENERATOR_LAUNCHER",
    "NON_REPLAYABLE_FLAGS",
    "OUTPUT_DIR",
    "portable_generator_argv",
    "save_sdm",
    "stamped",
]

OUTPUT_DIR = Path(__file__).resolve().parents[3] / "output"


def stamped(name: str, ext: str) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return OUTPUT_DIR / f"{name}_{date.today():%Y%m%d}.{ext}"


#: Flags stripped from the recorded generator command.
#:
#: THE RECORDED COMMAND MUST BE IDEMPOTENT. A viewer re-runs it on every
#: parameter change and compares what comes back against what it asked for. A
#: command that re-SOLVES rather than re-renders answers differently each time,
#: the viewer reads that as a change, and it requests another rebuild. A
#: viewer that cannot converge re-requests without bound, saturating the
#: server so the part never finishes loading.
#:
#: Empty here, because this template only renders. It exists so that the day
#: someone adds `--optimise` the tests already say what to do with it.
NON_REPLAYABLE_FLAGS: frozenset = frozenset()


#: The launcher the recorded command runs under.
#:
#: Bare `python` is not it: the process that re-emits (a sidecar installed as
#: a uv tool) has its own interpreter, and `python` on its PATH is either
#: missing (macOS ships only `python3`) or a Python without this CEM's
#: dependencies. `uv run` resolves the project from `cwd`, so the command
#: works wherever the repo is checked out and uv is installed. `--frozen`
#: uses uv.lock as it stands, so a re-emit never rewrites the lockfile.
GENERATOR_LAUNCHER: tuple = ("uv", "run", "--frozen")

#: Flags the re-emit supplies itself. The engine appends its own `--out`, and
#: the recorded one is an absolute path on the machine that built the file.
_RE_EMIT_SUPPLIED = "--out"


def _replayable_argv(argv: list) -> list:
    """The command minus anything that would not reproduce this document."""
    return [a for a in argv if a not in NON_REPLAYABLE_FLAGS]


def _without_out(args: list) -> list:
    """`args` without `--out` and its value (either `--out X` or `--out=X`)."""
    kept: list = []
    it = iter(args)
    for a in it:
        if a == _RE_EMIT_SUPPLIED:
            next(it, None)
        elif not str(a).startswith(_RE_EMIT_SUPPLIED + "="):
            kept.append(a)
    return kept


def portable_generator_argv(argv: list) -> list:
    """The command that rebuilds this document, with no machine in it.

    `argv[0]` is whatever launched the build, usually the absolute path of the
    console script inside one developer's venv. Only its name survives, and
    `uv run` finds the script again from the project.
    """
    script = Path(str(argv[0])).stem
    return [*GENERATOR_LAUNCHER, script, *_without_out(_replayable_argv(list(argv[1:])))]


def _relative_cwd(out: Path) -> str:
    """The current directory as seen from the `.sdm`, the way the engine
    resolves it. POSIX separators, so the same file reads the same everywhere."""
    return Path(os.path.relpath(Path.cwd().resolve(), out.resolve().parent)).as_posix()


def save_sdm(
    part: Part,
    name: str,
    *,
    out: Path | None = None,
    argv: list | None = None,
) -> Path:
    """Serialise a `Part`, stamping how it was produced."""
    from software_defined_matter import save

    path = out or stamped(name, "sdm")
    part.metadata = dict(part.metadata or {})
    part.metadata["generator"] = {
        # Defaults to sys.argv, which is right for a real CLI call and WRONG
        # whenever main() runs in-process: under pytest sys.argv is pytest's
        # own command line, so the document would record a generator that
        # rebuilds nothing. The CLI passes its own.
        "argv": portable_generator_argv(list(argv) if argv is not None else sys.argv),
        "cwd": _relative_cwd(path),
        # Which flags this CLI understands. A tool cannot tell from argv alone
        # whether a generator takes --out and --set; without the declaration
        # its only option is to stage edited values in the .sdm and rely on
        # the generator reading its own output. Declared, it can pass them on
        # the command line and the generator stays a pure function of its
        # arguments.
        #
        # Both together or neither: --set without --out would have the
        # generator write over the source file mid-rebuild.
        "accepts": ["--out", "--set"],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    save(part, path)
    return path
