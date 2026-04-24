"""CompiledGrammar: the compile-time artefacts parse() needs.

compile(text, *, cache_key) is the primary entry. compile_from_path(path)
is a thin wrapper that stats the file, builds a (path, mtime, size, flavour) key,
checks the cache to skip the file read on hit, and delegates to compile().

One cache covers both entry points.

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

from lexic.codegen import build_classes_and_specs
from lexic.codegen.lark_builder import LarkBuilder
from lexic.grammars import adapter_for_extension

if TYPE_CHECKING:
    from lexic.base import GrammarModel
    from lexic.ir import RuleSpec


@dataclass(frozen=True)
class CompiledGrammar:
    """Parse-ready artefacts produced by compile()."""

    classes: dict[str, type]
    specs: dict[str, "RuleSpec"]
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
    classes, specs_list = build_classes_and_specs(text, stem=stem, flavour=flavour)
    specs = {s.rule_name: s for s in specs_list}

    builder = LarkBuilder(specs_list)
    grammar_str, start_rule = builder.build_grammar()
    parser = lark.Lark(
        grammar_str, parser="earley", ambiguity="resolve", start=start_rule
    )
    # Task 11 deletes LarkBuilder.build_transformer; for now it still works.
    transformer = builder.build_transformer(classes)

    return CompiledGrammar(
        classes=classes, specs=specs, parser=parser, transformer=transformer
    )


def compile(  # pylint: disable=redefined-builtin
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
        flavour = adapter_for_extension(path).name
    key = (str(path), stat.st_mtime, stat.st_size, flavour)
    cached = _CACHE.get(key)
    if cached is not None:
        return cached
    return compile(path.read_text(encoding="utf-8"), cache_key=key, flavour=flavour)
