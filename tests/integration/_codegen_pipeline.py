"""Shared codegen-pipeline front-half for integration tests.

The binding scaffold and the IR-native codegen gate start from the exact AST
``compile.py`` feeds its back half — since the Task 5 flip that front half is
the public :func:`lexic.compile.canonical_grammar`; this helper only adds the
file-path/flavour plumbing.
"""

from __future__ import annotations

from pathlib import Path

from lexic.compile import canonical_grammar
from lexic.grammars import flavour_for_extension
from lexic.ir.nodes import IrAst


def canonical_ast(path: Path) -> IrAst:
    """The canonical, semantic-flagged AST — ``compile.py``'s front half.

    :param path: A grammar file (flavour inferred from its extension).
    :returns: The canonicalised AST with start and ``semantic=False`` noise
        flags bound, ready for ``build_codegen_grammar``.
    """
    text = path.read_text(encoding="utf-8")
    return canonical_grammar(text, flavour_for_extension(path))
