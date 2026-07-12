"""parse_grammar / canonical_grammar / compile_text — grammar entry points.

``parse_grammar(text, flavour)`` is the public grammar-text → ``IrAst`` seam:
the flavour's own self-grammar (Earley-normalised, memoised per flavour)
parses the source and the flavour's ``Reducer`` folds the derivation to IR.

Pipeline (compile_text / compile_from_path — grammar text → CompiledGrammar)::

  text ─► canonical_grammar = parse_grammar + canonicalize + directive flags
                     │            (the canonical AST — start bound,
                     │             noise rules flagged semantic=False)
                     ▼
          build_codegen_grammar   (groups hoisted, arms hoisted, noise
                     │             refs relaxed — lexic.codegen.passes)
                     ▼
             compute_binding ──► codegen  (classes w/ Annotated IrBind
                     │                     fields, __grammar__ footers)
                     ▼
          IR body-table ──► ModelFold (lexic.parsing.fold; bakes to RuleFold)
                     │
                     ▼
   instance grammar = normalize(lift_optional_nullables(codegen_grammar))
   — the SAME normalize as the grammar-text path, so the engine's
   identity-memoised tables are shared shapes; tables are run-collapsed
   under the fold-config licence at build time.

``canonical_grammar(text, flavour)`` is the public front half (parse +
canonicalize + directive flags → flagged ``IrAst``); ``generate.py`` and
transpilers build on it.

Every compiled grammar also carries a predictive PDA sibling
(``lexic.parsing.pda.clones.compile_pda`` → ``PdaTables``, ``None`` on a
whole-grammar opt-out); ``CompiledGrammar.parse`` runs it PDA-first
(``parse_pda``) and falls back to the full engine on any ``PdaFail``, so one
public ``parse`` keeps unchanged semantics.

Runtime seams: lexic.codegen (codegen, build_codegen_grammar,
compute_binding) and the engine (lexic.parsing / .fold / .normalize /
.reduce / .pda.clones / .pda.runtime). compile.py is the single runtime module
importing either; no private-symbol imports cross the seams.
"""

from __future__ import annotations

import hashlib
from collections.abc import Hashable
from dataclasses import dataclass
from pathlib import Path

from lexic.base import GrammarModel
from lexic.codegen import (
    RuleBinding,
    build_codegen_grammar,
    codegen,
    compute_binding,
    resolve_out_dir,
)
from lexic.exceptions import UnsupportedConstructError
from lexic.grammars import flavour_for_extension, get_flavour
from lexic.ir.base import IrLambda, IrNone, IrSeq, IrTuple
from lexic.ir.canonical import canonicalize, fold_name
from lexic.ir.flavour import IrFlavour
from lexic.ir.mapping import IrMap
from lexic.ir.nodes import IrAst, IrRule, IrRuleRef
from lexic.parsing import ParserTables, parse_first, parse_reduced
from lexic.parsing.earley.normalize import normalize
from lexic.parsing.earley.reduce import Reducer
from lexic.parsing.fold import (
    FastCtor,
    FieldFold,
    ModelBody,
    ModelFold,
    RuleFold,
    collapsed_fold_tables,
    lift_optional_nullables,
)
from lexic.parsing.pda.clones import (
    IslandRef,
    PdaTables,
    compile_pda,
    compile_reduce_pda,
)
from lexic.parsing.pda.reduce_runtime import parse_pda
from lexic.parsing.pda.runtime import PdaFail


def _flavour_reducer(flavour: IrFlavour) -> Reducer:
    """The flavour's :class:`Reducer`, narrowed once — the single home for the check.

    :param flavour: The grammar flavour.
    :returns: Its ``reducer`` ClassVar, narrowed to :class:`Reducer`.
    :raises UnsupportedConstructError: When the flavour carries no ``Reducer``.
    """
    reducer = flavour.reducer
    if not isinstance(reducer, Reducer):
        raise UnsupportedConstructError(
            f"compile: flavour {flavour.name!r} carries no parse Reducer"
        )
    return reducer


@dataclass(frozen=True)
class _ParseRoute:
    """The one internal parse seam: PDA-first, then a per-path Earley completion.

    ``pda_first`` is the routing **policy datum** (not a code-path fork): the
    PDA attempt is identical across paths (``parse_pda`` dispatches model vs
    reduce on ``tables.reduce``); :meth:`earley` — the fallback completion — is
    the sole per-path difference. Both paths are PDA-first since the Task-7
    flip (2026-07-12).

    :ivar pda: The predictive PDA, or ``None`` (engine-only).
    :ivar pda_first: Whether to try the PDA before the Earley completion.
    """

    pda: PdaTables | None
    pda_first: bool

    def run(self, text: str) -> object:
        """Parse ``text``: PDA-first when routed, else the Earley completion."""
        if self.pda_first and self.pda is not None:
            try:
                return parse_pda(self.pda, text, self._pda_fold())
            except PdaFail:
                pass  # deterministic parse failed → whole-input engine reparse
        return self.earley(text)

    def _pda_fold(self) -> ModelFold | None:
        """The fold ``parse_pda`` splices island sub-models through (``None`` = reduce)."""
        return None

    def earley(self, text: str) -> object:
        """The path's whole-input Earley completion (subclass responsibility)."""
        raise NotImplementedError


@dataclass(frozen=True)
class _ModelRoute(_ParseRoute):
    """Instance path: PDA-first + Earley (``parse_first`` → positional fold) fallback.

    :ivar grammar: The Earley-normalised instance grammar.
    :ivar tables: Its run-collapsed tables.
    :ivar fold: The positional ParseTree → model fold.
    """

    grammar: IrAst
    tables: ParserTables
    fold: ModelFold

    def _pda_fold(self) -> ModelFold | None:
        return self.fold

    def earley(self, text: str) -> object:
        return self.fold.apply(parse_first(self.grammar, text, self.tables))


@dataclass(frozen=True)
class _ReduceRoute(_ParseRoute):
    """Grammar-text path: PDA-first (Task 7 flip), ``parse_reduced`` completion.

    The two sides deliberately run *different* normalised grammars: the PDA
    (from :func:`self_grammar_pda`) is compiled over
    ``normalize(lift_optional_nullables(flavour.grammar))``, the Earley
    completion over ``normalize(flavour.grammar)`` (un-lifted) — each side
    internally consistent, reductions keyed by rule name. The one structural
    divergence class is the ε-channel (a lifted nullable ``R`` from ``R?``
    runs its reduction on empty children where the un-lifted route skips the
    node); the authored reduce bodies absorb it, and the Task-7 differential
    sweep (whole corpus + adversarial battery, byte-equal IrAst) is the
    standing guard. See ``REVIEW_PRE7.md`` finding 4 in the plan dir.

    :ivar grammar: The Earley-normalised (un-lifted) self-grammar.
    :ivar reducer: The flavour's reduction policy.
    """

    grammar: IrAst
    reducer: Reducer

    def earley(self, text: str) -> object:
        return parse_reduced(self.grammar, text, self.reducer)


@dataclass(frozen=True)
class CompiledGrammar:
    """Parse-ready artefacts produced by compile().

    :ivar classes: Generated model classes by class name.
    :ivar grammar: The canonical grammar AST (what the user's grammar IS —
        the transpile/re-emit source; also the generated module's GRAMMAR).
    :ivar instance_grammar: The Earley-normalised instance grammar (held so
        the engine's identity-memoised table compilation stays hot).
    :ivar fold: The positional ParseTree → model-instance fold.
    :ivar tables: The instance grammar's run-collapsed tables — every lexical
        run the fold-config licence proves safe steps in one scan (compiled
        once at build time; see
        :func:`~lexic.parsing.fold.collapsed_fold_tables`).
    :ivar pda: The predictive PDA sibling (:class:`~lexic.parsing.pda.clones.PdaTables`),
        or ``None`` on a whole-grammar opt-out — an unsupported construct or a
        start rule that is itself an island. When present, :meth:`parse` runs it
        first and falls back to the engine on :class:`~lexic.parsing.pda.runtime.PdaFail`.
    """

    classes: dict[str, type]
    grammar: IrAst
    instance_grammar: IrAst
    fold: ModelFold
    tables: ParserTables
    pda: PdaTables | None = None

    def parse(self, text: str) -> GrammarModel:
        """Parse text against the compiled grammar and return a model instance.

        Runs the predictive PDA first when one is compiled; a
        :class:`~lexic.parsing.pda.runtime.PdaFail` (any non-deterministic point
        or unresolved island) falls back to a whole-input engine reparse, which
        owns the user-facing diagnostics.

        :raises UnsupportedConstructError: If ``text`` does not parse, or the
            fold produced no model for the start rule.
        """
        route = _ModelRoute(
            self.pda, True, self.instance_grammar, self.tables, self.fold
        )
        return self._ensure_model(route.run(text))

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


_CACHE: dict[Hashable, CompiledGrammar] = {}

_NORM_GRAMMAR_CACHE: dict[str, IrAst] = {}

_SELF_PDA_CACHE: dict[str, PdaTables | None] = {}


def reset_cache_for_tests() -> None:
    """Public test seam: clear the compile cache."""
    _CACHE.clear()


def self_grammar_pda(flavour: IrFlavour) -> PdaTables | None:
    """The flavour's self-grammar reduce PDA (grammar-text path), cached per name.

    Compiles a predictive PDA for ``flavour.grammar`` whose completion feeds the
    flavour's :class:`~lexic.parsing.earley.reduce.Reducer` bodies (b1 — no
    intermediate ParseTree), over the reducer's *own* grammar (``flavour.grammar``
    lifted + normalised, so rule names match the reducer's reductions — never the
    codegen-hoisted shape). ``None`` on a whole-grammar opt-out — an unsupported
    construct, or a start rule that is itself an island (ABNF ``rulelist`` today).

    Routed PDA-first by :func:`parse_grammar` since the Task-7 flip
    (2026-07-12); the b1 capture runs end-to-end (island splices reduce
    through the same :class:`Reducer`). A flavour whose grammar opts out
    returns ``None`` and stays on the engine path.

    :param flavour: The grammar flavour.
    :returns: The compiled reduce :class:`PdaTables`, or ``None`` on an opt-out.
    """
    key = flavour.name
    if key in _SELF_PDA_CACHE:
        return _SELF_PDA_CACHE[key]
    reducer = _flavour_reducer(flavour)
    lifted = lift_optional_nullables(flavour.grammar)
    instance_grammar = normalize(lifted)
    try:
        pda: PdaTables | None = compile_reduce_pda(lifted, instance_grammar, reducer)
    except UnsupportedConstructError:
        pda = None
    else:
        if isinstance(pda.start_key, IslandRef):
            pda = None  # start rule is itself an island — whole-grammar opt-out
    _SELF_PDA_CACHE[key] = pda
    return pda


def _normalized_grammar(flavour: IrFlavour) -> IrAst:
    """Return the flavour's Earley-normalised self-grammar, memoised by name.

    The identity of the returned :class:`IrAst` is stable across calls, so the
    engine's object-identity table memoisation (``compile_tables``) stays hot.

    :param flavour: The grammar flavour whose ``grammar`` ClassVar to normalise.
    :returns: The normalised self-grammar.
    """
    cached = _NORM_GRAMMAR_CACHE.get(flavour.name)
    if cached is None:
        cached = normalize(flavour.grammar)
        _NORM_GRAMMAR_CACHE[flavour.name] = cached
    return cached


def parse_grammar(text: str, flavour: IrFlavour) -> IrAst:
    """Parse grammar source into its IR AST via the flavour's engine path.

    :param text: Grammar source in ``flavour``'s syntax.
    :param flavour: The grammar flavour (e.g. ``GBNF_FLAVOUR``).
    :returns: The reduced grammar AST.
    :raises UnsupportedConstructError: If the flavour carries no ``Reducer``,
        ``text`` does not parse, or the reduction is not an ``IrAst``.
    """
    reducer = _flavour_reducer(flavour)
    route = _ReduceRoute(
        self_grammar_pda(flavour), True, _normalized_grammar(flavour), reducer
    )
    ast = route.run(text)
    if not isinstance(ast, IrAst):
        raise UnsupportedConstructError(
            f"compile: flavour {flavour.name!r} reduction produced "
            f"{type(ast).__name__!r}, not an IrAst"
        )
    return ast


def _stem_for_text(text: str) -> str:
    """Stable filename for a grammar string with no path."""
    return "anon_" + hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


def _scan_directives(text: str, line_comment: str) -> tuple[str | None, frozenset[str]]:
    """Extract ``(start, non_semantic)`` from source comments — a pre-lexical scan.

    A line ``<line_comment> @<name> <args...>`` declares a directive: ``@start
    <rule>`` overrides the start rule, ``@non-semantic <rule> ...`` names
    structural-noise rules. The scan reads the raw source before the parser so
    comments never become load-bearing grammar tokens; ``canonical_grammar``
    resolves precedence and applies the result to the AST.

    :param text: Grammar source text.
    :param line_comment: The flavour's line-comment marker (``#``/``;``); empty
        disables directive parsing.
    :returns: ``(start, non_semantic)`` — ``start`` is the ``@start`` rule name
        or ``None``; ``non_semantic`` is the set of ``@non-semantic`` names.
    """
    if not line_comment:
        return None, frozenset()
    non_semantic: set[str] = set()
    start_rule: str | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line.startswith(line_comment):
            continue
        rest = line[len(line_comment) :].lstrip()
        if not rest.startswith("@"):
            continue
        parts = rest[1:].split()
        if not parts:
            continue
        name, *args = parts
        if name == "non-semantic":
            non_semantic.update(args)
        elif name == "start" and args:
            start_rule = args[0]  # last @start wins on duplicates
    return start_rule, frozenset(non_semantic)


def canonical_grammar(
    text: str,
    flavour: IrFlavour,
    *,
    non_semantic_rules: frozenset[str] | None = None,
    start: str | None = None,
) -> IrAst:
    """Parse + canonicalize + bind directive flags — the compile front half.

    `start` resolution precedence:
      1. explicit `start` argument
      2. `@start <rule>` directive in source comments
      3. `ast.rules[0].name` (positional fallback)

    `non_semantic_rules` resolution:
      1. explicit `non_semantic_rules` argument
      2. `@non-semantic <rule> ...` directives in source comments

    The resolved `start` is bound onto the canonical IrAst (the AST is rebuilt
    — it is frozen), and each rule the resolved non-semantic set names is
    reconstructed with `semantic=False` (`ast.non_semantic` derives from the
    flags). A directive naming a rule the grammar never defines is silently
    ignored: no rule is flagged for it.

    Errors: malformed grammar source bubbles up as UnsupportedConstructError
    (raised by the engine / reducer, or here if the flavour carries no Reducer,
    its reduction does not yield an IrAst, or the start rule is undefined).
    """
    dir_start, dir_non_semantic = _scan_directives(text, flavour.line_comment)
    if non_semantic_rules is None:
        non_semantic_rules = dir_non_semantic
    parsed = parse_grammar(text, flavour)
    raw_start = start or dir_start or (parsed.rules[0].name if parsed.rules else "")
    ast = canonicalize(IrAst(rules=parsed.rules, start=raw_start))
    start = ast.start  # canonicalize folds names; directive/arg names fold too
    if start and not any(r.name == start for r in ast.rules):
        raise UnsupportedConstructError(
            f"start rule {start!r} not defined in grammar; "
            f"available rules: {[r.name for r in ast.rules]}"
        )
    folded_non_semantic = frozenset(fold_name(n) for n in non_semantic_rules)
    rules = IrSeq(
        *(
            IrRule(r.name, r.body, False) if r.name in folded_non_semantic else r
            for r in ast.rules
        )
    )
    return IrAst(rules=rules, start=start)


def _fast_ctor(cls: type, kind: str, fields: tuple[FieldFold, ...]) -> FastCtor | None:
    """Grant a rule's :class:`~lexic.parsing.fold.FastCtor` licence, or refuse.

    The class-level half comes from :meth:`GrammarModel.fast_construct`
    (no validators / post-init / config / non-``None`` defaults); the
    fold-level half checks that every field the fold can leave unset (a
    ``gtext`` or ``model`` bind whose item can match nothing, ``lo == 0``)
    has a default to fall back on, and that the fold's field names cover
    every non-defaulted model field.

    :param cls: The rule's generated model class.
    :param kind: The rule's fold kind.
    :param fields: The rule's bound fields.
    :returns: The licence, or ``None`` (validated construction only).
    """
    if kind == "alternation" or not issubclass(cls, GrammarModel):
        return None
    parts = cls.fast_construct()
    if parts is None:
        return None
    make, defaults = parts
    names = {"value"} if kind == "value_str" else {f.name for f in fields}
    model_names = set(cls.model_fields)
    if not names <= model_names:
        return None
    if any(n not in names and n not in defaults for n in model_names):
        return None
    for field in fields:
        skippable = field.mode in ("gtext", "model") and field.lo == 0
        if skippable and field.name not in defaults:
            return None
    return FastCtor(make, defaults)


def _fold_config(
    codegen_grammar: IrAst, binding: list[RuleBinding], classes: dict[str, type]
) -> IrMap:
    """Build the fold's IR body-table from the binding view + classes.

    Per rule a :class:`~lexic.parsing.fold.ModelBody`: kind from the binding,
    the model constructor wrapped in :class:`~lexic.ir.base.IrLambda`
    (:data:`~lexic.ir.base.IrNone` for an ``alternation``, which has none),
    ``n_items`` from the codegen grammar's single non-empty sequence arm, and
    one :class:`~lexic.parsing.fold.FieldFold` per bound field (`lo` read from
    the bound item's quantifier — consumed by the ``gtext`` absence rule).

    :param codegen_grammar: The post-pass grammar the binding was computed on.
    :param binding: The binding view, in emission order.
    :param classes: Generated classes by class name.
    :returns: An :class:`~lexic.ir.mapping.IrMap` from each rule's
        :class:`~lexic.ir.nodes.IrRuleRef` to its
        :class:`~lexic.parsing.fold.ModelBody`.
    """
    rules = {str(rule.name): rule for rule in codegen_grammar.rules}
    dyads: list[IrTuple] = []
    for bound in binding:
        arms = [arm for arm in rules[bound.rule_name].body if arm]
        items = arms[0] if bound.kind == "sequence" and arms else ()
        fields = tuple(
            FieldFold(bind.item, bind.mode, name, int(items[bind.item].quantifier.lo))
            for name, bind in bound.fields.items()
        )
        cls = classes[bound.class_name]
        ctor = IrNone if bound.kind == "alternation" else IrLambda(cls)
        body = ModelBody(
            bound.kind, ctor, len(items), fields, _fast_ctor(cls, bound.kind, fields)
        )
        dyads.append(IrTuple(IrRuleRef(bound.rule_name), body))
    return IrMap(*dyads)


def _build_pda(
    lifted: IrAst, instance_grammar: IrAst, fold_config: dict[str, RuleFold]
) -> PdaTables | None:
    """Compile the predictive PDA sibling, or opt the whole grammar out.

    Returns ``None`` (engine-only) in the two whole-grammar opt-out cases: the
    analysis / clone compiler hits a construct it cannot handle
    (:exc:`UnsupportedConstructError`), or the start rule is itself an island
    (its ``start_key`` is an :class:`~lexic.parsing.pda.clones.IslandRef`, so
    :func:`~lexic.parsing.pda.runtime.parse_pda` would ``PdaFail`` on every
    input). Otherwise the compiled tables drive the PDA-first parse path.

    :param lifted: The lifted-but-unnormalised codegen grammar the analysis and
        clones are cut against (``lift_optional_nullables(codegen_grammar)``).
    :param instance_grammar: The Earley-normalised instance grammar the island
        sub-parses run over (``normalize(lifted)``).
    :param fold_config: Rule name → its :class:`~lexic.parsing.fold.RuleFold`,
        baked into each rule clone.
    :returns: The compiled :class:`PdaTables`, or ``None`` on an opt-out.
    """
    try:
        tables = compile_pda(lifted, instance_grammar, fold_config)
    except UnsupportedConstructError:
        return None
    return None if isinstance(tables.start_key, IslandRef) else tables


def _compile_core(
    text: str, *, stem: str, flavour: str = "gbnf", out_dir: str | Path | None = None
) -> CompiledGrammar:
    flavour_cls = get_flavour(flavour)
    ast = canonical_grammar(text, flavour_cls)
    codegen_grammar = build_codegen_grammar(ast)
    binding = compute_binding(codegen_grammar)
    classes = codegen(ast, codegen_grammar, binding, stem, out_dir)
    fold = ModelFold(_fold_config(codegen_grammar, binding, classes))
    lifted = lift_optional_nullables(codegen_grammar)
    instance_grammar = normalize(lifted)
    pda = _build_pda(lifted, instance_grammar, fold.baked)
    return CompiledGrammar(
        classes=classes,
        grammar=ast,
        instance_grammar=instance_grammar,
        fold=fold,
        tables=collapsed_fold_tables(instance_grammar, fold),
        pda=pda,
    )


def compile_text(
    text: str,
    *,
    cache_key: Hashable | None = None,
    flavour: str = "gbnf",
    out_dir: str | Path | None = None,
) -> CompiledGrammar:
    """Compile from a grammar string, memoised by content by default.

    The default cache key is ``(content sha stem, flavour, resolved out_dir)``
    — compiling the same source in the same flavour to the same output
    directory returns the cached :class:`CompiledGrammar` (and its class
    objects). Pass ``cache_key`` to override the key (an explicit key is used
    as-is, not augmented with ``out_dir``); the test seam
    :func:`reset_cache_for_tests` clears the cache when a caller needs fresh
    class objects.

    :param text: Grammar source in ``flavour``'s syntax.
    :param cache_key: Explicit memo key; ``None`` uses the content default.
    :param flavour: The grammar flavour name.
    :param out_dir: Directory the generated module is written to; ``None``
        resolves to the project's ``generated/`` directory.
    :returns: The compiled grammar (cached across calls with the same key).
    """
    stem = _stem_for_text(text)
    resolved_out_dir = str(resolve_out_dir(out_dir).resolve())
    key = cache_key if cache_key is not None else (stem, flavour, resolved_out_dir)
    cached = _CACHE.get(key)
    if cached is not None:
        return cached
    cg = _compile_core(text, stem=stem, flavour=flavour, out_dir=out_dir)
    _CACHE[key] = cg
    return cg


def compile_from_path(
    grammar_path: str | Path,
    *,
    flavour: str | None = None,
    out_dir: str | Path | None = None,
) -> CompiledGrammar:
    """Compile from a file path; memoised by (path, mtime, size, flavour, out_dir).

    :param grammar_path: Path to the grammar source file.
    :param flavour: The grammar flavour name; inferred from the file
        extension if omitted.
    :param out_dir: Directory the generated module is written to; ``None``
        resolves to the project's ``generated/`` directory.
    :returns: The compiled grammar (cached across calls with the same key).
    """
    path = Path(grammar_path).resolve()
    stat = path.stat()
    if flavour is None:
        flavour = flavour_for_extension(path).name
    resolved_out_dir = str(resolve_out_dir(out_dir).resolve())
    key = (str(path), stat.st_mtime, stat.st_size, flavour, resolved_out_dir)
    cached = _CACHE.get(key)
    if cached is not None:
        return cached
    text = path.read_text(encoding="utf-8")
    cg = _compile_core(text, stem=path.stem, flavour=flavour, out_dir=out_dir)
    _CACHE[key] = cg
    return cg
