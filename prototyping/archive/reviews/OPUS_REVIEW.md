Lexic — impartial review
Concept and positioning
Lexic aims to do something interesting and underserved: take a GBNF grammar and produce typed Pydantic classes that can parse text, reconstruct it verbatim, and (eventually) translate instances across grammars. The pipeline factoring is clean on paper — one IR (RuleSpec) between the GBNF AST and three emitters (ModelEmitter, GBNFEmitter, LarkBuilder), each with a stated single responsibility. CLAUDE.md is a good, opinionated spec; REQUIREMENTS.md is unusually disciplined for a WIP.
What looks solid

IR separation is real, not cosmetic. ir.py is a tight 80 lines, and the three emitters genuinely only depend on it. That's the kind of boundary that survives contact with new grammars.
GrammarModel base is minimal and driven by data (__grammar__), not codegen templating tricks. to_text() is a 40-line walker over items and field_map — easy to reason about.
semantic_dump() as S04 prep is a nice design move — excluding ws fields gives you a grammar-portable dict without committing to a translation mechanism yet. The repo is explicit about not implementing S04 speculatively, which is the right call.
No exec/eval, generated code goes to disk as a real importable module. That matches the stated constraint and makes debugging generated classes possible.
Test layout mirrors the code layout one-to-one (8 test files for 8 source modules). 220 claimed tests for ~2k SLOC is a reasonable ratio.

Concerns

pyproject.toml still says name = "vyx-2" while the README/CLAUDE.md insist the canonical name is Lexic. Rename drift.
issues.md contradicts the polished README. It describes an earlier, broken state ("FUNDAMENTALLY broken", "WAAAAYYYYY slower", references to SHIT/, demos/, built/ that no longer exist in this tree). Either stale or a signal that the current src/ is a rewrite that hasn't been fully reconciled with surrounding artifacts.
_classify() in ir_builder.py is doing a lot. Five classification paths (value_str, pure_literal_alt, named_alt, sequence, fallback) gated by _is_structurally_complex, _is_pure_literal_seq, _is_single_ruleref, _has_any_ruleref, _has_nontrivial_group, _has_group_with_alt. It works by case enumeration rather than a principled tree transformation — adding an 8th grammar will probably require another branch. This is the part most likely to rot.
gbnf_emitter.py:_normalize_charclass_pattern_for_gbnf is a red flag. The comment admits "this is complex" and the fix is a single .replace('|\\\\\\\\(', '|"\\\\\\\\\\\\"(') with 12 backslashes. That's the smell of IR leaking regex syntax that shouldn't be in the IR at all. Either CharClassAtom.pattern should be canonical GBNF and converted to regex in LarkBuilder, or canonical regex and converted to GBNF in GBNFEmitter — but right now patterns built by _group_to_regex are regex-shaped, which forces GBNFEmitter to reverse a lossy transform.
_build_instance in lark_builder.py is ~115 lines of position-matching with special cases for ws, optional char classes, origin is list, Optional unwrapping, etc. It works, but it's the kind of code that silently miscorrelates fields when a grammar is ambiguous. I'd want property-based tests that throw random valid strings at each grammar and assert parse(x).to_text() == x, not just example-based tests.
Field naming by position (first, second, third) for CharClassAtom is fragile for S04. Two grammars that both have a "first char class, then a second" will map onto each other even when the semantics are unrelated. This will bite when translation lands.
Root-rule-first enforcement is a post-hoc patch in _topo_sort (pop and insert at 0). Suggests the topological sort doesn't naturally produce the right order — fine for now, worth fixing before the IR has more consumers.
Imports rely on pythonpath = ["src"] rather than a proper package. from base import GrammarModel inside generated/*.py only works via pytest config; anyone doing python -c "import generated.arithmetic" from the repo root needs to know to set PYTHONPATH. Minor but packaging is not solved.
Stray files at the repo root — tst.py, quick_tst.py, quick_tst2.py, with_guidance.py — mix scratch experiments with the library. MILESTONE-BRIEF.md says quick_tst2.py is the reference for the Approach B generation loop, but R005 ("LLM constrained generation API") is listed as active and nothing in src/ implements it. There's a gap between the requirements doc and the code.

Alignment with stated requirements

R001, R002, R003, R004: implemented in src/, test files exist for each.
R005 (constrained generation API): not in src/ — only as scratch scripts.
R006 (cross-grammar translate): explicitly deferred, groundwork present.
R007 (generic across 7 grammars): 7 generated modules exist in generated/, which suggests it's at least been exercised end-to-end. I wasn't able to actually run the test suite in this session, so I can't confirm the "220 tests pass" claim — that would be the single most useful thing to verify next.
R008 (tests first): impossible to audit from the tree alone.

Bottom line
A genuinely well-structured core (IR + 3 emitters + thin parse) that's more ambitious than most grammar toolkits, held back by (a) one messy classifier, (b) an IR that's leaking regex into patterns meant to round-trip to GBNF, (c) a positional field-naming scheme that will be wrong for translation, and (d) scope/naming drift between issues.md, pyproject.toml, the README, and the scratch scripts at the root. Fixing the pattern representation and adding round-trip property tests would strengthen the foundation before S04 lands.
