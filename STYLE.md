# Lexic — Python style guide

This is the coding standard for `src/lexic/` and `tests/`. It is deliberately
opinionated and short. If a rule below conflicts with something in
`CLAUDE.md`, `CLAUDE.md` wins for its specific domain; this guide covers the
default for everything else.

The organising principle: **write code that can be deleted and rewritten in
isolation.** If a function can't be explained without referring to three other
modules, it's doing too much.

---

## 1. SOLID, concretely

These map to specific smells in this codebase. Don't invoke SOLID as a slogan;
check the smell.

### Single Responsibility

A function has one job if you can name it with one verb and no "and". If the
name is `_build_instance_and_filter_tokens_and_handle_lists`, split it.

**Red flag:** a function that takes a `spec` *and* a list of Lark children *and*
a class *and* builds Pydantic kwargs *and* handles type-hint inspection. That
is five responsibilities.

**Rule:** each function/class owns one axis of change. If two unrelated bugs
could both land in the same function, it's two functions.

### Open/Closed

Adding a new atom type, a new grammar shape, or a new emission target should
not require editing an existing `if isinstance(...)` cascade. Prefer
dispatch tables or polymorphism.

**Red flag:**

```python
if isinstance(atom, CharClassAtom): ...
elif isinstance(atom, QuantifiedLiteralAtom): ...
elif isinstance(atom, InlineRegexAtom): ...
# adding a new atom means finding every cascade in the repo
```

**Rule:** if you find yourself about to add a branch to a cascade that exists
in more than one file, stop and introduce a dispatch table or a method on
the atom. Don't propagate the cascade.

### Liskov

If `Spec.kind == "alternation"` means a spec has no fields, and
`Spec.kind == "sequence"` means it does, *every* consumer now has to check
`kind` before touching `field_map`. That's a Liskov violation hiding behind a
string tag.

**Rule:** if two variants of a type have structurally different contracts,
they should be two types, not one type with a `kind` discriminator.

### Interface Segregation

A caller should not have to import types it doesn't use. `parse.py` currently
imports `codegen.ir_builder`, `codegen.lark_builder`, `codegen.parser`, and
`codegen` itself. That's the full build-time surface for a runtime function.
Make the runtime depend on a narrower contract (`CompiledGrammar`) and let
the build-time surface hide behind it.

**Rule:** a module imports what it needs, not what the author happens to have
open in their editor.

### Dependency Inversion

`base.py` must not import from `codegen/`. `generated/*.py` must not import
from `codegen/`. Runtime code depends on IR (pure data); build-time code
produces runtime code. Arrows go one way.

**Rule:** imports should flow from concrete → abstract, never the reverse. If
you need a lazy `from lexic.codegen.X import Y` inside a function, the
architecture is telling you something.

---

## 2. Function size and shape

Not hard limits — signals. If you hit two of them in one function, split it.

- **> 40 lines.** Not wrong by itself, but worth a second look.
- **> 4 levels of indentation.** Almost always means an extracted helper is
  hiding.
- **More than one `for` nested inside another with an `if` inside each.**
  Flatten with early returns or a comprehension. If you can't, the inner
  body is a named function.
- **Multiple `isinstance` branches with different return shapes.** Replace
  with a dispatch dict.
- **A parameter that's consulted in one branch and ignored in another.** Two
  functions pretending to be one.

### Prefer early returns

**Don't:**

```python
def decode(atom):
    if atom is not None:
        if atom.value:
            if atom.value.startswith('"'):
                return atom.value[1:-1]
            else:
                return atom.value
        else:
            return ""
    else:
        return None
```

**Do:**

```python
def decode(atom):
    if atom is None:
        return None
    if not atom.value:
        return ""
    if atom.value.startswith('"'):
        return atom.value[1:-1]
    return atom.value
```

Guard clauses first, happy path last, no `else` branches that sit at the end
of the function.

### Extract named conditions

**Don't:**

```python
if isinstance(atom, CharClassAtom) and atom.min == 0 and atom.max == 1:
    ...
```

**Do:**

```python
def _is_optional_charclass(atom) -> bool:
    return isinstance(atom, CharClassAtom) and atom.min == 0 and atom.max == 1

if _is_optional_charclass(atom):
    ...
```

The name is the comment.

---

## 3. Fix the root cause, not the symptom

This is the single most important rule in this codebase. The review has a
running theme of "the test passes because of an accidental interaction three
modules away". That is the failure mode this rule exists to prevent.

### Never silence a problem you don't understand

- **No bare `except:`** and no `except Exception: pass`. If you don't know
  what was going to be raised, you don't know what you just hid.
- **No `# type: ignore`** without a one-line comment explaining what the
  actual type is and why Pyright is wrong. Same for `# noqa`.
- **No "try the thing, fall back to the other thing" code** unless the two
  paths are both valid outcomes. Exceptions are not conditionals.
- **No sentinel defaults that paper over a missing value.** If a field can
  legitimately be absent, model it as `Optional[X]`. If it can't, let the
  code raise.

### Fix the structure, not the call site

If three files contain a `pattern.startswith("(") and "|" in p` sniff to
decide what a `CharClassAtom` really means, the fix is not a fourth sniff. It
is to split the type so the sniff is unnecessary. (This is what V2 → V3
actually did — it's the template.)

If `_build_instance` needs one more special case to handle a new grammar
shape, the fix is probably not the special case. It is probably a dispatch
table.

### Don't patch around the thing you're trying to test

A test that passes because of the test harness's quirks is a test that will
pass on broken code. If you add a `# noqa` to a test, the test is telling you
something — listen.

---

## 4. Avoid speculative abstractions

The inverse of rule 3. Don't design for hypothetical future requirements.

- **No abstract base classes with one concrete implementation.**
- **No `**kwargs` forwarded for "flexibility".** Name your parameters.
- **No `Optional[X] = None` parameters that nothing ever passes.** Remove it;
  you can add it back the day a caller actually needs it.
- **No generic "processor" / "handler" / "manager" classes.** A name that
  doesn't tell you what the class does is a name that's been chosen to avoid
  a decision.
- **No feature flags or `if version_major >= 2` branches** unless the two
  versions literally coexist in production right now.

Three similar lines is better than a premature abstraction. The cost of
inlined duplication is bounded; the cost of the wrong abstraction compounds.

---

## 5. Data shape

### Prefer `@dataclass(frozen=True)` for value types

Atoms, RuleSpecs, annotations, configurations. Frozen dataclasses are free
validation, free `__eq__`, free `__repr__`, and they document intent.

### Prefer concrete types over `dict[str, Any]`

A dict keyed on strings is an anonymous type. Every consumer has to know
which keys exist and what they mean, without the type system helping. If the
dict has a known schema, make it a dataclass.

### Don't use mutable defaults

```python
def f(items: list = []):   # NO
def f(items: list[int] | None = None):  # YES — then `items = items or []`
```

### Don't return tuples of three or more things

```python
def compile(path) -> tuple[dict, dict, str]:   # NO
```

Name them. Return a dataclass.

### Type everything at module boundaries

Every public function has full type annotations. Internal helpers may skip
them if the types are obvious from the body, but prefer annotating.

---

## 6. Errors and boundaries

**Trust internal callers.** Lexic's own code does not need to validate that a
`RuleSpec` passed into an emitter is well-formed. The IR builder is
responsible for producing well-formed specs; if it emits garbage, fix the
builder.

**Validate at system boundaries.** `parse(text, grammar_path)` takes
user-controlled input and checks it. Everything downstream of that gets to
assume the input is valid.

**Raise specific exceptions.** `ValueError("bad grammar: expected ruleref at
line 3")` beats `Exception("oops")` every time.

**Don't catch what you can't handle.** If a function can't meaningfully
recover from `FileNotFoundError`, don't catch it. Let it propagate.

---

## 7. Comments

Default to none. When you do write one:

- **WHY, not WHAT.** The code is the what. If the reader needs to know
  "because llama.cpp's sampler doesn't support X", say that.
- **Tie non-obvious invariants to the line that would be wrong without them.**
  "This loop must run after `_assign_field_names` because it reads
  `field_map`" is useful. "This is a for loop" is not.
- **Don't reference the current task, the commit that added the line, or
  who asked for it.** That belongs in `git log`, not in the file.
- **Don't re-explain a function in a docstring if the name and signature
  already do.** One-liner docstrings are fine and preferred.
- **No block comments describing "the approach".** If you need a design
  discussion, put it in the PR or in a doc, not in the code.

---

## 8. Naming

- **Use full words.** `spec`, `atom`, `rule` are fine because they're domain
  terms. `sp`, `at`, `r` are not.
- **Private is `_leading_underscore`.** Module-private is enough; don't
  double-underscore unless you actually need name-mangling.
- **Booleans read as predicates.** `is_optional`, `has_quantifier`,
  `should_regenerate`. Not `optional` (ambiguous), not `flag` (meaningless).
- **Verbs for functions, nouns for data.** `parse()`, not `parser()` (unless
  `parser` is a concrete instance).
- **Don't embed types in names.** `atoms_list` adds nothing over `atoms`.
  Pyright already knows it's a list.

---

## 9. Imports

- **Absolute imports only** (`from lexic.ir import RuleSpec`), never relative
  (`from ..ir import RuleSpec`).
- **Sort by `ruff`'s isort convention** — stdlib, third-party, first-party,
  each block alphabetised. Don't hand-order.
- **No `from module import *`.** Ever.
- **No lazy imports** (`def f(): from x import y`) unless you are breaking an
  actual cycle and have no other option. Lazy imports are a signal that
  the module layering is wrong; prefer fixing the layering.

---

## 10. Testing

- **One assertion per test** where practical. If a test fails, the failure
  message should tell you exactly what broke.
- **Name tests by what they assert.** `test_roundtrip_preserves_whitespace`,
  not `test_1` or `test_arithmetic`.
- **Unit tests live next to their module** in the parallel `tests/unit/`
  tree. Integration tests span modules. Property tests go in
  `tests/property/`.
- **Don't mock what you own.** Mocking `RuleSpec` in a transformer test hides
  integration bugs. Use real IR produced from a small hand-written grammar.
- **Property tests generate inputs; regression tests pin specific failing
  cases.** When a hypothesis seed catches a bug, convert it to a named
  regression test before fixing.

---

## 11. Performance

- **Don't optimise speculatively.** If a function isn't in a hot loop, don't
  cache it. If it is, measure first.
- **Don't pre-materialise what you can generate.** If a function returns a
  list that's always consumed once, a generator is fine.
- **Don't import heavy modules at top level** if only one function needs
  them. (This is the one exception to rule 9's "no lazy imports" — measured
  startup cost, not cycle avoidance.)

The R005 performance concern (`parse()` regenerating modules every call) is
the real performance ceiling today; everything else is far below the noise
floor.

---

## 12. Generated code

- **Never edit files in `generated/` by hand.** They are write-once
  artifacts. If they are wrong, fix the template in
  `src/lexic/codegen/model_emitter.py`.
- **If `ruff` flags a generated file, fix the emitter, not the file.**
- **Keep generated files free of hand-written markers.** No "DO NOT EDIT"
  banner is needed if the first line is an auto-generated docstring pointing
  at the source grammar.

---

## 13. Tooling

Always via `uv run`:

```bash
uv run pytest tests/ -v
uv run ruff check src/ tests/
uv run ruff format src/ tests/
uv run pyright src/
```

Pre-commit hooks exist (`.pre-commit-config.yaml`, `tools/run_checks.sh`);
don't bypass with `--no-verify`. If a hook fails, the hook is doing its job.

---

## Quick self-review checklist

Before committing, re-read the diff asking:

- [ ] Does every new function do one thing I can name without "and"?
- [ ] Is any function over 40 lines or nested deeper than 4 levels? Can I
      split it?
- [ ] Am I silencing any error I don't fully understand?
- [ ] Am I adding an `isinstance` branch to a cascade? Should this be a
      dispatch table?
- [ ] Have I added an abstraction I don't have two concrete uses for?
- [ ] Does every public function have full type annotations?
- [ ] Do my comments explain WHY, not WHAT?
- [ ] Have I edited `generated/*.py` instead of the emitter?
- [ ] Did any test pass because of harness accident rather than the code
      under test?

If any answer is uncertain, the change isn't ready.
