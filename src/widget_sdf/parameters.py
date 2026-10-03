"""Single source of truth for the widget's geometry.

A flanged bushing: a tube with a bore, a flange at one end, and a bolt circle
through the flange. Deliberately simple: the point of this repo is the SHAPE
OF A CEM, not the shape of the part.

THE ONE RULE THIS FILE EXISTS TO DEMONSTRATE: every derived value is an
`@property`, computed from the declared fields, never stored. Store a derived
value as its own field and it becomes a second source of truth that nothing
keeps in sync. That is exactly how a param edit produces geometry that
violates the model with nothing reporting a problem. `d_bore_radius` is
`d_outer_radius - d_wall_thickness`; write it down as a field and someone will
eventually set the three of them to values that disagree.

Naming follows the org playbook (`conventions/naming.md`): the prefix IS the
type. `d_` float, `n_` int, `b_` bool, `s_` str, `a_` array.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

__all__ = ["WidgetParameters"]


@dataclass(frozen=True)
class WidgetParameters:
    """Immutable parameter set. Use `dataclasses.replace()` for variants.

    Frozen on purpose: a CEM gets called from an optimizer that will happily
    hold a reference to a params object across iterations, and a mutable one
    turns that into a bug you find three results later.
    """

    # ── Topology (changing these changes how many nodes the tree has) ──

    n_bolt_holes: int = 6
    """Number of holes in the flange bolt circle."""

    # ── Envelope (mm) ──

    d_outer_radius: float = 12.0
    """Outer radius of the tube."""

    d_wall_thickness: float = 3.0
    """Tube wall thickness. The bore follows from this (see `d_bore_radius`)."""

    d_length: float = 30.0
    """Overall axial length, flange included."""

    # ── Flange (mm) ──

    d_flange_radius: float = 20.0
    """Flange outer radius. Must exceed `d_outer_radius` to be a flange."""

    d_flange_thickness: float = 4.0
    """Flange axial thickness."""

    d_bolt_hole_radius: float = 1.7
    """Radius of each bolt hole (M3 clearance)."""

    d_bolt_circle_radius: float = 16.0
    """Radius of the circle the bolt holes sit on."""

    # ── Toolchain, not design ──

    d_voxel_size_mm: float = 0.25
    """Default voxel size for meshing. Declared `role = "tool"` in cem.toml:
    it configures the toolchain, not the part."""

    # ── Derived: computed, never stored ──

    @property
    def d_bore_radius(self) -> float:
        """Inner radius of the tube."""
        return self.d_outer_radius - self.d_wall_thickness

    @property
    def d_bolt_angular_pitch(self) -> float:
        """Angle between adjacent bolt holes (radians).

        0 when there are no holes. `n_bolt_holes = 0` is inside the declared
        bounds (it means "no bolt circle"), so this and `d_flange_ligament`
        must both survive it. Found by the build test, not by inspection: the
        zero case reads as obviously fine until something divides by it.
        """
        if self.n_bolt_holes <= 0:
            return 0.0
        return 2.0 * math.pi / self.n_bolt_holes

    @property
    def d_flange_ligament(self) -> float:
        """Material left between adjacent bolt holes at the bolt circle.

        The number a reviewer actually asks about, and the reason `validate()`
        has a floor: holes that nearly touch make a perforation, not a flange.
        """
        if self.n_bolt_holes <= 0:
            return math.inf  # no holes, no ligament to run out of
        chord = 2.0 * self.d_bolt_circle_radius * math.sin(self.d_bolt_angular_pitch / 2.0)
        return chord - 2.0 * self.d_bolt_hole_radius

    def bbox(self) -> tuple[list[float], list[float]]:
        """Axis-aligned bounds, with a voxel of margin.

        Declared rather than inferred: sdm-core can infer a domain by sampling,
        but on a tree of any size that is slow and, on small cores, has been
        wrong. A CEM knows its own envelope. Say it.
        """
        r = max(self.d_outer_radius, self.d_flange_radius) + self.d_voxel_size_mm
        return ([-r, -r, -self.d_voxel_size_mm], [r, r, self.d_length + self.d_voxel_size_mm])

    def validate(self) -> list[str]:
        """Every constraint that a per-param bound cannot express.

        Returns a list of messages rather than raising, so a caller (an
        optimizer, a coder agent) can see ALL the problems at once instead of
        fixing them one exception at a time.

        These mirror `[[cem.constraints]]` in `cem.toml`. The manifest is what
        a tool reads; this is what actually runs. Keep them in step: the test
        suite checks that every constraint named in the manifest is enforced
        here, which is the only thing stopping the two from drifting.
        """
        errs: list[str] = []
        if self.d_wall_thickness >= self.d_outer_radius:
            errs.append(
                f"wall_thickness_below_outer_radius: wall {self.d_wall_thickness} "
                f">= outer radius {self.d_outer_radius}, leaving no bore"
            )
        if self.d_flange_radius <= self.d_outer_radius:
            errs.append(
                f"flange_exceeds_tube: flange radius {self.d_flange_radius} <= "
                f"tube radius {self.d_outer_radius}, so it is not a flange"
            )
        if not (self.d_outer_radius < self.d_bolt_circle_radius < self.d_flange_radius):
            errs.append(
                f"bolt_circle_within_flange: bolt circle {self.d_bolt_circle_radius} "
                f"must sit between tube {self.d_outer_radius} and flange "
                f"{self.d_flange_radius}"
            )
        if self.d_flange_ligament < 2.0:
            errs.append(
                f"flange_ligament_floor: only {self.d_flange_ligament:.2f} mm "
                "between adjacent bolt holes (floor 2.0). This is a "
                "perforation, not a flange"
            )
        if self.d_flange_thickness >= self.d_length:
            errs.append(
                f"flange_within_length: flange {self.d_flange_thickness} >= "
                f"overall length {self.d_length}"
            )
        return errs
