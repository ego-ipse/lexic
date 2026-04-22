"""CompiledGrammar: the compile-time artefacts parse() needs.

compile(text, *, cache_key) is the primary entry. compile_from_path(path)
is a thin wrapper that stats the file, builds a (path, mtime, size) key,
checks the cache to skip the file read on hit, and delegates to compile().

One cache covers both entry points.

Runtime→codegen seam: this module imports exactly two public symbols from
lexic.codegen — build_classes_and_specs and LarkBuilder. No private-symbol
imports cross the seam.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Hashable

import lark

from lexic.codegen import build_classes_and_specs
from lexic.codegen.lark_builder import LarkBuilder

if TYPE_CHECKING:
    from lexic.base import GrammarModel
    from lexic.ir import RuleSpec


@dataclass(frozen=True)
class CompiledGrammar:
    classes: dict[str, type]
    specs: dict[str, "RuleSpec"]
    parser: "lark.Lark"
    transformer: "lark.Transformer"

    def parse(self, text: str) -> "GrammarModel":
        tree = self.parser.parse(text)
        return self.transformer.transform(tree)


_CACHE: dict[Hashable, CompiledGrammar] = {}


def reset_cache_for_tests() -> None:
    """Public test seam: clear the compile cache."""
    _CACHE.clear()


def _stem_for_text(text: str) -> str:
    """Stable filename for a grammar string with no path."""
    return "anon_" + hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


def _compile_core(text: str, *, stem: str) -> CompiledGrammar:
    classes, specs_list = build_classes_and_specs(text, stem=stem)
    specs = {s.rule_name: s for s in specs_list}

    builder = LarkBuilder(specs_list)
    grammar_str, start_rule = builder.build_grammar()
    parser = lark.Lark(
        grammar_str, parser="earley", ambiguity="resolve", start=start_rule
    )
    transformer = builder.build_transformer(classes)

    return CompiledGrammar(
        classes=classes, specs=specs, parser=parser, transformer=transformer
    )


def compile(text: str, *, cache_key: Hashable | None = None) -> CompiledGrammar:
    """Compile from a grammar string. cache_key=None means 'do not memoize'."""
    if cache_key is not None:
        cached = _CACHE.get(cache_key)
        if cached is not None:
            return cached
    cg = _compile_core(text, stem=_stem_for_text(text))
    if cache_key is not None:
        _CACHE[cache_key] = cg
    return cg


def compile_from_path(grammar_path: str | Path) -> CompiledGrammar:
    """Compile from a file path; memoised by (path, mtime, size)."""
    path = Path(grammar_path).resolve()
    stat = path.stat()
    key = (str(path), stat.st_mtime, stat.st_size)
    cached = _CACHE.get(key)
    if cached is not None:
        return cached
    return compile(path.read_text(), cache_key=key)
