"""Document transpilation across grammars — the model-plane pipeline, whole.

What these defend: a transform table authored in RULE NAMES serves ANY
formulation of the source language (no privileged formulation — ex16's own
table bakes against json.gbnf and json.abnf alike), survives the notation
as pure data, holds its gates over generated documents in bulk, and refuses
its stated domain with words. The table under test IS the shipped example's
— imported, not copied.
"""

import random

from getting_started.ex16_transpile_json_yaml import RULES, YAML_GRAMMAR
from lexic import compile_from_path, compile_text, generate
from lexic.compile import Flat, Is, Make, Spelled, Split, load_ir, transpile
from lexic.compile.notation import emit_ir
from lexic.exceptions import UnsupportedConstructError
from lexic.ir import IrMap
from tests.paths import GROUND_TRUTH

DOCS = (
    '{"name": "lexic", "stars": 3}',
    '{"a": {"b": 1}}',
    "{}",
    '{"my key": 1}',
    '{"a": "x: y"}',
    '{"a": "l1\\nl2"}',
    '{"a": 1.5}',
    '{"a": 1, "a": 2}',
    '{"a": "\\u00e9"}',
    '{"a": true, "b": false, "c": 1, "d": 0}',
    '{"a": [1.5, true, {"b": null}]}',
)


def _yaml():
    """The compiled target, shared across the module's tests."""
    return compile_text(YAML_GRAMMAR, cache_key="it-transpile-yaml")


def test_one_table_serves_every_formulation_of_the_source() -> None:
    """No privileged formulation: the SAME rule-named table bakes against
    json.gbnf and json.abnf, and both produce the identical yaml."""
    yaml = _yaml()
    via_gbnf = transpile(compile_from_path(GROUND_TRUTH / "json.gbnf"), yaml, RULES)
    via_abnf = transpile(compile_from_path(GROUND_TRUTH / "json.abnf"), yaml, RULES)
    for doc in DOCS:
        assert via_gbnf.run(doc) == via_abnf.run(doc)


def test_every_document_holds_the_gates() -> None:
    """Fixed documents: floats, duplicates, escapes, nesting — all carried,
    every run gated for completeness, membership and fidelity."""
    to_yaml = transpile(compile_from_path(GROUND_TRUTH / "json.gbnf"), _yaml(), RULES)
    for doc in DOCS:
        out = to_yaml.run(doc)
        assert _yaml().parse(out).to_text() == out


def test_generated_documents_transpile_or_refuse_with_words() -> None:
    """The bulk witness: random valid documents from the grammar's own
    generator either pass every gate or refuse the stated domain in words.
    Nothing third — no silent drop, no mangled output — is possible."""
    compiled = compile_from_path(GROUND_TRUTH / "json.gbnf")
    to_yaml = transpile(compiled, _yaml(), RULES)
    rules_by_name = {str(rule.name): rule for rule in compiled.grammar.rules}
    outcomes = {"transpiled": 0, "refused": 0}
    for seed in range(24):
        doc = generate("json-text", rules_by_name, rng=random.Random(seed))
        try:
            out = to_yaml.run(doc)
        except UnsupportedConstructError as refusal:
            assert "has no spelling here" in str(refusal)
            outcomes["refused"] += 1
            continue
        assert _yaml().parse(out).to_text() == out
        outcomes["transpiled"] += 1
    assert outcomes["transpiled"] > 0, "the generator never produced a map"


def test_the_table_travels_as_notation_and_still_runs() -> None:
    """The transform is pure data: through the notation and back, then run.

    The only symbols a reader needs are the transpile vocabulary's own —
    no class objects ride in an authored table. The contract is the REPR
    FIXPOINT (the table carries identity-equality leaves like ``IrThis``,
    so ``==`` is deliberately not it), and the witness that matters is the
    loaded table producing the same document.
    """
    text = emit_ir(RULES, width=100)
    back = IrMap.ensure(
        load_ir(
            text,
            symbols={
                "Make": Make,
                "Spelled": Spelled,
                "Flat": Flat,
                "Split": Split,
                "Is": Is,
            },
        )
    )
    assert repr(back) == repr(RULES)
    a = compile_from_path(GROUND_TRUTH / "json.gbnf")
    doc = '{"a": 1.5, "b": [true, null]}'
    assert transpile(a, _yaml(), back).run(doc) == transpile(a, _yaml(), RULES).run(doc)
