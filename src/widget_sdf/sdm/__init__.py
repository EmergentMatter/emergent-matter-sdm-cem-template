"""Layer 2: turn parameters into an sdm-core `Part`.

Split from `parameters.py` so the design's numbers stay importable without
pulling in sdm-core, and split into `trees_*` + `assembly` because that is the
seam that stops one file becoming the whole CEM.
"""

from __future__ import annotations

__all__: list[str] = []
