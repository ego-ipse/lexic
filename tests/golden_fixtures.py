"""Golden fixture helper — the parity oracle recorded from pydantic (Task 0).

The golden FILES were recorded once from the retired pydantic implementation
(Task 0) and are byte-pinned; the record spine (Task 1) must keep their
ORACLE keys equal (ruling 12,
``zzz_current_work/260716-ir-native/PLAN_v4.md``): ``runtime_dump``,
``runtime_semantic_dump``, ``to_text``. The declared-schema keys
(``model_dump``/``semantic_dump`` as recorded) characterized the pydantic
serializer and are retired data — uncomputable on the spine, kept in the
files as the historical record, no longer asserted.

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
..., "semantic_dump": ..., "runtime_semantic_dump": ..., "to_text": str}``
(the two ``model_dump``/``semantic_dump`` keys exist only in the Task-0
recordings; :func:`compute_record` now produces the oracle keys alone).

**F-DUMP-1 (coordinator finding, mid-Task-0 addendum — historical).**
pydantic's ``model_dump()`` was declared-schema-driven: a nested arm
instance riding a field annotated with its field-less abstract alternation
PARENT serialized as ``{}`` (the whole subtree erased), so every golden
record carries two forms side by side. RULED (PLAN_v4 ruling 12,
2026-07-16): the runtime forms are THE parity oracle for Tasks 1–8; the
declared-schema forms characterized the retired serializer:

- ``model_dump`` / ``semantic_dump`` — pydantic's declared-schema form,
  erasure warts included. Retired recordings; no longer computable.
- ``runtime_dump`` / ``runtime_semantic_dump`` — recorded from pydantic via
  ``model_dump(serialize_as_any=True)`` (verified byte-equal to a
  hand-rolled runtime-type walker on the GT corpus), and byte-equal to the
  record spine's native ``model_dump()``/``semantic_dump()``, which
  :func:`runtime_dump`/:func:`runtime_semantic_dump` now delegate to.

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

NOTE: regeneration now writes oracle-keys-only records — it would drop the
Task-0 declared-schema recordings from the files. The Task-0 files are
byte-pinned; do not regenerate without a ruling.
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
    """The runtime-type-driven dump — the golden ``runtime_dump`` form.

    On the record spine the native :meth:`~lexic.base.GrammarModel.model_dump`
    IS runtime-complete (ruling 12), byte-equal to the pydantic
    ``model_dump(serialize_as_any=True)`` the goldens were recorded with.

    :param model: A parsed model instance.
    :returns: The runtime-complete dump.
    """
    return model.model_dump()


def runtime_semantic_dump(model: GrammarModel) -> dict[str, Any]:
    """:func:`runtime_dump` with the model's own non-semantic fields excluded.

    The native :meth:`~lexic.base.GrammarModel.semantic_dump` — the same
    top-level-only exclusion depth (R2-5) the golden
    ``runtime_semantic_dump`` form was recorded with.

    :param model: A parsed model instance.
    :returns: The runtime-complete dump, semantic exclusions applied.
    """
    return model.semantic_dump()


def compute_record(cg: CompiledGrammar, sample: str) -> dict[str, Any]:
    """Parse ``sample`` and capture the oracle outputs (ruling 12).

    The declared-schema ``model_dump``/``semantic_dump`` keys of the Task-0
    recordings are NOT produced — they characterized the retired pydantic
    serializer and exist only in the persisted files.

    :param cg: The compiled grammar to parse against.
    :param sample: One representative input.
    :returns: ``{"input", "runtime_dump", "runtime_semantic_dump", "to_text"}``.
    """
    model = cg.parse(sample)
    return {
        "input": sample,
        "runtime_dump": runtime_dump(model),
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
