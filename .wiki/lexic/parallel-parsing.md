# Parallel Parsing

**When to load:** changing how a document is split across workers; adding or altering a safety proof in `stitch/`; touching `plan/`, `discovery/`, replicas, or the warm pool; debugging a split that declines when you expected it to engage.

See also: [[architecture]], [[public-api]], [[invariants]]

---

## The one rule

**A split is indistinguishable from the sequential parse, or it declines.** Same
model, same bytes back, and the same refusal — type and message — where
sequential refuses. Whether a split engages is the mechanism's own business;
being *wrong* never is.

Everything below exists to make declining cheap and engaging provable.

---

## Splitting is a question about the GRAMMAR, asked before the route

`CompiledGrammar.parse` asks for a split first, of the grammar alone. A
segmented (token) grammar never yields a plan — its terminals match ids, so no
character is structural. Neither does an unsupported shape, a short input, or a
failing chunk; each simply parses sequentially.

The floor is **2 KiB per worker**, measured against thread spin-up. Below it,
splitting costs more than it returns.

---

## The plan cascade

`plan/` derives, per grammar, the shapes a split could take. A plan is derived
once per grammar and reused across documents; **cuts are a function of the
document and are never cached across two of them**.

| plan kind | shape it needs | how a cut is licensed |
|---|---|---|
| separated | a repetition with a separator character | `owner_excludes` — the unit provably cannot emit the separator at this depth |
| terminated | a repetition whose unit ends on a mark | `terminates_once` — every visible mark is the unit's final edge |
| terminated, boundary route | unit emits its own mark (continuation lines) | the unit ANNOUNCES itself: a certified prefix, filtered at runtime by `admits` |
| envelope | optional head/tail wrapping the repetition, separator is a noise run | the envelope's own certified boundary |
| routed | an interior a character sweep cannot see | route-derived interiors |

Multiple plans can be certified for one grammar; the cascade decides per
document. `envelope_plans` returns one plan per provable mark in stable order.

---

## Safety proofs are per owner, and they refuse by default

`stitch/safety.py` holds the proofs. Two things about them decide what a split can do:

**Per owner, never pooled.** Pooling every rule reachable anywhere would reject
JSON, because a nested object quite properly contains commas. The proof asks
what *this* owner can emit at *this* depth.

**Failure to prove is an ordinary decline**, not an error. A grammar whose shape
is not provably safe parses sequentially and nobody hears about it.

The two mirror clauses that license a construct carrying the mark:

- `_ends_once` — the mark is the construct's **final** edge (a comment closed by
  its newline).
- `_leads_once` — the mark is its **leading** edge (a continuation separator like
  `"\n  | "`). Stated as per-arm CharSet disjointness: every arm leading with the
  mark must have `FIRST(what follows it, through nullables)` disjoint from the
  prefix head. An arm the walk cannot decide answers "reachable" and the plan
  declines. A construct carrying the mark at a leading edge AND somewhere
  interior gets no clause at all.

**One admission function, two callers.** The static certification licenses the
plan; `_cut_offsets` filters candidate marks at runtime. Both read the same
`Boundary`, so the proof and the filter cannot disagree about what they admit.

---

## Interiors: what a sweep must skip

`discovery/` certifies regions a character sweep would otherwise misread —
strings, bracketed runs, delimited spans. A region family is a rule's arms taken
as **one construct**: same-spelling openings with different closers must refuse
together, and a fully-literal arm spelling exactly `opening + closing` is the
region's own empty instance rather than a competitor.

Certification is derived on the grammar the parser actually runs. That matters:
the codegen passes hoist groups and arms, so shapes present in the authored
grammar are not always the shapes the analysis meets.

---

## Replicas: why concurrent parses stop fighting

The engine memoises compiled tables per `(grammar, binding)` **identity**. Under
free threading that is the bottleneck — the tables are read-only, but an object
one thread allocated costs every OTHER thread an atomic reference count per
read (biased reference counting: ownership is per object, and the cost is paid
on a single CPU with no concurrency at all, not only as cross-core cache-line
traffic), and scaling flattens around 1.8× however many cores exist.

Each worker gets an **equal but distinct** grammar and its own replica of the
product's executor (`Replica`, `ModelExecutable.replica()`), hence its own memo
entry, hence its own objects. Measured on 8 threads when this landed: 1.82×
shared, 3.71× with grammar replicas, 4.21× with the executor shallow-copied,
5.34× once its container spine is copied too.

A replica only pays when the thread that PARSES against it is the thread that
compiled it, so **a replica is owned by a THREAD**, and by one thread only.
Ownership is established once under `_MINTING` — a cold lock, taken the first
time a thread asks for a pair; every later parse reads the answer out of that
thread's own thread-local. Neither half of the pairing can be an index:
choosing by TASK let the pool reshuffle the pairing every document, and 44 % of
cut-route and 74 % of region-route chunk parses ran against another thread's
replica at 12–23 % of a chunk's CPU; a pool-LOCAL worker number cannot be an
identity at all, because two live pools number their own threads from zero. The
lock is what a length read plus an append cannot do — without it, N threads
first-touching one pair all mint against the same stale population.

**Two kinds of claimant, and they never share one view.**

- The thread parsing a whole DOCUMENT claims its own EXECUTABLE view with
  `document_view`, in `CompiledGrammar.parse`, **before a split is even
  attempted** — because a split's driver does not only hand chunks out. It
  parses the separator leads, the routed stand-in shells and the region
  boundaries itself while the workers run, it parses the sequential fallback
  when the split declines, and it stitches through that same product
  afterwards. Claiming only on the fallback would leave every one of those on a
  pair a concurrent whole-document caller can be handed. The GRAMMAR stays the
  artefact's: it is the split plan's identity and every analysis is memoised on
  it, so replicating it would re-derive them per thread to privatise nothing
  that thread parses through.
- A chunk WORKER claims with `worker_replica`, by thread, and always mints —
  including a copy of the grammar, because a worker also reaches memos keyed on
  the grammar alone. `worker_parse` is the entry, and it is called from inside
  the work, never from the submitting thread.

The FIRST document thread keeps the original pair, which is therefore never
issued to a worker, so a single-threaded program compiles no second set of
tables. Where `available_workers()` is 1 at all — a GIL build, a one-cpu
machine — `document_view` hands the binding straight back and claims nothing.
An exited thread's replica is dropped and its tables released rather
than re-issued, since re-issuing hands a live worker objects a dead thread
allocated. `replica_count` is the meter.

Synthesized model classes stay shared by necessity — two workers building two
different classes for one rule would break model equality, which is the thing
the split exists to preserve.

Sharing those classes turns out to cost nothing, and the reason generalises:
free-threaded CPython gives heap **types**, functions and module dicts
*deferred* reference counts, so instantiating one shared class from sixteen
threads measures the same as instantiating a per-worker one. Only ordinary
mortal objects pay per reference.

## The document is copied per thread

An object every worker reaches costs an atomic read-modify-write on one cache
line for each reference taken. The parse loop takes one per terminal match —
the kernel holds the document as `self.text` and passes it as the first
argument of every matcher — so a document shared across threads is the densest
possible case: one line, every core, millions of times a second. Measured, it
runs *slower than a single thread*.

`parse_model` and `token_model` therefore take their own copy of the input
before doing anything else, and every parse owns the string it reads. The copy
is `"".join((text, ""))`: `str.join` returns its argument unchanged for a
one-element sequence, and so do `text[:]`, `str(text)`, `text + ""` and
`text * 1` — every obvious idiom hands back the shared object and does nothing.
It costs one `memcpy` (~0.02 ms/MB, 0.002–0.005% of a parse at every size from
16 KB to 10.6 MB) and lifts independent documents on 8 threads from 4.97× to
7.23×, against a 7.62× process control.

Splitting one document is already clear of this: `orchestrate.py` slices
`text[a:b]` inside the worker, so each piece is a fresh string made on the
thread that parses it.

**Identity caches pin their key objects.** `id()` is recycled the moment an
address is free, so a cache keyed on bare ints can be hit by a brand-new object
that merely landed where a dead one used to be. Every replica cache — including
the per-thread one — holds the key objects and re-checks with `is`, so a hit is
always the right pair. Skipping that pin does not fail loudly: it hands out a
replica compiled for a different grammar, and strands memo entries whose owner
never became an adoption root.

---

## Pool lifecycle

`PoolLease` borrows a warm executor for one split and returns it. The ownership
rule is exact: **every pool is either lent to exactly one caller or idle in the
cache.**

- Returned only on a clean exit. A phase that raised may still be draining work,
  and a pool of unknown state is not worth the microseconds it saves — that one
  is closed.
- `RETAINED = 2` idle pools per worker count, so a caller parsing document after
  document pays executor build and shutdown once rather than every time.
- `reset_pools()` closes only IDLE pools. A lent pool is unreachable from the
  cache, so a reset cannot disturb a parse in flight.

**A retained pool is not evidence a split engaged.** The lease is taken before
the plan is consulted, so a declining grammar leaves a warm pool behind whose
executor never had work submitted to it.

### A refusal and a bug leave by different doors

`WorkPool.map` — and `ParsePool.map` through it — treats the two kinds of
failure as different facts, because they are:

- A **domain refusal**, meaning anything in the `LexicError` family, is an
  answer about one item. The phase DRAINS: work past the first failure is
  cancelled, everything still running is waited on and collected, and the
  EARLIEST input's verdict is what gets raised. Without the drain, "earliest
  input" would report whichever chunk lost the race and the split would move
  the wrong cut. The pool is whole afterwards and stays usable.
- **Anything else** is a bug, not a verdict, so nothing about it is learned by
  waiting. The queued work is cancelled, the pool is marked failed, and the
  error reaches the caller AT ONCE — running siblings are *not* waited on,
  since one of them may be blocked on the very caller this error has to
  release. `close()` on a failed pool likewise does not wait, and cancels
  instead.

Reusing a failed pool raises **`RuntimeError`**, and the type is the point:
deliberately NOT a `LexicError`. A caller catches that family to fall back to a
sequential parse, and a broken pool must not read as a chunk that would not
parse. A failed pool is never re-lent either — a lease whose phase raised
closes its pool rather than returning it to the cache.

---

## Cache lifetime

`parsing/caches.py` bounds the identity memos by the artefact that owns them.
A memo registers with `memo()`, saying which key positions hold an owner
identity; a derived object stored as a memo's value is `adopt`ed under the
identities that entry is keyed by, so the chain — artefact → codegen grammar →
lifted grammar, normalised instance, PDA tables, Earley tables → run analysis —
releases transitively from one root. An owner calls `track()` once and a
weakref finalizer releases the rest when it dies.

**Adoption is under BOTH key identities, never one.** The model product is
memoised per `(grammar, binding)` pair and mints that whole derived chain, and
neither key outlives the other in general:

- Owned by the GRAMMAR alone, a chain minted for a private binding — a document
  thread's view, a worker's replica — outlives the binding it was minted for and
  can then be released by nothing short of the artefact. Every thread that comes
  and goes leaves one chain behind: that is the leak.
- Owned by the BINDING alone, the mirror case leaks. `CompiledGrammar.bind`
  returns a new artefact carrying a FRESH codegen grammar over the SAME product,
  so a service rebinding per vocabulary pins its chains to a product that never
  dies.

Under both, a retiring binding takes its chain with it and a live sibling on the
same grammar keeps what it still needs. `release` therefore also clears the
released identities out of every OTHER owner's adoption record: without that
sweep the surviving owner accumulates a dead id per released child for as long
as it lives, and a recycled address later reads as still owned.

Every registered memo is a **pure memo**: dropping an entry costs a
recomputation and changes no answer. That is what makes eviction safe even when
an identity is released while another holder still uses the object.

This matters most where grammars are DERIVED at run time — `bind()` mints a
fresh codegen grammar per vocabulary, a reducer mints a variant per policy — so
a service that rebinds per request would otherwise grow every memo without
bound.
