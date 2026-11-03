"""A second worked shape: a mounting plate with a row of bolt holes.

WHY A SECOND EXAMPLE. The flanged bushing in `examples/bushing_sdf/` is built
entirely from cylinders, so it never exercises the trap that catches most
people writing their first plate-like part: the two rounding primitives
disagree with each other, and both validate either way.

WHY IT IS NOT A SECOND CEM. The repo root's `cem.toml` is the one manifest a
tool reads, with one `entry_point`, and the MCP server's `read_cem` assumes
exactly that. An example's manifest is documentation (see
`examples/bushing_sdf/cem.toml`); this one has none. So this is a reference
implementation you read and copy from, not a part the CLI builds.
Delete this directory when you start your own CEM.
"""

from __future__ import annotations
