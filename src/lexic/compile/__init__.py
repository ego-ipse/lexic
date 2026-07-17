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
                     │             refs relaxed — lexic.compile.passes)
                     ▼
             compute_binding ──► synthesize  (record classes built at
                     │                        runtime — __grammar__ + __binds__,
                     │                        no source emit, no file write)
                     ▼
          IR body-table ──► ModelFold (bakes to the runtime fold records)

``canonical_grammar(text, flavour)`` is the public front half (parse +
canonicalize + directive flags → flagged ``IrAst``); ``generate.py`` and
transpilers build on it.

``CompiledGrammar`` carries the codegen grammar + its fold; ``parse`` hands
them to the engine's ``parse_model`` product, and ``parse_grammar`` hands the
flavour's authored self-grammar + reducer to ``parse_reduced``. Both products
own the whole PDA-first-→-Earley-completion pipeline internally (lifting,
normalisation, PDA/table compilation, memoisation) — one public call each, no
predictive-PDA sibling on the artefact and no whole-grammar opt-out.

The grammar→grammar passes, the binding view and runtime class synthesis all
live inside this package (``lexic.compile.passes`` / ``.binding`` /
``.synthesis``). The only external runtime seam is the engine (``lexic.parsing``
— root API only: ``parse_model`` / ``parse_reduced`` / ``ModelFold`` +
fold-authoring types / ``Reducer``); ``compile/__init__.py`` is the single
runtime module importing it, and imports the ``lexic.parsing`` package root
only, no submodule or private name.
"""

from __future__ import annotations

import hashlib
from collections.abc import Hashable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from lexic.base import GrammarModel
from lexic.compile.binding import (
    RuleBinding,
    check_supplied_class,
    compute_binding,
    field_kwargs,
)
from lexic.compile.notation import load_ir, load_ir_from_path
from lexic.compile.passes import build_codegen_grammar
from lexic.compile.synthesis import synthesize
from lexic.exceptions import UnsupportedConstructError
from lexic.grammars import flavour_for_extension, get_flavour
from lexic.ir.base import IrLambda, IrNone, IrSeq, IrTuple
from lexic.ir.canonical import canonicalize, fold_name
from lexic.ir.flavour import IrFlavour
from lexic.ir.mapping import IrMap
from lexic.ir.nodes import IrAst, IrItem, IrRule, IrRuleRef
from lexic.parsing import (
    FastCtor,
    FieldFold,
    ModelBody,
    ModelFold,
    Reducer,
    parse_model,
    parse_reduced,
)

__all__ = [
    "CompiledGrammar",
    "canonical_grammar",
    "compile_from_path",
    "compile_text",
    "load_ir",
    "load_ir_from_path",
    "parse_grammar",
    "reset_cache_for_tests",
]


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
    """

    classes: dict[str, type]
    grammar: IrAst
    codegen_grammar: IrAst
    fold: ModelFold[GrammarModel]

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


_CACHE: dict[Hashable, CompiledGrammar] = {}


def reset_cache_for_tests() -> None:
    """Public test seam: clear the compile cache."""
    _CACHE.clear()


def parse_grammar(text: str, flavour: IrFlavour) -> IrAst:
    """Parse grammar source into its IR AST via the flavour's engine path.

    Delegates to the engine's :func:`~lexic.parsing.parse_reduced` product over
    the flavour's authored self-grammar and its :class:`Reducer` (PDA-first,
    Earley reduce completion inside the engine, memoised per flavour identity).

    :param text: Grammar source in ``flavour``'s syntax.
    :param flavour: The grammar flavour (e.g. ``GBNF_FLAVOUR``).
    :returns: The reduced grammar :class:`IrAst`.
    :raises UnsupportedConstructError: If the flavour carries no ``Reducer``,
        ``text`` does not parse, or the reduction is not an ``IrAst``.
    """
    reducer = _flavour_reducer(flavour)
    return parse_reduced(flavour.grammar, text, reducer)


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
    (trivially granted on the record spine); the fold-level half checks
    that every field the fold can leave unset (a ``gtext`` or ``model``
    bind whose item can match nothing, ``lo == 0``) has a default to fall
    back on, and that the fold's field names cover every non-defaulted
    model field.

    :param cls: The rule's generated model class.
    :param kind: The rule's fold kind.
    :param fields: The rule's bound fields.
    :returns: The licence, or ``None`` (validated construction only).
    """
    if kind == "alternation" or not issubclass(cls, GrammarModel):
        return None
    make, defaults = cls.fast_construct()
    names = {"value"} if kind == "value_str" else {f.name for f in fields}
    model_names = set(cls._fields)
    if not names <= model_names:
        return None
    if any(n not in names and n not in defaults for n in model_names):
        return None
    for field in fields:
        skippable = field.mode in ("gtext", "model") and field.lo == 0
        if skippable and field.name not in defaults:
            return None
    return FastCtor(make, defaults)


def _derive_body(bound: RuleBinding, cls: type, items: Sequence[IrItem]) -> ModelBody:
    """Derive a rule's :class:`~lexic.parsing.fold.ModelBody` from a supplied class.

    The supplied-class sugar of the open binding table (settled 7): the class
    is the fold constructor, and the body's structural metadata comes from the
    binding view + the codegen grammar's sequence arm.

    :param bound: The rule's binding view.
    :param cls: The supplied constructor class.
    :param items: The rule's single non-empty sequence arm (empty otherwise).
    :returns: The rule's fold body.
    """
    fields = tuple(
        FieldFold(bind.item, bind.mode, name, int(items[bind.item].quantifier.lo))
        for name, bind in bound.fields.items()
    )
    if bound.kind == "alternation":
        return ModelBody("alternation", IrNone, len(items), fields, None)
    return ModelBody(
        bound.kind,
        IrLambda(cls),
        len(items),
        fields,
        _fast_ctor(cls, bound.kind, fields),
    )


def _fold_config(
    codegen_grammar: IrAst,
    binding: list[RuleBinding],
    classes: dict[str, type],
    overrides: Mapping[str, ModelBody | type] | None = None,
) -> IrMap:
    """Build the fold's IR body-table from the binding view — the open table.

    Per rule the compile seam accepts EITHER a full authored
    :class:`~lexic.parsing.fold.ModelBody` (the primitive — used verbatim) OR a
    class serving as the fold constructor (the sugar — :func:`_derive_body`
    builds the body from the binding view). With no ``overrides`` entry a rule
    falls back to its synthesized class (also a supplied class). ``kind`` /
    ``n_items`` / ``FieldFold``\\ s all come from the codegen grammar's single
    non-empty sequence arm (``lo`` from the bound item's quantifier, consumed by
    the ``gtext`` absence rule).

    :param codegen_grammar: The post-pass grammar the binding was computed on.
    :param binding: The binding view, in emission order.
    :param classes: Generated classes by class name.
    :param overrides: Per-rule fold-body override — a
        :class:`~lexic.parsing.fold.ModelBody` (primitive) or a constructor
        class (sugar); ``None`` uses the synthesized classes throughout.
    :returns: An :class:`~lexic.ir.mapping.IrMap` from each rule's
        :class:`~lexic.ir.nodes.IrRuleRef` to its
        :class:`~lexic.parsing.fold.ModelBody`.
    """
    overrides = overrides or {}
    rules = {str(rule.name): rule for rule in codegen_grammar.rules}
    dyads: list[IrTuple] = []
    for bound in binding:
        override = overrides.get(bound.rule_name)
        if isinstance(override, ModelBody):
            dyads.append(IrTuple(IrRuleRef(bound.rule_name), override))
            continue
        arms = [arm for arm in rules[bound.rule_name].body if arm]
        items = arms[0] if bound.kind == "sequence" and arms else ()
        if override is not None:  # a supplied class (sugar) — enforce the contract
            check_supplied_class(override, field_kwargs(bound))
            cls = override
        else:  # the trusted synthesized class
            cls = classes[bound.class_name]
        body = _derive_body(bound, cls, items)
        dyads.append(IrTuple(IrRuleRef(bound.rule_name), body))
    return IrMap(*dyads)


def _compile_core(text: str, *, stem: str, flavour: str = "gbnf") -> CompiledGrammar:
    flavour_cls = get_flavour(flavour)
    ast = canonical_grammar(text, flavour_cls)
    codegen_grammar = build_codegen_grammar(ast)
    binding = compute_binding(codegen_grammar)
    classes = synthesize(codegen_grammar, binding, stem)
    fold = ModelFold(_fold_config(codegen_grammar, binding, classes))
    return CompiledGrammar(
        classes=classes,
        grammar=ast,
        codegen_grammar=codegen_grammar,
        fold=fold,
    )


def compile_text(
    text: str,
    *,
    cache_key: Hashable | None = None,
    flavour: str = "gbnf",
) -> CompiledGrammar:
    """Compile from a grammar string, memoised by content by default.

    The cache key is ``(content sha stem, flavour)`` — compiling the same
    source in the same flavour returns the cached :class:`CompiledGrammar`
    (and its class objects; synthesis writes no files, so there is no output
    directory to key on). An explicit ``cache_key`` is *prepended* to that
    content key rather than used as-is: ``(cache_key, stem, flavour)``.
    Folding the content stem in means the same key can never serve a stale
    grammar — different source text under one ``cache_key`` yields distinct
    entries, while identical text still hits the memo. The test seam
    :func:`reset_cache_for_tests` clears the cache when a caller needs fresh
    class objects.

    :param text: Grammar source in ``flavour``'s syntax.
    :param cache_key: Extra key prefix disambiguating otherwise-identical
        compilations; ``None`` uses the content key alone.
    :param flavour: The grammar flavour name.
    :returns: The compiled grammar (cached across calls with the same key).
    """
    stem = _stem_for_text(text)
    content_key = (stem, flavour)
    key = (cache_key, *content_key) if cache_key is not None else content_key
    cached = _CACHE.get(key)
    if cached is not None:
        return cached
    cg = _compile_core(text, stem=stem, flavour=flavour)
    _CACHE[key] = cg
    return cg


def compile_from_path(
    grammar_path: str | Path,
    *,
    flavour: str | None = None,
) -> CompiledGrammar:
    """Compile from a file path; memoised by (path, mtime, size, flavour).

    :param grammar_path: Path to the grammar source file.
    :param flavour: The grammar flavour name; inferred from the file
        extension if omitted.
    :returns: The compiled grammar (cached across calls with the same key).
    """
    path = Path(grammar_path).resolve()
    stat = path.stat()
    if flavour is None:
        flavour = flavour_for_extension(path).name
    key = (str(path), stat.st_mtime, stat.st_size, flavour)
    cached = _CACHE.get(key)
    if cached is not None:
        return cached
    text = path.read_text(encoding="utf-8")
    cg = _compile_core(text, stem=path.stem, flavour=flavour)
    _CACHE[key] = cg
    return cg
