"""compile_grammar / compile_text — grammar compilation entry points.

Pipeline (compile_grammar — grammar text → specs):

  text  ──┬──►  parse_directives  ──►  Directives(non_semantic, start)
          │                                          │
          │                                          ▼
          │                       (resolve `start` arg precedence)
          │
          └──►  parse_reduced(normalize(flavour.grammar), text, flavour.reducer)
                                                          │  ──►  IrAst
                                                          ▼
                      derive_specs(ast, non_semantic_rules=...)
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
from lexic.ir.derive import derive_specs
from lexic.ir.directives import parse_directives
from lexic.ir.flavour import IrFlavour
from lexic.ir.nodes import IrAst
from lexic.ir.spec import RuleSpec
from lexic.parsing import parse_first, parse_reduced
from lexic.parsing.models import ModelFold, build_instance_parser
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
    """

    classes: dict[str, type]
    specs: dict[str, RuleSpec]
    grammar: IrAst
    fold: ModelFold

    def parse(self, text: str) -> GrammarModel:
        """Parse text against the compiled grammar and return a model instance.

        :raises UnsupportedConstructError: If ``text`` does not parse, or the
            fold produced no model for the start rule.
        """
        model = self.fold.apply(parse_first(self.grammar, text))
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

    Errors: malformed grammar source bubbles up as UnsupportedConstructError
    (raised by the engine / reducer, or here if the flavour carries no Reducer
    or its reduction does not yield an IrAst).
    """
    directives = parse_directives(text, flavour.line_comment)
    if non_semantic_rules is None:
        non_semantic_rules = directives.non_semantic
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
    if start is None:
        start = directives.start or (ast.rules[0].name if ast.rules else "")
    if start and not any(r.name == start for r in ast.rules):
        raise UnsupportedConstructError(
            f"start rule {start!r} not defined in grammar; "
            f"available rules: {[r.name for r in ast.rules]}"
        )
    specs = derive_specs(ast, non_semantic_rules=non_semantic_rules)
    return start, specs
