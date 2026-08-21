"""``CompiledGrammar`` — the parse-ready artefact ``compile_*`` produces.

Its own module (not ``__init__``) so sibling submodules (``export``) can
import it without an import cycle through the package root; externally it is
reachable only as ``lexic.compile.CompiledGrammar``, per the layering rule.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from functools import partial
from typing import NamedTuple

from lexic.compile.pipeline.moments import CompileMoments, GrammarMoments
from lexic.compile.pipeline.synthesis import fold_config
from lexic.compile.reduce.fold import ReduceFold
from lexic.compile.reduction import (
    FoldPlan,
    RunSpec,
    SubRun,
    derive_reduction,
    sub_grammar,
)
from lexic.exceptions import UnsupportedConstructError
from lexic.ir import (
    IrAst,
    IrEncoding,
    IrMap,
    IrSelf,
    IrStr,
    IrTokenizer,
    IrTuple,
    IrUnicode,
    Reducer,
    canonicalize,
    concretize,
    inline_refs,
)
from lexic.model import GrammarModel
from lexic.parsing import (
    ModelFold,
    PdaTables,
    TokenMaskCursor,
    parse_model,
    pda_tables,
    token_model,
)
from lexic.parsing.earley.kernel.forest.support.ambiguity import Resolver
from lexic.parsing.parallel import AUTO, anchors, split_model, thread_replica
from lexic.parsing.parallel.orchestrate import Request


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

    :ivar grammar: The canonical grammar AST (what the user's grammar IS —
        the transpile/re-emit source; also the generated module's GRAMMAR).
    :ivar fold: The positional ParseTree → model-instance fold.
    :ivar moments: Every stage this compilation passed through — the grammar
        states, the binding view, the classes. Retained rather than recomputed:
        the pipeline built each one anyway, so a caller that wants to see the
        compilation asks the artefact instead of running it again.
    :ivar flavour: The source flavour's name (drives the export docstrings).
    :ivar stem: The grammar stem (file stem / content-hash stem) — the
        exported module's default identity.
    :ivar tokens: What this grammar knows about tokens — the bound vocabulary
        and whether the grammar segments. See :class:`TokenBinding`.
    """

    grammar: IrAst
    fold: ModelFold[GrammarModel]
    moments: CompileMoments
    flavour: str = "gbnf"
    stem: str = "grammar"
    tokens: TokenBinding = TokenBinding()

    @property
    def classes(self) -> dict[str, type]:
        """Generated model classes by class name — the compilation's last moment.

        Read off :attr:`moments` rather than stored beside it: two copies of
        one answer is a drift surface, and the moments already ARE the answer.
        """
        return self.moments.classes

    @property
    def codegen_grammar(self) -> IrAst:
        """The post-pass codegen grammar the fold binds against.

        The engine key :meth:`parse` hands to
        :func:`~lexic.parsing.parse_model` (the engine memoises its lifted /
        normalised / PDA / run-collapsed compilation per this grammar's
        identity) — and the moments' ``resolved`` state, by definition.
        """
        return self.moments.grammar.resolved

    def anchors(self) -> frozenset[str]:
        """The grammar's structural anchor characters — provable split points.

        A character no opaque interior (co-finite class, token terminal)
        can emit and no derived run charset contains is structural at every
        occurrence in valid input — a local scan cannot be fooled. Derived
        from the codegen grammar (the form the engine parses) and memoised
        with it by the engine's analysis; the per-site hypothesis map is
        :func:`lexic.parsing.parallel.anchor_sites`.

        :returns: The anchor characters; empty when the grammar admits no
            provable split point — the cue for sequential processing.
        """
        return anchors(self.codegen_grammar)

    def parse(
        self, text: str, resolve: Resolver | None = None, cores: int = AUTO
    ) -> GrammarModel:
        """Parse text against the compiled grammar and return a model instance.

        **Splitting is a question about the grammar, asked before the route.**
        When the analysis finds a cut plan (a repetition whose units the
        derived anchors can separate) and ``cores`` allows more than one
        worker, the input is split, the chunks parsed concurrently, and the
        result stitched into the very model a sequential parse would build.
        A segmented grammar never yields a plan — its terminals match ids,
        so no character is structural — and neither does an unsupported
        shape, a short input, or a failing chunk; each of those simply
        parses sequentially below. ``cores=1`` says so outright.

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
        :param cores: 0 (default) = split across as many workers as this
            machine allows, 1 = parse sequentially, N = at most N workers.
        :raises UnsupportedConstructError: If ``text`` does not parse, the fold
            produced no model for the start rule, or the input means two things
            and no resolver was supplied.
        """
        tok = self.tokens.tokenizer
        self._needs_vocabulary()
        # Splitting is asked FIRST and of the grammar alone: whether the
        # input is split has nothing to do with which route reads it. A
        # segmented grammar simply never yields a plan (its terminals are
        # alphabet atoms, so no character is structural), which is the
        # analysis saying so rather than this branch assuming it.
        split = split_model(
            parse_model,
            self.codegen_grammar,
            Request(text, self.fold, resolve),
            cores,
        )
        if split is not None:
            return GrammarModel.ensure(split, "compile: the start rule's fold")
        if tok is not None and self.tokens.segmented:
            bounds = {
                start: (tid, end - start) for start, end, tid in tok.boundaries(text)
            }
            return GrammarModel.ensure(
                token_model(self.codegen_grammar, text, self.fold, bounds, resolve),
                "compile: the start rule's fold",
            )
        # Concurrent whole-document parses contend on one artefact's tables
        # exactly as chunk workers do, so a thread parses against its own
        # replica. Sequential callers and GIL builds get the original pair.
        grammar, fold = thread_replica(self.codegen_grammar, self.fold)
        return GrammarModel.ensure(
            parse_model(grammar, text, fold, resolve),
            "compile: the start rule's fold",
        )

    def _needs_vocabulary(self) -> None:
        """Refuse, with words, a grammar whose terminals name an encoding.

        Both the parse seam and the compiled-table seam reach the engine, and
        both are unusable until a vocabulary is bound — so both say the same
        sentence. Without this the table seam surfaced the dispatcher's own
        miss (``IrTypeMap: no entry for IrAlphabet``), which names an internal
        table rather than the thing the caller must do.

        :raises UnsupportedConstructError: When the grammar is token-segmented
            and no tokenizer is bound.
        """
        if self.tokens.segmented and self.tokens.tokenizer is None:
            raise UnsupportedConstructError(
                "compile: this grammar's terminals name an encoding, so "
                "parsing needs a vocabulary — compile with tokenizer= or "
                "registry=, or bind one. (Reading and emitting it needs none.)"
            )

    def reduce(self, text: str, reducer: Reducer, *, cores: int = AUTO) -> IrSelf:
        """Parse ``text`` and fold it to ``reducer``'s value — the reduce product.

        The reducer's declarations derive an ``@lexical`` variant of this
        grammar (memoised per artefact + reducer pair): DROP subtrees
        collapse to text nodes, span-valued rules keep their text, and
        repetition runs whose values are their text hoist to marked run
        rules. The variant's parse builds the PRUNED model, and a thin fold
        over the binding view rebuilds each remaining rule's reduce channel
        and applies its body. A grammar the derivation cannot touch still
        reduces — the variant is then the grammar itself and the fold walks
        the full model.

        Ambiguity is refused exactly as in :meth:`parse` (the variant's
        language is this grammar's). A refusing reducer body (``IrRaise``)
        refuses here at fold time, with the same exception it raises fused.

        :param text: The input to reduce.
        :param reducer: The grammar's reduction policy.
        :param cores: 0 (default) = split when the variant's analysis allows,
            1 = parse sequentially, N = at most N workers.
        :returns: The reduction — whatever the start rule's body builds.
        :raises UnsupportedConstructError: If ``text`` does not parse, or a
            reducer body refuses.
        """
        if not isinstance(reducer, Reducer):
            raise UnsupportedConstructError(
                f"compile: reducer is {type(reducer).__name__!r}, not a Reducer"
            )
        entry = _reduce_entry(self, reducer)
        model = entry.variant.parse(text, cores=cores)
        return entry.fold.reduce(model)

    def pda_tables(self) -> PdaTables:
        """The predictive engine's compiled tables for this artefact.

        Reaches the engine's identity-memoised instance product for
        ``(codegen_grammar, fold)`` — this artefact holds the exact objects
        the memo is keyed by, so the tables returned are the very ones
        :meth:`parse` drives: hot if this grammar has parsed already,
        compiled once and shared forward if not.

        :returns: The compiled :class:`~lexic.parsing.PdaTables`.
        :raises UnsupportedConstructError: When the grammar's terminals name an
            encoding and no vocabulary is bound — the same refusal
            :meth:`parse` gives, in the same words.
        """
        self._needs_vocabulary()
        return pda_tables(self.codegen_grammar, self.fold)

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
        codegen_grammar = source if resolved is None else concretize(source, resolved)
        # Only the LAST grammar moment moves: rebinding re-resolves the
        # authored form and reuses everything the resolution cannot change.
        grammar_moments = GrammarMoments(
            *self.moments.grammar[:-1], resolved=codegen_grammar
        )
        return CompiledGrammar(
            grammar=self.grammar,
            fold=self.fold,
            moments=CompileMoments(
                grammar_moments, self.moments.binding, self.moments.classes
            ),
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


class _ReduceEntry(NamedTuple):
    """One artefact + reducer pair's derived reduce machinery.

    Pins ``source`` and ``reducer`` live so the ``id``-keyed cache entry can
    never be re-served to a different object at a recycled address.

    :ivar source: The artefact the derivation started from.
    :ivar reducer: The reducer the variant was derived for.
    :ivar variant: The derived ``@lexical`` variant artefact the parse runs on.
    :ivar fold: The thin fold from the variant's pruned model to the value.
    """

    source: CompiledGrammar
    reducer: Reducer
    variant: CompiledGrammar
    fold: ReduceFold


_REDUCE_ENTRIES: dict[tuple[int, int], _ReduceEntry] = {}


def reset_reduction_cache() -> None:
    """Test seam: clear the artefact + reducer derived-variant memo."""
    _REDUCE_ENTRIES.clear()


def _variant_artifact(
    compiled: CompiledGrammar, ast: IrAst, tag: str
) -> CompiledGrammar:
    """Assemble a derived variant's artefact — the back half, in miniature.

    Mirrors the compile back half for a grammar that never had text of its
    own: moments from the prepared AST, the fold from the binding view, the
    source artefact's token binding carried over (the variant's language is
    the source's, so its segmentation fact is too).

    :param compiled: The source artefact.
    :param ast: The prepared (canonical, inlined) variant AST.
    :param tag: A short discriminator for the synthetic module identity.
    :returns: The variant artefact.
    """
    registry = encoding_registry(compiled.tokens.tokenizer, None)
    content = hashlib.sha1(repr(ast).encode("utf-8")).hexdigest()[:12]
    moments = CompileMoments.of(ast, registry, f"{compiled.stem}_{tag}_{content}")
    fold = ModelFold(
        fold_config(moments.grammar.resolved, moments.binding, moments.classes)
    )
    return CompiledGrammar(
        grammar=ast,
        fold=fold,
        moments=moments,
        flavour=compiled.flavour,
        stem=compiled.stem,
        tokens=TokenBinding(
            compiled.tokens.tokenizer,
            compiled.tokens.segmented,
            moments.grammar.relaxed,
        ),
    )


def _sub_run(
    compiled: CompiledGrammar, reducer: Reducer, run_name: str, spec: RunSpec
) -> SubRun:
    """A run's escape hatch: its group-named sub-grammar, compiled and folded."""
    ast, synthetic = sub_grammar(compiled.grammar, run_name, spec.element)
    sub = _variant_artifact(compiled, canonicalize(ast), f"reduce_{run_name}")
    fold = ReduceFold(sub.moments, reducer, FoldPlan(synthetic=synthetic))
    return SubRun(partial(sub.parse, cores=1), fold)


def _reduce_entry(compiled: CompiledGrammar, reducer: Reducer) -> _ReduceEntry:
    """The memoised derived machinery for one artefact + reducer pair."""
    key = (id(compiled), id(reducer))
    entry = _REDUCE_ENTRIES.get(key)
    if entry is not None:
        return entry
    derivation = derive_reduction(compiled.grammar, reducer)
    prepared = inline_refs(canonicalize(derivation.variant), derivation.marks)
    variant = _variant_artifact(compiled, prepared, "reduce")
    subs = {
        name: _sub_run(compiled, reducer, name, spec)
        for name, spec in derivation.runs.items()
    }
    fold = ReduceFold(
        variant.moments,
        reducer,
        FoldPlan(runs=derivation.runs, subs=subs, marks=derivation.marks),
    )
    entry = _ReduceEntry(compiled, reducer, variant, fold)
    _REDUCE_ENTRIES[key] = entry
    return entry
