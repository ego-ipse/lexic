"""Export a compiled grammar as an importable twin module.

Compilation synthesizes classes in memory (``type()``, no files);
``export_module`` is the one write seam — it renders an importable Python
twin: typed fields, the rule as the class docstring, the grammar embedded in
the IR-constructor notation. Lexic then eats its own output twice over:

- ``parse_module`` parses the twin's SOURCE with lexic's own module
  self-grammar (no ``ast`` walk — a grammar parse);
- ``verify_module`` cross-checks the parsed classes against the compiled
  binding view.

Run::

    uv run python getting_started/ex08_twin_module.py
"""

from __future__ import annotations

import runpy
from pathlib import Path
from tempfile import TemporaryDirectory

from lexic import compile_text
from lexic.compile import export_module, export_source, parse_module, verify_module

GRAMMAR = """\
greeting ::= salutation " " name "!"
salutation ::= "Hello" | "Hi" | "Hey"
name ::= [A-Za-z]+
"""


def main() -> None:
    """Export the greeting grammar, verify it, import it, use the classes."""
    compiled = compile_text(GRAMMAR, cache_key="ex08")

    source = export_source(compiled)
    print("=== twin module (first 12 lines) ===")
    print("\n".join(source.splitlines()[:12]))

    # Lexic parses its own export and cross-checks it against the binding.
    module_model = parse_module(source)
    verify_module(compiled, source)
    print("\nparse_module classes:", [str(c.name) for c in module_model.classes])

    # Write + load the twin; its classes carry the same __grammar__.
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "greeting_twin.py"
        export_module(compiled, path, stem=compiled.stem)
        twin = runpy.run_path(str(path))

    # Construct a model directly from the loaded classes — checked
    # construction: ref-bound fields take SUB-MODELS (Salutation("Hey")), not
    # bare strings, and every value is validated against the grammar.
    greeting = twin["Greeting"](
        salutation=twin["Salutation"]("Hey"), name=twin["Name"]("Lexic")
    )
    print("\nConstructed:", greeting.to_text())
    assert greeting.to_text() == "Hey Lexic!"
    assert twin["Greeting"].__grammar__ == compiled.classes["Greeting"].__grammar__


if __name__ == "__main__":
    main()
