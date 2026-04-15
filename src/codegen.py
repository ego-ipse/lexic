"""
GBNF → Pydantic codegen.

codegen(grammar_path) parses a .gbnf file, classifies each rule per the
design contract (S01-SCENARIOS.md), and writes an importable Python module
to src/generated/<stem>.py containing real Pydantic model classes.

Does not use exec.  Generated .py files use standard class syntax.
eval() is used *only* to resolve type-annotation strings against
a known registry namespace.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional



# ---------------------------------------------------------------------------
# 1. GBNF AST
# ---------------------------------------------------------------------------


@dataclass
class Literal:
    value: str


@dataclass
class CharClass:
    pattern: str  # e.g. "[a-z]"


@dataclass
class RuleRef:
    name: str  # e.g. "expr"


@dataclass
class Group:
    alt: Alternation


@dataclass
class Item:
    atom: Literal | CharClass | RuleRef | Group
    quantifier: str | None = None  # None, "?", "*", "+"


@dataclass
class Sequence:
    items: list[Item] = field(default_factory=list)


@dataclass
class Alternation:
    seqs: list[Sequence] = field(default_factory=list)


@dataclass
class Rule:
    name: str
    body: Alternation


# ---------------------------------------------------------------------------
# 2. GBNF Parser
# ---------------------------------------------------------------------------


class GBNFParser:
    """Hand-written recursive-descent parser for GBNF."""

    def __init__(self, text: str):
        self.text = text
        self.pos = 0

    # -- helpers --

    def _at_end(self) -> bool:
        return self.pos >= len(self.text)

    def _peek(self) -> str:
        if self._at_end():
            return ""
        return self.text[self.pos]

    def _advance(self) -> str:
        ch = self.text[self.pos]
        self.pos += 1
        return ch

    def _skip_ws_inline(self):
        """Skip spaces/tabs but NOT newlines."""
        while not self._at_end() and self.text[self.pos] in " \t":
            self.pos += 1

    def _skip_line_comment(self):
        if not self._at_end() and self.text[self.pos] == "#":
            while not self._at_end() and self.text[self.pos] != "\n":
                self.pos += 1

    def _skip_ws_and_comments(self):
        while not self._at_end():
            if self.text[self.pos] in " \t\n\r":
                self.pos += 1
            elif self.text[self.pos] == "#":
                self._skip_line_comment()
            else:
                break

    # -- top-level --

    def parse(self) -> list[Rule]:
        rules: list[Rule] = []
        self._skip_ws_and_comments()
        while not self._at_end():
            rules.append(self._parse_rule())
            self._skip_ws_and_comments()
        return rules

    def _parse_rule(self) -> Rule:
        name = self._parse_name()
        self._skip_ws_inline()
        # expect "::="
        assert self.text[self.pos : self.pos + 3] == "::=", (
            f"Expected '::=' at pos {self.pos}, got {self.text[self.pos : self.pos + 10]!r}"
        )
        self.pos += 3
        self._skip_ws_inline()
        body = self._parse_alternation()
        return Rule(name, body)

    def _parse_name(self) -> str:
        start = self.pos
        while not self._at_end() and (
            self.text[self.pos].isalnum() or self.text[self.pos] in "-_"
        ):
            self.pos += 1
        return self.text[start : self.pos]

    # -- alternation / sequence / item --

    def _parse_alternation(self) -> Alternation:
        seqs = [self._parse_sequence()]
        while True:
            self._skip_body_ws()
            if not self._at_end() and self._peek() == "|":
                self.pos += 1
                self._skip_body_ws()
                seqs.append(self._parse_sequence())
            else:
                break
        return Alternation(seqs)

    def _skip_body_ws(self):
        """Skip whitespace within a rule body (including newlines that are
        continuations of the current rule, but not ones starting a new rule)."""
        while not self._at_end():
            ch = self.text[self.pos]
            if ch in " \t":
                self.pos += 1
            elif ch == "\n":
                # Check if next non-ws content is a rule definition
                saved = self.pos
                self.pos += 1
                # skip spaces/tabs
                while not self._at_end() and self.text[self.pos] in " \t":
                    self.pos += 1
                # skip comment lines
                if not self._at_end() and self.text[self.pos] == "#":
                    self._skip_line_comment()
                    continue
                # Check if we hit end or a new rule
                if self._at_end():
                    break
                # new rule starts with identifier ::=
                probe = self.pos
                while probe < len(self.text) and (
                    self.text[probe].isalnum() or self.text[probe] in "-_"
                ):
                    probe += 1
                # skip spaces
                while probe < len(self.text) and self.text[probe] in " \t":
                    probe += 1
                if (
                    probe + 3 <= len(self.text)
                    and self.text[probe : probe + 3] == "::="
                ):
                    # This is a new rule — backtrack
                    self.pos = saved
                    break
                # otherwise it's continuation of current rule
            else:
                break

    def _parse_sequence(self) -> Sequence:
        items: list[Item] = []
        while True:
            self._skip_body_ws()
            if self._at_end():
                break
            ch = self._peek()
            if ch == "#":
                # Inline comment — skip to end of line
                self._skip_line_comment()
                continue
            if ch in "|)\n":
                # Check if newline is actually end of rule
                if ch == "\n":
                    saved = self.pos
                    self._skip_body_ws()
                    if self.pos == saved:
                        break
                    continue
                break
            item = self._parse_item()
            if item is not None:
                items.append(item)
            else:
                # Unknown character — skip to avoid infinite loop
                self.pos += 1
        return Sequence(items)

    def _parse_item(self) -> Item | None:
        atom = self._parse_atom()
        if atom is None:
            return None
        quantifier = None
        if not self._at_end() and self._peek() in "?*+":
            quantifier = self._advance()
        # Handle {N,M} quantifiers (used in json grammars) - treat as no quantifier
        if not self._at_end() and self._peek() == "{":
            saved = self.pos
            self.pos += 1
            # parse digits, comma, digits, }
            content = ""
            while not self._at_end() and self._peek() != "}":
                content += self._advance()
            if not self._at_end():
                self.pos += 1  # skip }
            # {N,M} is a bounded repeat — for our purposes, treat as no quantifier
            # (the pattern is still str)
        return Item(atom, quantifier)

    def _parse_atom(self) -> Literal | CharClass | RuleRef | Group | None:
        if self._at_end():
            return None
        ch = self._peek()
        if ch == '"':
            return self._parse_literal()
        if ch == "[":
            return self._parse_charclass()
        if ch == "(":
            return self._parse_group()
        if ch.isalpha() or ch == "_":
            return self._parse_ruleref()
        return None

    def _parse_literal(self) -> Literal:
        assert self._advance() == '"'
        value = ""
        while not self._at_end() and self._peek() != '"':
            ch = self._advance()
            if ch == "\\":
                value += ch + self._advance()
            else:
                value += ch
        assert self._advance() == '"'
        return Literal(value)

    def _parse_charclass(self) -> CharClass:
        start = self.pos
        assert self._advance() == "["
        # handle ] as first char in class
        if not self._at_end() and self._peek() == "^":
            self._advance()
        if not self._at_end() and self._peek() == "]":
            self._advance()
        while not self._at_end() and self._peek() != "]":
            if self._peek() == "\\":
                self._advance()
                if not self._at_end():
                    self._advance()
            else:
                self._advance()
        if not self._at_end():
            self._advance()  # ]
        return CharClass(self.text[start : self.pos])

    def _parse_group(self) -> Group:
        assert self._advance() == "("
        self._skip_body_ws()
        alt = self._parse_alternation()
        self._skip_body_ws()
        if not self._at_end() and self._peek() == ")":
            self._advance()
        return Group(alt)

    def _parse_ruleref(self) -> RuleRef:
        name = self._parse_name()
        return RuleRef(name)


# ---------------------------------------------------------------------------
# 3. Helpers
# ---------------------------------------------------------------------------

# Rules that are always semantic terminals (value: str) regardless of structure
_ALWAYS_SEMANTIC_TERMINAL = frozenset(
    {
        "ws",
        "singleLineComment",
        "multiLineComment",
    }
)


def _is_structurally_complex(alt: Alternation) -> bool:
    """Heuristic: a rule is D10 (semantic terminal) if its body is dominated
    by character-level patterns rather than meaningful sub-components.

    Triggers:
    1. *-quantified group with nested NON-trivial groups (escape patterns)
    2. Body has no rule-ref items at all (pure char/literal/group composition)
    """

    def _has_any_ruleref(items: list[Item]) -> bool:
        for it in items:
            if _is_ws_item(it):
                continue
            if isinstance(it.atom, RuleRef):
                return True
            if isinstance(it.atom, Group):
                for seq in it.atom.alt.seqs:
                    if _has_any_ruleref(seq.items):
                        return True
        return False

    def _has_nontrivial_nested_group(items: list[Item]) -> bool:
        """Check if items contain groups that aren't pure-literal alternations."""
        for it in items:
            if isinstance(it.atom, Group):
                if not _is_all_pure_literal_alt(it.atom.alt):
                    return True
        return False

    for seq in alt.seqs:
        stripped = _strip_ws(seq)
        # Check 1: *-quantified group with non-trivial nested groups
        for it in stripped.items:
            if isinstance(it.atom, Group) and it.quantifier == "*":
                for inner_seq in it.atom.alt.seqs:
                    if _has_nontrivial_nested_group(inner_seq.items):
                        return True

    # Check 2: no rule references AND contains groups with alternations →
    # character-level pattern (e.g., JSON number with ("-"? ([0-9] | [1-9] [0-9]{...})))
    # Groups without alternations (like optional `([a-h] "x")?`) are NOT complex.
    def _has_group_with_alt(items: list[Item]) -> bool:
        for it in items:
            if isinstance(it.atom, Group):
                if len(it.atom.alt.seqs) > 1:
                    return True
                # Check nested
                for seq in it.atom.alt.seqs:
                    if _has_group_with_alt(seq.items):
                        return True
        return False

    all_no_refs = True
    has_group_alt = False
    for seq in alt.seqs:
        stripped = _strip_ws(seq)
        if _has_any_ruleref(stripped.items):
            all_no_refs = False
            break
        if _has_group_with_alt(stripped.items):
            has_group_alt = True
    if all_no_refs and has_group_alt:
        return True

    return False


def _to_pascal(name: str) -> str:
    """Convert rule name to PascalCase."""
    # Split on hyphens and underscores
    parts = re.split(r"[-_]", name)
    return "".join(p[0].upper() + p[1:] if p else "" for p in parts)


def _is_ws_item(item: Item) -> bool:
    """Check if an item is a ws rule reference."""
    return isinstance(item.atom, RuleRef) and item.atom.name == "ws"


def _strip_ws(seq: Sequence) -> Sequence:
    """Return sequence with ws references removed."""
    return Sequence([it for it in seq.items if not _is_ws_item(it)])


def _is_pure_literal(item: Item) -> bool:
    """Check if item is a literal or char-class (maps to str)."""
    return isinstance(item.atom, (Literal, CharClass))


def _is_pure_literal_seq(seq: Sequence) -> bool:
    """Check if every item in the sequence is a literal or char-class."""
    return len(seq.items) > 0 and all(_is_pure_literal(it) for it in seq.items)


def _is_single_ruleref(seq: Sequence) -> str | None:
    """If sequence is exactly one rule-ref (after ws stripping), return rule name."""
    stripped = _strip_ws(seq)
    if len(stripped.items) == 1:
        it = stripped.items[0]
        atom = it.atom
        if it.quantifier is None and isinstance(atom, RuleRef):
            return atom.name
        # Unwrap group containing single rule ref
        if it.quantifier is None and isinstance(atom, Group):
            inner = atom.alt
            if len(inner.seqs) == 1:
                inner_stripped = _strip_ws(inner.seqs[0])
                if len(inner_stripped.items) == 1:
                    inner_it = inner_stripped.items[0]
                    if inner_it.quantifier is None and isinstance(
                        inner_it.atom, RuleRef
                    ):
                        return inner_it.atom.name
    return None


def _unwrap_group_alt(alt: Alternation) -> Alternation:
    """If alternation has one sequence that is a single unquantified group, unwrap it."""
    if len(alt.seqs) == 1:
        seq = alt.seqs[0]
        stripped = _strip_ws(seq)
        if len(stripped.items) == 1:
            it = stripped.items[0]
            if isinstance(it.atom, Group) and it.quantifier is None:
                return it.atom.alt
    return alt


def _is_all_pure_literal_alt(alt: Alternation) -> bool:
    """Check if all arms (after ws stripping) are pure-literal sequences."""
    for seq in alt.seqs:
        stripped = _strip_ws(seq)
        if len(stripped.items) == 0:
            continue  # empty arm (like ws rule's first arm)
        if not _is_pure_literal_seq(stripped):
            return False
    return True


def _is_inline_literal_alt_group(item: Item) -> bool:
    """Check if item is an unquantified group whose alternation is all pure literals.
    e.g. ("+" | "-") or ("true" | "false" | "null")
    """
    if not isinstance(item.atom, Group) or item.quantifier is not None:
        return False
    return _is_all_pure_literal_alt(item.atom.alt)


# ---------------------------------------------------------------------------
# 4. Rule Classification
# ---------------------------------------------------------------------------


@dataclass
class FieldSpec:
    name: str  # field1, field2, ...
    type_str: str  # "str", "Optional[str]", "List[Foo]", etc.
    annotation: Any  # actual type object for create_model


@dataclass
class ClassSpec:
    name: str
    base: str  # "BaseModel" or parent class name
    is_abstract: bool
    fields: list[FieldSpec] = field(default_factory=list)
    is_value_str: bool = False  # class Foo(BaseModel): value: str


def _classify_rule(rule: Rule, rules_dict: dict[str, Rule]) -> str:
    """Return classification: 'semantic_terminal', 'pure_literal_alt', 'named_alt', 'sequence'"""
    # D14 priority 1: semantic terminal
    if rule.name in _ALWAYS_SEMANTIC_TERMINAL:
        return "semantic_terminal"

    alt = _unwrap_group_alt(rule.body)

    # D10: structurally complex rules (escape sequences, etc.)
    if _is_structurally_complex(alt):
        return "semantic_terminal"

    # Strip ws from all arms
    arms = [_strip_ws(seq) for seq in alt.seqs]
    # Remove empty arms
    arms = [a for a in arms if len(a.items) > 0]

    if len(arms) == 0:
        return "semantic_terminal"

    # D14 priority 2: pure literal alternation
    if len(arms) > 1 and all(_is_pure_literal_seq(a) for a in arms):
        return "pure_literal_alt"

    # Also check if it's a single group that's all-literal
    if len(arms) == 1 and len(arms[0].items) == 1:
        it = arms[0].items[0]
        if isinstance(it.atom, Group) and it.quantifier is None:
            if _is_all_pure_literal_alt(it.atom.alt):
                return "pure_literal_alt"

    # D14 priority 3: named-rule alternation (at least some arms are single named refs)
    if len(arms) > 1:
        has_named = False
        for a in arms:
            ref = _is_single_ruleref(a)
            if ref is not None:
                has_named = True
        if has_named:
            return "named_alt"

    # D14 priority 4: sequence (single arm or multi-arm where no arm is a named ref)
    if len(arms) == 1:
        return "sequence"

    # Multi-arm where no arm is single named ref → still named_alt with all anonymous arms
    if len(arms) > 1:
        return "named_alt"

    return "sequence"


# ---------------------------------------------------------------------------
# 5. Code Generation
# ---------------------------------------------------------------------------


def _count_opt_groups(seq: Sequence) -> int:
    """Count multi-element optional groups in sequence (for Opt numbering)."""
    count = 0
    for it in seq.items:
        if _is_ws_item(it):
            continue
        if it.quantifier == "?" and isinstance(it.atom, Group):
            inner_stripped = (
                _strip_ws(it.atom.alt.seqs[0])
                if len(it.atom.alt.seqs) == 1
                else it.atom.alt.seqs[0]
            )
            if len(inner_stripped.items) > 1:
                count += 1
    return count


def _seq_to_fields_and_helpers(
    seq: Sequence,
    class_name: str,
    name_map: dict[str, str],
) -> tuple[list[FieldSpec], list[ClassSpec]]:
    """Convert a sequence to fields and helper classes."""
    fields: list[FieldSpec] = []
    helpers: list[ClassSpec] = []
    field_idx = 0
    opt_count = _count_opt_groups(seq)
    opt_idx = 0

    for it in seq.items:
        if _is_ws_item(it):
            continue

        field_idx += 1
        fname = f"field{field_idx}"

        atom = it.atom
        q = it.quantifier

        # --- Literal or CharClass ---
        if isinstance(atom, (Literal, CharClass)):
            if q == "?":
                fields.append(FieldSpec(fname, "Optional[str]", (Optional[str], ...)))
            else:
                fields.append(FieldSpec(fname, "str", (str, ...)))

        # --- RuleRef ---
        elif isinstance(atom, RuleRef):
            ref_cls = name_map.get(atom.name, _to_pascal(atom.name))
            if q is None:
                fields.append(FieldSpec(fname, ref_cls, (ref_cls, ...)))
            elif q == "?":
                fields.append(
                    FieldSpec(fname, f"Optional[{ref_cls}]", (Optional[str], ...))
                )  # placeholder
            elif q in ("+", "*"):
                fields.append(
                    FieldSpec(fname, f"List[{ref_cls}]", (list, ...))
                )  # placeholder

        # --- Group ---
        elif isinstance(atom, Group):
            inner_alt = atom.alt
            inner_arms = [_strip_ws(s) for s in inner_alt.seqs]
            inner_arms = [a for a in inner_arms if len(a.items) > 0]

            # Inline literal alternation group → str
            if _is_inline_literal_alt_group(it):
                if q == "?":
                    fields.append(
                        FieldSpec(fname, "Optional[str]", (Optional[str], ...))
                    )
                else:
                    fields.append(FieldSpec(fname, "str", (str, ...)))

            # D4: Inline alternation of named rules → Union
            elif (
                q is None
                and len(inner_arms) > 1
                and all(_is_single_ruleref(a) is not None for a in inner_arms)
            ):
                ref_names = [
                    name_map.get(
                        _is_single_ruleref(a), _to_pascal(_is_single_ruleref(a))
                    )
                    for a in inner_arms
                ]
                union_str = f"Union[{', '.join(ref_names)}]"
                fields.append(FieldSpec(fname, union_str, (str, ...)))  # placeholder

            # Repeated group (+ or *) → List[HelperItem]
            elif q in ("+", "*"):
                if len(inner_arms) == 1 and len(inner_arms[0].items) == 1:
                    # Single item repeated
                    inner_it = inner_arms[0].items[0]
                    if isinstance(inner_it.atom, RuleRef):
                        ref_cls = name_map.get(
                            inner_it.atom.name, _to_pascal(inner_it.atom.name)
                        )
                        fields.append(FieldSpec(fname, f"List[{ref_cls}]", (list, ...)))
                    else:
                        fields.append(FieldSpec(fname, "List[str]", (list, ...)))
                else:
                    # Multi-element repeated group → helper Item class
                    helper_name = f"{class_name}Item"
                    h_fields, h_helpers = _seq_to_fields_and_helpers(
                        inner_arms[0] if len(inner_arms) == 1 else inner_arms[0],
                        helper_name,
                        name_map,
                    )
                    helpers.extend(h_helpers)
                    helpers.append(ClassSpec(helper_name, "BaseModel", False, h_fields))
                    fields.append(FieldSpec(fname, f"List[{helper_name}]", (list, ...)))

            # Optional group → helper Opt class
            elif q == "?":
                if len(inner_arms) == 1 and len(inner_arms[0].items) == 1:
                    inner_it = inner_arms[0].items[0]
                    if isinstance(inner_it.atom, (Literal, CharClass)):
                        fields.append(
                            FieldSpec(fname, "Optional[str]", (Optional[str], ...))
                        )
                    elif isinstance(inner_it.atom, RuleRef):
                        ref_cls = name_map.get(
                            inner_it.atom.name, _to_pascal(inner_it.atom.name)
                        )
                        fields.append(
                            FieldSpec(
                                fname, f"Optional[{ref_cls}]", (Optional[str], ...)
                            )
                        )
                    else:
                        fields.append(
                            FieldSpec(fname, "Optional[str]", (Optional[str], ...))
                        )
                else:
                    opt_idx += 1
                    if opt_count > 1:
                        helper_name = f"{class_name}Opt{opt_idx}"
                    else:
                        helper_name = f"{class_name}Opt"
                    h_fields, h_helpers = _seq_to_fields_and_helpers(
                        inner_arms[0] if len(inner_arms) == 1 else inner_arms[0],
                        helper_name,
                        name_map,
                    )
                    helpers.extend(h_helpers)
                    helpers.append(ClassSpec(helper_name, "BaseModel", False, h_fields))
                    fields.append(
                        FieldSpec(
                            fname, f"Optional[{helper_name}]", (Optional[str], ...)
                        )
                    )

            # Unquantified single-arm group (just transparent)
            elif q is None and len(inner_arms) == 1:
                # Undo the field_idx increment from the outer loop since
                # we're inlining the group's contents directly
                field_idx -= 1
                # Treat contents as inline sequence elements
                for inner_it in inner_arms[0].items:
                    if _is_ws_item(inner_it):
                        continue
                    # Recurse as a single-item sequence
                    sub_fields, sub_helpers = _seq_to_fields_and_helpers(
                        Sequence([inner_it]), class_name, name_map
                    )
                    # Re-number fields
                    for sf in sub_fields:
                        field_idx += 1
                        sf.name = f"field{field_idx}"
                        fields.append(sf)
                    helpers.extend(sub_helpers)

            else:
                # fallback
                fields.append(FieldSpec(fname, "str", (str, ...)))

    return fields, helpers


def generate_classes(grammar_path: str | Path) -> dict[str, type]:
    """Parse a GBNF file and return a dict of generated Pydantic model classes."""
    grammar_path = Path(grammar_path)
    gbnf_text = grammar_path.read_text()
    stem = grammar_path.stem

    # Parse
    parser = GBNFParser(gbnf_text)
    rules = parser.parse()
    rules_dict = {r.name: r for r in rules}

    # Build name map
    name_map: dict[str, str] = {}
    for r in rules:
        name_map[r.name] = _to_pascal(r.name)

    # Classify rules
    classifications: dict[str, str] = {}
    for r in rules:
        classifications[r.name] = _classify_rule(r, rules_dict)

    # Build parent map for named alternations
    # parent_of[child_rule_name] = parent_class_name
    parent_of: dict[str, str] = {}
    # arm_anon[parent_rule_name] = [(arm_idx, seq)] for anonymous arms
    arm_anon: dict[str, list[tuple[int, Sequence]]] = {}

    for r in rules:
        if classifications[r.name] != "named_alt":
            continue
        alt = _unwrap_group_alt(r.body)
        arms = [_strip_ws(seq) for seq in alt.seqs]
        anon_arms = []
        arm_counter = 0
        for arm in arms:
            if len(arm.items) == 0:
                continue
            arm_counter += 1
            ref = _is_single_ruleref(arm)
            if ref is not None:
                parent_of[ref] = name_map[r.name]
            else:
                anon_arms.append((arm_counter, arm))
        arm_anon[r.name] = anon_arms

    # Generate class specs
    all_specs: list[ClassSpec] = []

    for r in rules:
        cls_name = name_map[r.name]
        cls = classifications[r.name]

        if cls in ("semantic_terminal", "pure_literal_alt"):
            base = parent_of.get(r.name, "BaseModel")
            all_specs.append(
                ClassSpec(
                    cls_name,
                    base,
                    False,
                    [FieldSpec("value", "str", (str, ...))],
                    is_value_str=True,
                )
            )

        elif cls == "named_alt":
            base = parent_of.get(r.name, "BaseModel")
            # Abstract base
            all_specs.append(ClassSpec(cls_name, base, True))
            # Anonymous arm subclasses
            for arm_idx, arm_seq in arm_anon.get(r.name, []):
                arm_name = f"{cls_name}Arm{arm_idx}"
                fields, helpers = _seq_to_fields_and_helpers(
                    arm_seq, arm_name, name_map
                )
                all_specs.extend(helpers)
                all_specs.append(ClassSpec(arm_name, cls_name, False, fields))

        elif cls == "sequence":
            base = parent_of.get(r.name, "BaseModel")
            alt = _unwrap_group_alt(r.body)
            arms = [_strip_ws(seq) for seq in alt.seqs]
            arms = [a for a in arms if len(a.items) > 0]

            if len(arms) == 0:
                all_specs.append(
                    ClassSpec(
                        cls_name,
                        base,
                        False,
                        [FieldSpec("value", "str", (str, ...))],
                        is_value_str=True,
                    )
                )
            else:
                seq = arms[0]
                fields, helpers = _seq_to_fields_and_helpers(seq, cls_name, name_map)
                all_specs.extend(helpers)
                all_specs.append(ClassSpec(cls_name, base, False, fields))

    # Topological sort: base classes before subclasses
    spec_map = {s.name: s for s in all_specs}
    ordered: list[ClassSpec] = []
    visited: set[str] = set()

    def visit(name: str):
        if name in visited:
            return
        visited.add(name)
        spec = spec_map.get(name)
        if spec is None:
            return
        if spec.base not in ("BaseModel",) and spec.base in spec_map:
            visit(spec.base)
        ordered.append(spec)

    for s in all_specs:
        visit(s.name)

    # Write Python source file
    out_dir = Path(__file__).parent / "generated"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{stem}.py"

    lines = [
        '"""Auto-generated Pydantic models from {stem}.gbnf."""'.format(stem=stem),
        "from __future__ import annotations",
        "",
        "from abc import ABC",
        "from typing import List, Optional, Union",
        "",
        "from pydantic import BaseModel",
        "",
        "",
    ]

    for spec in ordered:
        bases = []
        if spec.base == "BaseModel":
            bases.append("BaseModel")
        else:
            bases.append(spec.base)
        if spec.is_abstract:
            bases.append("ABC")
        base_str = ", ".join(bases)

        lines.append(f"class {spec.name}({base_str}):")
        if spec.is_abstract:
            lines.append("    pass")
        elif spec.is_value_str:
            lines.append("    value: str")
        elif spec.fields:
            for f in spec.fields:
                lines.append(f"    {f.name}: {f.type_str}")
        else:
            lines.append("    pass")
        lines.append("")
        lines.append("")

    # model_rebuild calls
    lines.append("# Resolve forward references")
    lines.append("_ns = {k: v for k, v in globals().items() if isinstance(v, type)}")
    for spec in ordered:
        lines.append(f"{spec.name}.model_rebuild(_types_namespace=_ns)")
    lines.append("")

    out_path.write_text("\n".join(lines))

    # Import and return
    import importlib

    module_name = f"src.generated.{stem}"
    # Remove from cache if previously imported
    import sys

    if module_name in sys.modules:
        del sys.modules[module_name]

    mod = importlib.import_module(module_name)

    result: dict[str, type] = {}
    for spec in ordered:
        cls_obj = getattr(mod, spec.name, None)
        if cls_obj is not None:
            result[spec.name] = cls_obj

    return result


def codegen(grammar_path: str | Path) -> dict[str, type]:
    """Public API: parse GBNF, generate models, return dict[name, type]."""
    return generate_classes(grammar_path)
