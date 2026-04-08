"""PEG interpreter — walks GBNFNode IR to parse arbitrary text.

No knowledge of any target language. Driven entirely by grammar rules.

Usage:
    rules  = GBNFParser().parse(grammar_text)
    models = GBNFModelBuilder(rules).build()
    interp = GBNFInterpreter(rules, models)

    result = interp.parse("rule-name", input_text)
    # Returns (value, consumed_pos) or None if no match.
    #
    # Value types by node kind:
    #   GBNFLiteral            → str (the matched literal)
    #   GBNFCharClass          → str (the matched character)
    #   GBNFRepetition/charclass → str (joined chars)
    #   GBNFRepetition/other   → list[Any]
    #   GBNFOptional           → inner value or (None, same_pos) on no match
    #   GBNFSequence           → BaseModel instance if rule has a model, else dict
    #   GBNFAlternation        → value from first matching arm
    #   GBNFReference          → result of recursing into named rule
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel

from ogbnf import (
    GBNFAlternation,
    GBNFCharClass,
    GBNFLiteral,
    GBNFNode,
    GBNFOptional,
    GBNFReference,
    GBNFRepetition,
    GBNFSequence,
)


def _charclass_to_re(pattern: str) -> re.Pattern[str]:
    """Convert GBNF character class to a compiled Python regex.

    GBNF stores hex ranges as \\xHH (two backslash bytes + xHH).
    Python re needs \\xHH (one backslash) to interpret them as hex escapes.
    Simple alpha ranges like [a-z] pass through unchanged.
    """
    # Each pair of consecutive backslashes in the grammar file arrives here
    # as two actual backslash characters. Replace them with one so Python re
    # interprets \\xHH as a hex escape for the right codepoint.
    py_pattern = pattern.replace("\\\\", "\\")
    return re.compile(py_pattern)


class GBNFInterpreter:
    """PEG interpreter over GBNFNode IR."""

    def __init__(
        self,
        rules: dict[str, GBNFNode],
        models: dict[str, type[BaseModel]],
    ) -> None:
        self._rules = rules
        self._models = models
        self._re_cache: dict[str, re.Pattern[str]] = {}

    def parse(self, rule: str, text: str, pos: int = 0) -> tuple[Any, int] | None:
        """Parse text[pos:] against the named rule.

        Returns (value, new_pos) or None on no match.
        """
        if rule not in self._rules:
            return None
        return self._match(self._rules[rule], text, pos, rule_name=rule)

    # ------------------------------------------------------------------
    # Core matching — one method per GBNFNode type
    # ------------------------------------------------------------------

    def _match(
        self,
        node: GBNFNode,
        text: str,
        pos: int,
        rule_name: str | None = None,
    ) -> tuple[Any, int] | None:
        match node:
            case GBNFLiteral(values=values):
                for v in values:
                    if text[pos : pos + len(v)] == v:
                        return v, pos + len(v)
                return None

            case GBNFCharClass(pattern=pattern):
                compiled = self._re_cache.get(pattern)
                if compiled is None:
                    compiled = _charclass_to_re(pattern)
                    self._re_cache[pattern] = compiled
                m = compiled.match(text, pos)
                if m:
                    return m.group(), m.end()
                return None

            case GBNFAlternation(arms=arms):
                for arm in arms:
                    result = self._match(arm, text, pos)
                    if result is not None:
                        return result
                return None

            case GBNFSequence(elements=elements):
                return self._match_sequence(elements, text, pos, rule_name)

            case GBNFRepetition(element=el, min=min_count):
                return self._match_repetition(el, text, pos, min_count)

            case GBNFOptional(element=el):
                result = self._match(el, text, pos)
                if result is None:
                    return None, pos
                return result

            case GBNFReference(rule=r):
                return self.parse(r, text, pos)

            case _:
                return None

    def _match_sequence(
        self,
        elements: tuple,
        text: str,
        pos: int,
        rule_name: str | None,
    ) -> tuple[Any, int] | None:
        fields: dict[str, Any] = {}
        cur = pos
        seen: dict[str, int] = {}
        for el in elements:
            result = self._match(el.node, text, cur)
            if result is None:
                return None
            base = el.name
            count = seen.get(base, 0)
            fname = base if count == 0 else f"{base}_{count}"
            seen[base] = count + 1
            fields[fname], cur = result

        # Instantiate the Pydantic model for this rule if one exists
        if rule_name and rule_name in self._models:
            try:
                return self._models[rule_name](**fields), cur
            except Exception:
                pass  # fall through to dict on validation error
        return fields, cur

    def _match_repetition(
        self,
        element: GBNFNode,
        text: str,
        pos: int,
        min_count: int,
    ) -> tuple[Any, int] | None:
        is_charclass = isinstance(element, GBNFCharClass)
        items: list[Any] = []
        cur = pos

        while True:
            result = self._match(element, text, cur)
            if result is None or result[1] == cur:
                break  # no match or zero-length match — stop to avoid infinite loop
            items.append(result[0])
            cur = result[1]

        if len(items) < min_count:
            return None

        if is_charclass:
            return "".join(str(i) for i in items), cur
        return items, cur
