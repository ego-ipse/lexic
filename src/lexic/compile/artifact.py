"""``CompiledGrammar`` — the parse-ready artefact ``compile_*`` produces.

Its own module (not ``__init__``) so sibling submodules (``export``) can
import it without an import cycle through the package root; externally it is
reachable only as ``lexic.compile.CompiledGrammar``, per the layering rule.
"""

from __future__ import annotations

from dataclasses import dataclass

from lexic.exceptions import UnsupportedConstructError
from lexic.ir import (
    IrAst,
    IrEncoding,
    IrMap,
    IrStr,
    IrTokenizer,
    IrTuple,
    IrUnicode,
    concretize,
)
from lexic.model import GrammarModel
from lexic.parsing import ModelFold, TokenMaskCursor, parse_model, token_model
from lexic.parsing.earley.kernel.forest.ambiguity import Resolver


def encoding_registry(
    tokenizer: IrTokenizer | None, registry: IrMap | None
) -> IrMap | None:
    """The name → encoding registry concretize binds against.

    The two inputs COMPOSE — ``registry=`` binds names, ``tokenizer=`` also
    binds that one under its own ``name`` — over a default ``unicode``. They
    are not alternatives, so passing both is fine; only a genuine conflict
    (the same name bound to two different encodings) is an error.

    :param tokenizer: A tokenizer to bind under its own ``name``.
    :param registry: An explicit ``IrMap[IrStr, IrEncoding]``; the grammar's
        encoding *names* are its keys. Entries win over the default ``unicode``.
    :returns: The resolved registry, or ``None`` for a plain char grammar.
    :raises UnsupportedConstructError: When ``tokenizer.name`` is already bound
        to a different encoding by ``registry``.
    """
    if tokenizer is None and registry is None:
        return None
    bound: dict[IrStr, IrEncoding] = {IrStr("unicode"): IrUnicode()}
    if registry is not None:
        bound |= {IrStr(name): enc for name, enc in registry.items()}
    if tokenizer is not None:
        name = IrStr(tokenizer.name)
        existing = bound.get(name)
        if existing is not None and existing is not tokenizer and name != "unicode":
            raise UnsupportedConstructError(
                f"compile: encoding name {str(name)!r} is bound by registry= "
                "and by tokenizer= to different encodings"
            )
        bound[name] = tokenizer
    return IrMap(*(IrTuple(name, enc) for name, enc in bound.items()))


def segmentation_tokenizer(registry: IrMap | None) -> IrTokenizer | None:
    """The registry's sole tokenizer — the bound vocabulary.

    Segmentation and generation both want one tokenizer; ``unicode`` is never
    it. Zero or multiple tokenizers ⇒ none is implied. Whether it SEGMENTS is
    a separate question, answered against the grammar.

    Counted by VALUE, not by entry and not by identity: ``tokenizer=`` and
    ``registry=`` compose, so one vocabulary bound under two names (its own
    and the grammar's) is still ONE vocabulary. Counting entries made that
    supported combination silently lose its segmentation; counting identities
    did the same for two equal vocabularies built separately, which is what a
    caller constructing one per call would hit.

    :param registry: The resolved encoding registry (or ``None``).
    :returns: The single :class:`IrTokenizer` in ``registry``, else ``None``.
    """
    if registry is None:
        return None
    toks = {enc for enc in registry.values() if isinstance(enc, IrTokenizer)}
    return next(iter(toks)) if len(toks) == 1 else None


@dataclass(frozen=True)
class TokenBinding:
    """What a compiled grammar knows about tokens — one value, three facts.

    The first two are separate questions and conflating them broke
    additivity: a tokenizer can be bound to a grammar that does not segment.

    :ivar tokenizer: The bound vocabulary. Supplies the segmentation for a
        token grammar's parse AND the vocabulary for ``constrain`` — a char
        grammar may carry one for the latter alone.
    :ivar segmented: Whether the grammar's terminals reference an encoding, so
        its input must be segmented into tokens. Derived from the grammar, so
        binding a tokenizer to a char grammar cannot move it.
    :ivar unresolved: The codegen grammar BEFORE its alphabets were resolved
        to ids — what :meth:`CompiledGrammar.bind` re-concretizes. Retained
        because resolution is lossy: ordinals are baked and the spellings are
        gone, so a rebind cannot start from ``codegen_grammar``.
    """

    tokenizer: IrTokenizer | None = None
    segmented: bool = False
    unresolved: IrAst | None = None


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
    :ivar tokens: What this grammar knows about tokens — the bound vocabulary
        and whether the grammar segments. See :class:`TokenBinding`.
    """

    classes: dict[str, type]
    grammar: IrAst
    codegen_grammar: IrAst
    fold: ModelFold[GrammarModel]
    flavour: str = "gbnf"
    stem: str = "grammar"
    tokens: TokenBinding = TokenBinding()

    def parse(self, text: str, resolve: Resolver | None = None) -> GrammarModel:
        """Parse text against the compiled grammar and return a model instance.

        A **token grammar** — one whose terminals reference an encoding —
        routes through :func:`~lexic.parsing.token_model`: lexic segments
        ``text`` with the bound tokenizer and every token terminal matches
        id-granular against that segmentation. A char grammar delegates to
        :func:`~lexic.parsing.parse_model` (PDA-first, Earley completion;
        ``PdaFail`` never surfaces).

        The route is chosen by the GRAMMAR, not by whether a tokenizer happens
        to be bound: a char grammar is unaffected by token machinery (the
        additivity invariant), and a tokenizer bound to one is there for
        :meth:`constrain`, which needs a vocabulary for char grammars too.

        Ambiguity is refused on BOTH routes: a span whose derivations build
        two different models raises rather than one route quietly picking.
        ``resolve`` is the caller's explicit opt-out — a deterministic resolver
        handed both derivations, whose choice is their concern — and it reaches
        whichever route the grammar selects, so the promise does not depend on
        whether the terminals happen to name an encoding.

        :param text: The input to parse.
        :param resolve: The caller's resolver, or ``None`` to refuse ambiguity.
        :raises UnsupportedConstructError: If ``text`` does not parse, the fold
            produced no model for the start rule, or the input means two things
            and no resolver was supplied.
        """
        tok = self.tokens.tokenizer
        if self.tokens.segmented and tok is None:
            raise UnsupportedConstructError(
                "compile: this grammar's terminals name an encoding, so "
                "parsing needs a vocabulary — compile with tokenizer= or "
                "registry=, or bind one. (Reading and emitting it needs none.)"
            )
        if tok is not None and self.tokens.segmented:
            bounds = {
                start: (tid, end - start) for start, end, tid in tok.boundaries(text)
            }
            return GrammarModel.ensure(
                token_model(self.codegen_grammar, text, self.fold, bounds, resolve),
                "compile: the start rule's fold",
            )
        return GrammarModel.ensure(
            parse_model(self.codegen_grammar, text, self.fold, resolve),
            "compile: the start rule's fold",
        )

    def bind(
        self, tokenizer: IrTokenizer, registry: IrMap | None = None
    ) -> CompiledGrammar:
        """This grammar against a different vocabulary — a NEW artefact.

        Re-resolves the retained unresolved codegen grammar against the new
        registry and reuses the classes, binding and fold unchanged. That is
        sound because they are **invariant** under which tokenizer is bound:
        field naming dispatches on the atom type (``IrAlphabet``), which
        resolution preserves — it rewrites only the inner ordinals. So two
        vocabularies give identical class names, ``__binds__`` and fold keys,
        and only the codegen grammar differs (and only where the ids do).

        Measured at ~18× cheaper than recompiling, a ratio that grows with
        grammar size: the skipped stages scale with the grammar, while
        resolution scales with the count of alphabet atoms.

        Returns a new artefact rather than mutating: the engine memoises its
        tables per grammar identity, and a rebound grammar SHOULD be a
        different identity because its ids differ.

        :param tokenizer: The vocabulary to bind.
        :param registry: Further name → encoding bindings, composed as at
            compile time.
        :returns: A new artefact bound to ``tokenizer``.
        """
        source = IrAst.ensure(self.tokens.unresolved, "compile: the unresolved grammar")
        resolved = encoding_registry(tokenizer, registry)
        return CompiledGrammar(
            classes=self.classes,
            grammar=self.grammar,
            codegen_grammar=(
                source if resolved is None else concretize(source, resolved)
            ),
            fold=self.fold,
            flavour=self.flavour,
            stem=self.stem,
            tokens=TokenBinding(
                segmentation_tokenizer(resolved), self.tokens.segmented, source
            ),
        )

    def constrain(self, tokenizer: IrTokenizer | None = None) -> TokenMaskCursor:
        """A generation cursor: the admissible next-token mask (capability C).

        Returns a :class:`~lexic.parsing.TokenMaskCursor` over this grammar and
        the bound (or supplied) tokenizer — ``mask()`` gives the admissible
        next-token ids at the current prefix, ``push(id)`` advances, ``accepts()``
        tests end-of-input. Generation is inherently id-space, so this is a
        separate surface from :meth:`parse`, not a second parse interface.

        Supplying a vocabulary is how a CHAR grammar generates: it has no
        token terminals, so any vocabulary drives it. A grammar that
        SEGMENTS is different — its terminals are already resolved to the
        bound vocabulary's ids, so ranging over another one matches nothing
        and yields an empty mask, which reads as "this grammar is
        unsatisfiable" rather than as an error. That combination is refused;
        :meth:`bind` is how a token grammar changes vocabulary.

        :param tokenizer: The tokenizer to range over; defaults to the one bound
            at compile time.
        :returns: A fresh mask cursor at the empty prefix.
        :raises UnsupportedConstructError: When no tokenizer is available, or
            when a segmented grammar is given a vocabulary other than its own.
        """
        tok = tokenizer if tokenizer is not None else self.tokens.tokenizer
        if tok is None:
            raise UnsupportedConstructError(
                "compile: constrain() needs a tokenizer (none was bound)"
            )
        bound = self.tokens.tokenizer
        if (
            self.tokens.segmented
            and tokenizer is not None
            and tokenizer is not bound
            and tokenizer != bound
        ):
            # Two different wrongs, so two different diagnoses: a grammar
            # resolved against ANOTHER vocabulary, versus one never resolved
            # at all. Both point at bind(); saying "the bound vocabulary"
            # when nothing was bound sends the reader looking for it.
            against = "another vocabulary" if bound is not None else "no vocabulary yet"
            raise UnsupportedConstructError(
                f"compile: this grammar's terminals are resolved against "
                f"{against}, so constraining it with this one matches "
                "nothing — use compiled.bind(tokenizer).constrain() instead"
            )
        return TokenMaskCursor.of(self.codegen_grammar, tok)
