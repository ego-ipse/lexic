Copied from Slice A draft to preserve work.


### Task 12: Split `IRBuilder._build_rule` into per-kind methods

**Files:**
- Modify: `src/lexic/codegen/ir_builder.py`

Rationale: `_build_rule` is still the largest method in `IRBuilder` (lines 522–644 as of writing) and has three branches (`value_str`/`pure_literal_alt`, `named_alt`, `sequence`). Splitting mirrors the three `classify()` kinds and makes each branch independently readable.

- [ ] **Step 1: Read the current `_build_rule`; map each branch**

Identify the three blocks:
1. Lines ~532–566: `value_str` / `pure_literal_alt` → `_build_value_str(rule, cls_name, parent_cls)`
2. Lines ~568–612: `named_alt` → `_build_named_alt(rule, cls_name, parent_cls, parent_of)`
3. Lines ~614–644: `sequence` → `_build_sequence(rule, cls_name, parent_cls, parent_of)`

- [ ] **Step 2: Extract into three private methods**

In `src/lexic/codegen/ir_builder.py`, add three methods to `IRBuilder`:

```python
def _build_value_str(self, rule, cls_name, parent_cls) -> list[RuleSpec]:
    alt = _unwrap_group_alt(rule.body)
    items: list[Atom] = []
    for seq in alt.seqs:
        for it in seq.items:
            if isinstance(it.atom, CharClass):
                min_, max_ = quantifier_to_bounds(it.quantifier)
                items.append(CharClassAtom(it.atom.pattern, min_, max_))
            elif isinstance(it.atom, Literal):
                if it.quantifier is not None:
                    min_, max_ = quantifier_to_bounds(it.quantifier)
                    items.append(QuantifiedLiteralAtom(it.atom.value, min_, max_))
                else:
                    items.append(LiteralAtom(it.atom.value))
            elif isinstance(it.atom, Group):
                min_, max_ = quantifier_to_bounds(it.quantifier)
                items.append(_build_inline_regex(it.atom, min_, max_))
    return [RuleSpec(
        rule_name=rule.name, class_name=cls_name, parent_class_name=parent_cls,
        kind="value_str", items=items, field_map={},
    )]


def _build_named_alt(self, rule, cls_name, parent_cls, parent_of) -> list[RuleSpec]:
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
            atoms = _seq_to_atoms(
                stripped, arm_cls_name, self._helpers, self._name_map, parent_of,
            )
            fm = FieldNamer().assign(atoms)
            arm_specs.append(RuleSpec(
                rule_name=arm_rule_name, class_name=arm_cls_name,
                parent_class_name=cls_name, kind="sequence",
                items=atoms, field_map=fm,
            ))

    abstract_spec = RuleSpec(
        rule_name=rule.name, class_name=cls_name, parent_class_name=parent_cls,
        kind="alternation",
        items=[AlternationAtom(arm_rule_names=arm_rule_names)],
        field_map={},
    )
    return [abstract_spec] + arm_specs


def _build_sequence(self, rule, cls_name, parent_cls, parent_of) -> list[RuleSpec]:
    alt = _unwrap_group_alt(rule.body)
    full_arms = [s for s in alt.seqs if _strip_ws(s).items]
    arms = [_strip_ws(s) for s in full_arms]
    if not arms:
        return [RuleSpec(
            rule_name=rule.name, class_name=cls_name, parent_class_name=parent_cls,
            kind="value_str", items=[], field_map={},
        )]
    atoms_seq = _seq_to_atoms(
        full_arms[0], cls_name, self._helpers, self._name_map, parent_of,
    )
    fm_seq = FieldNamer().assign(atoms_seq)
    return [RuleSpec(
        rule_name=rule.name, class_name=cls_name, parent_class_name=parent_cls,
        kind="sequence", items=atoms_seq, field_map=fm_seq,
    )]
```

Rewrite `_build_rule` as a dispatch:

```python
def _build_rule(self, rule, parent_of) -> list[RuleSpec]:
    classification = self._classifier.classify(rule).kind
    cls_name = self._name_map[rule.name]
    parent_cls = parent_of.get(rule.name, "GrammarModel")

    if classification in ("value_str", "pure_literal_alt"):
        return self._build_value_str(rule, cls_name, parent_cls)
    if classification == "named_alt":
        return self._build_named_alt(rule, cls_name, parent_cls, parent_of)
    return self._build_sequence(rule, cls_name, parent_cls, parent_of)
```

Delete the old `_build_rule` body.

- [ ] **Step 3: Run the full suite**

```bash
uv run pytest tests/ -q && uv run ruff check src/ tests/
```
Expected: all tests green.

- [ ] **Step 4: Commit**

```bash
git add src/lexic/codegen/ir_builder.py
git commit -m "refactor(ir_builder): split _build_rule into per-kind methods"
```

---
