"""compile_grammar / compile_text — grammar compilation entry points.

Pipeline (compile_grammar — new IR-AST path):

  text  ──┬──►  parse_directives  ──►  Directives(non_semantic, start)
          │                                          │
          │                                          ▼
          │                       (resolve `start` arg precedence)
          │
          └──►  MetaGrammarParser.for_flavour(flavour)  ──►  IrAst
                                                          │
                                                          ▼
                      derive_specs(ast, non_semantic_rules=...)
                                                          │
                                                          ▼
                                          (start_name, list[RuleSpec])

compile_text(text, *, cache_key) is the old-pipeline primary entry; returns
a CompiledGrammar (Lark parser + transformer + classes). Retired in Task 25a.
compile_from_path(path) is a thin wrapper that stats the file, builds a
(path, mtime, size, flavour) key, checks the cache to skip the file read on
hit, and delegates to compile_text(). One cache covers both old-pipeline
entry points.

Runtime→codegen seam: build_classes_and_specs from lexic.codegen (the
package) and LarkBuilder from lexic.codegen.lark_builder (the sub-module).
No private-symbol imports cross the seam.
"""

from __future__ import annotations

import hashlib
from collections.abc import Hashable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import lark

from lexic.codegen import codegen
from lexic.exceptions import UnsupportedConstructError
from lexic.grammars import flavour_for_extension, get_flavour
from lexic.ir.derive import derive_specs
from lexic.ir.directives import parse_directives
from lexic.ir.flavour import IrFlavour
from lexic.ir.spec import RuleSpec
from lexic.parsing.lark_builder import build_lark
from lexic.parsing.meta_parser import MetaGrammarParser

if TYPE_CHECKING:
    from lexic.base import GrammarModel


@dataclass(frozen=True)
class CompiledGrammar:
    """Parse-ready artefacts produced by compile()."""

    classes: dict[str, type]
    specs: dict[str, RuleSpec]
    parser: "lark.Lark"
    transformer: "lark.Transformer"

    def parse(self, text: str) -> "GrammarModel":
        """Parse text against the compiled grammar and return a model instance."""
        tree = self.parser.parse(text)
        return self.transformer.transform(tree)


_CACHE: dict[Hashable, CompiledGrammar] = {}


def reset_cache_for_tests() -> None:
    """Public test seam: clear the compile cache."""
    _CACHE.clear()


def _stem_for_text(text: str) -> str:
    """Stable filename for a grammar string with no path."""
    return "anon_" + hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


def _compile_core(text: str, *, stem: str, flavour: str = "gbnf") -> CompiledGrammar:
    flavour_cls = get_flavour(flavour)
    start_rule, specs_list = compile_grammar(text, flavour_cls)
    classes = codegen(specs_list, stem)
    _, parser, transformer = build_lark(specs_list, classes, start_rule)
    return CompiledGrammar(
        classes=classes,
        specs={s.rule_name: s for s in specs_list},
        parser=parser,
        transformer=transformer,
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
    stem = path.stem
    text = path.read_text(encoding="utf-8")
    flavour_cls = get_flavour(flavour)
    start_rule, specs_list = compile_grammar(text, flavour_cls)
    classes = codegen(specs_list, stem)
    _, parser, transformer = build_lark(specs_list, classes, start_rule)
    cg = CompiledGrammar(
        classes=classes,
        specs={s.rule_name: s for s in specs_list},
        parser=parser,
        transformer=transformer,
    )
    _CACHE[key] = cg
    return cg


def compile_grammar(
    text: str,
    flavour: IrFlavour,
    *,
    non_semantic_rules: frozenset[str] | None = None,
    start: str | None = None,
) -> tuple[str, list[RuleSpec]]:
    """Parse + derive NewRuleSpecs via the new IR-AST pipeline.

    Pipeline:

      text  ──┬──►  parse_directives  ──►  Directives(non_semantic, start)
              │                                          │
              │                                          ▼
              │                       (resolve `start` arg precedence)
              │
              └──►  MetaGrammarParser.for_flavour(flavour)  ──►  IrAst
                                                              │
                                                              ▼
                          derive_specs(ast, non_semantic_rules=...)
                                                              │
                                                              ▼
                                              (start_name, list[RuleSpec])

    `start` resolution precedence:
      1. explicit `start` argument
      2. `@start <rule>` directive in source comments
      3. `ast.rules[0].name` (positional fallback)

    `non_semantic_rules` resolution:
      1. explicit `non_semantic_rules` argument
      2. `@non-semantic <rule> ...` directives in source comments

    Errors: malformed grammar source bubbles up as UnsupportedConstructError
    (wrapped at MetaGrammarParser boundary).
    """
    directives = parse_directives(text, flavour.line_comment)
    if non_semantic_rules is None:
        non_semantic_rules = directives.non_semantic
    ast = MetaGrammarParser.for_flavour(flavour).parse(text)
    if start is None:
        start = directives.start or (ast.rules[0].name if ast.rules else "")
    if start and not any(r.name == start for r in ast.rules):
        raise UnsupportedConstructError(
            f"start rule {start!r} not defined in grammar; "
            f"available rules: {[r.name for r in ast.rules]}"
        )
    specs = derive_specs(ast, non_semantic_rules=non_semantic_rules)
    return start, specs
