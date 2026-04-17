"""IRBuilder: converts GBNF AST (list[Rule]) into list[RuleSpec].

Single responsibility: understanding GBNF semantics.
Knows nothing about Lark, Python source, or Pydantic.
"""

from __future__ import annotations

import re
from typing import cast

from .ast import Alternation, CharClass, Group, Item, Literal, Rule, RuleRef, Sequence
from .ir import (
    AlternationAtom,
    Atom,
    CharClassAtom,
    LiteralAtom,
    RuleRefAtom,
    RuleSpec,
)


# ── Name utilities ────────────────────────────────────────────────────────────


def to_pascal(name: str) -> str:
    """Convert 'jp-char' or 'json_ws' → 'JpChar' / 'JsonWs'."""
    parts = re.split(r"[-_]", name)
    return "".join(p[0].upper() + p[1:] if p else "" for p in parts)


def _quantifier_to_bounds(q: str | None) -> tuple[int, int | None]:
    """Parse GBNF quantifier string → (min, max). max=None means unbounded."""
    if q is None:
        return 1, 1
    if q == "?":
        return 0, 1
    if q == "*":
        return 0, None
    if q == "+":
        return 1, None
    inner = q[1:-1]  # strip { }
    if "," in inner:
        parts = inner.split(",", 1)
        lo = int(parts[0])
        hi = int(parts[1]) if parts[1] else None
        return lo, hi
    n = int(inner)
    return n, n


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


def _group_to_regex(group: Group, quantifier: str | None) -> str:
    """Convert a GBNF Group (alternation of sequences) into a regex pattern string.

    Used to represent complex inline groups (e.g. the string-char alternatives)
    as a single regex-style CharClassAtom pattern for the Lark grammar.

    Literals are emitted as-is (their GBNF escape sequences are valid regex escapes).
    CharClass patterns are emitted verbatim.
    """
    arms: list[str] = []
    for seq in group.alt.seqs:
        parts: list[str] = []
        for it in seq.items:
            if isinstance(it.atom, Literal):
                # Escape regex metacharacters in the literal so e.g. "*" becomes
                # "\*" and doesn't look like a quantifier in the pattern.
                # re.escape handles all regex special chars safely.
                parts.append(re.escape(it.atom.value))
            elif isinstance(it.atom, CharClass):
                q = it.quantifier or ""
                parts.append(it.atom.pattern + q)
            elif isinstance(it.atom, Group):
                nested = _group_to_regex(it.atom, it.quantifier)
                parts.append(nested)
            elif isinstance(it.atom, RuleRef):
                # Can't inline a named rule ref — skip
                pass
        arms.append("".join(parts))
    body = "|".join(arms)
    result = f"({body})" if len(arms) > 1 else body
    if quantifier:
        result += quantifier
    return result


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


# ── Field naming ─────────────────────────────────────────────────────────────

_CC_NAMES = ["first", "second", "third", "fourth", "fifth"]


def _assign_field_names(items: list[Atom]) -> dict[str, int]:
    """Assign semantic field names to non-literal atoms.

    Rules:
    - LiteralAtom → never a field
    - AlternationAtom in a sequence → field name "value" (holds the chosen arm)
    - RuleRefAtom(rule_name) → field name = rule_name (underscores for hyphens)
      Duplicates get suffix: 'ws', 'ws2', 'ws3', etc.
    - CharClassAtom → 'first', 'second', 'third', ... by position among char classes
    """
    field_map: dict[str, int] = {}
    rule_ref_counts: dict[str, int] = {}
    cc_count = 0

    for i, atom in enumerate(items):
        if isinstance(atom, LiteralAtom):
            continue

        if isinstance(atom, AlternationAtom):
            # Inline alternation inside a sequence: store chosen arm as "value".
            field_map["value"] = i
            continue

        if isinstance(atom, RuleRefAtom):
            base = atom.rule_name.replace("-", "_")
            count = rule_ref_counts.get(base, 0) + 1
            rule_ref_counts[base] = count
            fname = base if count == 1 else f"{base}{count}"
            field_map[fname] = i

        elif isinstance(atom, CharClassAtom):
            cc_count += 1
            fname = (
                _CC_NAMES[cc_count - 1]
                if cc_count <= len(_CC_NAMES)
                else f"cc{cc_count}"
            )
            field_map[fname] = i

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
            if item.quantifier in ("+", "*", "?"):
                # Quantified literal: represent as CharClassAtom so the optional/
                # repeated nature is preserved in the IR and Lark grammar.
                min_, max_ = _quantifier_to_bounds(item.quantifier)
                atoms.append(
                    CharClassAtom(
                        pattern=f'"{item.atom.value}"',
                        min=min_,
                        max=max_,
                    )
                )
            else:
                atoms.append(LiteralAtom(value=item.atom.value))

        elif isinstance(item.atom, CharClass):
            min_, max_ = _quantifier_to_bounds(item.quantifier)
            atoms.append(CharClassAtom(pattern=item.atom.pattern, min=min_, max=max_))

        elif isinstance(item.atom, RuleRef):
            min_, max_ = _quantifier_to_bounds(item.quantifier)
            atoms.append(RuleRefAtom(rule_name=item.atom.name, min=min_, max=max_))

        elif isinstance(item.atom, Group):
            min_, max_ = _quantifier_to_bounds(item.quantifier)
            inner_arms = [
                a
                for a in (_strip_ws(s) for s in item.atom.alt.seqs)
                if len(a.items) > 0
            ]

            # Inline literal alternation → treat as single char-class-like atom
            if all(_is_pure_literal_seq(a) for a in inner_arms):
                atoms.append(
                    CharClassAtom(
                        pattern="("
                        + "|".join(
                            "".join(
                                f'"{it.atom.value}"'
                                if isinstance(it.atom, Literal)
                                else cast(CharClass, it.atom).pattern
                                for it in a.items
                            )
                            for a in inner_arms
                        )
                        + ")",
                        min=min_ if min_ is not None else 1,
                        max=max_,
                    )
                )
                continue

            # Inline union of named rules (no quantifier) → inline alternation atom
            if (
                item.quantifier is None
                and len(inner_arms) > 1
                and all(_is_single_ruleref(a) is not None for a in inner_arms)
            ):
                arm_names: list[str] = [
                    cast(str, _is_single_ruleref(a)) for a in inner_arms
                ]
                atoms.append(AlternationAtom(arm_rule_names=arm_names))
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
                        min_, max_ = _quantifier_to_bounds(it.quantifier)
                        items.append(CharClassAtom(it.atom.pattern, min_, max_))
                    elif isinstance(it.atom, Literal):
                        if it.quantifier in ("+", "*", "?"):
                            # Quantified literal: represent as CharClassAtom to
                            # preserve optionality/repetition in the IR.
                            min_, max_ = _quantifier_to_bounds(it.quantifier)
                            items.append(
                                CharClassAtom(
                                    pattern=f'"{it.atom.value}"',
                                    min=min_,
                                    max=max_,
                                )
                            )
                        else:
                            items.append(LiteralAtom(it.atom.value))
                    elif isinstance(it.atom, Group):
                        # Inline group: convert to a regex pattern CharClassAtom.
                        min_, max_ = _quantifier_to_bounds(it.quantifier)
                        pattern = _group_to_regex(it.atom, None)
                        items.append(CharClassAtom(pattern=pattern, min=min_, max=max_))
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

        for s in specs:
            visit(s.class_name)

        # Ensure the root rule spec is always first
        root_idx = next(
            (i for i, s in enumerate(ordered) if s.rule_name == "root"), None
        )
        if root_idx is not None and root_idx != 0:
            root_spec = ordered.pop(root_idx)
            ordered.insert(0, root_spec)

        return ordered
