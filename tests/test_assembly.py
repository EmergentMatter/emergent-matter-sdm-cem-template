"""`write_assembly`: one file per physical part, placed by an `Assembly`.

The bushing is one piece, so the CEM itself emits one `Part`. These tests
build the shape a multi-part product takes, from the two example parts this
repo already has: the bushing and the plate are separate pieces, so each is
its own `Part` and an `Assembly` places them. Nothing here claims the two fit
together; the point is the file layout and that it survives a round trip.

Then the same checks as everywhere else: load it back through `load_bundle`
and EVALUATE each part's field at points whose sign is known. An assembly
that loads is not an assembly of the right parts.
"""

from __future__ import annotations

import pytest
from plate_sdf.plate import PlateParameters, build_plate_part
from software_defined_matter import Assembly, Frame, Part, load_bundle

from widget_sdf.parameters import WidgetParameters
from widget_sdf.sdm.assembly import build_widget_part, source_metadata, write_assembly


def _sdf(part: Part, point: list[float]) -> float:
    import jax.numpy as jnp
    from software_defined_matter.sdf.compile import make_sdf_closure

    closure = make_sdf_closure(part.materials[0].sdf_tree, part)
    free = jnp.asarray(closure.binding.initial_free_vector())
    return float(closure(jnp.asarray(point, dtype=float), free))


@pytest.fixture(scope="module")
def written(tmp_path_factory):
    """Plate on the bench, bushing standing on its top face."""
    directory = tmp_path_factory.mktemp("assembly")
    plate = PlateParameters()
    path = write_assembly(
        [
            ("plate", build_plate_part(plate), Frame()),
            ("bushing", build_widget_part(), Frame(position=(0.0, 0.0, plate.d_thickness))),
        ],
        directory,
        name="example",
        source=source_metadata(WidgetParameters()),
    )
    return directory, path


def test_each_physical_part_is_its_own_file(written) -> None:
    directory, path = written
    assert path == directory / "example.sdm"
    assert sorted(p.name for p in (directory / "parts").iterdir()) == ["plate.sdm", "widget.sdm"]


def test_references_are_relative_and_pinned(written) -> None:
    _, path = written
    root = load_bundle(path).root
    for instance in root.instances:
        assert instance.part_ref.path.startswith("parts/")
        assert instance.part_ref.content_hash.startswith("sha256:")


def test_the_assembly_round_trips_through_load_bundle(written) -> None:
    _, path = written
    bundle = load_bundle(path)
    assert isinstance(bundle.root, Assembly)
    assert [i.id for i in bundle.root.instances] == ["plate", "bushing"]
    assert bundle.root.instances[1].transform.position[2] == PlateParameters().d_thickness


def test_each_generated_file_records_what_produced_it(written) -> None:
    """The CEM owns the dimensions; the file must say which CEM and which
    values, so a reviewer can check it against its source."""
    _, path = written
    bundle = load_bundle(path)
    expected = source_metadata(WidgetParameters())
    assert bundle.root.metadata["source"] == expected
    assert bundle.definitions["bushing"].metadata["source"] == expected


def test_no_dimension_is_driven_from_the_file(written) -> None:
    """Assembly params and instance overrides are for designs authored as
    `.sdm` with no CEM. Here the CEM owns every dimension, so the file carries
    neither: a second place to set a number is a second owner."""
    _, path = written
    root = load_bundle(path).root
    assert root.params == {}
    assert all(not i.param_overrides for i in root.instances)


def test_each_loaded_part_evaluates_to_the_right_shape(written) -> None:
    """The field of every part, read back from disk, at hand-checkable points."""
    _, path = written
    bundle = load_bundle(path)
    plate, bushing = bundle.definitions["plate"], bundle.definitions["bushing"]
    assert isinstance(plate, Part) and isinstance(bushing, Part)

    pp = PlateParameters()
    assert _sdf(plate, [0.0, pp.d_width / 4.0, pp.d_thickness / 2.0]) < 0.0
    assert _sdf(plate, [0.0, pp.d_width / 4.0, pp.d_thickness + 0.5]) > 0.0

    wp = WidgetParameters()
    r_mid = (wp.d_bore_radius + wp.d_outer_radius) / 2.0
    assert _sdf(bushing, [r_mid, 0.0, wp.d_length * 0.75]) < 0.0, "tube wall should be solid"
    assert _sdf(bushing, [0.0, 0.0, wp.d_length * 0.5]) > 0.0, "bore should be open"


def test_a_part_placed_twice_is_written_once(tmp_path) -> None:
    part = build_widget_part()
    write_assembly(
        [
            ("left", part, Frame(position=(-30.0, 0.0, 0.0))),
            ("right", part, Frame(position=(30.0, 0.0, 0.0))),
        ],
        tmp_path,
        name="pair",
    )
    assert [p.name for p in (tmp_path / "parts").iterdir()] == ["widget.sdm"]
    assert len(load_bundle(tmp_path / "pair.sdm").root.instances) == 2


def test_two_different_parts_cannot_share_a_name(tmp_path) -> None:
    import dataclasses

    longer = build_widget_part(dataclasses.replace(WidgetParameters(), d_length=40.0))
    with pytest.raises(ValueError, match="both named 'widget'"):
        write_assembly(
            [("a", build_widget_part(), Frame()), ("b", longer, Frame())], tmp_path, name="clash"
        )


def test_assemblies_nest(written) -> None:
    """A sub-assembly is placed by its file, exactly like a part."""
    directory, sub = written
    top = write_assembly(
        [("first", sub, Frame()), ("second", sub, Frame(position=(0.0, 60.0, 0.0)))],
        directory,
        name="top",
    )
    bundle = load_bundle(top)
    assert isinstance(bundle.definitions["first"], Assembly)
    assert isinstance(bundle.definitions["second.bushing"], Part)
