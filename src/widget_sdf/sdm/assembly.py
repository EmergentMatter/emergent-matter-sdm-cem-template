"""Compose the trees into a `Part`, and Parts into an `Assembly`.

`cem.toml` names `widget_sdf.sdm.assembly:build_widget_part` as `entry_point`,
so this signature is a contract: params in (or None for defaults), `Part` out.

ONE `Part` PER PHYSICAL PART. The bushing comes off the printer as one piece,
so it is one `Part`. A product made of separable pieces (fastened, bonded,
pressed in, or just dropped in place) is one `Part` per piece, placed by an
`Assembly`; `write_assembly` below writes that. Packing separable bodies into
one Part's material regions hides the bill of materials from everyone who
reviews the file. README's "One Part per physical part" has the rule.
"""

from __future__ import annotations

import dataclasses
import hashlib
from collections.abc import Sequence
from pathlib import Path

from software_defined_matter import (
    Assembly,
    Frame,
    Instance,
    MaterialRegion,
    Param,
    Part,
    PartRef,
    save,
)

from widget_sdf import __version__
from widget_sdf.parameters import WidgetParameters
from widget_sdf.sdm.trees_body import body_tree

__all__ = [
    "MATERIAL_ID",
    "MATERIAL_NAME",
    "PARAM_FIELDS",
    "build_widget_part",
    "source_metadata",
    "write_assembly",
]

MATERIAL_ID = 1
MATERIAL_NAME = "nylon12_sls"

#: The fields that ship in the `.sdm` as params. Derived values are NOT here:
#: they are recomputed from these, and shipping them as free params is what
#: severs a derived value from its inputs (the hexafoil bug:
#: schema 0.2 cannot express a param expression, so a derived param written as
#: a free one desyncs the moment a slider moves).
#: field -> unit, and the units must come from sdm-core's schema enum
#: ("mm", "count", "rad", "deg", "ratio", "N", "MPa", ...). An empty string is
#: REFUSED by the schema, which is easy to hit and reads as an unrelated
#: validation dump. Written out per field rather than inferred from the prefix
#: because `d_` is a float, not a millimetre: an angle is `d_` too.
#: field -> (unit, (lo, hi)). Mirrors `cem.toml`; a test asserts they agree.
#:
#: BOUNDS ARE NOT OPTIONAL, and omitting them is a silent failure that only
#: shows up in a tool. A viewer builds its control from what the DOCUMENT says,
#: not from `cem.toml`, so a param emitted with `bounds: null` has no range to
#: slide between and renders as a control nothing can move. Declaring a range
#: in the manifest and leaving it out here means the manifest describes a
#: control nothing can offer.
PARAM_FIELDS = {
    "n_bolt_holes": ("count", (0, 24)),
    "d_outer_radius": ("mm", (4.0, 60.0)),
    "d_wall_thickness": ("mm", (0.8, 20.0)),
    "d_length": ("mm", (5.0, 200.0)),
    "d_flange_radius": ("mm", (5.0, 100.0)),
    "d_flange_thickness": ("mm", (1.0, 30.0)),
    "d_bolt_hole_radius": ("mm", (0.5, 10.0)),
    "d_bolt_circle_radius": ("mm", (3.0, 90.0)),
}


def _params_block(p: WidgetParameters) -> dict:
    """`.sdm` params. Names lose the type prefix: `cem.toml` records that
    mapping under `emits`, so a consumer can join the two without guessing."""
    return {
        f.split("_", 1)[1]: Param(
            name=f.split("_", 1)[1],
            value=float(getattr(p, f)),
            free=False,
            bounds=bounds,
            unit=unit,
        )
        for f, (unit, bounds) in PARAM_FIELDS.items()
    }


def source_metadata(params: WidgetParameters) -> dict:
    """What produced a document: this CEM, its version, and every declared
    parameter it ran with. Stored under `metadata["source"]`.

    The CEM owns its dimensions and the `.sdm` is its output, so anyone
    reviewing the file needs to be able to check it against its source. The
    params block alone cannot show that: it carries only the fields that
    ship, not the toolchain ones.
    """
    return {
        "cem": __name__.split(".")[0],
        "version": __version__,
        "parameters": dataclasses.asdict(params),
    }


def build_widget_part(params: WidgetParameters | None = None, *, name: str = "widget") -> Part:
    """Build the widget as a single-material `Part`.

    Validates FIRST and raises on failure. A CEM that emits geometry from
    invalid parameters produces a plausible-looking part that violates its own
    design rules, and nothing downstream can tell.
    """
    params = params or WidgetParameters()
    errors = params.validate()
    if errors:
        raise ValueError("invalid widget parameters:\n  " + "\n  ".join(errors))

    lo, hi = params.bbox()
    return Part(
        name=name,
        params=_params_block(params),
        materials=[
            MaterialRegion(
                material_id=MATERIAL_ID,
                name=MATERIAL_NAME,
                sdf_tree=body_tree(params),
            )
        ],
        metadata={"bbox": [lo, hi], "units": "mm", "source": source_metadata(params)},
    )


def _pinned_ref(directory: Path, rel_path: str) -> PartRef:
    """A relative reference pinned to the exact bytes on disk.

    The pin is what makes the assembly reproducible: `load_bundle` refuses a
    referenced file whose bytes have changed since the assembly was written,
    instead of quietly placing a different part.
    """
    digest = hashlib.sha256((directory / rel_path).read_bytes()).hexdigest()
    return PartRef(rel_path, "sha256:" + digest)


def write_assembly(
    placements: Sequence[tuple[str, Part | Path, Frame]],
    directory: Path,
    *,
    name: str,
    source: dict | None = None,
    metadata: dict | None = None,
) -> Path:
    """Write `directory/parts/<part>.sdm` per distinct Part and
    `directory/<name>.sdm`, an `Assembly` placing them.

    `placements` is `(instance_id, what, frame)`. `what` is a `Part`, written
    once under `parts/` however many times it is placed (six identical bolts
    are one file and six instances), or the `Path` of an `.sdm` already
    written under `directory`, which is how assemblies nest: write the
    sub-assembly first, then place its file like a part.

    Every reference is relative to `directory` and pinned by sha256, so the
    directory can be moved or copied as a unit. `source` (see
    `source_metadata`) records what produced the assembly; for a parent CEM
    that includes the shared dimensions it owns.

    The Assembly gets NO params and its instances no `param_overrides`. Those
    are for designs authored directly as `.sdm`. Here the CEM owns every
    dimension: a change goes into the CEM and the files are regenerated, and
    an override in the file would give one number two owners.
    """
    directory = Path(directory)
    (directory / "parts").mkdir(parents=True, exist_ok=True)
    written: dict[str, Part] = {}
    instances = []
    for instance_id, what, frame in placements:
        if isinstance(what, Part):
            rel = f"parts/{what.name}.sdm"
            if what.name in written:
                if written[what.name] != what:
                    raise ValueError(
                        f"two different parts are both named {what.name!r}; "
                        "each physical part needs its own file name"
                    )
            else:
                save(what, directory / rel)
                written[what.name] = what
        else:
            rel = Path(what).resolve().relative_to(directory.resolve()).as_posix()
        instances.append(Instance(instance_id, _pinned_ref(directory, rel), transform=frame))
    out = directory / f"{name}.sdm"
    save(
        Assembly(
            name,
            instances=tuple(instances),
            metadata={
                "units": "mm",
                **(metadata or {}),
                **({"source": source} if source is not None else {}),
            },
        ),
        out,
    )
    return out
