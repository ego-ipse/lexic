"""``CompiledGrammar`` — the parse-ready artefact ``compile_*`` produces.

Its own module (not ``__init__``) so sibling submodules (``export``) can
import it without an import cycle through the package root; externally it is
reachable only as ``lexic.compile.CompiledGrammar``, per the layering rule.
"""

from __future__ import annotations

from dataclasses import dataclass

from lexic.exceptions import UnsupportedConstructError
from lexic.ir.encoding import IrTokenizer
from lexic.ir.nodes import IrAst
from lexic.model import GrammarModel
from lexic.parsing import ModelFold, TokenMaskCursor, parse_model, token_model


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
    tokenizer: IrTokenizer | None = None

    def parse(self, text: str) -> GrammarModel:
        """Parse text against the compiled grammar and return a model instance.

        A **token grammar** (compiled with a bound :attr:`tokenizer`) routes
        through :func:`~lexic.parsing.token_model`: lexic segments ``text`` with
        its own tokenizer and every token terminal matches id-granular against
        that segmentation. A char grammar delegates to
        :func:`~lexic.parsing.parse_model` (PDA-first, Earley completion;
        ``PdaFail`` never surfaces).

        :raises UnsupportedConstructError: If ``text`` does not parse, or the
            fold produced no model for the start rule.
        """
        if self.tokenizer is not None:
            bounds = {
                start: (tid, end - start)
                for start, end, tid in self.tokenizer.boundaries(text)
            }
            return self._ensure_model(
                token_model(self.codegen_grammar, text, self.fold, bounds)
            )
        return self._ensure_model(parse_model(self.codegen_grammar, text, self.fold))

    def constrain(self, tokenizer: IrTokenizer | None = None) -> TokenMaskCursor:
        """A generation cursor: the admissible next-token mask (capability C).

        Returns a :class:`~lexic.parsing.TokenMaskCursor` over this grammar and
        the bound (or supplied) tokenizer — ``mask()`` gives the admissible
        next-token ids at the current prefix, ``push(id)`` advances, ``accepts()``
        tests end-of-input. Generation is inherently id-space, so this is a
        separate surface from :meth:`parse`, not a second parse interface.

        :param tokenizer: The tokenizer to range over; defaults to the one bound
            at compile time.
        :returns: A fresh mask cursor at the empty prefix.
        :raises UnsupportedConstructError: When no tokenizer is available.
        """
        tok = tokenizer if tokenizer is not None else self.tokenizer
        if tok is None:
            raise UnsupportedConstructError(
                "compile: constrain() needs a tokenizer (none was bound)"
            )
        return TokenMaskCursor.of(self.codegen_grammar, tok)

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
