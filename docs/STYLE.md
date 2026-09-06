# Lexic — Python style guide

The coding standard for `src/lexic/` and `tests/`. Deliberately opinionated and
short. Where this conflicts with `CLAUDE.md`, `CLAUDE.md` wins for its domain.

The organising principle: **write code that can be deleted and rewritten in
isolation.** If a function can't be explained without referring to three other
modules, it's doing too much.

Every example below is live code in this repo. If one stops being true, fix
the example — a style guide that teaches against a codebase that no longer
exists is worse than none.

---

## 1. The type system is a design tool, not paperwork

This is the rule with the highest yield here, and the one most often broken.

**A return type that lost its shape is a design bug.** When a function's honest
return is a union its callers can't name, the signature decays to `object` and
every caller casts it back. The cast is not the problem; it's the receipt.

Three symptoms, one disease:

- **`-> object` / `-> Any`.** Never ship one. If you can't name the return,
  the function is doing two things.
- **A `cast(...)` at a call site.** Ask what the callee should have declared.
  Nine times in ten the fix is upstream: make the callee generic in its
  product, or split it.
- **An `isinstance` that decides behaviour** (as opposed to validating input at
  a boundary). It usually means one type is standing in for two.

The worked example: `parse_pda(tables, text, fold) -> object` branched on
`tables.reduce`, ignored `fold` on one branch, and returned a different type
from each. Splitting it into `pda_reduce(tables, text) -> IrSelf` and
`pda_model[M](tables, text, fold) -> M` deleted thirteen casts across the repo.

**Make the container generic before you narrow at the call site.**
`PdaKernel[M]`, `ModelFold[M]`, `TokenMaskCursor[K: ResumableKernel]` all exist
so a caller's type survives the call. When a subclass needs a narrower field
than its base declares, parameterise the base — don't add a property that
`assert isinstance`s it back.

**But don't over-declare either.** `IrMap[IrStr, IrSelf]` is *worse* than bare
`IrMap`: it conveys nothing (every value is an `IrSelf`) while blocking every
read, so callers start writing narrowing asserts to get their work done. Bare
`IrMap` reads as unknown and flows. Parameterise when the parameter carries
information; otherwise leave it off.

**Where narrowing IS right:** one `isinstance` at a genuine system boundary,
where the caller has schema knowledge the type system can't. Reading a parsed
JSON document is the honest case:

```python
doc = parse_reduced(JSON_GRAMMAR, text, JSON_REDUCER)
assert isinstance(doc, IrMap)   # parse_reduced returns IrSelf; this is the boundary
model = doc["model"]            # ... and then plain reads flow
```

---

## 2. Name your data

`IrNamedTuple` **is** a tuple. Naming a record costs nothing at runtime, so
there is no performance excuse for an anonymous one.

**Don't return tuples of three or more things.** `-> tuple[dict, dict, str]` is
an anonymous type every caller has to decode.

**Don't put a known schema in a keyed map.** `EscapeCodec` once held one
`tables: IrMap` bag plus five properties that dug the tables back out, each
re-narrowing with `isinstance` and silently falling back to empty on a miss. The
schema was fixed at five. Making them five fields deleted the properties, the
fallbacks, the key constants and the constructor — and not one algorithm
changed, which is the tell that nothing ever wanted the bag.

**A silent default is worse than a raise.** `return table if isinstance(table,
IrMap) else IrMap()` turns a misspelled table into "escaping quietly disabled".

Plain tuples and bare type aliases in `parsing/` hot paths are a deliberate
exception — see §7.

---

## 3. One way to do each thing

**No sugar beside the real channel, guarded by a runtime raise.** If you find
yourself writing *"pass X or Y, not both"*, you have shipped two doors into one
field and substituted an error message for a decision. Pick the channel.

**No parameter that one branch consults and another ignores.** That's two
functions wearing one signature.

**Don't contort code to satisfy a linter.** Reordering a public `__all__` so
pylint stops seeing duplicate lines is a suppression with extra steps. Fix the
duplication or take the finding to the user — never edit `pyproject.toml`.

---

## 4. SOLID, concretely

Check the smell, don't invoke the slogan.

**Single responsibility.** One job if you can name it with one verb and no
"and".

**Open/closed.** Adding an atom type, grammar shape, or emission target must not
mean editing an `isinstance` cascade. Use an open `IrDispatch`/`IrTypeMap` with
a raising `UnsupportedConstructError` default — never a silent fallback. If
you're about to add a branch to a cascade that exists in more than one file,
stop and introduce a dispatch table or a method on the type.

**Liskov.** If two variants have structurally different contracts, they are two
types, not one type with a discriminator. `TokenMaskCursor` branched
token-vs-char grammar in four places via *two* different discriminators
(`self._trie is not None` and `isinstance(kern, TokenKernel)`) that had to be
kept in sync by hand; it is now an ABC plus `TokenTermCursor` /
`CharTrieCursor`. The engine already modelled this correctly one layer down
(`Kernel → ResumableKernel → TokenKernel`).

**Interface segregation.** A module imports what it needs, not what the author
had open.

**Dependency inversion.** Arrows go one way; see `CLAUDE.md` §Layering, which a
test enforces by static grep.

---

## 5. Function size and shape

Signals, not limits. Two in one function means split it.

- More than ~40 lines.
- **More than 4 levels of indentation** — an extracted helper is hiding.
- Nested `for` with an `if` in each.
- `isinstance` branches with different return shapes → dispatch table.

**Flat helpers, not closures.** A nested `def` inside a function is a helper
that wants to be module-level. (One day of work was reset over this.)

**Guard clauses first, happy path last.** No `else` at the end of a function.

**Extract named conditions** — the name is the comment.

---

## 6. Errors and boundaries

**No bare `ValueError`/`Exception`** for library failures; use the
`exceptions.py` hierarchy (`UnsupportedConstructError`, `FieldValidationError`).

**Trust internal callers, validate at system boundaries.** Lexic's own code
doesn't re-check well-formed IR it produced.

**Never silence what you don't understand.** No bare `except:`, no
`except Exception: pass`, no exceptions-as-conditionals.

**No `# type: ignore`, `# noqa`, or `# pylint: disable` without explicit
permission.** Fix the root cause. This is absolute.

---

## 7. Performance

**`ir/` is strict. `parsing/` and `compile/` hot paths are deliberately not.**
Plain `None`, bare tuple aliases (`_WMeta`, `TrieNode`), positional tuple
access and mutable cursors are correct choices in the engine and should not be
"cleaned up" into records. Strictness is `ir/`'s contract, not the engine's.
The PDA frame is the exception, and the reason is the test: its lanes have
different types, so a flat list erased all nine and made one of them
unnameable. A record earns its place where positional access hides a type,
not merely where a record would look tidier.

**Time CPU, not the wall.** `time.process_time()` ignores the time the process
spent descheduled, so a loaded machine stops mattering. The same comparison that
swung 30 points between passes on wall-clock reads to a fraction of a percent on
CPU time.

**Pick the instrument by whether the change can be TOGGLED.** This is the one
that gets chosen wrong, and it is wrong in both directions:

- *Toggleable* — a call inlined, a branch reordered, one method's body. Swap the
  two versions **in one process**, alternating, and take the min. Cross-process
  cannot resolve it: two byte-identical trees measure ±2.7% apart, which is
  wider than any lever worth landing.
- *Structural* — a data representation, a protocol, anything present on every
  path. Run **two trees, cross-process**, alternating, and state the control
  floor you measured by running two byte-identical trees through the same
  harness. An in-process swap is blind here: if both arms carry the new
  machinery, the swap cannot see the machinery's own cost. One such swap read a
  9–21% regression as a 1–7% win, twice, before a cross-process run against the
  real baseline found it.

**Carry a control row.** A row the change cannot reach reads the noise band
directly, and it is what says whether a −1.4% is a result or the floor.

**Count the price, not just the population.** "87–100% of slots hold one model"
says how often a saving applies and nothing about what it costs; that lever
added 5.4 calls per character to remove 0.9. Convert both sides to the same
unit before predicting: a removed Python call is worth ~40–50 ns, one demoted to
a C-level partial ~11, and rows run 1800–3000 ns/char — so a population under
~1 call/char cannot reach 1% however often it hits.

For a change you believe is type-only, compare opcode streams
(`dis.get_instructions`) rather than timing anything — it's decisive and takes
seconds.

**Don't optimise speculatively.** Not in a hot loop? Don't cache it.

---

## 8. Comments and docstrings

Default to few. When you write one: **why, not what.**

- One-liner docstrings are preferred. Sphinx `:param:`/`:returns:`/`:raises:`
  for public surfaces.
- Tie a non-obvious invariant to the line that would be wrong without it.
- **No internal history.** No effort names, dated decisions, task numbers, or
  references to gitignored directories. Present-tense architecture only.
- Don't re-explain what the name and signature already say.

---

## 9. Naming

Full domain words (`spec`, `atom`, `rule`), not abbreviations. Private is one
leading underscore. Booleans read as predicates. Verbs for functions, nouns for
data. Don't embed types in names.

**Check for collisions before naming a new symbol.** `reduce_pda` was
unavailable as a function name: it already named a test helper *and* a module.
`pda_reduce`/`pda_model` mirrored the existing `earley_reduce`/`earley_model`
pair instead.

---

## 10. Imports

Absolute only. Sorted by ruff/isort — never hand-ordered. No `import *`. No
lazy imports except to break a measured startup cost; a lazy import to dodge a
cycle means the layering is wrong.

No `import x as x` re-export aliasing. No string-quoted annotations unless the
name genuinely isn't defined yet (a self-referential base like
`Spec(IrMap[IrStr, "Keep | Spec"])` is the legitimate case; PEP 695 `type`
aliases are lazy and never need quoting).

---

## 11. Testing

- Name tests by what they assert.
- Don't mock what you own — use real IR from a small grammar.
- Property tests generate; regression tests pin a specific failure.
- **Port tests, never delete them.** Fix construction syntax and keep the
  assertions. The one exception is a test whose exact target symbol is being
  deleted.
- Re-pinning a changed contract is normal; do it deliberately and say so.

**The test tree mirrors the source tree exactly.** `src/lexic/foo/bar.py` →
`tests/unit/lexic/foo/test_bar.py`. A source file created, moved, renamed or
deleted gets the same treatment. `__init__.py` modules use
`test_init_<package>.py`.

---

## 12. Tooling

Always `uv run`. `tools/auto_fix.sh` before hand-editing for lint. Work is done
when `tools/run_checks.sh` exits 0 — not before. Don't bypass hooks.
