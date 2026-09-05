# TBD after target-shaped parsing

These are deliberately not implementation steps in `TODO.md`. Re-evaluate them
only after the target-shaped architecture is complete, cleaned, documented,
profiled, tested, and committed. The measurements must describe the exact
landed source tree.

The authoritative baseline and acceptance evidence will be the final report in
`zzz_current_work/260826-target-shaped-parse/reports/`. Historical evidence
remains in `zzz_current_work/260821-one-path/reports/`.

## 1a — user-pinned parallel target

- [ ] **USER-PINNED TARGET (2026-08-22; user-filed, only the user closes it):
      16 cores must deliver at least 8–10x, or we optimize until they do.** The
      current best rows sit at 4.2–5.3x at 16 workers; that is not acceptance,
      it is the gap. What is already measured about the gap: independent
      documents on fully distinct replicas saturate at 5.5–6x on 16 threads
      (P2 3a — engine-level contention, not scheduling), and the serial `find`
      sweep is at CPython's per-offset floor.
      **[2026-08-25 correction, i19_report.md F1: that 5.5–6x figure was
      measured with ONE str object shared across threads; with per-worker
      documents threads reach 7.63x at 16 vs a 7.98x process control. The
      hardware's own answer at 16 workers on this 8-core box is ~8x for the
      construction-heavy corpus, so this bar sits at the machine's edge here;
      the user holds it as aspirational (ruled 2026-08-25).]** Consequence: no
      scheduling lever can reach this target — it goes through the construction
      ceiling (P2 3a) and, if that resolves to allocator/refcount contention,
      through engine-level work (object construction volume, interning,
      allocation strategy under free threading). Every increment toward it
      reports the 16-worker ladder against THIS bar.

Apply the target to the final same-codomain product, not to the deleted
model-plus-fold pipeline: compare `cores=1` with 1/2/4/8/16-worker execution of
the same `ReductionMorphism` and final result. Attribute remaining time in
`src/lexic/parsing/parallel/`, product fragment construction/join, recognition,
decoding, allocation, and finalization. Do not raise the 2 KiB floor, suppress
an eligible split, or run multithreaded benchmarks concurrently.

## 4a — payload/export efficiency

- [ ] **Make payload/export efficient without changing the product:** remove
      giant Python literal tuples and redundant whole-value walks or parses
      while preserving fixpoint, digest/provenance, importability, and atomic
      agreement among source, cache, and data. Measure checked projection,
      render, validation/write/byte-compile, import/load, and RSS on the real
      path. Preserve exact exported bytes or explain every intentional
      representation change through the existing product gates.

Start at `src/lexic/compile/payload/`, `src/lexic/compile/output/writer.py`, and
the export call used by the tokenizer example. The target-shaped parser ends at
a ready `IrTokenizer`; this item owns the subsequent export cost. Do not push
export representation concerns back into parser completion or add production
profiling hooks.

## 1b step 5 — putative recognition/product overlap

- [ ] **PUTATIVE ONLY — explicit user go/no-go after the final measurements.**
      I22 step 5 proposed overlapping parse and fold after subtree completion.
      The target-shaped architecture deletes `ReduceFold`, so that proposal is
      not carried forward as an implementation recipe. First determine whether
      the final profile exposes any material serial boundary between recognized
      region completion and direct `ProductProgram` fragment construction or
      join.

If such a boundary exists, write a fresh design against the final owners in
`src/lexic/parsing/parallel/`, the final product ABI, transactional state,
ordered failure semantics, and `FragmentProduct` entry/exit laws. It must prove
that streaming a completed region cannot expose speculative state, reorder a
verdict, duplicate construction, finalize a root twice, or create nested pool
leases. Compare its predicted ceiling with simpler removal of the measured
bottleneck. Present the evidence and an explicit go/no-go to the user before
prototyping or changing source.

If the final parser already constructs the product at recognition completion,
or no distinct serial stage remains, close this as structurally obsolete.

## Benchmark host — the GitHub Actions runner beside the desktop (user, 2026-09-04)

Measure the Actions runner against the local desktop as a benchmark target. It
is free, quiet, and already runs the 72-row protocol on every push; its
CPU-clock envelopes read about 1 % where the desktop, under a browser, reads
27–60 % on threaded wall rows. Known about it: 4 vCPUs; CPython 3.14.7
free-threaded built with Clang 22 (the desktop's 3.14.3t / Clang 21 agreed
with it row for row on the PDA rows).

Shape when taken up: a host fingerprint (cores, interpreter build, CPU model)
in the row contract; a runner-labelled measurement rendered beside the local
numbers in the committed artifact; never two hosts inside one pair. No gate
depends on it.
