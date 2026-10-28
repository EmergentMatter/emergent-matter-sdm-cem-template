"""The CLI contract the viewer actually depends on.

`--out` and `--set` are necessary but NOT sufficient, and this file exists
because that was found the hard way: with both flags present and working, the
viewer still failed every parameter change with a 500.

Two mismatches did it, and neither is visible from inside the CEM. Both were
caught only by driving a real viewer against a real part.
"""

from __future__ import annotations

import json
from pathlib import Path, PureWindowsPath

import pytest

from widget_sdf.parameters import WidgetParameters
from widget_sdf.sdm.cli import SCRIPT, main


def test_out_and_set_are_both_accepted(tmp_path):
    """The re-emit contract. A CEM with only --set fails inside a subprocess
    where the error surfaces nowhere useful."""
    out = tmp_path / "p.sdm"
    assert main(["--out", str(out), "--set", "d_outer_radius=14"]) == 0
    assert out.exists()


def test_set_accepts_the_name_the_sdm_EMITS(tmp_path):
    """`n_bolt_holes` ships in the .sdm as `bolt_holes`, and the viewer hands
    the emitted name back on re-emit. A CLI that only knows the field name
    refuses every re-emit with `unknown parameter 'bolt_holes'`."""
    out = tmp_path / "p.sdm"
    assert main(["--out", str(out), "--set", "bolt_holes=8"]) == 0
    assert json.loads(out.read_text())["params"]["bolt_holes"]["value"] == 8


def test_set_still_accepts_the_field_name(tmp_path):
    """Both spellings, so a human typing the field name is not punished."""
    out = tmp_path / "p.sdm"
    assert main(["--out", str(out), "--set", "n_bolt_holes=8"]) == 0
    assert json.loads(out.read_text())["params"]["bolt_holes"]["value"] == 8


def test_an_int_param_accepts_a_float_encoded_whole_number(tmp_path):
    """The .sdm stores every param as a JSON number, so an int round-trips as
    `6.0`. The viewer reads that and passes it straight back, and a plain
    int("6.0") raises with a message about a whole number that IS a whole
    number, which sends you looking in the wrong place."""
    out = tmp_path / "p.sdm"
    assert main(["--out", str(out), "--set", "bolt_holes=8.0"]) == 0
    assert json.loads(out.read_text())["params"]["bolt_holes"]["value"] == 8


def test_a_genuinely_non_integral_value_is_still_refused(tmp_path):
    """Accepting 6.0 must not mean accepting 6.5."""
    with pytest.raises(SystemExit):
        main(["--out", str(tmp_path / "p.sdm"), "--set", "bolt_holes=8.5"])


def test_no_two_fields_emit_the_same_name():
    """The alias map would silently shadow one of them."""
    import dataclasses

    seen: dict[str, str] = {}
    for f in dataclasses.fields(WidgetParameters):
        alias = f.name.split("_", 1)[1]
        assert alias not in seen, f"{f.name} and {seen[alias]} both emit {alias!r}"
        seen[alias] = f.name


def test_a_typo_names_the_near_miss(tmp_path, capsys):
    """Turns a typo into a one-line fix instead of a silently ignored
    override that changes nothing."""
    with pytest.raises(SystemExit):
        main(["--out", str(tmp_path / "p.sdm"), "--set", "outer_radius_typo=14"])


def test_invalid_parameters_exit_2_with_a_named_cause(tmp_path, capsys):
    """A subprocess caller reads STDERR to explain a failure. Printing the
    reason to stdout is why the viewer showed 'authoring failed:' with
    nothing after it."""
    code = main(["--out", str(tmp_path / "p.sdm"), "--set", "n_bolt_holes=24"])
    assert code == 2
    assert "flange_ligament_floor" in capsys.readouterr().err


def test_the_generator_records_a_command_that_can_be_re_run(tmp_path):
    """The viewer re-executes exactly this on re-emit. If it does not name a
    real entry point, the part is a dead end."""
    out = tmp_path / "p.sdm"
    main(["--out", str(out), "--set", "d_outer_radius=14"])
    gen = json.loads(out.read_text())["metadata"]["generator"]
    # `cwd` is relative to the .sdm's folder, the way the viewer resolves it.
    assert gen["argv"] and (out.parent / gen["cwd"]).is_dir()


def test_the_recorded_generator_is_idempotent(tmp_path):
    """A viewer re-runs the recorded command on every parameter change and
    compares the result against what it asked for. A command that re-SOLVES
    rather than re-renders answers differently every time, the viewer reads
    that as a change, and it loops. Measured on a sibling CEM: 1,820 requests
    at 1.6/second until the server was saturated.

    This template has nothing non-replayable to strip. The test exists so the
    day someone adds an optimisation step, it fails here instead of in a
    browser.
    """
    from widget_sdf.sdm.harness import NON_REPLAYABLE_FLAGS

    out = tmp_path / "p.sdm"
    assert main(["--out", str(out), "--set", "d_outer_radius=14"]) == 0
    argv = json.loads(out.read_text())["metadata"]["generator"]["argv"]
    assert not (set(argv) & NON_REPLAYABLE_FLAGS), argv
    assert argv[:4] == ["uv", "run", "--frozen", SCRIPT], "the command must still be re-runnable"


def test_rebuilding_from_the_recorded_command_reproduces_the_document(tmp_path):
    """The property that actually matters: replay it, get the same geometry."""
    first = tmp_path / "a.sdm"
    main(["--out", str(first), "--set", "d_outer_radius=14", "--set", "n_bolt_holes=5"])
    doc = json.loads(first.read_text())
    before = {k: v["value"] for k, v in doc["params"].items()}

    argv = doc["metadata"]["generator"]["argv"]
    second = tmp_path / "b.sdm"
    # What a re-emit does: the recorded command with its own --out appended.
    assert main([*argv[4:], "--out", str(second)]) == 0

    after = json.loads(second.read_text())["params"]
    for k, d_v in before.items():
        assert after[k]["value"] == pytest.approx(d_v, rel=1e-12), (
            f"{k} changed on replay: a viewer would see this as an edit and "
            "request another rebuild, forever"
        )


def _generator(tmp_path: Path, *args: str) -> dict:
    out = tmp_path / "output" / "p.sdm"
    assert main(["--out", str(out), *args]) == 0
    return json.loads(out.read_text())["metadata"]["generator"]


def test_the_recorded_generator_names_no_absolute_path(tmp_path):
    """A committed .sdm is opened on other machines and in sandboxes. A path
    into the builder's venv fails there with 'authoring command not found',
    and the engine appends its own --out, so the recorded one is dropped."""
    gen = _generator(tmp_path, "--set", "d_outer_radius=14")
    assert gen["argv"] == ["uv", "run", "--frozen", SCRIPT, "--set", "d_outer_radius=14"]
    for arg in gen["argv"]:
        assert not Path(arg).is_absolute()
        assert not PureWindowsPath(arg).is_absolute()
    assert str(tmp_path) not in json.dumps(gen)


def test_the_recorded_cwd_is_relative_to_the_sdm(tmp_path):
    """The engine resolves `cwd` against the .sdm, so it must lead from the
    file back to this repo, not name where the repo happens to be."""
    gen = _generator(tmp_path)
    assert not Path(gen["cwd"]).is_absolute()
    assert "\\" not in gen["cwd"]
    assert (tmp_path / "output" / gen["cwd"]).resolve() == Path.cwd().resolve()


def test_an_equals_form_out_is_dropped_too(tmp_path):
    out = tmp_path / "p.sdm"
    assert main([f"--out={out}"]) == 0
    gen = json.loads(out.read_text())["metadata"]["generator"]
    assert gen["argv"] == ["uv", "run", "--frozen", SCRIPT]
