"""The parallel layer — split analysis, roles, scan, policy; the orchestrator's home.

Neither engine consumes anything here: these are grammar and text
properties the parallel orchestrator composes ABOVE the products — which
is why they live in their own subpackage rather than on the parsing root.
The user surface is ``CompiledGrammar.anchors()``; everything else is the
orchestrator's own vocabulary, public for composition and tests.

- :mod:`.anchors` — the characters no opaque interior can emit, and their
  site maps (the disambiguation hypothesis set).
- :mod:`.roles` — what those characters DO: opener/closer pairs, separators.
- :mod:`.scan` — the self-locating window scan and its prefix-sum rebase.
- :mod:`.policy` — how many workers a document should get (auto, or the
  caller's explicit override).
- :mod:`.pool` — N documents in flight against one parse callable; lexic
  owns the threading, callers just map.
"""

from lexic.parsing.parallel.anchors import SITE_EMITS, anchor_sites, anchors
from lexic.parsing.parallel.policy import MIN_CHUNK, doc_workers, worker_count
from lexic.parsing.parallel.pool import ParsePool
from lexic.parsing.parallel.roles import Roles, roles
from lexic.parsing.parallel.scan import Scanner, Window

__all__ = [
    "MIN_CHUNK",
    "ParsePool",
    "Roles",
    "SITE_EMITS",
    "Scanner",
    "Window",
    "anchor_sites",
    "anchors",
    "doc_workers",
    "roles",
    "worker_count",
]
