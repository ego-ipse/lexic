# Handover — parallel parsing

## Result

`parse_reduced` splits a document by its bracketed runs. The tokenizer read
is multithreaded.

Free-threaded 3.14t, 16 cpus, Qwen3 `tokenizer.json` (10,635,788 chars):

| | time | per char |
|---|---|---|
| reduce, sequential | 31.06 s | 2.93 µs |
| reduce, split | 7.70 s | **0.75 µs** (4.03×) |
| `read_from_path` | 11.19 s | 1.05 µs |

`ex12_real_think_flow --reset` read step: **32.5 s → 11.5 s**. Values equal
to the sequential reduce on both tokenizer files tried.

## Design

`src/lexic/parsing/parallel/regions.py`:

- **`find`** — one `str.find` sweep per watched char, then a stack walk over
  structural offsets. Every bracketed run and the separators inside it, at
  whatever depth. Opaque interiors skipped whole, so a comma inside a string
  is never seen.
- **`choose`** — largest runs that neither contain one another nor fail to
  divide. A run that cannot divide steps aside for the runs inside it;
  otherwise the outermost object (8 top-level marks) claims the document and
  the split declines.
- **`pieces`** — cuts at equal byte POSITIONS, nearest separator taken. A
  piece carries only its own brackets, so it parses under that region's rule
  at the cost of its own text.
- **`shell` + `stub`** — the document with each run shrunk to its first item,
  parsed once. The shell is serial; keep it small.
- **`merge` / `route_to` / `splice`** — concatenate piece values, find where
  the stub's value sits in the shell, put the merged value there.

`interiors.py` derives the opaque regions (`"` delimiter, `\` escape) from
the grammar. Without it an RFC-shaped json certifies no structural character
and nothing splits.

## Tree

Last commit `d4c4826d`. Uncommitted:

```
NEW       parallel/regions.py, parallel/interiors.py
modified  parallel/orchestrate.py   product injection, Request bundle
modified  parallel/replicas.py      grammar_replicas, lazy per-index
modified  parsing/products.py       parse_reduced calls split_regions
modified  compile/artifact.py       passes parse_model + Request
modified  two test files            signatures only
modified  CLAUDE.md                 layout lines
```

## Left undone

1. **Gate fails** — pylint `R0914` (too many locals) and `R0911` (too many
   returns) in `regions.py`. `split_regions` needs its piece-parse and
   splice phases lifted into helpers.
2. **No tests for `regions.py` or `interiors.py`.** The 4500 passing tests
   never execute either file; `test_split_differential.py` covers the MODEL
   path. Only evidence is `equal=True` from throwaway probes on two files.
   Write the differential: per ground-truth grammar and a large generated
   document, `split_regions(...) == _reduce_one(...)`, refusal parity, and a
   non-vacuity gate proving at least one fixture really splits.

## The bug

`route_to` decided whether to descend with `isinstance(node, tuple)`.
`IrMap` iterates and has a length **without being a tuple subclass**, so
every reduced document read as a leaf, the splice never landed, and
`split_regions` did all its work and returned `None`. Every number before
the fix (0.31×, 0.58×, 0.64×, 0.98×) was split work plus a full sequential
fallback.

Walk `IrSelf.children()`, rebuild with `IrSelf.rebuild()`. Never hand-roll
`tuple(node)` / `type(node)(*parts)`; never widen a signature to `object` to
quiet a type checker.

## Gap to benchmark

`lexic-mt` ≈ 0.28 µs/char; reduce split 0.75.

1. Reduce product costs ~2× the model product per char (2.93 vs ~1.5
   sequential on json). Untouched.
2. Scaling ~4×, not ~16×. Phases on the 10 MB file: find+choose 1.15 s,
   pieces 6.98 s parallel, shell 1.90 s, merge 0.33 s — the piece work alone
   got 4.3× from 16 cores. Contention. Biggest lever, measurable today.
3. Directives worth ~23% on the model path; never measured on reduce.

## Do not redo

- Wrapping pieces in the document's whole prefix+suffix — 0.31× measured.
- Fixed-depth cutting — the tokenizer's parallelism is three levels down.
- Cuts by mark INDEX — unbalanced; one worker gets the whole document.
- A memory cap in `policy.py` — treated a symptom of the unbalanced cut.

## Probes

`tok_*.py`, `real_tokenizer.py` here. The `tok_*` ones read the Qwen3 file
under `~/.cache/huggingface/hub/models--Qwen--Qwen3-0.6B/` — ex12 reads THAT
file (151k tokens), not the smaller SmolLM2 one; measuring the wrong file
cost real time. Run under `tools/guarded.sh`. Throwaway — delete once tests
exist.

## Note

Most of this session was spent on measurements that were artefacts of the
bug above, on results generalised from a single grammar, and on patching
symptoms rather than finding causes. The speedup is real and reproducible;
the path to it is not one to repeat.
