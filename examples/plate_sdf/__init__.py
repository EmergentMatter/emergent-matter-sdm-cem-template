"""A second worked shape: a mounting plate with a row of bolt holes.

WHY A SECOND EXAMPLE. The flanged bushing in `src/widget_sdf/` is built
entirely from cylinders, so it never exercises the trap that catches most
people writing their first plate-like part: the two rounding primitives
disagree with each other, and both validate either way.

WHY IT IS NOT A SECOND CEM. `cem.toml` is singular. One repo declares one
manifest with one `entry_point`, and the MCP server's `read_cem` assumes exactly
that. A second manifest would break every tool that reads one. So this is a
reference implementation you read and copy from, not a part the CLI builds.
Delete this directory when you start your own CEM.
"""

from __future__ import annotations
