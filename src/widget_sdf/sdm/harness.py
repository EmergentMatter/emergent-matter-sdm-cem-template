"""Save wrapper: `Part` to a `.sdm` on disk.

Thin on purpose. The one thing it adds over `software_defined_matter.save` is
GENERATOR METADATA: the argv and cwd that produced the file. Downstream, a
viewer's `/reemit` reads exactly that to rebuild the part when a topology param
changes; without it the file is a dead end that can be rendered and never
re-derived.

The `/reemit` contract is `--out` AND `--set`. A CEM whose CLI takes only
`--set` fails inside a subprocess, where the error is easy to lose.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from software_defined_matter import Part

__all__ = ["OUTPUT_DIR", "NON_REPLAYABLE_FLAGS", "stamped", "save_sdm"]

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


def _replayable_argv(argv: list) -> list:
    """The command minus anything that would not reproduce this document."""
    return [a for a in argv if a not in NON_REPLAYABLE_FLAGS]


def save_sdm(
    part: Part,
    name: str,
    *,
    out: Path | None = None,
    argv: list | None = None,
) -> Path:
    """Serialise a `Part`, stamping how it was produced."""
    from software_defined_matter import save

    part.metadata = dict(part.metadata or {})
    part.metadata["generator"] = {
        # Defaults to sys.argv, which is right for a real CLI call and WRONG
        # whenever main() runs in-process: under pytest sys.argv is pytest's
        # own command line, so the document would record a generator that
        # rebuilds nothing. The CLI passes its own.
        "argv": _replayable_argv(list(argv) if argv is not None else sys.argv),
        "cwd": str(Path.cwd()),
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
    path = out or stamped(name, "sdm")
    path.parent.mkdir(parents=True, exist_ok=True)
    save(part, path)
    return path
