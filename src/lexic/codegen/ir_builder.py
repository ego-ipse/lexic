"""IRBuilder: converts GBNF AST (list[Rule]) into list[RuleSpec].

Single responsibility: understanding GBNF semantics.
Knows nothing about Lark, Python source, or Pydantic.
"""

from __future__ import annotations

import re
from typing import cast

from .ast import Alternation, CharClass, Group, Item, Literal, Rule, RuleRef, Sequence
from lexic.ir import (
    AlternationAtom,
    Atom,
    CharClassAtom,
    InlineAlternationAtom,
    InlineRegexAtom,
    LiteralAtom,
    QuantifiedLiteralAtom,
    RuleRefAtom,
    RuleSpec,
)
from lexic.utils.quantifiers import quantifier_to_bounds


# ── Name utilities ────────────────────────────────────────────────────────────


def to_pascal(name: str) -> str:
    """Convert 'jp-char' or 'json_ws' → 'JpChar' / 'JsonWs'."""
    parts = re.split(r"[-_]", name)
    return "".join(p[0].upper() + p[1:] if p else "" for p in parts)


# ── Classification helpers ────────────────────────────────────────────────────


def _is_ws_item(item: Item) -> bool:
    return isinstance(item.atom, RuleRef) and item.atom.name == "ws"


def _strip_ws(seq: Sequence) -> Sequence:
    return Sequence([it for it in seq.items if not _is_ws_item(it)])


def _is_pure_literal(item: Item) -> bool:
    return isinstance(item.atom, (Literal, CharClass))


def _is_pure_literal_seq(seq: Sequence) -> bool:
    stripped = _strip_ws(seq)
    return len(stripped.items) > 0 and all(
        _is_pure_literal(it) for it in stripped.items
    )


def _is_single_ruleref(seq: Sequence) -> str | None:
    """If sequence is exactly one unquantified rule ref (after ws strip), return name."""
    stripped = _strip_ws(seq)
    if len(stripped.items) != 1:
        return None
    it = stripped.items[0]
    if it.quantifier is not None:
        return None
    if isinstance(it.atom, RuleRef):
        return it.atom.name
    if isinstance(it.atom, Group):
        inner = it.atom.alt
        if len(inner.seqs) == 1:
            inner_stripped = _strip_ws(inner.seqs[0])
            if len(inner_stripped.items) == 1:
                inner_it = inner_stripped.items[0]
                if inner_it.quantifier is None and isinstance(inner_it.atom, RuleRef):
                    return inner_it.atom.name
    return None


def _to_regex(group: Group) -> str:
    """Convert a GBNF Group to a regex pattern string for Lark terminals."""
    arms: list[str] = []
    for seq in group.alt.seqs:
        parts: list[str] = []
        for it in seq.items:
            if isinstance(it.atom, Literal):
                q = it.quantifier or ""
                parts.append(re.escape(it.atom.value) + q)
            elif isinstance(it.atom, CharClass):
                q = it.quantifier or ""
                parts.append(it.atom.pattern + q)
            elif isinstance(it.atom, Group):
                q = it.quantifier or ""
                parts.append(_to_regex(it.atom) + q)
            # RuleRef inside a group cannot be inlined — skip
        arms.append("".join(parts))
    body = "|".join(arms)
    return f"({body})" if len(arms) > 1 else body


def _to_gbnf(group: Group) -> str:
    """Convert a GBNF Group back to GBNF syntax for GBNFEmitter."""
    arms: list[str] = []
    for seq in group.alt.seqs:
        parts: list[str] = []
        for it in seq.items:
            if isinstance(it.atom, Literal):
                q = it.quantifier or ""
                parts.append(f'"{it.atom.value}"{q}')
            elif isinstance(it.atom, CharClass):
                q = it.quantifier or ""
                parts.append(it.atom.pattern + q)
            elif isinstance(it.atom, Group):
                q = it.quantifier or ""
                parts.append(_to_gbnf(it.atom) + q)
        arms.append("".join(parts))
    body = "|".join(arms)
    return f"({body})" if len(arms) > 1 else body


def _build_inline_regex(group: Group, min_: int, max_: int | None) -> InlineRegexAtom:
    """Build an InlineRegexAtom from a pure-literal or mixed GBNF group."""
    return InlineRegexAtom(
        regex=_to_regex(group),
        gbnf=_to_gbnf(group),
        min=min_,
        max=max_,
    )


def _unwrap_group_alt(alt: Alternation) -> Alternation:
    if len(alt.seqs) != 1:
        return alt
    stripped = _strip_ws(alt.seqs[0])
    if len(stripped.items) == 1:
        it = stripped.items[0]
        if isinstance(it.atom, Group) and it.quantifier is None:
            return it.atom.alt
    return alt


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


def _has_nontrivial_group(items: list[Item]) -> bool:
    for it in items:
        if isinstance(it.atom, Group):
            for seq in it.atom.alt.seqs:
                if any(isinstance(i.atom, Group) for i in seq.items):
                    return True
    return False


def _has_group_with_alt(items: list[Item]) -> bool:
    for it in items:
        if isinstance(it.atom, Group) and len(it.atom.alt.seqs) > 1:
            return True
    return False


def _is_structurally_complex(alt: Alternation) -> bool:
    for seq in alt.seqs:
        stripped = _strip_ws(seq)
        for it in stripped.items:
            if isinstance(it.atom, Group) and it.quantifier == "*":
                for inner_seq in it.atom.alt.seqs:
                    if _has_nontrivial_group(inner_seq.items):
                        return True
    all_no_refs = not any(_has_any_ruleref(_strip_ws(seq).items) for seq in alt.seqs)
    has_group_alt = any(_has_group_with_alt(_strip_ws(seq).items) for seq in alt.seqs)
    return all_no_refs and has_group_alt


def _classify(rule: Rule) -> str:
    alt = _unwrap_group_alt(rule.body)
    if _is_structurally_complex(alt):
        return "value_str"
    arms = [a for a in (_strip_ws(seq) for seq in alt.seqs) if len(a.items) > 0]
    if not arms:
        return "value_str"
    if len(arms) > 1 and all(_is_pure_literal_seq(a) for a in arms):
        return "pure_literal_alt"
    if (
        len(arms) == 1
        and len(arms[0].items) == 1
        and isinstance(arms[0].items[0].atom, Group)
        and arms[0].items[0].quantifier is None
        and all(
            _is_pure_literal_seq(_strip_ws(s)) for s in arms[0].items[0].atom.alt.seqs
        )
    ):
        return "pure_literal_alt"
    if len(arms) > 1 and any(_is_single_ruleref(a) is not None for a in arms):
        return "named_alt"
    if len(arms) == 1:
        # Single arm with only literals/char classes (no rule refs at all) → value_str
        # Check if the full (non-stripped) sequences contain ANY rule reference (inc. ws)
        full_seqs = alt.seqs
        has_any_rule_ref = any(
            any(isinstance(it.atom, RuleRef) for it in s.items) for s in full_seqs
        )
        if not has_any_rule_ref and _is_pure_literal_seq(arms[0]):
            return "value_str"
        return "sequence"
    return "named_alt"


# ── Semantic field naming ─────────────────────────────────────────────────────

_CHARCLASS_NAMES: dict[str, str] = {
    "[0-9]": "digit",
    "[1-9]": "digit",
    "[0-9a-fA-F]": "hex",
    "[a-fA-F0-9]": "hex",
    "[a-f]": "hex_lower",
    "[A-F]": "hex_upper",
    "[a-z]": "lower",
    "[A-Z]": "upper",
    "[a-zA-Z]": "alpha",
    "[a-z0-9_]": "alnum",
    "[a-zA-Z_]": "name_start",
    "[a-zA-Z0-9_]": "alnum",
    "[a-zA-Z_0-9]": "alnum",
    "[+\\-*/]": "op",
    "[-+*/]": "op",
    "[+#]": "annotation",
    "[ \\t\\n]": "ws_char",
    "[ \\t]": "hspace",
    "[^\\n]": "non_newline",
    '[^"\\\\]': "str_char",
}

_LITERAL_NAMES: dict[str, str] = {
    "-": "sign",
    "+": "sign",
    ".": "dot",
    ",": "comma",
    ":": "colon",
    ";": "semicolon",
    "=": "eq",
    "x": "x",
    "e": "e",
    "E": "E",
}


def _sanitize_pattern(pattern: str) -> str:
    """Derive a readable name hint from a bracket expression.

    '[NBKQR]' → 'nbkqr', '[a-h]' → 'a_h', '[1-8]' → 'cc_1_8'

    Note: backslash-heavy patterns (e.g. [\\\\n], [\\\\u2028]) produce an
    empty string here — the caller falls back to a generic quantifier name.
    Patterns in _CHARCLASS_NAMES are handled before this function is called.
    """
    inner = re.sub(r"[\[\]\^]", "", pattern)
    inner = inner.replace("-", "_").lower()
    # Remove any remaining non-identifier characters
    inner = re.sub(r"[^a-z0-9_]", "", inner)
    inner = inner.strip("_")
    # Collapse repeated underscores
    inner = re.sub(r"_+", "_", inner)
    if not inner:
        return ""
    # Python identifiers cannot start with a digit
    if inner[0].isdigit():
        inner = "cc_" + inner
    return inner[:12].strip("_")


def _charclass_field_name(atom: "CharClassAtom", min_: int, max_: int | None) -> str:
    """Derive a semantic field name for a CharClassAtom."""
    if atom.pattern in _CHARCLASS_NAMES:
        return _CHARCLASS_NAMES[atom.pattern]
    hint = _sanitize_pattern(atom.pattern)
    if hint:
        return hint
    if max_ is None:
        return "tail"
    if min_ == 0 and max_ == 1:
        return "opt"
    return "cc"


def _quantified_literal_field_name(value: str) -> str:
    """Derive a field name for a QuantifiedLiteralAtom."""
    if value in _LITERAL_NAMES:
        return _LITERAL_NAMES[value]
    sanitized = re.sub(r"[^a-zA-Z0-9]", "_", value).strip("_").lower()[:12]
    return sanitized or "lit"


def _inline_regex_field_name(gbnf: str) -> str:
    """Derive a field name for an InlineRegexAtom from its first arm."""
    body = gbnf.strip()
    if body.startswith("(") and body.endswith(")"):
        body = body[1:-1]
    first_arm = body.split("|")[0].strip().strip('"')
    sanitized = re.sub(r"[^a-zA-Z0-9]", "_", first_arm).strip("_").lower()
    # Collapse repeated underscores
    sanitized = re.sub(r"_+", "_", sanitized).strip("_")
    sanitized = sanitized[:12]
    if not sanitized:
        return "inline"
    # Python identifiers cannot start with a digit
    if sanitized[0].isdigit():
        sanitized = ("val_" + sanitized)[:12].strip("_")
    return sanitized


def _assign_field_names(items: list[Atom]) -> dict[str, int]:
    """Assign semantic field names to non-literal atoms."""
    field_map: dict[str, int] = {}
    name_counts: dict[str, int] = {}

    def _unique(base: str) -> str:
        count = name_counts.get(base, 0) + 1
        name_counts[base] = count
        return base if count == 1 else f"{base}{count}"

    for i, atom in enumerate(items):
        if isinstance(atom, LiteralAtom):
            continue

        if isinstance(atom, AlternationAtom):
            continue  # kind='alternation' rules have no fields

        if isinstance(atom, InlineAlternationAtom):
            field_map[_unique("value")] = i

        elif isinstance(atom, RuleRefAtom):
            base = atom.rule_name.replace("-", "_")
            field_map[_unique(base)] = i

        elif isinstance(atom, CharClassAtom):
            base = _charclass_field_name(atom, atom.min, atom.max)
            field_map[_unique(base)] = i

        elif isinstance(atom, QuantifiedLiteralAtom):
            base = _quantified_literal_field_name(atom.value)
            field_map[_unique(base)] = i

        elif isinstance(atom, InlineRegexAtom):
            base = _inline_regex_field_name(atom.gbnf)
            field_map[_unique(base)] = i

    return field_map


# ── Sequence → items ─────────────────────────────────────────────────────────


def _seq_to_atoms(
    seq: Sequence,
    parent_class_name: str,
    helper_specs: list[RuleSpec],
    name_map: dict[str, str],
    parent_of: dict[str, str],
) -> list[Atom]:
    """Convert a single grammar sequence into a list of IR atoms.

    When a quantified group is encountered, a helper RuleSpec is created and
    appended to helper_specs, and a RuleRefAtom pointing to it is returned.
    """
    atoms: list[Atom] = []

    for item in seq.items:
        if isinstance(item.atom, Literal):
            if item.quantifier is not None:
                # Quantified literal: emit as QuantifiedLiteralAtom so the optional/
                # repeated nature is preserved in the IR and downstream emitters.
                min_, max_ = quantifier_to_bounds(item.quantifier)
                atoms.append(
                    QuantifiedLiteralAtom(value=item.atom.value, min=min_, max=max_)
                )
            else:
                atoms.append(LiteralAtom(value=item.atom.value))

        elif isinstance(item.atom, CharClass):
            min_, max_ = quantifier_to_bounds(item.quantifier)
            atoms.append(CharClassAtom(pattern=item.atom.pattern, min=min_, max=max_))

        elif isinstance(item.atom, RuleRef):
            min_, max_ = quantifier_to_bounds(item.quantifier)
            atoms.append(RuleRefAtom(rule_name=item.atom.name, min=min_, max=max_))

        elif isinstance(item.atom, Group):
            min_, max_ = quantifier_to_bounds(item.quantifier)
            inner_arms = [
                a
                for a in (_strip_ws(s) for s in item.atom.alt.seqs)
                if len(a.items) > 0
            ]

            # Inline literal alternation → InlineRegexAtom
            if all(_is_pure_literal_seq(a) for a in inner_arms):
                atoms.append(_build_inline_regex(item.atom, min_, max_))
                continue

            # Inline union of named rules (no quantifier) → InlineAlternationAtom
            if (
                item.quantifier is None
                and len(inner_arms) > 1
                and all(_is_single_ruleref(a) is not None for a in inner_arms)
            ):
                arm_names: list[str] = [
                    cast(str, _is_single_ruleref(a)) for a in inner_arms
                ]
                atoms.append(InlineAlternationAtom(arm_rule_names=arm_names))
                continue

            # Unquantified single-arm group → inline its contents
            if item.quantifier is None and len(inner_arms) == 1:
                inner_atoms = _seq_to_atoms(
                    inner_arms[0], parent_class_name, helper_specs, name_map, parent_of
                )
                atoms.extend(inner_atoms)
                continue

            # Quantified group → create helper RuleSpec
            helper_rule_name = f"{parent_class_name.lower()}-item"
            # Deduplicate helper names
            existing = {s.rule_name for s in helper_specs}
            suffix = 2
            candidate = helper_rule_name
            while candidate in existing:
                candidate = f"{helper_rule_name}{suffix}"
                suffix += 1
            helper_rule_name = candidate

            helper_class_name = to_pascal(helper_rule_name)
            helper_atoms = _seq_to_atoms(
                inner_arms[0] if inner_arms else seq,
                helper_class_name,
                helper_specs,
                name_map,
                parent_of,
            )
            helper_fm = _assign_field_names(helper_atoms)
            helper_spec = RuleSpec(
                rule_name=helper_rule_name,
                class_name=helper_class_name,
                parent_class_name="GrammarModel",
                kind="sequence",
                items=helper_atoms,
                field_map=helper_fm,
            )
            helper_specs.append(helper_spec)
            atoms.append(RuleRefAtom(rule_name=helper_rule_name, min=min_, max=max_))

    return atoms


# ── Main builder ─────────────────────────────────────────────────────────────


class IRBuilder:
    """Converts a list of GBNF Rule objects into a list of RuleSpec IR objects.

    Knows nothing about Lark, Python source, or Pydantic.
    """

    def __init__(self, rules: list[Rule]):
        self._rules = rules
        self._rules_dict = {r.name: r for r in rules}
        self._name_map = {r.name: to_pascal(r.name) for r in rules}

    def build(self) -> list[RuleSpec]:
        """Build and return specs in grammar order (root first)."""
        parent_of = self._compute_parents()
        all_specs: list[RuleSpec] = []

        for rule in self._rules:
            specs = self._build_rule(rule, parent_of, all_specs)
            all_specs.extend(specs)

        return self._topo_sort(all_specs)

    def _compute_parents(self) -> dict[str, str]:
        """For each rule that is a named arm of an alternation, record its parent class."""
        parent_of: dict[str, str] = {}
        for rule in self._rules:
            classification = _classify(rule)
            if classification != "named_alt":
                continue
            alt = _unwrap_group_alt(rule.body)
            parent_cls = self._name_map[rule.name]
            for seq in alt.seqs:
                ref = _is_single_ruleref(_strip_ws(seq))
                if ref is not None:
                    parent_of[ref] = parent_cls
        return parent_of

    def _build_rule(
        self,
        rule: Rule,
        parent_of: dict[str, str],
        existing_specs: list[RuleSpec],
    ) -> list[RuleSpec]:
        classification = _classify(rule)
        cls_name = self._name_map[rule.name]
        parent_cls = parent_of.get(rule.name, "GrammarModel")

        # value_str / pure_literal_alt → single `value: str` field
        if classification in ("value_str", "pure_literal_alt"):
            alt = _unwrap_group_alt(rule.body)
            items: list[Atom] = []
            for seq in alt.seqs:
                for it in seq.items:
                    if isinstance(it.atom, CharClass):
                        min_, max_ = quantifier_to_bounds(it.quantifier)
                        items.append(CharClassAtom(it.atom.pattern, min_, max_))
                    elif isinstance(it.atom, Literal):
                        if it.quantifier is not None:
                            # Quantified literal: emit as QuantifiedLiteralAtom to
                            # preserve optionality/repetition in the IR.
                            min_, max_ = quantifier_to_bounds(it.quantifier)
                            items.append(
                                QuantifiedLiteralAtom(
                                    value=it.atom.value, min=min_, max=max_
                                )
                            )
                        else:
                            items.append(LiteralAtom(it.atom.value))
                    elif isinstance(it.atom, Group):
                        # Inline group: convert to an InlineRegexAtom.
                        min_, max_ = quantifier_to_bounds(it.quantifier)
                        items.append(_build_inline_regex(it.atom, min_, max_))
            return [
                RuleSpec(
                    rule_name=rule.name,
                    class_name=cls_name,
                    parent_class_name=parent_cls,
                    kind="value_str",
                    items=items,
                    field_map={},
                )
            ]

        # named_alt → abstract class + anonymous arm classes
        if classification == "named_alt":
            alt = _unwrap_group_alt(rule.body)
            arm_rule_names: list[str] = []
            arm_specs: list[RuleSpec] = []
            arm_idx = 0

            for seq in alt.seqs:
                stripped = _strip_ws(seq)
                if not stripped.items:
                    continue
                arm_idx += 1
                ref = _is_single_ruleref(stripped)
                if ref is not None:
                    arm_rule_names.append(ref)
                else:
                    arm_rule_name = f"{rule.name}-arm{arm_idx}"
                    arm_cls_name = f"{cls_name}Arm{arm_idx}"
                    arm_rule_names.append(arm_rule_name)
                    helper_specs: list[RuleSpec] = []
                    atoms = _seq_to_atoms(
                        stripped, arm_cls_name, helper_specs, self._name_map, parent_of
                    )
                    fm = _assign_field_names(atoms)
                    arm_specs.extend(helper_specs)
                    arm_specs.append(
                        RuleSpec(
                            rule_name=arm_rule_name,
                            class_name=arm_cls_name,
                            parent_class_name=cls_name,
                            kind="sequence",
                            items=atoms,
                            field_map=fm,
                        )
                    )

            abstract_spec = RuleSpec(
                rule_name=rule.name,
                class_name=cls_name,
                parent_class_name=parent_cls,
                kind="alternation",
                items=[AlternationAtom(arm_rule_names=arm_rule_names)],
                field_map={},
            )
            return [abstract_spec] + arm_specs

        # sequence
        alt = _unwrap_group_alt(rule.body)
        # Use stripped arms only to check non-emptiness; pass full seqs to atom builder
        full_arms = [s for s in alt.seqs if _strip_ws(s).items]
        arms = [_strip_ws(s) for s in full_arms]
        if not arms:
            return [
                RuleSpec(
                    rule_name=rule.name,
                    class_name=cls_name,
                    parent_class_name=parent_cls,
                    kind="value_str",
                    items=[],
                    field_map={},
                )
            ]

        helper_specs_seq: list[RuleSpec] = []
        atoms_seq = _seq_to_atoms(
            full_arms[0], cls_name, helper_specs_seq, self._name_map, parent_of
        )
        fm_seq = _assign_field_names(atoms_seq)
        seq_spec = RuleSpec(
            rule_name=rule.name,
            class_name=cls_name,
            parent_class_name=parent_cls,
            kind="sequence",
            items=atoms_seq,
            field_map=fm_seq,
        )
        return helper_specs_seq + [seq_spec]

    def _topo_sort(self, specs: list[RuleSpec]) -> list[RuleSpec]:
        """Order specs so parent classes appear before subclasses, with root first."""
        by_cls = {s.class_name: s for s in specs}
        ordered: list[RuleSpec] = []
        visited: set[str] = set()

        def visit(cls_name: str) -> None:
            if cls_name in visited:
                return
            visited.add(cls_name)
            spec = by_cls.get(cls_name)
            if spec and spec.parent_class_name not in ("GrammarModel", "BaseModel"):
                visit(spec.parent_class_name)
            if spec:
                ordered.append(spec)

        # Seed with root first so it always appears at index 0
        root_spec = next((s for s in specs if s.rule_name == "root"), None)
        if root_spec:
            visit(root_spec.class_name)
        for s in specs:
            visit(s.class_name)

        return ordered
