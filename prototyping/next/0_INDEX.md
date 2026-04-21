# Lexic — `prototyping/next/` index

This directory holds the distilled plan for the next implementation arc.
It is a reconciliation of the six documents in `prototyping/curr/`, with
one deliberate override (see `1_NORTH_STAR.md` §Core principle) and
with tokenisation and grammar-flavour translation held out of scope.

## Documents

| # | File | Purpose |
|---|------|---------|
| 0 | this file | Navigation |
| 1 | `1_NORTH_STAR.md` | End-state. Core principle, in-scope list, out-of-scope list, invariants every slice must preserve. |
| 2 | `2_ARCHITECTURE.md` | Target module layout, IR shape, layering rules, extensibility protocols, error vocabulary. |
| 3 | `3_ROADMAP.md` | Five slices (A–E), each with a uniform card: scope, rationale, entry/exit criteria, non-goals, open questions for its brainstorming session. |

## Ordering rule

Higher index overrides earlier in direct contradictions. This applies
within `next/` (as it does within `curr/`); across the two directories
the rule below takes precedence.

## Relationship to `prototyping/curr/`

`curr/` remains authoritative until a slice lands that makes a specific
`curr/` document obsolete, at which point the affected file rotates to
`prototyping/old/`. Until then, `curr/` and `next/` coexist: `curr/` is
the raw source material this arc distils; `next/` is the committed
plan.

## Relationship to `prototyping/old/`

`old/` holds fully superseded thinking (`OPUS_REVIEW.md`,
`OPUS_REVIEW_V2.md`). The pattern is: a document rotates from `curr/`
to `old/` only when a shipped slice makes it factually out-of-date, not
when a newer document in `curr/` or `next/` disagrees with it.

## Out of scope for this arc (with allowances)

- GBNF tokeniser tokens (`<think>`, `<[1000]>`, `!<…>`).
- Grammar-flavour translation (ABNF, EBNF, Lark, PEG adapters).
- Cross-grammar data translation (R006).
- LLM token-level constrained generation (R005 mask engine).

For each of these, `1_NORTH_STAR.md` lists the minimal allowances this
arc ships so the feature can be added later without breaking 1.0
callers.
