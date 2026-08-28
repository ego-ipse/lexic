# Prototype 8 — exact starting-tree RSS and persistent root meanings

**Phase:** final pre-implementation pass after `REVIEW_8`. `src` remains
unchanged. This report closes the missing §0 memory reference and records the
representation correction found while attacking the root-ambiguity plan.

## 1 — the measured source is the exact release baseline

The working branch is at `9540414479cf358352214347d71bade8932e0360`, but
`git diff --stat 0faa7289 -- src` is empty. The deleted
`src/lexic/parsing/parallel/stitch/carrier.py` is absent. The measurements below
therefore execute the exact production source at release commit `0faa7289`
without checking out another tree or reconstructing rejected work.

Environment:

- CPython 3.14.3 free-threading build, GIL disabled;
- AMD Ryzen 7 5700X3D, 8 physical / 16 logical CPUs, 96 MiB L3;
- Linux `ru_maxrss`/GNU time high-water RSS in KiB;
- garbage collector enabled throughout production calls;
- public tokenizer reader, its default `cores=AUTO`, and the 2 KiB floor;
- Qwen3 fixture: 11,422,654 bytes / 10,635,788 characters,
  SHA-256 `aeb13307a71acd8fe81861d94ad54ab689df773318809eed3cbe794b4492dae4`.

The frozen external matrix records, for every baseline/candidate/control arm:
commit and source diff, fixture digest/bytes/chars, Python build and GC state,
CPU topology, public entry and direct engine entry, requested and actual
workers, engaged/declined plan kind, cold compile/bind, first parse and warmed
parse, result or refusal digest, opcode/capture counts, product-table bytes,
wall, aggregate process CPU, and peak RSS. Allocation/constructor observation
is a separate untimed run. Candidate and unchanged source alternate as complete
fresh processes; preparation, warming, timing, and shutdown never overlap.
Resident, first path, and retained second-path calls are separate scenarios.

`proto/baseline_rss.py` hashes the ready encode/rank tables after the timed
reader without rendering another document. Every row returned 151,669 vocab
entries, 151,387 merges, and the same BLAKE2b digest:

```text
63648186ee97d1a37eb7dd970df744826f717d7491ad8c546b12300b80890eac1f9fb2a3112df77fb26eb6ed81032d7b7e0b3ccda9282e4ea3b8b50277f42c85
```

## 2 — baseline memory matrix

Each row ran alone under `tools/guarded.sh 8G`; no agent or other benchmark ran
during its preparation, parse, fold, construction, digest, or shutdown.

| scenario | timed call | process CPU | wall | peak RSS |
|---|---|---:|---:|---:|
| resident text, first product | `read(text, ...)` | 104.839638 s | 17.054242 s | 633,000 KiB |
| cold path, first product | `read_from_path(...)` | 100.994081 s | 16.780420 s | 632,888 KiB |
| warm path, second product | second `read_from_path(...)` in one process | 104.436933 s | 16.927789 s | 838,120 KiB |

The resident row's high-water mark before product construction was 110,384
KiB. The cold-path process began the product at 37,076 KiB. In the warm-path
process, the first ready-tokenizer call established a 634,592 KiB high-water
mark; after deleting that result and collecting, the second call raised the
process high-water mark to 838,120 KiB, an additional 203,528 KiB. Because
`ru_maxrss` is monotonic, that difference is a process high-water increment,
not a live-retention or leak diagnosis.

These are pinned reference rows, not a statistical timing baseline. §12 still
alternates the unchanged source and candidate in fresh like-for-like processes.
Memory acceptance is scenario-specific: compare first resident/cold calls to
about 633 MiB and a two-call warm process to 838,120 KiB. Do not compare a
candidate's warm retained process against the cold 633 MiB row or hide a larger
warm footprint behind a lower cold peak.

Commands:

```text
/usr/bin/time -v tools/guarded.sh 8G 240 -- uv run python proto/baseline_rss.py --mode resident
/usr/bin/time -v tools/guarded.sh 8G 240 -- uv run python proto/baseline_rss.py --mode path-cold
/usr/bin/time -v tools/guarded.sh 8G 360 -- uv run python proto/baseline_rss.py --mode path-warm
```

## 3 — exact persistent ambiguity meanings

The final adversarial pass found that `root_meaning_incremental.py` proved only
dirty-cone **semantic-operation count**. A flat eager list/map could still copy
or compare the whole document per alternate, so “alternate cost follows the
cone” was too broad.

`proto/persistent_meaning.py` supplies the built-in accumulator representation:
an immutable balanced contribution tree, identity-shared unchanged branches,
path-copying at the changed leaf, and iterative exact equality. It uses no
probabilistic digest as an equality decision. On 65,536 leaves:

```text
persistent items=65536 different_visits=18 equal_visits=33 dropped_visits=1 materializations=1
```

Only the resolver's chosen meaning is flattened into the eager public result.
This keeps exact root-value semantics and makes changed/equal internal choices
proportional to shared structure for built-in products. A custom target which
cannot expose an exact shareable meaning may pay a full cold ambiguity
comparison; it may not add witness state to the unambiguous hot path.

## 4 — current-consumer inventory

The implementation handoff starts with these production owners; generated
flavour resources and READMEs are additional serialization/documentation
consumers, not alternate runtime paths.

- `Reducer`: `ir/reduction.py` and the IR façade; all four shipped flavour
  declarations; notation parse/loader; `compile/reduction.py`, `artifact.py`,
  and `compile/reduce/fold.py`; the tokenizer reader; and the parallel request
  type in `parallel/orchestrate.py`.
- `ModelBody` / `model_fold`: `parsing/fold.py`; compile foldkit, pipeline
  binding/synthesis, notation parse, generated self-grammar, and templating;
  plus their parsing/compile façades.
- `ModelFold` / `RuleFold` / `fold_config`: the preceding authored owners;
  `CompiledGrammar`; Earley engine/forest, product and trace entries; PDA clone,
  lowering, flattening, build, kernel, and islands; parallel replicas,
  orchestration, and every model stitch owner.
- `derive_reduction` / `ReduceFold`: `compile/reduction.py`, `artifact.py`, and
  `compile/reduce/fold.py`, with the declaration reference in
  `ir/reduction.py`.
- `Template`: `compile/output/templating.py` and the compile façade. The
  unrelated layout-algebra type alias with the same spelling remains outside
  this deletion.
- `split_model`: `compile/artifact.py` and the parallel façade/orchestrator.
- tokenizer reader surfaces: `api/json_tokenizer.py` owns `read`,
  `read_from_path`, `tokenizer_of`, and its `IrTokenizer.from_merges` call;
  `ir/text/tokenizer.py` owns `from_merges` itself; `api/__init__.py` exports
  the reader surface.

The exact repository search was run over `src`, `tests`, examples, tools, wiki,
root docs, and `CLAUDE.md`. §10 ports/deletes production callers; §11 updates
serialized/docs/examples; §13 owns every mirrored unit, integration, property,
and performance assertion rather than deleting behavior with a symbol.

## Design consequences

- §0 now has explicit cold/resident and warm-process RSS denominators.
- RSS comparison is scenario-matched; the cold and retained-warm ceilings are
  not interchangeable.
- Root ambiguity uses persistent exact meanings for built-in accumulators and
  materializes the chosen eager product once.
- The predecessor-key dependency index, contextual completed-code operations,
  dropping-parent acceptance, separate roots, and large flat accumulation are
  committed test obligations rather than prototype assumptions.

## Verification

`baseline_rss.py` and `persistent_meaning.py` pass Ruff format/check and
Pyright with zero findings. The persistent witness executes successfully. All
three memory rows completed with identical result digests and exit status 0.
