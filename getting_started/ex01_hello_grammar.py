"""Hello, grammar.

Define a tiny GBNF grammar inline, compile it, parse a string, and round-trip
the resulting model back to its grammar text. Demonstrates the core invariant:
``parse(text).to_text() == text`` on every valid input.

Run::

    uv run python getting_started/01_hello_grammar.py
"""

from __future__ import annotations

from lexic import compile_text

GRAMMAR = """\
greeting ::= salutation " " name "!"
salutation ::= "Hello" | "Hi" | "Hey"
name ::= [A-Za-z]+
"""


def main() -> None:
    """Compile, parse a sample, print the model, round-trip back to text."""
    compiled = compile_text(GRAMMAR, cache_key="hello")

    text = "Hello World!"
    model = compiled.parse(text)
    print("Parsed model:", model)
    print("Fields:      ", model.model_dump())
    print()
    print("Round-trip:  ", repr(model.to_text()))
    assert model.to_text() == text, "round-trip must be lossless"


if __name__ == "__main__":
    main()
