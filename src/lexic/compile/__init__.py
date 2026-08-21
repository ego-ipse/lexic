"""parse_grammar / canonical_grammar / compile_text — grammar entry points.

``parse_grammar(text, flavour)`` is the public grammar-text → ``IrAst`` seam:
the flavour's self-grammar is compiled once, and its IR ``Reducer`` derives a
pruned model variant whose thin fold produces the grammar AST.

Pipeline (compile_text / compile_from_path — grammar text → CompiledGrammar)::

  text ─► canonical_grammar = parse_grammar + canonicalize + directive flags
                     │            (the canonical AST — start bound,
                     │             noise rules flagged semantic=False)
                     ▼
             CompileMoments   (the retaining product — groups hoisted,
                     │           arms hoisted, noise refs relaxed, resolved
                     │           against a vocabulary when one is bound,
                     │           then compute_binding ──► synthesize)
                     ▼
          IR body-table ──► ModelFold (bakes to the runtime fold records)

Every stage above is a MOMENT the product keeps, and ``_assemble_core`` runs
through it rather than beside it — so ``CompiledGrammar.moments`` is what the
compilation actually did, never a re-run of it. ``build_codegen_grammar`` is
the fused form, and reads the same product's last grammar.

``canonical_grammar(text, flavour)`` is the public front half (parse +
canonicalize + directive flags → flagged ``IrAst``); ``generate.py`` and
transpilers build on it. ``compile_ast(ast)`` is the IR-born twin of
``compile_text``: same back half, no text — the given AST is canonicalized
as it stands and its own ``semantic`` flags survive (the emit-and-recompile
detour loses them with the comments).

``CompiledGrammar`` carries the codegen grammar + its fold; ``parse`` hands
them to the engine's model product, and ``parse_grammar`` compiles the flavour's
authored self-grammar once and calls that artefact's ``reduce`` capability.
Model parsing and grammar-text reduction therefore enter through the same
artefact seam; the reducer-derived variant decides what the latter builds.

The grammar→grammar passes, the binding view and runtime class synthesis all
live inside this package (``lexic.compile.pipeline.passes`` / ``.binding`` /
``.synthesis``, composed once in ``.moments``) and are re-exported from this
root, which is the only import route to them. The engine is the package's only
external runtime seam, and compile modules are its only non-engine consumers.
Reducer data comes only from ``lexic.ir``. Outside the package every runtime
module reaches compile only through
``from lexic.compile import ...`` (the ``__init__`` root), never a submodule.
``test_layering_invariants.py`` pins both halves.
"""

from __future__ import annotations

import hashlib
from collections.abc import Hashable, Mapping
from pathlib import Path
from typing import NamedTuple

from lexic.compile.artifact import (
    CompiledGrammar,
    TokenBinding,
    encoding_registry,
    reset_reduction_cache,
    segmentation_tokenizer,
)
from lexic.compile.module.export import export_module, export_source
from lexic.compile.module.selfgrammar import parse_module, verify_module
from lexic.compile.notation.parse import load_ir, load_ir_from_path
from lexic.compile.payload.export import export_value
from lexic.compile.pipeline.binding import RuleBinding, compute_binding
from lexic.compile.pipeline.moments import (
    GRAMMAR_MOMENTS,
    CompileMoments,
    GrammarMoments,
    build_codegen_grammar,
)
from lexic.compile.pipeline.synthesis import fold_config, synthesize
from lexic.compile.presentation import Draw, Presentation, Row, Rows, present
from lexic.compile.templating import (
    KEEP,
    Keep,
    MapShape,
    SpanEntry,
    SpanLevel,
    SpanPair,
    Spec,
    Template,
    spanify,
    template,
)
from lexic.compile.transpile import (
    Flat,
    Is,
    Make,
    Spelled,
    Split,
    Transpiler,
    transpile,
)
from lexic.compile.verdict import Verdict
from lexic.exceptions import UnsupportedConstructError
from lexic.grammars import flavour_for_extension, get_flavour
from lexic.ir import (
    IrAlphabet,
    IrAst,
    IrFlavour,
    IrMap,
    IrRule,
    IrSelf,
    IrSeq,
    IrTokenizer,
    Reducer as _Reducer,
    canonicalize,
    fold_name,
    inline_refs,
    refs_in_order,
    rule_closure,
)
from lexic.model import GrammarModel
from lexic.parsing import ModelFold

# Case-insensitive order — keeps this list and the submodules' own __all__
# blocks from sharing linter-length runs of identical lines.
__all__ = [
    "Directives",
    "Draw",
    "Vocabulary",
    "bind_module",
    "build_codegen_grammar",
    "CompileMoments",
    "canonical_grammar",
    "compile_ast",
    "compile_from_path",
    "compile_text",
    "CompiledGrammar",
    "compute_binding",
    "export_module",
    "export_source",
    "export_value",
    "Flat",
    "GRAMMAR_MOMENTS",
    "GrammarMoments",
    "KEEP",
    "Keep",
    "load_ir",
    "Is",
    "load_ir_from_path",
    "Make",
    "MapShape",
    "parse_grammar",
    "present",
    "Presentation",
    "parse_instance",
    "parse_instance_from_path",
    "parse_module",
    "Row",
    "Rows",
    "reset_cache_for_tests",
    "RuleBinding",
    "SpanEntry",
    "SpanLevel",
    "SpanPair",
    "spanify",
    "Spec",
    "Spelled",
    "Split",
    "synthesize",
    "Template",
    "template",
    "TokenBinding",
    "transpile",
    "Transpiler",
    "Verdict",
    "verify_module",
]


def _flavour_reducer(flavour: IrFlavour) -> _Reducer:
    """The flavour's :class:`Reducer`, narrowed once — the single home for the check.

    :param flavour: The grammar flavour.
    :returns: Its ``reducer`` ClassVar, narrowed to :class:`Reducer`.
    :raises UnsupportedConstructError: When the flavour carries no ``Reducer``.
    """
    reducer = flavour.reducer
    if not isinstance(reducer, _Reducer):
        raise UnsupportedConstructError(
            f"compile: flavour {flavour.name!r} carries no IR Reducer"
        )
    return reducer


class Vocabulary(NamedTuple):
    """The vocabulary a grammar's terminals are read through — one lens.

    ``tokenizer`` and ``registry`` were never two channels: they COMPOSE over a
    default ``unicode`` and :func:`encoding_registry` merges them into one
    resolved registry before anything reads a terminal. Naming the pair is what
    they always were.

    :ivar tokenizer: A single tokenizer, bound under its own ``name``.
    :ivar registry: An ``IrMap[IrStr, IrEncoding]`` binding encoding *names* to
        encodings (``unicode`` is always present) — the general form.
    """

    tokenizer: IrTokenizer | None = None
    registry: IrMap | None = None


class Directives(NamedTuple):
    """What a grammar's ``@directives`` say, as an argument.

    Exactly what :func:`_scan_directives` reads out of the source comments, so a
    caller who already knows can hand it over instead of writing it into the
    grammar. Given explicitly, it OVERRIDES what the source says.

    :ivar start: The start rule (``@start``), or ``None`` to use the source's.
    :ivar non_semantic: Rules to mark structural noise (``@non-semantic``), or
        ``None`` to use the source's.
    :ivar lexical: Rules whose references are inlined until their bodies are
        ref-free (``@lexical``), or ``None`` to use the source's. A marked rule
        keeps its matched TEXT instead of a subtree of interior models — the
        author's declaration that a rule is lexical, not structural.
    """

    start: str | None = None
    non_semantic: frozenset[str] | None = None
    lexical: frozenset[str] | None = None


_CACHE: dict[Hashable, CompiledGrammar] = {}


def reset_cache_for_tests() -> None:
    """Public test seam: clear the compile cache and the derived-reduce memo."""
    _CACHE.clear()
    reset_reduction_cache()


def parse_grammar(text: str, flavour: IrFlavour) -> IrAst:
    """Parse grammar source into its IR AST via the flavour's engine path.

    Compiles the flavour's authored self-grammar through the ordinary AST
    route, then calls the artefact's :meth:`CompiledGrammar.reduce` capability.
    The artefact and its reducer-derived pruned variant are both memoised.

    :param text: Grammar source in ``flavour``'s syntax.
    :param flavour: The grammar flavour (e.g. ``GBNF_FLAVOUR``).
    :returns: The reduced grammar :class:`IrAst`, with dangling references
        into the flavour's ``core_rules`` prelude resolved (the referenced
        core rules appended; nothing else added, nothing overridden).
    :raises UnsupportedConstructError: If the flavour carries no ``Reducer``,
        ``text`` does not parse, or the reduction is not an ``IrAst``.
    """
    reducer = _flavour_reducer(flavour)
    self_grammar = compile_ast(flavour.grammar, cache_key="parse-grammar")
    reduced = self_grammar.reduce(text, reducer)
    if not isinstance(reduced, IrAst):
        raise UnsupportedConstructError(
            f"parse_grammar: reduction produced {type(reduced).__name__!r}, "
            "not an IrAst"
        )
    return _resolve_prelude(reduced, flavour)


def _resolve_prelude(ast: IrAst, flavour: IrFlavour) -> IrAst:
    """Append flavour core rules for dangling refs — to closure, since a core
    rule may reference further core rules (``crlf`` → ``cr``/``lf``).

    :param ast: The freshly reduced grammar.
    :param flavour: The flavour whose ``core_rules`` prelude applies.
    :returns: ``ast`` unchanged when nothing dangles into the prelude.
    """
    prelude = flavour.core_rules
    core: dict[str, IrRule] = {str(key): prelude[key] for key in prelude.keys()}
    if not core:
        return ast
    rules = list(ast.rules)
    # Rulenames are case-insensitive pre-canonicalization (a ref may spell
    # ALPHA); fold both sides so the later name-folding pass connects the
    # appended lowercase rule to the source-case ref.
    defined = {fold_name(str(rule.name)) for rule in rules}
    grew = True
    while grew:
        grew = False
        referenced: list[str] = []
        for rule in rules:
            refs_in_order(rule.body, referenced)
        for name in (fold_name(ref) for ref in referenced):
            rule = core.get(name)
            if rule is not None and name not in defined:
                rules.append(rule)
                defined.add(name)
                grew = True
    if len(rules) == len(ast.rules):
        return ast
    return IrAst(IrSeq(*rules), ast.start)


def _content_tag(text: str) -> str:
    """A grammar's content identity — the short hash both stems carry."""
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


def _stem_for_text(text: str) -> str:
    """Stable filename for a grammar string with no path."""
    return "anon_" + _content_tag(text)


def _identity_for(stem: str, text: str) -> str:
    """A grammar's synthetic-module identity — its stem, content-tagged.

    A generated class's ``__module__`` is ``generated.<identity>``, and that
    name is what a consumer has to read to tell two grammars apart: the payload
    projection interns a symbol per ``(module, name)``, so two different
    grammars whose start rules are both called ``Root`` are distinguishable only
    if the module is. A bare file stem is not — ``a/g.gbnf`` and ``b/g.gbnf``
    were ``generated.g`` twice and the two ``Root``s merged silently.

    Distinct from :attr:`CompiledGrammar.stem`, which names the EXPORTED FILE
    and stays a plain filename. One field was doing both jobs.

    :param stem: The artefact's stem (file stem, or the anon content stem).
    :param text: The grammar source.
    :returns: ``<stem>_<12 hex>``, or ``stem`` when it already carries the tag.
    """
    tag = _content_tag(text)
    return stem if stem.endswith(tag) else f"{stem}_{tag}"


def _directive_bodies(text: str, flavour: IrFlavour) -> list[str]:
    """The text inside each comment, for whichever comment form the flavour has.

    A surface that can spell a comment can spell a directive. EBNF has only
    ``(* *)`` block comments, and a mechanism GBNF and ABNF could express while
    EBNF structurally could not would be a privileged formulation — it cost
    ``json.ebnf`` the whole predictive path, because it could not mark ``ws``
    structural and every parse escaped at position 0.

    :param text: Grammar source text.
    :param flavour: The flavour, for its comment delimiters.
    :returns: One entry per comment, stripped of its delimiters.
    """
    bodies: list[str] = []
    if flavour.line_comment:
        for raw in text.splitlines():
            line = raw.strip()
            if line.startswith(flavour.line_comment):
                bodies.append(line[len(flavour.line_comment) :])
    if len(flavour.block_comment) == 2:
        opener, closer = flavour.block_comment[0], flavour.block_comment[1]
        rest = text
        while (a := rest.find(opener)) != -1:
            b = rest.find(closer, a + len(opener))
            if b == -1:
                break
            bodies.append(rest[a + len(opener) : b])
            rest = rest[b + len(closer) :]
    return bodies


def _scan_directives(
    text: str, flavour: IrFlavour
) -> tuple[str | None, frozenset[str], frozenset[str]]:
    """Extract the directives from source comments — a pre-lexical scan.

    A comment reading ``@<name> <args...>`` declares a directive: ``@start
    <rule>`` overrides the start rule, ``@non-semantic <rule> ...`` names
    structural-noise rules, ``@lexical <rule> ...`` names rules whose
    references are inlined so they keep their text rather than an interior of
    models. The scan reads the raw source before the parser so comments never
    become load-bearing grammar tokens; ``canonical_grammar`` resolves
    precedence and applies the result to the AST.

    :param text: Grammar source text.
    :param flavour: The flavour, for its comment delimiters. One with neither
        comment form cannot carry a directive.
    :returns: ``(start, non_semantic, lexical)`` — the ``@start`` rule name or
        ``None``, and the two directive name sets.
    """
    non_semantic: set[str] = set()
    lexical: set[str] = set()
    start_rule: str | None = None
    for body in _directive_bodies(text, flavour):
        rest = body.strip()
        if not rest.startswith("@"):
            continue
        parts = rest[1:].split()
        if not parts:
            continue
        name, *args = parts
        if name == "non-semantic":
            non_semantic.update(args)
        elif name == "lexical":
            lexical.update(args)
        elif name == "start" and args:
            start_rule = args[0]  # last @start wins on duplicates
    return start_rule, frozenset(non_semantic), frozenset(lexical)


def canonical_grammar(
    text: str,
    flavour: IrFlavour,
    *,
    non_semantic_rules: frozenset[str] | None = None,
    start: str | None = None,
    lexical_rules: frozenset[str] | None = None,
) -> IrAst:
    """Parse + canonicalize + bind directive flags — the compile front half.

    `start` resolution precedence:
      1. explicit `start` argument
      2. `@start <rule>` directive in source comments
      3. `ast.rules[0].name` (positional fallback)

    `non_semantic_rules` resolution:
      1. explicit `non_semantic_rules` argument
      2. `@non-semantic <rule> ...` directives in source comments

    `lexical_rules` resolves the same way against `@lexical`, and is applied
    as the ref-inlining transform (`inline_refs`) — the one directive that
    changes a rule's SHAPE rather than a flag on it.

    The resolved `start` is bound onto the canonical IrAst (the AST is rebuilt
    — it is frozen), and each rule the resolved non-semantic set names is
    reconstructed with `semantic=False` (`ast.non_semantic` derives from the
    flags). A directive naming a rule the grammar never defines is silently
    ignored: no rule is flagged for it.

    Errors: malformed grammar source bubbles up as UnsupportedConstructError
    (raised by the engine / reducer, or here if the flavour carries no Reducer,
    its reduction does not yield an IrAst, or the start rule is undefined).
    """
    dir_start, dir_non_semantic, dir_lexical = _scan_directives(text, flavour)
    if non_semantic_rules is None:
        non_semantic_rules = dir_non_semantic
    if lexical_rules is None:
        lexical_rules = dir_lexical
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
    folded_lexical = frozenset(fold_name(n) for n in lexical_rules)
    return inline_refs(IrAst(rules=rules, start=start), folded_lexical)


def _is_segmented(ast: IrAst) -> bool:
    """Whether any terminal references an encoding — i.e. this is a token grammar.

    What :meth:`~lexic.compile.artifact.CompiledGrammar.parse` routes on. It is
    a property of the GRAMMAR, never of whether a tokenizer happens to be
    bound: binding one to a char grammar must not move it (the additivity
    invariant), and a char grammar may legitimately carry a tokenizer for
    :meth:`~lexic.compile.artifact.CompiledGrammar.constrain`.

    :param ast: The grammar to inspect.
    :returns: ``True`` when some atom is an :class:`IrAlphabet`.
    """
    stack: list[IrSelf] = [ast]
    while stack:
        node = stack.pop()
        if isinstance(node, IrAlphabet):
            return True
        stack.extend(node.children())
    return False


def _flavour_key(flavour: str | IrFlavour) -> Hashable:
    """The memo component a flavour contributes — its name, or its class.

    A name string keys by itself. An INSTANCE keys by its class object:
    flavour value equality is not a designed key in either direction —
    record-tier equality is content-based, so two field-less records of
    DIFFERENT classes compare equal (aliasing), while two loads of the SAME
    manifest compare unequal (their tables' actions differ by identity) —
    whereas the class object is identity-stable and the cache entry pins it
    live, so (unlike an ``id()``) it can never be reused for another flavour.
    """
    return flavour if isinstance(flavour, str) else type(flavour)


def _compile_core(
    text: str,
    *,
    stem: str,
    flavour: str | IrFlavour = "gbnf",
    vocabulary: Vocabulary = Vocabulary(),
    directives: Directives = Directives(),
) -> CompiledGrammar:
    flavour_cls = get_flavour(flavour) if isinstance(flavour, str) else flavour
    ast = canonical_grammar(
        text,
        flavour_cls,
        non_semantic_rules=directives.non_semantic,
        start=directives.start,
        lexical_rules=directives.lexical,
    )
    flavour_name = flavour if isinstance(flavour, str) else type(flavour).name
    return _assemble_core(
        ast, stem=stem, source=text, flavour_name=flavour_name, vocabulary=vocabulary
    )


def _assemble_core(
    ast: IrAst, *, stem: str, source: str, flavour_name: str, vocabulary: Vocabulary
) -> CompiledGrammar:
    """The compile back half — canonical flagged AST → :class:`CompiledGrammar`.

    Shared verbatim by the text route (:func:`_compile_core`) and the AST
    route (:func:`compile_ast`); everything from here down is front-half
    agnostic. ``source`` is the content string the synthetic-module identity
    tags (:func:`_identity_for`) — the grammar text on the text route,
    ``repr(ast)`` on the AST route.
    """
    resolved = encoding_registry(vocabulary.tokenizer, vocabulary.registry)
    # Resolution is for MATCHING, not for meaning. concretize COMMUTES with
    # the grammar passes, so the unresolved codegen grammar is built once and
    # resolved beside it; the ENGINE gets the resolved form (ids match a
    # segmentation) while everything that carries meaning back to the user —
    # the canonical AST and each class's `__grammar__` — keeps the AUTHORED
    # form. A vocabulary is a lens on a grammar, never part of what it says,
    # so binding one must not make `to_grammar()` lossy.
    moments = CompileMoments.of(ast, resolved, _identity_for(stem, source))
    unresolved = moments.grammar.relaxed
    codegen_grammar = moments.grammar.resolved
    classes = moments.classes
    fold = ModelFold(fold_config(codegen_grammar, moments.binding, classes))
    return CompiledGrammar(
        grammar=ast,
        fold=fold,
        moments=moments,
        flavour=flavour_name,
        stem=stem,
        tokens=TokenBinding(
            segmentation_tokenizer(resolved),
            _is_segmented(codegen_grammar),
            unresolved,
        ),
    )


def compile_text(
    text: str,
    *,
    cache_key: Hashable | None = None,
    flavour: str | IrFlavour = "gbnf",
    vocabulary: Vocabulary = Vocabulary(),
    directives: Directives = Directives(),
) -> CompiledGrammar:
    """Compile from a grammar string, memoised by content by default.

    The cache key is ``(content sha stem, flavour key)`` — compiling the same
    source in the same flavour returns the cached :class:`CompiledGrammar`
    (and its class objects; synthesis writes no files, so there is no output
    directory to key on). An explicit ``cache_key`` is *prepended* to that
    content key rather than used as-is: ``(cache_key, stem, flavour key)``.
    Folding the content stem in means the same key can never serve a stale
    grammar — different source text under one ``cache_key`` yields distinct
    entries, while identical text still hits the memo. The test seam
    :func:`reset_cache_for_tests` clears the cache when a caller needs fresh
    class objects.

    A flavour INSTANCE is used directly and never touches the registry: a
    loaded session manifest compiles without ``register_flavour``, and the
    shipped singleton under the same name is not shadowed. It contributes
    its class object to the memo key — identity-stable, pinned live by the
    cache entry — so two different flavours can never alias one entry.

    :param text: Grammar source in ``flavour``'s syntax.
    :param cache_key: Extra key prefix disambiguating otherwise-identical
        compilations; ``None`` uses the content key alone.
    :param flavour: The grammar flavour — a registered name, or a live
        :class:`~lexic.ir.IrFlavour` instance.
    :param vocabulary: The lens the grammar's terminals are read through — a
        tokenizer, a name → encoding registry, or both (they compose).
    :param directives: What the ``@directives`` would say, as an argument;
        overrides what the source's own comments say.
    :returns: The compiled grammar (cached across calls with the same key).
    """
    stem = _stem_for_text(text)
    # BY VALUE, like the path twin: keying on id() is unsound because ids are
    # unique only among LIVE objects, so a dropped vocabulary's address can be
    # reused and hand back another one's artefact. Both are hashable.
    # The directives are part of WHAT WAS COMPILED, so they key the memo too:
    # without them one source compiled two ways would hand back the first.
    content_key: tuple[Hashable, ...] = (
        stem,
        _flavour_key(flavour),
        vocabulary,
        directives,
    )
    key = (cache_key, *content_key) if cache_key is not None else content_key
    cached = _CACHE.get(key)
    if cached is not None:
        return cached
    cg = _compile_core(
        text,
        stem=stem,
        flavour=flavour,
        vocabulary=vocabulary,
        directives=directives,
    )
    _CACHE[key] = cg
    return cg


def _canonical_ast(ast: IrAst, directives: Directives) -> IrAst:
    """The AST route's front half — canonicalize + resolve the flags.

    Mirrors :func:`canonical_grammar` with the AST itself as the source:
    ``directives.start`` overrides ``ast.start`` (else the first rule),
    ``directives.non_semantic`` REPLACES the rules' own ``semantic`` flags
    when given — ``None`` keeps them (canonicalize preserves the flag) —
    and ``directives.lexical`` is applied as the same ref-inlining transform
    the text route runs (an AST has no comments, so ``None`` means none).

    :raises UnsupportedConstructError: When the resolved start rule is not
        defined in the grammar.
    """
    start = directives.start or ast.start or (ast.rules[0].name if ast.rules else "")
    canon = canonicalize(IrAst(rules=ast.rules, start=start))
    if canon.start and not any(r.name == canon.start for r in canon.rules):
        raise UnsupportedConstructError(
            f"start rule {canon.start!r} not defined in grammar; "
            f"available rules: {[r.name for r in canon.rules]}"
        )
    flagged = canon
    if directives.non_semantic is not None:
        folded = frozenset(fold_name(n) for n in directives.non_semantic)
        rules = IrSeq(
            *(IrRule(r.name, r.body, r.name not in folded) for r in canon.rules)
        )
        flagged = IrAst(rules=rules, start=canon.start)
    if not directives.lexical:
        return flagged
    folded_lexical = frozenset(fold_name(n) for n in directives.lexical)
    return inline_refs(flagged, folded_lexical)


def compile_ast(
    ast: IrAst,
    *,
    cache_key: Hashable | None = None,
    vocabulary: Vocabulary = Vocabulary(),
    directives: Directives = Directives(),
) -> CompiledGrammar:
    """Compile from a grammar AST — the IR-born twin of :func:`compile_text`.

    The entry for a grammar that never had text: authored natively in IR, or
    loaded through the notation. The text route's front half is skipped, not
    emulated — emitting IR through a flavour and recompiling that text is
    lossy (``semantic=False`` flags vanish with the comments) and can only
    spell what the chosen flavour can spell. Here the given AST is
    canonicalized as it stands (rule flags survive), the start and flags
    resolve from the AST itself with ``directives`` overriding — the text
    route's precedence — and the back half is shared verbatim.

    Memoised like the text twin, with ``repr(ast)`` as the content: repr is
    codegen-exact, so the key distinguishes what AST equality deliberately
    ignores (the ``semantic`` flags). The artefact's ``flavour`` is ``"ir"``
    — the notation is the surface it arrived in; ``to_grammar`` still takes
    its target flavour explicitly.

    :param ast: The grammar AST; need not be canonical.
    :param cache_key: Extra key prefix, prepended as in :func:`compile_text`.
    :param vocabulary: The lens the grammar's terminals are read through
        (see :func:`compile_text`).
    :param directives: Overrides for what the AST's own start and flags say.
    :returns: The compiled grammar (cached across calls with the same key).
    :raises UnsupportedConstructError: When the resolved start rule is not
        defined in the grammar.
    """
    source = repr(ast)
    stem = _stem_for_text(source)
    content_key: tuple[Hashable, ...] = (stem, "ir", vocabulary, directives)
    key = (cache_key, *content_key) if cache_key is not None else content_key
    cached = _CACHE.get(key)
    if cached is not None:
        return cached
    cg = _assemble_core(
        _canonical_ast(ast, directives),
        stem=stem,
        source=source,
        flavour_name="ir",
        vocabulary=vocabulary,
    )
    _CACHE[key] = cg
    return cg


def _expected_fields(bound: RuleBinding) -> tuple[str, ...]:
    """The record fields a generated class must declare for its binding.

    :param bound: The rule's binding view.
    :returns: The field names in declaration order (``value_str`` classes
        carry the implicit ``value`` field; ``alternation`` classes none).
    """
    if bound.kind == "value_str":
        return ("value",)
    if bound.kind == "alternation":
        return ()
    return tuple(bound.fields)


def bind_module(grammar: IrAst, namespace: Mapping[str, object]) -> None:
    """Attach the runtime tables to a generated twin module's classes.

    The module-end call of a dunder-free generated module: recomputes the
    codegen grammar and binding view from the module's ``GRAMMAR`` (the same
    deterministic pipeline the runtime runs) and writes each class's
    ``__grammar__`` + ``__shape__`` + ``__binds__``. ``_child_attrs`` is deliberately left
    alone — the class-body annotations already derived the runtime-identical
    value at class creation.

    :param grammar: The module's canonical ``GRAMMAR`` AST.
    :param namespace: The module namespace (``globals()`` at the call site).
    :raises UnsupportedConstructError: When a binding's class is missing from
        the namespace, is not a :class:`~lexic.model.GrammarModel` subclass,
        or declares fields that do not match its rule's binding.
    """
    codegen_grammar = build_codegen_grammar(grammar)
    rules = {str(rule.name): rule for rule in codegen_grammar.rules}
    shapes = rule_closure(codegen_grammar)
    for bound in compute_binding(codegen_grammar):
        cls = namespace.get(bound.class_name)
        if not (isinstance(cls, type) and issubclass(cls, GrammarModel)):
            raise UnsupportedConstructError(
                f"bind_module: rule {bound.rule_name!r} needs a GrammarModel "
                f"class named {bound.class_name!r} in the module"
            )
        expected = _expected_fields(bound)
        declared = tuple(cls._fields)
        if declared != expected:
            raise UnsupportedConstructError(
                f"bind_module: class {bound.class_name!r} declares fields "
                f"{declared}, but rule {bound.rule_name!r} binds {expected}"
            )
        cls.__grammar__ = rules[bound.rule_name]
        cls.__shape__ = shapes[bound.rule_name]
        cls.__binds__ = {b.item: (n, b) for n, b in bound.fields.items()}


def compile_from_path(
    grammar_path: str | Path,
    *,
    flavour: str | IrFlavour | None = None,
    vocabulary: Vocabulary = Vocabulary(),
    directives: Directives = Directives(),
) -> CompiledGrammar:
    """Compile from a file path; memoised by (path, mtime, size, flavour key).

    The path-taking wrapper around :func:`compile_text`, carrying its whole
    surface: a grammar with token terminals binds a vocabulary here exactly
    as it would from source, and a flavour instance compiles registry-free
    exactly as it would there.

    :param grammar_path: Path to the grammar source file.
    :param flavour: The grammar flavour name or instance; inferred from the
        file extension if omitted.
    :param vocabulary: The lens the grammar's terminals are read through
        (see :func:`compile_text`).
    :param directives: What the ``@directives`` would say, as an argument.
    :returns: The compiled grammar (cached across calls with the same key).
    """
    path = Path(grammar_path).resolve()
    stat = path.stat()
    if flavour is None:
        flavour = flavour_for_extension(path).name
    # The bound vocabulary is part of the artefact, so it is part of the key —
    # BY VALUE. Keying on id() would be unsound: ids are unique only among
    # LIVE objects, so a dropped tokenizer's address can be reused and hand
    # back another vocabulary's artefact. Both are hashable (an IrTokenizer is
    # an IrNamedTuple, a registry an IrMap), and the hash is computed once.
    key = (
        str(path),
        stat.st_mtime,
        stat.st_size,
        _flavour_key(flavour),
        vocabulary,
        directives,
    )
    cached = _CACHE.get(key)
    if cached is not None:
        return cached
    text = path.read_text(encoding="utf-8")
    cg = _compile_core(
        text,
        stem=path.stem,
        flavour=flavour,
        vocabulary=vocabulary,
        directives=directives,
    )
    _CACHE[key] = cg
    return cg


def parse_instance(
    text: str, grammar: str, *, flavour: str | IrFlavour = "gbnf"
) -> GrammarModel:
    """Parse ``text`` against grammar SOURCE — the one-line entry.

    Sugar for ``compile_text(grammar, flavour=flavour).parse(text)``; the
    compilation is memoised by content, so repeated calls with the same
    grammar reuse the artefact. Callers doing more than one-off parses
    should hold the :class:`CompiledGrammar` themselves.

    :param text: The instance text to parse.
    :param grammar: Grammar source in ``flavour``'s syntax.
    :param flavour: The grammar flavour name or instance.
    :returns: The start rule's model instance.
    :raises UnsupportedConstructError: If the grammar or the text refuses.
    """
    return compile_text(grammar, flavour=flavour).parse(text)


def parse_instance_from_path(
    text: str, grammar_path: str | Path, *, flavour: str | IrFlavour | None = None
) -> GrammarModel:
    """Parse ``text`` against a grammar FILE — the path-taking twin.

    :param text: The instance text to parse.
    :param grammar_path: Path to the grammar source file.
    :param flavour: The grammar flavour name or instance; inferred from the
        file extension if omitted.
    :returns: The start rule's model instance.
    :raises UnsupportedConstructError: If the grammar or the text refuses.
    """
    return compile_from_path(grammar_path, flavour=flavour).parse(text)
