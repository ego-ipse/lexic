"""``CompiledGrammar`` — the parse-ready artefact ``compile_*`` produces.

Its own module (not ``__init__``) so sibling submodules (``export``) can
import it without an import cycle through the package root; externally it is
reachable only as ``lexic.compile.CompiledGrammar``, per the layering rule.
"""

from __future__ import annotations

from dataclasses import dataclass

from lexic.exceptions import UnsupportedConstructError
from lexic.ir.nodes import IrAst
from lexic.model import GrammarModel
from lexic.parsing import ModelFold, parse_model


@dataclass(frozen=True)
class CompiledGrammar:
    """Parse-ready artefacts produced by compile().

    :ivar classes: Generated model classes by class name.
    :ivar grammar: The canonical grammar AST (what the user's grammar IS —
        the transpile/re-emit source; also the generated module's GRAMMAR).
    :ivar codegen_grammar: The post-pass codegen grammar the fold binds against
        — the engine key :meth:`parse` hands to
        :func:`~lexic.parsing.parse_model` (the engine memoises its lifted /
        normalised / PDA / run-collapsed compilation per this grammar's identity).
    :ivar fold: The positional ParseTree → model-instance fold.
    :ivar flavour: The source flavour's name (drives the export docstrings).
    :ivar stem: The grammar stem (file stem / content-hash stem) — the
        exported module's default identity.
    """

    classes: dict[str, type]
    grammar: IrAst
    codegen_grammar: IrAst
    fold: ModelFold[GrammarModel]
    flavour: str = "gbnf"
    stem: str = "grammar"

    def parse(self, text: str) -> GrammarModel:
        """Parse text against the compiled grammar and return a model instance.

        Delegates to the engine's :func:`~lexic.parsing.parse_model` product,
        which runs the predictive PDA first and completes on the Earley engine
        on any non-deterministic point (that completion owns the user-facing
        diagnostics). ``PdaFail`` never surfaces.

        :raises UnsupportedConstructError: If ``text`` does not parse, or the
            fold produced no model for the start rule.
        """
        return self._ensure_model(parse_model(self.codegen_grammar, text, self.fold))

    @staticmethod
    def _ensure_model(model: object) -> GrammarModel:
        """Assert the start rule folded to a :class:`GrammarModel`.

        :param model: The object the PDA or the fold produced for the start rule.
        :returns: ``model`` narrowed to :class:`GrammarModel`.
        :raises UnsupportedConstructError: When ``model`` is not a model instance.
        """
        if not isinstance(model, GrammarModel):
            raise UnsupportedConstructError(
                f"compile: start rule folded to {type(model).__name__!r}, "
                "not a GrammarModel"
            )
        return model
