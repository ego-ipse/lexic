"""Golden fixture helper — the pydantic-implementation parity oracle (Task 0).

Pins ``model_dump()``/``semantic_dump()``/``to_text()`` from TODAY's pydantic
implementation as the byte-form baseline every later ir-native task must
match against (settled 12,
``zzz_current_work/260716-ir-native/PLAN_v4.md``). THE parity oracle for
Tasks 1-8 of that effort.

Byte form (settled 12, pinned here and nowhere else): one fixed
serialization — ``json.dumps(records, ensure_ascii=False, indent=2,
sort_keys=False)`` (key order = each dict's insertion order, i.e. the field
declaration order ``model_dump()`` already produces), newline-terminated.
Both :func:`write_golden` (regeneration) and :func:`load_golden` (replay) go
through :func:`_serialize`/``json.loads``, so the byte form has exactly one
definition. JSON cannot distinguish a tuple from a list nor an ``IrInt`` from
a plain ``int`` (C12) — the golden-check test in
``tests/integration/test_golden_parity.py`` compares *parsed-back* JSON
against a fresh live dump for that reason; the stricter in-process
dump-dict-equality medium lives in
``tests/unit/lexic/test_base_surface_freeze.py``.

Golden files live at ``tests/goldens/<grammar-stem>.json`` (git-tracked), one
per ground-truth grammar file under ``resources/ground_truth/``, each a JSON
list of per-input records: ``{"input": str, "model_dump": ..., "runtime_dump":
..., "semantic_dump": ..., "runtime_semantic_dump": ..., "to_text": str}``.

**F-DUMP-1 (coordinator finding, mid-Task-0 addendum).** ``model_dump()`` is
declared-schema-driven: a nested arm instance riding a field annotated with
its field-less abstract alternation PARENT serializes as ``{}`` — the whole
subtree erased, since pydantic-core builds the field's serializer off the
declared annotation, not the runtime type. Verify on ``arithmetic.gbnf``:
parse ``"6=k\t \n"``; ``item = model.root_item[0]``; ``item.term.model_dump()``
is a full dict but ``item.model_dump()["term"] == {}``. Deep grammars
(c.gbnf, vyx.gbnf) additionally mix erased and full subtrees at schema-joint
stride boundaries (``__schema_joint__``, ``lexic/base.py``). A golden
recorded via bare ``model_dump()`` alone would enshrine that artifact as if
it were meaningful per-grammar data, when for an abstract-typed field it is
really just ``{}`` regardless of which arm matched — exit criterion 1 and
settled 12 of PLAN_v4.md assume ``model_dump`` goldens are a meaningful
oracle; the erasure weakens that (any two arm subtrees compare equal as
``{}``). Two ways to serialize are recorded side by side per record.
RULED (PLAN_v4 ruling 12, 2026-07-16): the runtime forms are THE parity
oracle for Tasks 1–8; the declared-schema forms are characterization-only
and die with pydantic in Task 8:

- ``model_dump`` / ``semantic_dump`` — pydantic's default, declared-schema
  form, warts (the erasure) included. Exactly what the original Task-0
  brief asked for.
- ``runtime_dump`` / ``runtime_semantic_dump`` (:func:`runtime_dump`,
  :func:`runtime_semantic_dump`) — ``model_dump(serialize_as_any=True)``,
  pydantic's built-in duck-typed/runtime-type serialization. Verified
  byte-equal to a hand-rolled runtime-type walker on the GT corpus AND
  through a hand-built schema-joint boundary (no GT grammar reaches the
  64-rule joint stride) — see
  ``tests/unit/lexic/test_base_surface_freeze.py``'s cross-check tests,
  which also record an empirical correction: ``serialize_as_any=True``
  does NOT degrade through a joint (it bypasses the joint's custom
  ``_joint_dump`` serializer entirely rather than calling it without the
  flag), contrary to the addendum's initial worry.

:data:`CORPUS` is the representative-input registry per grammar stem —
drawn from existing round-trip/integration test corpora
(``tests/integration/test_full_round_trip.py``'s per-fixture samples and
JSON escape inputs, ``tools/benchmark/pipeline_bench.py``'s arithmetic/c/
chess/JSON snippets, ``tests/integration/test_compile_grammar_vyx.py``'s
``PACKET_SAMPLES``) plus a handful of :func:`lexic.generate.generate`
samples at fixed seeds. Generated samples are recorded here as literal
text, computed once at authoring time and pinned — the corpus is a fixed,
reviewed set, independent of ``generate.py``'s own future evolution (a
change to the generator must not silently reshape what Task 0 pinned).

Regenerate every golden file (only after a *ruled* behavior change — see
the plan's settled-12 note; a routine code change should make this suite
FAIL, not need re-running) via::

    uv run python -m tests.golden_fixtures
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from lexic.base import GrammarModel
from lexic.compile import CompiledGrammar, compile_from_path
from tests.integration.test_compile_grammar_vyx import PACKET_SAMPLES
from tests.paths import GROUND_TRUTH
from tests.unit.lexic.parsing.pda.runtime.test_runtime import ARITHMETIC_BENCH_SNIPPETS

GOLDEN_DIR = Path(__file__).parent / "goldens"

_JSON_SAMPLES = [
    '"\\""',
    '"\\\\"',
    '"\\n"',
    '"A"',
    '"\\/"',
    '"\\u0041"',
    '\n{"": [\t\r\n]}',
    '""',
    '{"name": "alpha", "id": 1, "ok": true}',
    '{"nested": {"a": [1, 2.5e3, -4], "b": null}}',
    "-12.75e-2",
    '[true, false, null, 0, "s"]',
]

# Representative inputs per ground-truth grammar file. Hand samples are
# drawn from existing test corpora (see module docstring); samples marked
# "gen(seed=N)" below were produced once via
# ``lexic.generate.generate(start, specs, rng=random.Random(N), max_depth=4)``
# against the grammar's own canonical rules and pinned as literal text.
CORPUS: dict[str, list[str]] = {
    "arithmetic.gbnf": [
        *ARITHMETIC_BENCH_SNIPPETS,
        "p=z\t\n",  # gen(seed=1)
        "((705\t\t)) +o-(\n\t( \n((  (( y)-2)\t))/1)+0*h )=(2)\n",  # gen(seed=2)
        "((\t\n8\t)\n ) =(\n\n59\n)\n",  # gen(seed=3)
    ],
    "arithmetic.abnf": [
        "6/3",  # gen(seed=1)
        "928/358/763",  # gen(seed=2)
        "7",  # gen(seed=3)
        "6",  # gen(seed=4)
        "13",  # gen(seed=5)
    ],
    "c.gbnf": [
        "int foo(){}",
        "char bar(int x){}",
        "float baz(){}",
        "int qux(char y){}",
        "int\t\tG(){T (3*9/J);AaN ();}",  # gen(seed=5) — root's lo=0 arm rolls
        # empty at seeds 1-4; seed=5 is the first non-empty expansion.
    ],
    "chess.gbnf": [
        "1. e4 e5\n2. Nf3 Nc6\n",
        "1. Ng1 O-O\n9. O-O-O Kg5g4\n",  # gen(seed=1)
        "1. axc7=N# Nf3+\n8. O-O Rhc5#\n8. Qab3+ O-O\n2. cxa1=Q N7xd6#\n",  # gen(seed=2)
    ],
    "japanese.gbnf": [
        "こんにちは",
        "ぺ",  # gen(seed=1)
        "〫\t〺ど酋\tモ",  # gen(seed=2)
    ],
    "json_arr.gbnf": [
        "[\n1\n]",
        "[\n ]",  # gen(seed=1)
        "[\n]",  # gen(seed=2)
    ],
    "json_ws.gbnf": [
        '{"a":1}',
        "{ } ",  # gen(seed=1)
        "{}",  # gen(seed=2)
    ],
    "list.gbnf": [
        "- apple\n",
        "- \U000f423b\n",  # gen(seed=1)
        "- \U0007aa7f\U0005f178\U000d77d0\n",  # gen(seed=2)
    ],
    "json.gbnf": list(_JSON_SAMPLES),
    "json.abnf": list(_JSON_SAMPLES),
    "vyx.gbnf": [text for _label, text in PACKET_SAMPLES],
}


def golden_path(stem: str) -> Path:
    """The golden JSON file path for a ground-truth grammar stem."""
    return GOLDEN_DIR / f"{stem}.json"


def runtime_dump(model: GrammarModel) -> dict[str, Any]:
    """The runtime-type-driven dump — F-DUMP-1's counterpart to ``model_dump()``.

    ``model_dump(serialize_as_any=True)`` (pydantic's built-in duck-typed
    serialization): every nested value serializes via ITS OWN runtime type
    rather than its field's declared annotation, so an arm instance riding
    an abstract-alternation-typed field dumps in full instead of eroding to
    ``{}``. See the module docstring's F-DUMP-1 note.

    :param model: A parsed model instance.
    :returns: The runtime-complete dump.
    """
    return model.model_dump(serialize_as_any=True)


def runtime_semantic_dump(model: GrammarModel) -> dict[str, Any]:
    """:func:`runtime_dump`, with ``model``'s own non-semantic fields excluded.

    The runtime-type-driven counterpart of :meth:`~lexic.base.GrammarModel.
    semantic_dump` (same top-level-only exclusion depth, R2-5) — exclusion
    is computed the same way ``semantic_dump()`` computes it, via the public
    :meth:`~lexic.base.GrammarModel.bound_fields`.

    :param model: A parsed model instance.
    :returns: The runtime-complete dump, semantic exclusions applied.
    """
    exclude = {
        name for name, bind in type(model).bound_fields().values() if not bind.semantic
    }
    return model.model_dump(exclude=exclude, serialize_as_any=True)


def compute_record(cg: CompiledGrammar, sample: str) -> dict[str, Any]:
    """Parse ``sample`` and capture the pinned outputs (F-DUMP-1: both dump forms).

    :param cg: The compiled grammar to parse against.
    :param sample: One representative input.
    :returns: ``{"input", "model_dump", "runtime_dump", "semantic_dump",
        "runtime_semantic_dump", "to_text"}``.
    """
    model = cg.parse(sample)
    return {
        "input": sample,
        "model_dump": model.model_dump(),
        "runtime_dump": runtime_dump(model),
        "semantic_dump": model.semantic_dump(),
        "runtime_semantic_dump": runtime_semantic_dump(model),
        "to_text": model.to_text(),
    }


def compute_records(stem: str) -> list[dict[str, Any]]:
    """Every golden record for a grammar stem, computed live."""
    cg = compile_from_path(GROUND_TRUTH / stem)
    return [compute_record(cg, sample) for sample in CORPUS[stem]]


def _serialize(records: list[dict[str, Any]]) -> str:
    """The pinned byte form (settled 12) for a stem's golden records."""
    return json.dumps(records, ensure_ascii=False, indent=2, sort_keys=False) + "\n"


def write_golden(stem: str) -> None:
    """(Re)write the golden file for ``stem`` from the live implementation."""
    golden_path(stem).write_text(_serialize(compute_records(stem)), encoding="utf-8")


def load_golden(stem: str) -> list[dict[str, Any]]:
    """Load the persisted golden records for ``stem``."""
    return json.loads(golden_path(stem).read_text(encoding="utf-8"))


def all_stems() -> list[str]:
    """Every grammar stem with a golden corpus, sorted."""
    return sorted(CORPUS)


if __name__ == "__main__":
    GOLDEN_DIR.mkdir(exist_ok=True)
    for _stem in all_stems():
        write_golden(_stem)
        print(f"wrote {golden_path(_stem)}")
