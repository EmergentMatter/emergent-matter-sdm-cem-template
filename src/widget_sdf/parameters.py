"""Single source of truth for the widget's geometry.

A rounded block: the smallest part that still has the shape of a CEM, with
declared parameters, a derived value, a constraint, and a tree built from them.
The part is a starting point; replace it.

THE ONE RULE THIS FILE EXISTS TO DEMONSTRATE: every derived value is an
`@property`, computed from the declared fields, never stored. Store a derived
value as its own field and it becomes a second source of truth that nothing
keeps in sync. That is exactly how a param edit produces geometry that
violates the model with nothing reporting a problem. `d_half_min_side` is
derived from the three extents; write it down as a field and someone will
eventually set the four of them to values that disagree.

Naming follows the org playbook (`conventions/naming.md`): the prefix IS the
type. `d_` float, `n_` int, `b_` bool, `s_` str, `a_` array.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["WidgetParameters"]


@dataclass(frozen=True)
class WidgetParameters:
    """Immutable parameter set. Use `dataclasses.replace()` for variants.

    Frozen on purpose: a CEM gets called from an optimizer that will happily
    hold a reference to a params object across iterations, and a mutable one
    turns that into a bug you find three results later.
    """

    # ── Envelope (mm) ──

    d_length: float = 40.0
    """Extent along x."""

    d_width: float = 30.0
    """Extent along y."""

    d_height: float = 20.0
    """Extent along z. The block stands on z = 0."""

    d_edge_radius: float = 3.0
    """Radius of the twelve rounded edges. 0 gives sharp edges."""

    # ── Toolchain, not design ──

    d_voxel_size_mm: float = 0.25
    """Default voxel size for meshing. Declared `role = "tool"` in cem.toml:
    it configures the toolchain, not the part."""

    # ── Derived: computed, never stored ──

    @property
    def d_half_min_side(self) -> float:
        """Half of the smallest extent: the most any edge radius can take."""
        return min(self.d_length, self.d_width, self.d_height) / 2.0

    def bbox(self) -> tuple[list[float], list[float]]:
        """Axis-aligned bounds, with a voxel of margin.

        Declared rather than inferred: sdm-core can infer a domain by sampling,
        but on a tree of any size that is slow and, on small cores, has been
        wrong. A CEM knows its own envelope. Say it.
        """
        v = self.d_voxel_size_mm
        return (
            [-self.d_length / 2.0 - v, -self.d_width / 2.0 - v, -v],
            [self.d_length / 2.0 + v, self.d_width / 2.0 + v, self.d_height + v],
        )

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
        if self.d_edge_radius >= self.d_half_min_side:
            errs.append(
                f"edge_radius_below_half_smallest_side: edge radius {self.d_edge_radius} "
                f">= {self.d_half_min_side}, half the smallest side, so no block is left"
            )
        return errs
