# Prototype 9 — REVIEW_9 corrections and planning gates

**Phase:** fold `REVIEW_9.md` into the implementation packet. Production source
is unchanged by this pass. The executable work remains under `proto/`.

## 1 — possessive lowering now declines both nullable hazards

`regular_region_proof.py` adds the two missing sufficient conditions:

- a nullable arm must be last under ordered atomic alternation; and
- a variable **or nullable** atom whose first set overlaps its continuation
  declines, including a once-required `{1,1}` reference.

`regular_region_lowering.py --mode identity` executes the earlier variable-
boundary witness plus the two REVIEW_9 minimal shapes. The corrected output is:

```text
entries  4000
slice_chars  79207
identity  native == gbnf == abnf == ebnf == json == engine reduce
edges  1/2/3 captures; empty valid; malformed refused; three unsafe shapes declined
derived  JSON vocab + non-JSON catalog
```

This supersedes `PROTOTYPE_7.md` §2's weaker “at most one nullable arm” and
“variable repetition” conditions. It changes no production parser.

## 2 — a route may cross intervening contextual clones

`route_continuation.py` now represents a descendant consumer path and one
route-specialized clone chain per finite route. The sibling form is a one-link
chain. The non-sibling witness models:

```text
member ::= string tail
tail ::= separator value
```

The PDA-shaped route selects the contextual `tail` clone, whose compiled chain
selects the contextual `value` clone. The Earley-shaped route advances through
two route-specific successor codes. Neither mechanism adds a grammar arm or
requires a descendant to consult an ancestor frame dynamically.

```text
PASS: decoded/raw routes cross PDA/Earley descendants; grammar_arm_additions=0
```

## 3 — frequent completion contains no target decoder table

`product_types.py` no longer stores target scalar decoders, validators, or
record constructors in `OperandTables`. Scalar decode is an engine-owned closed
operation selected by a plain integer. The remaining typed callables are
restricted to collection finish, root finalization, and meaning comparison.
`reducer_free_surface.py` now says explicitly that it proves only public inert
declaration data; `product_types.py` owns the separate private `_bind` protocol
and one homogeneous binding registry per declaration kind.

This is a boundary proof, not a claim that the production opcode vocabulary is
complete. §3 still inventories and implements every closed operation required
by the shipped reducers.

## 4 — settled REVIEW_9 decisions

- An island with a second target meaning does not settle ambiguity at the island
  span and does not discard the predictive parse. It carries a cold alternate-
  meaning seed through the enclosing product continuation to the requested
  root. Complete-document Earley is reserved for supplying derivations to an
  invoked `resolve=`, not for recomputing equality unconditionally.
- The `<1.000 s` ready-tokenizer gate applies to the public engaged
  `cores=AUTO` row. Sequential route-anchor decline is reported with
  CPU-per-byte and attribution but is not the same gate.
- `parsing/product/regular.py` reuses `parsing/pda/core/charsets.py` and
  `scanner.py`; it does not create a second first-set or possessive lowering.
- §4 runs `tools/check_generated.py` and accounts for every named foldkit symbol.
- §13 retains the three fresh-input property generators and replaces the
  deleted oracle with surviving one-path invariants; fixed §5 goldens become
  deterministic regression cases.
- The ambiguity dependency index is document-sized, built only for a real arm
  choice, and receives its own §12 RSS row.

## 5 — planning and decision work still open

`TODO.md` marks these as hard gates:

- **PLANNING REQUIRED before §8:** prototype and name the island seed,
  dependency/continuation trace, isolated replay state, resolver handoff, and
  dropping-parent witness without unconditional whole-document reparsing.
- **DECISION REQUIRED at §8:** each map/IR/tokenizer product must earn an exact
  persistent meaning or retain the exact isolated whole-result fallback.
- **DECISION REQUIRED at §6:** keep or omit arbitrary custom-class construction
  after its immutable-binding proof.
- **PLANNING REQUIRED before §12:** choose the ambiguous RSS witness and frozen
  baseline/candidate command before the measurement window.
- **USER DECISION REQUIRED:** no bugfix-related parsing regression is accepted
  without isolated attribution and the user's explicit approval.

No other REVIEW_9 finding remains implicit implementer discretion.

## 6 — static and executable checks

The corrected prototypes were formatted and checked with repository tools:

```text
uv run ruff format <five corrected prototypes>
uv run ruff check <five corrected prototypes>
uv run pyright <five corrected prototypes>
uv run python proto/product_types.py
uv run python proto/reducer_free_surface.py
uv run python proto/route_continuation.py
uv run python proto/regular_region_lowering.py --mode identity
```

The final results are recorded in `LEDGER.md`; all commands use external
instrumentation only and do not touch `src`.
