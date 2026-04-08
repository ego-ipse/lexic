"""GBNF intermediate representation and parser.

Pure Python — no dependencies. Parses GBNF grammar text into a
structured IR. Every rule becomes a typed GBNFNode.

The only external knowledge here is what GBNF syntax means.
No Vyx-specific knowledge lives in this file.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# ------------------------------------------------------------------
# IR node types
# ------------------------------------------------------------------


@dataclass(frozen=True)
class GBNFLiteral:
    """One or more literal strings collapsed into an alternation.

    values holds the unescaped string values.
    e.g. GBNFLiteral(values=("\\",)) for the GBNF token "\\\\".
    """

    values: tuple[str, ...]


@dataclass(frozen=True)
class GBNFReference:
    """Reference to another rule by name."""

    rule: str


@dataclass(frozen=True)
class GBNFCharClass:
    """Character class: [a-z0-9] or negated [^\\n]"""

    pattern: str


@dataclass(frozen=True)
class GBNFElement:
    """Named element within a sequence, with a required flag."""

    name: str
    node: "GBNFNode"
    required: bool = True


@dataclass(frozen=True)
class GBNFSequence:
    """Ordered sequence: A B C"""

    elements: tuple[GBNFElement, ...]


@dataclass(frozen=True)
class GBNFAlternation:
    """Ordered alternatives: A | B | C"""

    arms: tuple["GBNFNode", ...]


@dataclass(frozen=True)
class GBNFRepetition:
    """Repetition: x* (min=0) or x+ (min=1)"""

    element: "GBNFNode"
    min: int = 0


@dataclass(frozen=True)
class GBNFOptional:
    """Optional element: x?"""

    element: "GBNFNode"


GBNFNode = (
    GBNFLiteral
    | GBNFReference
    | GBNFCharClass
    | GBNFSequence
    | GBNFAlternation
    | GBNFRepetition
    | GBNFOptional
)


# ------------------------------------------------------------------
# Literal unescaping
# ------------------------------------------------------------------


def _unescape(raw: str) -> str:
    """Strip outer quotes from a GBNF literal token and unescape.

    GBNF escape sequences inside double-quoted literals:
        \\\\  →  \\ (single backslash)
        \\"  →  "  (double quote)
        \\n  →  \\n (newline character)
        \\t  →  \\t (tab character)

    raw is the full token as seen in the grammar file,
    including the surrounding double-quote characters.
    """
    # Strip surrounding double quotes
    assert raw.startswith('"') and raw.endswith('"'), f"not a literal: {raw!r}"
    s = raw[1:-1]

    out: list[str] = []
    i = 0
    while i < len(s):
        if s[i] == "\\" and i + 1 < len(s):
            c = s[i + 1]
            if c == "\\":
                out.append("\\")
                i += 2
            elif c == '"':
                out.append('"')
                i += 2
            elif c == "n":
                out.append("\n")
                i += 2
            elif c == "t":
                out.append("\t")
                i += 2
            else:
                out.append("\\")
                out.append(c)
                i += 2
        else:
            out.append(s[i])
            i += 1
    return "".join(out)


# ------------------------------------------------------------------
# Parser
# ------------------------------------------------------------------


class GBNFParser:
    """Parse GBNF grammar text into {rule_name: GBNFNode}.

    One pass over the grammar. Every line of the form
    ``rule-name ::= body`` produces one entry in the returned dict.
    Comment lines (starting with #) and blank lines are skipped.
    """

    # Tokeniser regex — matches one GBNF token at a time
    _TOKEN = re.compile(
        r"\s*(?:"
        r"(?P<define>::=)"  # ::=
        r'|(?P<literal>"[^"]*")'  # "literal"
        r"|(?P<charclass>\[[^\]]+\])"  # [char-class]
        r"|(?P<pipe>\|)"  # |
        r"|(?P<star>\*)"  # *
        r"|(?P<plus>\+)"  # +
        r"|(?P<opt>\?)"  # ?
        r"|(?P<lp>\()"  # (
        r"|(?P<rp>\))"  # )
        r"|(?P<rule>[a-z][a-z0-9_-]*)"  # rule reference (lowercase, must come last)
        r")"
    )

    def parse(self, grammar: str) -> dict[str, GBNFNode]:
        """Return {rule_name: GBNFNode} for every rule in grammar."""
        rules: dict[str, GBNFNode] = {}
        for raw_line in grammar.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if "::=" not in line:
                continue
            name, _, body = line.partition("::=")
            name = name.strip()
            node = self._parse_body(body.strip())
            rules[name] = node
        return rules

    # ------------------------------------------------------------------
    # Internal parsing
    # ------------------------------------------------------------------

    def _parse_body(self, text: str) -> GBNFNode:
        tokens = self._tokenise(text)
        node, _ = self._alternation(tokens, 0)
        return node

    def _tokenise(self, text: str) -> list[tuple[str, str]]:
        return [
            (m.lastgroup, m.group().strip())
            for m in self._TOKEN.finditer(text)
            if m.lastgroup and m.lastgroup != "define"
        ]

    def _alternation(self, t: list[tuple[str, str]], i: int) -> tuple[GBNFNode, int]:
        arms: list[GBNFNode] = []
        node, i = self._sequence(t, i)
        arms.append(node)
        while i < len(t) and t[i][0] == "pipe":
            node, i = self._sequence(t, i + 1)
            arms.append(node)
        if len(arms) == 1:
            return arms[0], i
        return GBNFAlternation(arms=tuple(arms)), i

    def _sequence(self, t: list[tuple[str, str]], i: int) -> tuple[GBNFNode, int]:
        elements: list[GBNFElement] = []
        while i < len(t) and t[i][0] not in ("pipe", "rp"):
            node, i = self._atom(t, i)
            name = _element_name(node, len(elements))
            elements.append(GBNFElement(name=name, node=node))
        if not elements:
            return GBNFLiteral(values=()), i
        if len(elements) == 1:
            return elements[0].node, i
        return GBNFSequence(elements=tuple(elements)), i

    def _atom(self, t: list[tuple[str, str]], i: int) -> tuple[GBNFNode, int]:
        kind, val = t[i]
        i += 1

        if kind == "literal":
            node: GBNFNode = GBNFLiteral(values=(_unescape(val),))
        elif kind == "rule":
            node = GBNFReference(rule=val)
        elif kind == "charclass":
            node = GBNFCharClass(pattern=val)
        elif kind == "lp":
            node, i = self._alternation(t, i)
            i += 1  # consume rp
        else:
            raise ValueError(f"unexpected token {kind!r}: {val!r}")

        # Postfix quantifier
        if i < len(t):
            if t[i][0] == "star":
                node = GBNFRepetition(element=node, min=0)
                i += 1
            elif t[i][0] == "plus":
                node = GBNFRepetition(element=node, min=1)
                i += 1
            elif t[i][0] == "opt":
                node = GBNFOptional(element=node)
                i += 1

        return node, i


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _element_name(node: GBNFNode, position: int) -> str:
    """Derive a field name for a sequence element."""
    match node:
        case GBNFReference(rule=r):
            return r.replace("-", "_")
        case GBNFLiteral(values=(v, *_)):
            cleaned = re.sub(r"\W+", "_", v).strip("_")
            return cleaned if cleaned else f"token_{position}"
        case _:
            return f"elem_{position}"


# ------------------------------------------------------------------
# Nullable check and first-terminal extraction
# Kept here (in the pure-Python file) so they can be used without pydantic.
# builder.py re-exports first_terminal for convenience.
# ------------------------------------------------------------------


def _is_nullable(node: GBNFNode) -> bool:
    """True if node can match the empty string."""
    match node:
        case GBNFOptional():
            return True
        case GBNFRepetition(min=0):
            return True
        case GBNFLiteral(values=(v,)) if v == "":
            return True
        case GBNFAlternation(arms=arms):
            return any(_is_nullable(a) for a in arms)
        case GBNFSequence(elements=els):
            return all(_is_nullable(e.node) for e in els)
        case _:
            return False


def first_terminal(
    rules: dict[str, "GBNFNode"],
    node: "GBNFNode",
    _seen: frozenset[str] = frozenset(),
) -> str | None:
    """Return the first fixed literal a rule must start with.

    - GBNFLiteral with non-empty value → return it
    - GBNFReference → recurse into the referenced rule
    - GBNFSequence → walk left to right, skip nullable elements
    - GBNFRepetition(min>=1) → recurse into element
    - GBNFAlternation where every arm shares the same first terminal → return it
    - Everything else → None
    """
    match node:
        case GBNFLiteral(values=(v, *_)) if v:
            return v

        case GBNFReference(rule=r) if r not in _seen and r in rules:
            return first_terminal(rules, rules[r], _seen | {r})

        case GBNFSequence(elements=elements):
            for el in elements:
                t = first_terminal(rules, el.node, _seen)
                if t is not None:
                    return t
                if not _is_nullable(el.node):
                    return None
            return None

        case GBNFRepetition(element=el, min=m) if m >= 1:
            return first_terminal(rules, el, _seen)

        case GBNFAlternation(arms=arms):
            terminals = [first_terminal(rules, a, _seen) for a in arms]
            if terminals and len(set(terminals)) == 1 and terminals[0] is not None:
                return terminals[0]
            return None

        case _:
            return None


def dispatch_table(
    rules: dict[str, "GBNFNode"],
    rule: str,
) -> dict[str, str]:
    """Return {first_literal: rule_name} for an alternation rule.

    Pure Python — no pydantic. Used by the parser and by the example.
    """
    if rule not in rules:
        return {}
    node = rules[rule]
    if not isinstance(node, GBNFAlternation):
        return {}
    table: dict[str, str] = {}
    for arm in node.arms:
        match arm:
            case GBNFReference(rule=r):
                t = first_terminal(rules, rules.get(r, arm))
                if t is not None:
                    table[t] = r
    return table
