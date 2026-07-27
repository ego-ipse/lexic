# `lexic.ir.text` — How characters and documents are spelled.

`encodings` gives a char class's ordinals meaning; `pipeline` is what happens
to text before a segmenter sees it; `tokenizer` is a vocabulary and the
segmenters that apply it. `escapes` is a flavour's emit-side spelling of
canonical text, and `layout` the width-aware document combinators every emitted
file is rendered through.

The first three are one family in dependency order; the last two are unrelated
to them and to each other, and sit here because spelling is what they are
both about.

## Modules

- `encodings.py`
- `escapes.py`
- `layout.py`
- `pipeline.py`
- `tokenizer.py`

Import from `lexic.ir`, not from these paths: the package façade is the
public surface, and it is lazy, so naming a symbol there costs only the
module that defines it.
