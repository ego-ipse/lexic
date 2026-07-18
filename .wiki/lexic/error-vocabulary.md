# Error Vocabulary

**When to load:** writing a parser, emitter, or atom dispatch table; choosing which exception class to raise; implementing an engine/reducer error boundary.

See also: [[architecture]]

Source: `exceptions.py`. No bare `raise ValueError` or `raise Exception` for library-level failures.

## Exception classes

| Class | Raised by | Message format |
|---|---|---|
| `UnsupportedConstructError` | The Earley engine (no parse / ambiguous parse — `lexic.parsing`'s `parse`/`parse_reduced`), reduction bodies (unrecognised construct), `canonical_grammar`'s boundary checks (missing/wrong-shaped `Reducer`, non-`IrAst` reduction result, unknown start rule), atom dispatch tables (unknown atom type), the codegen passes (arm-name collision — `codegen/passes.py`), the instance fold (unknown kind/mode, kid-count mismatch — `parsing/fold.py`) | Rule-first: "rule `foo`: unsupported construct `…`" |
| `FieldValidationError` | IR-intrinsic per-field checked construction in `GrammarModel.__new__` (charclass membership + bounds, `Literal` membership, model/models `isinstance`, required presence); trusted parse paths (`_from_parts`/`fast_construct`) bypass it | Field-path-first |

All inherit from `LexicError(Exception)`.

`GrammarAuthoringError` was deleted 2026-07-18 (260718-generated-files Task 0): a dead public stub — every planned raiser went with the pydantic-era design, and nothing ever raised it.

## Dispatch table contract

Every dispatch table that handles atom types **must** have an explicit default that raises:

```python
HANDLER: dict[type[Atom], Handler] = {
    LiteralAtom: ...,
    RuleRefAtom: ...,
    # ...
}

def dispatch(atom: Atom) -> Result:
    handler = HANDLER.get(type(atom))
    if handler is None:
        raise UnsupportedConstructError(
            f"No handler registered for atom type {type(atom).__name__}"
        )
    return handler(atom)
```

A silent `pass` or `None` return is never acceptable. This is how unexpected atom types are caught early with actionable messages rather than silent wrong output.

## Grammar-parse boundary (`canonical_grammar`, `compile.py`)

There is no Lark and no `MetaGrammarParser` anymore — `parse_grammar` runs the flavour's own self-grammar through the Earley engine (`parse_reduced`). The engine itself raises `UnsupportedConstructError` when text doesn't parse or parses ambiguously (see `lexic.parsing`'s module docstring). `canonical_grammar` (the public parse+canonicalize+directive front half, superseding the retired `compile_grammar`) adds its own explicit boundary checks, each an `UnsupportedConstructError`: the flavour's `reducer` must be an actual `Reducer` instance, the reduction must produce an `IrAst`, and a resolved `start` rule must actually be defined in the (canonicalized) grammar.

