# Prototype report — target-shaped performance feasibility

**Superseded composition note:** `PROTOTYPE_4.md` proves that this report's
native-capture and pre-created-IR freeze rows cannot be added into a ready
tokenizer budget. The measurements remain evidence for their isolated phases;
the selected composed carrier, canonical index contract, and scenario-relative
acceptance boundary are in `PROTOTYPE_4.md`.

**Date:** 2026-08-28
**Tree:** branch `targeter`, source baseline `0faa7289`; every executable and
instrumentation change is under this effort's `proto/`. `src/` is unchanged.

## Question

Can the composed grammar construct the Qwen tokenizer's demanded product near
the standing 105x target without first building JSON models, folding them, or
running a separate whole-document region-discovery pass?

The standing source is `resources/tokenizers/qwen3.tokenizer.json`, 11,422,654
bytes / 10,635,788 characters. The current uncontaminated read/reduce/build
baseline is 17.416359 s wall; 105x is about 0.166 s for a ready tokenizer.

## Controls

The stdlib Python-tree control constructs the complete recursive Qwen
`dict`/`list` value in a 0.084940 s median. The representation target below
0.100 s is therefore real on this machine.

The current Lexic reduction-variant parse remains 11.932296 s at one core and
8.335490 s under `AUTO`. No prototype result is presented as a current parser
improvement.

## Regular-region construction

The grammar-derived vocab program recognizes the real JSON `string`,
`name-separator`, and `int` lower rules and directly populates owned native
encode/decode indexes. The analogous merge program recognizes repeated
two-string arrays and directly populates ordered dyads.

The first parallel version reused one compiled regex pattern in every worker.
That result was misleading because `re.compile` caches by source: repeatedly
calling the compiler returned the identical pattern object. An identity check
confirmed all supposedly private `first`, `next`, and `stream` patterns were
shared.

An alternating four-cell run with genuinely cache-distinct but semantically
equal patterns gives the exact full vocab builder:

| 8-worker ownership | process CPU | wall |
|---|---:|---:|
| shared text / shared program | 0.572344 s | 0.097326 s |
| owned text / shared program | 0.541903 s | 0.090572 s |
| shared text / private programs | 0.353318 s | **0.064854 s** |
| owned text / private programs | 0.337019 s | 0.066408 s |

The input string is already a worker local and does not need copying. The
compiled pattern is the contended mortal object acquired at every transition.
Per-worker pattern ownership removes 32.5 ms wall and 219 ms CPU. This is the
same free-threaded mechanism isolated by `i19_report.md`, applied to the actual
capture loop rather than inferred from its scaling curve.

### Cumulative phase profile

With genuine per-worker patterns, the vocab worker phase separates as:

| cumulative operation | one-worker wall | eight-worker wall |
|---|---:|---:|
| captured transition match | 0.161590 s | 0.030898 s |
| named group extraction | 0.191220 s | 0.032848 s |
| lower-signature string decode | 0.208429 s | 0.042315 s |
| integer conversion | 0.217841 s | 0.043564 s |
| one key index | 0.242964 s | 0.042311 s |
| both final indexes | 0.263368 s | 0.050789 s |

Numeric groups measure 0.036101 s and slicing numeric capture bounds measures
0.035300 s. Neither improves on named groups. The dicts, duplicate checks, and
scalar conversions are not the parallel bottleneck. The full 0.064854 s arm is
dearer than the 0.050789 s worker phase because it also joins fragment-owned
indexes into their final mappings.

## Rejected discovery shapes

The current exact `regions.find` result over Qwen costs 0.392020 s and retains
303,070 marks. It cannot sit in front of a 0.166 s target.

A windowed escaped-interior transducer was exact but cost 0.930023 s at four
windows and 1.045337 s at eight. It allocated and sorted tagged events and ran
both possible quote states. The event representation is rejected; the result
does not reject parallel discovery itself.

An O(workers) cut finder which searched from the vocab opener to its tail cost
0.141200 s. Strengthening its tail to consume a complete last entry removed a
false positive inside a token spelling but raised planning to 0.256093 s. Its
first merge formulation also assumed a following member and failed because
Qwen's merges field is last. All opener-to-tail searches are rejected: they
re-recognize the high-volume region before workers recognize it again.

## One-pass anchored high-volume product

`proto/anchored_tokenizer_regions.py` exercises the replacement shape. Upper
schema route anchors propose the vocab and merge shells; O(workers)
grammar-entry searches choose arithmetic cuts; cache-distinct worker programs
capture both regions concurrently; and the coordinator joins final native
vocab, inverse-vocab, and exact source-order rank mappings once. There is no
all-entry planning list and no all-mark sidecar.

The product is exactly equal to the stdlib-read Qwen oracle on every round.
Every retained thread is forced through a pre-timing barrier; trivial task
submission is not accepted as proof that the complete pool started. Medians,
with equal workers assigned to each region, are:

| total retained workers | process CPU | wall |
|---:|---:|---:|
| 2 | 0.611183 s | 0.330756 s |
| 4 | 0.641654 s | 0.183093 s |
| 6 | 0.670600 s | 0.134352 s |
| 8 | 0.698544 s | **0.113811 s** |
| 10 | 0.827108 s | 0.124828 s |

Eight workers are the efficient point on this eight-physical-core host. Ten
workers regress wall by 11.0 ms while adding 18.4% CPU. The 0.113811 s result
includes anchor/cut planning, both captures, synchronization, duplicate checks,
vocab/inverse joins, and merge-rank normalization. It covers the two sections
which are 99.8–100% of tokenizer fixtures by volume; it is not a ready
`IrTokenizer` timing and does not include source file I/O.

The prototype uses Qwen's ordinary schema-key spelling to measure the fast-path
ceiling. Production may not trust that spelling or these offsets. Route anchors
are compiler-derived speculation from the lower grammar plus upper schema;
fragments and the coordinator shell must certify the exact composed language.
An absent, escaped, reordered, ambiguous, or false anchor declines before work
submission to the same sequential direct product. No JSON key or tokenizer
name may appear in generic parsing code.

`proto/schema_shell_cost.py` checks how that pre-submission decline can remain
cheap. It replaces only the two proposed interiors with typed empty witnesses
and validates the prefix, interstitial syntax, suffix, and exact nested routes.
The Qwen shell is 6,098 characters; proposal, construction, complete stdlib
syntax parse, and route validation cost **0.001864 s** median. Nested false
anchors, reordered unsupported proposals, and escaped-key proposals all
decline. This is a shell representation/control result, not a future Lexic
timing: production must validate typed holes at the exact composed states with
the same target program.

## Final tokenizer index shape

The earlier best route through existing `IrMap` construction remained outside
the target: staged construction measured about 0.534 s, and isolating canonical
repr-key ordering measured about 0.408 s. Canonical `IrMap` cannot be the final
tokenizer storage requirement and still fit a 0.166 s product.

`proto/tokenizer_index_shape.py` uses a tokenizer-native `IrTokenIndex` over
the real `IrStr`/`IrChr` vocab leaves and `IrTuple`/`IrInt` rank leaves. It is
an immutable `IrMapping` with deterministic builder/source insertion order,
not the general action map's repr-sorted order. Its lookup, equality, and view
operations are the existing dict-backed `IrMapping` implementation.

Freezing all three validated Qwen tables into final indexes costs **0.008423 s**
median. The prototype copies only the dict indexes in C and reuses every key
and value; the parse builders can then be released. This shape changes the
`IrTokenizer` field contract and payload codec deliberately—pre-0.1 has no
legacy representation requirement. The existing `IrMap` canonical invariant
remains untouched for action maps and other IR users.

## Non-JSON witnesses

The pattern-ownership result was repeated over Qwen-scale synthetic documents
using the real GBNF, ABNF, and EBNF lexical closures. Each arm recognized the
same 1,343,842 events:

| grammar | shared pattern | private patterns | wall reduction |
|---|---:|---:|---:|
| GBNF | 0.303106 s | 0.199430 s | 34.2% |
| ABNF | 0.299088 s | 0.218792 s | 26.9% |
| EBNF | 0.304776 s | 0.204575 s | 32.9% |

The mechanism is therefore grammar-derived rather than JSON-specific. These
dense per-token loops also remain materially slower than programs which consume
one complete upper-schema entry per transition. Product compilation should
specialize regular upper regions, not lower every grammar to a generic lexical
event stream.

## Design consequences

1. The target fast path cannot run complete generic region discovery and then
   capture the same syntax. Composed upper/lower route anchors propose bounded
   fragment entry states directly; a small composed shell certifies the
   proposal before submission, and compiled fragments certify the omitted
   interiors.
2. Every hot compiled recognizer used concurrently is worker-owned. Equal
   source passed repeatedly through `re.compile` is not a replica because the
   regex cache returns the same mortal object.
3. Fragment programs consume the largest compiler-proved regular unit available
   from the composed grammar. Per-character or per-token event sidecars are not
   the universal ABI.
4. The tokenizer joins vocab and merges in document order once. Merge workers
   may use local ranks; the coordinator normalizes them while constructing the
   one final rank map.
5. `IrTokenizer` owns tokenizer-native insertion-ordered indexes. It does not
   force its runtime lookup tables through general `IrMap` repr sorting.
6. Route-anchor failure is a pre-submission decline to the same direct product,
   never a partial target attempt followed by model-plus-fold.

## Remaining proof

The 0.113811 s result, 0.001864 s shell control, and 0.008423 s final-index
freeze leave about 42 ms inside the 105x reference for smaller fields, deferred
verdicts, root checks, and the tokenizer record/pipeline tail. That is
promising, not acceptance. Source work
must measure the ready tokenizer end to end, exercise arbitrary object order
and escape-equivalent keys, prove false-anchor decline and syntax-first failure,
and preserve base generated-model and token parsing performance exactly.

Pyright reports zero errors, warnings, and information messages over every new
prototype. No source file, test, committed documentation, or production timing
path was changed.
