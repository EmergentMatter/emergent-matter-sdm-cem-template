"""The worked example of a full CEM: a flanged bushing.

The template's own part is a small rounded block (`src/widget_sdf/`). This is
the bigger one, kept so the docs that teach parameters, roles, derived values
and constraints have a complete example to point at: `cem.toml` here is the
annotated manifest, `parameters.py` the dataclass, `bushing.py` the trees.

It is a reference to read and copy from. The CLI does not build it, and the
`cem.toml` beside it is documentation: the one manifest a tool reads is the
repo root's. Delete this directory, and `tests/test_example_bushing.py`, when you start
own CEM.
"""

from __future__ import annotations
