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
splitting costs more than it returns. It is stated once, in `policy.py`:
`MIN_CHUNK` caps the worker COUNT (`capacity(size)`, how many pieces a size can
feed), and `MIN_PIECE` (half a chunk) is how far under it one piece may fall —
`clears_floor` asks it of every piece. A cut lands on a mark, so a piece can
come out short of its share; dropping a worker for that idles a core that would
still win (on the benchmark roster a 1 KiB piece parses for 33 µs at the
cheapest row and ~0.95 ms at the median, against 7–21 µs to hand a warm pool
one more piece), so only a piece far under the chunk is refused. The three
dividers that cut at marks nearest even shares — the plan cuts
(`cuts._balanced_cuts`), `routed.divide` and `folded.divide` — share ONE
chooser, `regions.floor_cuts`, asked through a `Cutting` tuple: each cut snaps
to the nearest mark, and only where that leaves a piece, or what is left after
it, under `MIN_PIECE` does it walk on to the nearest mark that does not, or
take one worker fewer. Each divider says where the next piece starts and
whether the piece before keeps its mark (`after_mark` for the plans, one past
a terminator for routed, past the separator for folded).
`partition` holds every run to the same `clears_floor`, and asks `capacity`
only how many workers a size feeds.

**The routed split derives once and stitches trusted.** The interior's route
(the model steps down to it) depends only on the binding and the plan, so it is
memoised per `(binding, plan)` (`stitch/interior._route`); and the stitched run
is put back with a trusted positional build (`_with_run`), as the folded stitch
already is — the checked `rebuild` re-validated every element of a run the
piece parses had just built, about 100–200 µs of a 32 KB document's split.

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
| folded | a left recursion the predictive path folds into `(γ)(β)*`, its boundaries settled | every character of the mark excluded by every owner, both routes, plus a non-nullable step remainder |

Multiple plans can be certified for one grammar; the cascade decides per
document. `envelope_plans` returns one plan per provable mark in stable order.

**A whole-extent routed interior is bounded by its neighbours' text**, read
by `shapes.exact_text`: one string every time, an exactly-once item through
single-armed rules and nothing else. Every piece wears that text in front, so a
neighbour that varies — `pre{1,2}` spelling `#` or `##` — must decline: read
as one `#`, a piece whose interior opens with `#` parsed `pre` as two and the
stitched model lost a character per piece.

**The folded source reads the fold's SHAPE ANALYSIS**, not its compiled clones:
`plan/folded.py` calls `leftrec/shape.foldable` over the codegen grammar, on the
same `parallel -> pda` edge `plan/speculation.py` already uses for
`GrammarAnalysis`. The repetition it splits is one the grammar never states, so
no arm shape describes it and the character sweep has nothing to find.

Its boundary proof is the per-character form of `owner_excludes`. A mark wider
than `MARK_ARITY` gets "can spell" from `rule_spells` by design, so the whole
spelling is unaskable; exclusion on a substring implies exclusion on every
superstring, so asking each character separately is both askable and stronger.
With a non-empty remainder between two marks that proves every occurrence is a
separator, with no border theory: `" + "` and `"aba"` have the same borders, and
what separates them is the character a spurious occurrence would need.

It over-refuses and never mis-splits, which is the direction a decline is free
in. The refusal it is easiest to get wrong is a mark whose FIRST character is
excluded and whose later one is not — `"+a"` over `[a-z]+` — so that is a
committed witness rather than a note.

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
- `leads_once` — the mark is its **leading** edge (a continuation separator like
  `"\n  | "`). Stated as per-arm CharSet disjointness: every arm leading with the
  mark must have `FIRST(what follows it, through nullables)` disjoint from the
  prefix head. An arm the walk cannot decide answers "reachable" and the plan
  declines. A construct carrying the mark at a leading edge AND somewhere
  interior gets no clause at all.

**One admission function, two callers.** The static certification licenses the
plan; `_cut_offsets` filters candidate marks at runtime. Both read the same
`Boundary`, so the proof and the filter cannot disagree about what they admit.

---

## The stitch rebuilds what the product BUILT, not something equal to it

A repetition's run is a **plain `tuple`**, and `stitch/model.py`'s `is_run` tests
that by exact class — `child.__class__ is tuple`, never `isinstance`. Every
record and every `IrTuple` is a tuple subclass and none of them is a run, so a
subclass test answers yes to things that are not repetitions.

That makes the carrier's type load-bearing in a way most of the model does not
notice. An `IrTuple` in a repetition field compares equal to the plain one and
round-trips to identical text, so equality and a digest of the rendered TEXT
both pass — and it still answers "not a repetition" to the one question the
stitch asks. **A stitch must rebuild the exact class the sequential product
builds, not a value equal to it.**

What DOES separate them is the type-aware shape digest: it renders class names,
so a plain run reads `tuple(…)` and an `IrTuple` reads `IrTuple(tuple(…))`.
That is how the baseline failure was caught, and it is why "did the document
survive" and "is this the same product" are two questions with two digests.

`is_run` is public for the same reason: three call sites ask it, and a fourth
spelling would be a fourth chance to get the subclass case wrong.

---

## The region route divides top-down, and each piece is a worker's share

`discovery/partition.py` takes a tree of divisible spans — an opener, a closer and the
separators between items, nesting read from containment (`Span`) — and a
target of one worker's share of the text. A span's adjacent items pack into
runs of at most the target, and each run is ONE piece in the span's own
brackets, so siblings that ship together come back already joined. An item
larger than the target whose value is a span is descended into and
partitioned the same way. Every span on the path of an oversized item is
divided, even one whose items make a single run, so a descended span is HELD
by a piece and found by item — unless that path span keeps under `MIN_CHUNK`
of its own text, which then stays with its holder. The region scan is the one
supplier today.

`units` renders every piece and the shell with the stand-in of each span
divided inside it, and says which ITEM of the holding piece carries each
stand-in. The pieces of every level parse in ONE pool map, and the calling
thread parses the shell beside them (`WorkPool.map`'s `beside`): the shell is
parsed under the whole grammar, whose view that thread already holds, where a
pool worker drawing it would build a replica of the whole grammar for one
small parse. The stitch then runs innermost first: it finds a stand-in by the
holding item alone (`held_route`), and lays the span's merged items over the
stand-in's node together with its true edge slots. An edge slot can straddle
the bracket (`ws "}" ws`): its truth is the PIECE's part inside the bracket and
the HOLDER's part outside it, so the edge is built from the two slots'
children and taken only when it spells exactly that text.

A stand-in's needle must be unique in the unit that holds it, not in the whole
document. The uniqueness pre-filter reads the NEEDLE's text — what the holder's
node will spell — never the drawn witness's, which can carry noise the needle
does not.

The design keeps every per-unit cost from multiplying: no stand-in is found by
walking a whole unit per region (regions times unit size), and no more pieces
are made than the target asks for — on a skewed document that is a handful of
runs, not dozens of divided regions.

---

## The region walk reads ONE spelling string

`regions.py` classifies each structural character with a single `str.find` into
one concatenated spelling, not with a chain of dict tests. The sections are laid
out skips, openers, then closers and marks together, and **that order IS the
branch precedence**: `find` returns the earliest match, so a character carrying
two roles resolves exactly as it did when each table was tested in turn. Closers
and marks share a section because one test already separates them — a closer's
value is its opener, a mark's is `""` — which is also what lets an unmatched
closer fall through to the mark branch.

This is not a style preference. Shared-dict membership in that loop does not
scale across threads on this build: 0.53x on sixteen threads, against 7.64x for
the same loop over private containers. Reading one string is faster serially
too, so the change does not rest on that explanation holding. The tables are
aliased into locals before the loop — reading them off the record inside it
measures 10-30% slower across the roster.

**A spelling is not an alphabet.** `Roles.spelling` holds a two-role character
once per role, because that is what makes classification by precedence work.
`Roles.watched` holds each character once, and is what a sweep iterates.
Sweeping the spelling reports every offset of a two-role character twice.
`watched` is derived from `spelling`, which is what makes `spelling.find` total
over swept offsets: neither walk tests for `-1`.

## The windowed find: same answer, discovered in parallel

`par_find` divides a document into arithmetic windows, walks each with a stack
that may UNDERFLOW, and replays what a window could not settle against one
stack. Four event kinds carry that: a region opened and closed inside the window
is already final; a closer that underflowed carries the opener it wants and
whether it is also a separator; a separator at the underflow level; and an
opener still standing at the window's end, whose mark list later windows keep
appending to. The merge is O(windows x depth) — each window contributes at most
its own residual depth in openers, and every other event settles in constant
time.

Window bounds are arithmetic, which is sound because every watched spelling is
one character: no occurrence straddles a boundary, and every offset belongs to
exactly one window.

**A grammar whose vocabulary carries an opaque interior takes the serial walk.**
A window cannot know whether it begins inside one without a pass over everything
before it, and that prepass costs more than the walk it enables — it turned a
win into a regression on the grammar that needs it. The condition is read off
the vocabulary, so a grammar qualifies by what it derives; no grammar is named,
and one that grows an interior loses the window by itself.

## Interiors: what a sweep must skip

`discovery/` certifies regions a character sweep would otherwise misread —
strings, bracketed runs, delimited spans. A region family is a rule's arms taken
as **one construct**: same-spelling openings with different closers must refuse
together, and a fully-literal arm spelling exactly `opening + closing` is the
region's own empty instance rather than a competitor.

Certification is derived on the grammar the parser actually runs. That matters:
the codegen passes hoist groups and arms, so shapes present in the authored
grammar are not always the shapes the analysis meets.

### Which plans may SHARE a sweep

Several plans can be certified for one grammar, and the windowed ones sweep the
same document for their own marks. `plan/cuts.py` answers who may share:

- **`reads_a_sweep(plan)`** — true only when the plan has no envelope and its
  scanner is not opaque. An **envelope** plan cuts on its own noise run and
  reads no window at all; its mark is whitespace on the meta grammars, so
  sweeping for it enumerates a mark every few characters and discards every
  one. An **opaque** plan WALKS the document unit by unit under its own region
  table, which is not a windowed sweep and is not interchangeable with one.
- **`shared_scanner(grammar, plans)`** — one scanner over the UNION of the
  sweeping plans' spellings, or `None` when no certified plan reads a sweep.
  Every plan that does not read one is handed `None` and takes its own pass.

Two things make the union safe. Marks carry no depth, so merging two plans'
spellings changes neither window's depth accounting; and each plan still
narrows the union to its own spellings through `scan_marks`, so sharing cannot
propose a cut a plan would not have proposed alone. Narrowing to the certified
plans' marks is the point: a document is only ever cut at a mark some certified
plan keys on, and every other occurrence costs a `find`, a window build, a
depth rebase and a discard.

**A new plan shape must be checked against `reads_a_sweep`** — it is the rule
that decides whether the shape's cuts come from the shared scan or from a pass
of its own.

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

**A replica's tables are copied, not compiled.** `_mint` declares each view to
the product layer (`products.declare_replica`). A product, grants program,
island table or delegate set the view asks for is compiled ONCE on the
original pair — under a per-key lock taken on the miss alone, so a hit reads
lock-free — and the asking thread takes a structural private copy
(`ModelExecutable.copied`, over `PrivateCopy`). The copy makes anew every
object the compile minted: engine records, containers, baked closures and
their cells, and the IR value records the tables hold (a decoded rule's
reference is read on every tree node, and a shared one cost a copy 5% of an
Earley-heavy split's wall). It keeps what is the process's: what a lexic
module or class names (constants compared by identity, such as
`CharSet.EMPTY`), atoms, compiled `re` patterns (re's own cache shares them
between compiles anyway), and the binding's read-only projections. A copied
`PdaTables` and its `DelegateSource` carry an `origin`, the edge a miss asks
through. Recompiling per worker ran a full analysis of the grammar on every
thread that won a chunk. On vyx's compile that was 2 to 5 analyses of the GBNF
self-grammar at about 0.5 s of CPU each, and a clone-compile count that
changed from process to process (344 to 860). With copies, that compile runs
one analysis.

**A copy is earned by reuse.** A worker's FIRST split of a pair parses against
the original pair, shared; the copy is minted only when that thread meets the
pair again in a LATER split. Each pool lease numbers its split
(`WorkPool.lend`, `running_lease`), and a thread's cached first meeting
carries that number. A one-shot split, such as `compile_text` splitting a long
grammar source, therefore mints nothing. A copy costs 5 to 50 ms and is held
for the thread's life, while contention on a shared product costs a one-shot
split a fraction of that. Before this rule, vyx's benchmark worker kept 4 copies
of the GBNF self-grammar that nothing read, and every collection of the timed
parse walked them: retiring them was 0.904x CPU on vyx's Earley seat.
**The copies are made all at once, before the next split's pieces.** Which
threads serve which split is the executor's choice, so a thread's second
meeting — and with it its copy — used to land in whichever later split it next
served, inside that split's pieces. Now a split records the pairs its workers
met for the first time (`replicas.settle_first_meetings`), keyed by the
document's executable view, so they retire with it; the pool's next split
through the SAME view first gives every worker its own copy, one task per worker behind a
barrier, before any piece goes out (`replicas.warm_due`), along with every
island table and delegate set the original has met so far
(`PdaTables.copy_held_islands`). A repeatedly split
artefact therefore copies once per thread at the start of its second split,
and no later split ever copies. A split through another view warms nothing, so
a one-shot split still mints no copy and a gone document thread's pairs are
never copied.

**The shared original is the document thread's own.** `CompiledGrammar.parse`
compiles its product on the calling thread before asking for a split. Built by
the first worker to miss, it lived on in a pool thread's heap. The same 4 vyx
programs cost 1.035x CPU and 31% more pause per observation when retained from
pool threads rather than from the main thread, so on this interpreter an
object's owning thread matters to every later collection, not only its count.

**The bound.** What a grammar compiles is a function of the grammar and the
documents parsed. How many copies exist is not: replicas are a runtime cache
bounded by the pool size, at most one copy per thread that met the pair in two
splits, released with that thread. The retained set therefore varies with
scheduling, by whole copies, and that is by design.

The FIRST document thread keeps the original pair, which is therefore never
issued to a worker, so a single-threaded program compiles no second set of
tables. Where `available_workers()` is 1 at all — a GIL build, a one-cpu
machine — `document_view` hands the binding straight back and claims nothing.
An exited thread's replica is dropped and its tables released rather
than re-issued, since re-issuing hands a live worker objects a dead thread
allocated. `replica_count` meters one pair; `claim_census()` answers the
lifetime question it cannot — how many claims are held by threads that have
already exited.

**A worker releases its own claim when it exits, not when someone next asks.**
The liveness sweep inside `_claim` only ever prunes the pair being claimed
against, so a pair no document touches again would keep its dead claims for the
life of the process: one pass over a twelve-grammar roster left **189 of 203
claims held by exited threads**, and further parses of the first grammar never
moved it, because that pair self-cleans while the other sixteen are never
claimed against again.

The signal is object lifetime. `ThreadPoolExecutor` has an initializer and no
per-worker exit callback, so the first time a thread claims, a bare sentinel
goes into that thread's own local state with a `weakref.finalize` armed on it;
the thread's state is freed when the thread ends, the sentinel is collected,
and the finalizer retires what that thread held. Four details are load-bearing:

- the owning `Thread` is captured at claim time and passed to the finalizer,
  never read inside it — `threading.current_thread()` during a worker's
  teardown returns a dummy thread that matches no claim;
- the sentinel declares `__slots__ = ("__weakref__",)`; with `__slots__ = ()`
  it cannot be weakly referenced at all and the arming raises;
- arming happens at CLAIM time rather than in the pool's initializer, so a
  worker that never touches the registry pays nothing and holds nothing;
- the finalizer never waits on the claim lock (`_MINTING`). A finalizer runs
  on whatever thread frees the sentinel or anything else, and that may be the
  thread already holding the lock: mid-claim, or releasing another thread's
  claim, where the release frees the next sentinel. Waiting there deadlocked
  the thread on itself. So `retire_thread` only queues the thread and takes
  the lock if it is free, and every holder drains the queue before it
  releases, then asks again once released.

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

**Derived roles are a bounded memo too.** `roles(grammar)` walks every arm of
every rule to find the opener/closer pairs and repetition separators, and the
split asks for it once per DOCUMENT rather than once per grammar — on a meta
grammar that re-walk was several percent of the whole split parse. `_ROLES` is a
registered `memo({})` keyed on `id(grammar)`, and its value carries the grammar
itself: the strong reference pins the id, so a recycled address can never alias
a live entry. The split-plan memos in `planner.py` and `plan/routed.py` are
the same shape.

Every registered memo is a **pure memo**: dropping an entry costs a
recomputation and changes no answer. That is what makes eviction safe even when
an identity is released while another holder still uses the object.

This matters most where grammars are DERIVED at run time — `bind()` mints a
fresh codegen grammar per vocabulary, a reducer mints a variant per policy — so
a service that rebinds per request would otherwise grow every memo without
bound.

## The collector, for callers that retain

A compiled artefact is a large, permanently live, gc-tracked population, and
every full collection walks all of it. Measured on this machine, parsing each
roster grammar once at `cores=1`, medians of seven collections:

| tracked objects | full collection |
|---|---|
| 130,009 (interpreter + lexic) | 7.71 ms |
| 141,902 (4 artefacts) | 9.03 ms |
| 169,316 (8 artefacts) | 10.91 ms |
| 172,409 (12 artefacts) | 10.86 ms |

The cost tracks the population, and the population is what the caller chose to
keep. A service holding many compiled grammars pays that walk on every
collection the whole process triggers, including ones its own allocation did
not cause.

**`gc.freeze()` is the tool, and it belongs to the application.** It moves
everything currently tracked into a permanent generation that collections skip.
On the twelve-artefact tree above: 172,380 objects frozen, and a full collection
goes from **10.38 ms to 5.20 ms** — half. `gc.unfreeze()` restores it.

Lexic does not call it, and a library should not: freezing is a statement about
a process's whole lifecycle, made once after the artefacts a program intends to
keep are built and before it starts serving. The same applies to
`gc.set_threshold()` — thresholds are **process-wide**, so a library that tuned
them would be tuning its host's collector for every other allocation in the
program. Both are documented here as levers an application may reach for, and
neither is prescribed.

## A per-character loop must not read the document from a module global

Reproducible, and it costs everything: a loop that runs once per input
character and reads the text from a module-level name scales at **0.45x on
sixteen threads**, whatever container holds it. A module global is a shared
mortal object, so every read is an atomic reference count on one cache line,
and the loop does one per character.

Pass the text in. A parameter is a local, and a local read is not shared
traffic. This is the same effect the replicas exist to remove, arriving through
a different door — and it is worth stating on its own, because it is invisible
at one thread and looks like a scaling ceiling rather than a defect.
