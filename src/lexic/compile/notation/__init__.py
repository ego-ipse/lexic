"""The IR-constructor notation surface — parse + emit halves, manifest loader.

The parse half is ``load_ir`` / ``load_ir_from_path``, the emit half is
``emit_ir`` (and ``ir_doc``, the layout document it renders, for a caller
composing notation into a larger document), and the manifest loader is
``load_flavour`` / ``load_flavour_from_path``.

The two halves are inverses: ``load_ir(emit_ir(x)) == x``. Outside the
``lexic.compile`` package the seam is ``lexic.compile`` itself; this surface is
for the package and its tooling.
"""

from __future__ import annotations

from lexic.compile.notation.emit import emit_ir, ir_doc
from lexic.compile.notation.loader import load_flavour, load_flavour_from_path
from lexic.compile.notation.parse import load_ir, load_ir_from_path

__all__ = [
    "emit_ir",
    "ir_doc",
    "load_flavour",
    "load_flavour_from_path",
    "load_ir",
    "load_ir_from_path",
]
