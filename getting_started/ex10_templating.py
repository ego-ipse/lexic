"""Extract selected paths from a big document — parse only what you keep.

``template(compiled, shape, spec)`` works over ANY compiled grammar whose
language has a map shape: ``MapShape`` names the four grammar facts (the
section rule, the entry rule, its key and value fields), the spec is a nested
mapping with ``KEEP`` leaves, and ``run`` parses the document once in
span mode — skipped subtrees are captured as raw spans and never modelled;
only kept paths re-parse into real :class:`GrammarModel` instances.

The shape below fits both bundled json grammars unchanged (``json.gbnf`` and
``json.abnf`` share their rule names) — templating is grammar-native, not
format-native.

Run::

    uv run python getting_started/ex10_templating.py
"""

from __future__ import annotations

from pathlib import Path

from lexic import compile_from_path
from lexic.compile import KEEP, MapShape, template

REPO_ROOT = Path(__file__).resolve().parent.parent
GRAMMAR_PATH = REPO_ROOT / "resources" / "ground_truth" / "json.gbnf"

# object ::= begin-object (member (value-separator member)*)? end-object
# member ::= string name-separator value
SHAPE = MapShape(
    section="object", entry="member", key_field="string", value_field="value"
)

DOC = (
    '{"version": 2, "model": {"type": "BPE", "vocab": {"a": 1}}, '
    '"padding": null, "decoder": {"type": "ByteLevel"}}'
)

# Keys are RAW SPANS in the grammar's own surface — for json that includes
# the quotes. Nesting recurses into the value's own map level.
SPEC = {'"version"': KEEP, '"model"': {'"type"': KEEP}}


def main() -> None:
    """Compile json.gbnf, extract two paths, leave the rest unparsed."""
    compiled = compile_from_path(GRAMMAR_PATH)
    extractor = template(compiled, SHAPE, SPEC)  # compile once ...
    out = extractor.run(DOC)  # ... run many

    # Typed path reads — a kept model comes back AS a GrammarModel, and a
    # wrong or absent path raises with the failing path spelled out.
    version = out.model('"version"')
    model_type = out.model('"model"', '"type"')
    print("version:   ", version.to_text(), f"({type(version).__name__})")
    print("model.type:", model_type.to_text(), f"({type(model_type).__name__})")
    assert model_type.to_text() == '"BPE"'
    # Absent spec keys are simply absent — "padding"/"decoder" never parsed.
    assert set(out) == {'"version"', '"model"'}


if __name__ == "__main__":
    main()
