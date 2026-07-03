# Error Vocabulary

**When to load:** writing a parser, emitter, or atom dispatch table; choosing which exception class to raise; implementing an engine/reducer error boundary.

See also: [[architecture]]

Source: `exceptions.py`. No bare `raise ValueError` or `raise Exception` for library-level failures.

## Exception classes

| Class | Raised by | Message format |
|---|---|---|
| `UnsupportedConstructError` | The Earley engine (no parse / ambiguous parse — `lexic.parsing`'s `parse`/`parse_reduced`), reduction bodies (unrecognised construct), `compile_grammar`'s boundary checks (missing/wrong-shaped `Reducer`, non-`IrAst` reduction result, unknown start rule), atom dispatch tables (unknown atom type) | Rule-first: "rule `foo`: unsupported construct `…`" |
| `GrammarAuthoringError` | `@grammar_rule` decorator, `ModelEmitter` discriminator analysis | Fragment-quoted: "field `foo.bar`: expected `…`, got `…`" |
| `FieldValidationError` | Pydantic constraint failures (Slice C) | Field-path-first |

All inherit from `LexicError(Exception)`.

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

## Grammar-parse boundary (`compile_grammar`, `compile.py`)

There is no Lark and no `MetaGrammarParser` anymore — `compile_grammar` runs the flavour's own self-grammar through the Earley engine (`parse_reduced`). The engine itself raises `UnsupportedConstructError` when text doesn't parse or parses ambiguously (see `lexic.parsing`'s module docstring). `compile_grammar` adds its own explicit boundary checks, each an `UnsupportedConstructError`: the flavour's `reducer` must be an actual `Reducer` instance, the reduction must produce an `IrAst`, and a resolved `start` rule must actually be defined in the grammar.

## Stubs (wired in future slices)

- `GrammarAuthoringError` — stub in Slice B; wired in Slice C (discriminator ambiguity) and Slice D (`@grammar_rule` misuse).
- `FieldValidationError` — stub in Slice B; wired in Slice C when `Annotated[str, StringConstraints(...)]` emission lands.
