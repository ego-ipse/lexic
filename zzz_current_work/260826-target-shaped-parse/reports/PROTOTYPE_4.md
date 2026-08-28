# Prototype 4 — composable tokenizer carrier and scenario boundaries

**Phase:** post-`REVIEW_6` feasibility correction. Source remains unchanged.

## Question

`REVIEW_6` correctly found that the earlier component account did not compose:
the routed capture ended in native Python values, while the index-freeze timing
began with pre-created IR leaves. It also treated the standing 105x objective as
a source-start threshold. The user clarified the governing rule: 105x remains
an optimization goal and may not apply to every reduction; acceptance compares
the current and projected cost of each codomain separately.

This iteration therefore measures one resident-text route from high-volume
capture through final tokenizer indexes and an actual `IrTokenizer` record. It
also isolates the path-only source-read boundary. It does not claim that the
small-field/schema program or a ready tokenizer is complete.

## Environment and protocol

The witness remains Qwen3, 11,422,654 bytes / 10,635,788 decoded characters,
on Python 3.14.3 free-threading and the Ryzen 7 5700X3D host. Every MT process
ran alone. Eight retained threads were forced through a barrier before timing;
four workers captured vocab while four captured merges. Programs and the
resident source string were prepared outside the capture interval.

All executable prototypes pass the repository Pyright environment without a
suppression. No instrumentation or implementation touched `src`.

## Rejected final-leaf carrier

`proto/composed_ir_regions.py` constructs `IrStr`, `IrChr`, `IrTuple`, and
`IrInt` per retained entry inside the direct worker/join path, freezes the three
indexes, and constructs the actual tokenizer record. Seven-round medians are:

| phase | wall |
|---|---:|
| direct capture + joins into IR leaves | 0.338074 s |
| index freeze | 0.008822 s |
| record construction | 0.000032 s |
| total | **0.346817 s** |

Aggregate process CPU is 2.114464 core-seconds. This is 2.50x the selected
native-payload carrier below. A tokenizer index is itself the IR value; forcing
every internal lookup key/value to be a separate spine scalar or dyad is not an
IR invariant and is rejected.

## Selected tokenizer index payload

`proto/composed_native_tokenizer.py` instead captures the tokenizer's actual
lookup payloads: `str -> int`, `int -> str`, and `(str, str) -> int`. The three
immutable tokenizer-owned mapping values remain IR nodes, but their private
tables use the primitive values the tokenizer executes.

Canonical order is semantic, not source-object order:

- encode and decode are ordered by token id;
- ranks are ordered by rank;
- a builder already in that order is validated and frozen without sorting;
- a noncanonical public/readback input is sorted once before construction.

The prototype uses separate encode/decode/rank index roles so payload readback
knows which canonical rule applies. Equal values therefore have equal hash and
one physical iteration/repr/payload/notation order. `from_indexes` owns the
cross-index bijection, contiguous-rank, special-membership, pipeline, and root
checks. Public `resolve`/`spell` retain the `IrEncoding` boundary types; internal
tokenization can perform primitive lookups without allocating temporary IR
keys on every lookup.

Seven-round medians are:

| phase | wall |
|---|---:|
| route/cut proposal, native capture, joins, duplicates, rank normalization | 0.121197 s |
| canonical validation + three immutable index freezes | 0.017504 s |
| actual `IrTokenizer` record construction | 0.000032 s |
| measured carrier total | **0.138739 s** |

Aggregate process CPU is 0.713501 core-seconds. Two fresh one-round processes
observed 81,228–83,980 KiB (about 79.3–82.0 MiB) peak-RSS increase while
retaining the completed carrier.
The old reduced-IR fixture is deliberately a noncanonical input to the new
index order; converting and freezing it measured 0.105666 s in one standalone
sample. That is a separate already-reduced-input scenario, not part of direct
parse construction.

Exact native encode/decode/rank contents, id/rank order, tokenizer field
identity, and forward/inverse runtime lookups match the Qwen oracle. The
prototype contains no reduced document, `IrMap`, merge-dyad list, existing
tokenizer, or pre-created IR entry table on its measured route.

## Source-read boundary

`proto/source_read_cost.py` measures only `Path.read_text(encoding="utf-8")`:

| boundary | wall |
|---|---:|
| first read in the fresh process | 0.046713 s |
| seven-round median | 0.019701 s |

The historical observed-stage median was 0.213211 s. The new isolated result
does not erase it; it proves that resident-text and path-inclusive metrics must
be reported separately and that the path row needs its own alternating
baseline/candidate measurement. Source I/O may not be hidden inside a
resident-text multiplier.

## Current versus projected scenarios

The current Qwen path attribution is 17.416359 s including its historical
0.213211 s source read, or 17.203148 s for setup + parse + fold + tokenizer
build with the text resident. The current tokenizer-build tail alone is
0.961806 s.

The selected 0.138739 s result covers the dominant sections through immutable
final indexes and record construction, not small fields, a production
lower×upper shell, pipeline construction, target bind/setup, or root
validation. Consequently:

| scenario | current reference | projected evidence | acceptance meaning |
|---|---:|---:|---|
| resident tokenizer | 17.203148 s | 0.138739 s partial carrier | complete result must be measured; <1 s is concrete, 105x remains pursued |
| path tokenizer | 17.416359 s | carrier plus separately measured read | report cold and warm path rows; never substitute the resident row |
| already-reduced tokenizer build | 0.961806 s | 0.105666 s noncanonical index conversion sample | measure the complete converged constructor separately |
| Python recursive value | current full IR route; `json.loads` is 0.084940 s | product implementation unmeasured | <0.100 s goal and current-route multiplier are both reported |
| default IR | model + `ReduceFold` | direct product unmeasured | exact differential first; no parse regression |
| selection / extent | current parse/extract route | prior extent ceiling only | compare demanded result to the same semantic scenario |

At the measured carrier cost, a complete resident tokenizer below 1.000 s may
spend another 0.861261 s and would improve the current resident scenario by
more than 17x. Reaching 105x against the resident 17.203148 s reference means a
complete result near 0.163840 s, leaving about 25 ms beyond this carrier. That
is an optimization objective, not permission to omit work or reject other
codomains which achieve their own material gains.

## Gates retained

The 0.001864 s stdlib shell remains only a representation/control budget. It
does not prove production typed-hole certification. Source implementation must
still demonstrate the same lower×upper product over prefix, interstitial
syntax, suffix, exact hole states, fragment entry/exit, suspension/resumption,
ordered verdicts, and one root finalization.

Likewise, JSON key spellings in the measurement harness are witness locators,
not generic parser policy. Route compilation must produce equivalent products
for the native JSON and GBNF/ABNF/EBNF formulations without naming grammar
rules, and actual worker bindings must prove physically distinct hot recognizer
identities. These are phase exits. They are not replaced by the performance
prototype and do not authorize model-plus-fold fallback.
