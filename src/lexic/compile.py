"""parse_grammar / compile_grammar / compile_text — grammar entry points.

``parse_grammar(text, flavour)`` is the public grammar-text → ``IrAst`` seam:
the flavour's own self-grammar (Earley-normalised, memoised per flavour)
parses the source and the flavour's ``Reducer`` folds the derivation to IR.

Pipeline (compile_grammar — grammar text → specs):

  text  ──┬──►  _scan_directives  ──►  (start, non_semantic)
          │                                          │
          │                                          ▼
          │                       (resolve arg > directive > fallback)
          │                                          │
          └──►  parse_grammar(text, flavour) ─► IrAst │
                                                  │    │
                                                  ▼    ▼
                     IrAst(rules with semantic=False flags, start)  ← rebuilt
                                                  │
                                                  ▼
                              derive_specs(ast)  [reads ast.non_semantic]
                                                  │
                                                  ▼
                                  (start_name, list[RuleSpec])

compile_text(text, *, cache_key) / compile_from_path(path) then run codegen
and build the engine-backed instance parser: the specs reconstitute as an
instance grammar (``lexic.parsing.models.build_instance_parser``) and
``CompiledGrammar.parse`` drives the Earley engine + ``ModelFold`` — no Lark.

Runtime seams: codegen from lexic.codegen (the package); the engine entries
from lexic.parsing / lexic.parsing.models / lexic.parsing.normalize /
lexic.parsing.reduce. No private-symbol imports cross either seam.
"""

from __future__ import annotations

import hashlib
from collections.abc import Hashable
from dataclasses import dataclass
from pathlib import Path

from lexic.base import GrammarModel
from lexic.codegen import codegen
from lexic.exceptions import UnsupportedConstructError
from lexic.grammars import flavour_for_extension, get_flavour
from lexic.ir.base import IrSeq
from lexic.ir.derive import derive_specs
from lexic.ir.flavour import IrFlavour
from lexic.ir.nodes import IrAst, IrRule
from lexic.ir.spec import RuleSpec
from lexic.parsing import ParserTables, parse_first, parse_reduced
from lexic.parsing.models import (
    ModelFold,
    build_instance_parser,
    collapsed_instance_tables,
)
from lexic.parsing.normalize import normalize
from lexic.parsing.reduce import Reducer


@dataclass(frozen=True)
class CompiledGrammar:
    """Parse-ready artefacts produced by compile().

    :ivar classes: Generated model classes by class name.
    :ivar specs: RuleSpecs by rule name.
    :ivar grammar: The Earley-normalised instance grammar (held so the
        engine's identity-memoised table compilation stays hot across calls).
    :ivar fold: The ParseTree → model-instance fold.
    :ivar tables: The instance grammar's run-collapsed tables — every lexical
        run the ModelFold licence proves safe steps in one scan (compiled once
        at build time; see :func:`~lexic.parsing.models.collapsed_instance_tables`).
    """

    classes: dict[str, type]
    specs: dict[str, RuleSpec]
    grammar: IrAst
    fold: ModelFold
    tables: ParserTables

    def parse(self, text: str) -> GrammarModel:
        """Parse text against the compiled grammar and return a model instance.

        :raises UnsupportedConstructError: If ``text`` does not parse, or the
            fold produced no model for the start rule.
        """
        model = self.fold.apply(parse_first(self.grammar, text, self.tables))
        if not isinstance(model, GrammarModel):
            raise UnsupportedConstructError(
                f"compile: start rule folded to {type(model).__name__!r}, "
                "not a GrammarModel"
            )
        return model


_CACHE: dict[Hashable, CompiledGrammar] = {}

_NORM_GRAMMAR_CACHE: dict[str, IrAst] = {}


def reset_cache_for_tests() -> None:
    """Public test seam: clear the compile cache."""
    _CACHE.clear()


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
    reducer = flavour.reducer
    if not isinstance(reducer, Reducer):
        raise UnsupportedConstructError(
            f"compile: flavour {flavour.name!r} carries no parse Reducer"
        )
    ast = parse_reduced(_normalized_grammar(flavour), text, reducer)
    if not isinstance(ast, IrAst):
        raise UnsupportedConstructError(
            f"compile: flavour {flavour.name!r} reduction produced "
            f"{type(ast).__name__!r}, not an IrAst"
        )
    return ast


def _stem_for_text(text: str) -> str:
    """Stable filename for a grammar string with no path."""
    return "anon_" + hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


def _compile_core(text: str, *, stem: str, flavour: str = "gbnf") -> CompiledGrammar:
    flavour_cls = get_flavour(flavour)
    start_rule, specs_list = compile_grammar(text, flavour_cls)
    classes = codegen(specs_list, stem)
    grammar, fold = build_instance_parser(specs_list, classes, start_rule)
    return CompiledGrammar(
        classes=classes,
        specs={s.rule_name: s for s in specs_list},
        grammar=grammar,
        fold=fold,
        tables=collapsed_instance_tables(grammar, fold),
    )


def compile_text(
    text: str, *, cache_key: Hashable | None = None, flavour: str = "gbnf"
) -> CompiledGrammar:
    """Compile from a grammar string. cache_key=None means 'do not memoize'."""
    if cache_key is not None:
        cached = _CACHE.get(cache_key)
        if cached is not None:
            return cached
    cg = _compile_core(text, stem=_stem_for_text(text), flavour=flavour)
    if cache_key is not None:
        _CACHE[cache_key] = cg
    return cg


def compile_from_path(
    grammar_path: str | Path, *, flavour: str | None = None
) -> CompiledGrammar:
    """Compile from a file path; memoised by (path, mtime, size, flavour)."""
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


def _scan_directives(text: str, line_comment: str) -> tuple[str | None, frozenset[str]]:
    """Extract ``(start, non_semantic)`` from source comments — a pre-lexical scan.

    A line ``<line_comment> @<name> <args...>`` declares a directive: ``@start
    <rule>`` overrides the start rule, ``@non-semantic <rule> ...`` names
    structural-noise rules. The scan reads the raw source before the parser so
    comments never become load-bearing grammar tokens; ``compile_grammar``
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


def compile_grammar(
    text: str,
    flavour: IrFlavour,
    *,
    non_semantic_rules: frozenset[str] | None = None,
    start: str | None = None,
) -> tuple[str, list[RuleSpec]]:
    """Parse + derive RuleSpecs via the IR-AST pipeline.

    `start` resolution precedence:
      1. explicit `start` argument
      2. `@start <rule>` directive in source comments
      3. `ast.rules[0].name` (positional fallback)

    `non_semantic_rules` resolution:
      1. explicit `non_semantic_rules` argument
      2. `@non-semantic <rule> ...` directives in source comments

    The resolved `start` is bound onto the parsed IrAst (the AST is rebuilt —
    it is frozen), and each rule the resolved non-semantic set names is
    reconstructed with `semantic=False`; `derive_specs` reads both from the AST
    (`ast.start`, `ast.non_semantic` — the latter derived from the flags). A
    directive naming a rule the grammar never defines is silently ignored: no
    rule is flagged for it, so it never appears in `ast.non_semantic`.

    Errors: malformed grammar source bubbles up as UnsupportedConstructError
    (raised by the engine / reducer, or here if the flavour carries no Reducer
    or its reduction does not yield an IrAst).
    """
    dir_start, dir_non_semantic = _scan_directives(text, flavour.line_comment)
    if non_semantic_rules is None:
        non_semantic_rules = dir_non_semantic
    ast = parse_grammar(text, flavour)
    if start is None:
        start = dir_start or (ast.rules[0].name if ast.rules else "")
    if start and not any(r.name == start for r in ast.rules):
        raise UnsupportedConstructError(
            f"start rule {start!r} not defined in grammar; "
            f"available rules: {[r.name for r in ast.rules]}"
        )
    rules = IrSeq(
        *(
            IrRule(r.name, r.body, False) if r.name in non_semantic_rules else r
            for r in ast.rules
        )
    )
    specs = derive_specs(IrAst(rules=rules, start=start))
    return start, specs
