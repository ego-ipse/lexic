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
- :mod:`.policy` — what ``cores`` MEANS everywhere: 0 auto, 1 sequential,
  N that many.
- :mod:`.pool` — N documents in flight against one parse callable; lexic
  owns the threading, callers just map.
- :mod:`.replicas` — each worker's private tables; sharing one set is what
  caps concurrent scaling, and this is the measured fix.
- :mod:`.orchestrate` — ONE document split at derived separators, chunk-
  parsed under the container rule, stitched to the exact sequential model;
  everything unsupported falls back to the sequential product.
"""

from lexic.parsing.parallel.anchors import SITE_EMITS, anchor_sites, anchors
from lexic.parsing.parallel.orchestrate import SplitPlan, split_model, split_plan
from lexic.parsing.parallel.policy import (
    AUTO,
    MIN_CHUNK,
    available_workers,
    doc_workers,
    worker_count,
)
from lexic.parsing.parallel.pool import ParsePool
from lexic.parsing.parallel.replicas import Replica, replicas
from lexic.parsing.parallel.roles import Roles, Separator, roles
from lexic.parsing.parallel.scan import Scanner, Window

__all__ = [
    "AUTO",
    "MIN_CHUNK",
    "ParsePool",
    "Replica",
    "Roles",
    "SITE_EMITS",
    "Scanner",
    "Separator",
    "SplitPlan",
    "Window",
    "anchor_sites",
    "anchors",
    "available_workers",
    "doc_workers",
    "split_model",
    "replicas",
    "roles",
    "split_plan",
    "worker_count",
]
