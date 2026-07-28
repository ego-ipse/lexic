# `lexic.parsing.earley.kernel` — the paid loop

`kernel` is the flat Earley recogniser: the loop that actually costs something,
written against int-coded tables rather than IR nodes. `tables` is the compile
step that produces those — the parser's codegen moment. `chart`, `forest` and
`trampoline` are what it fills and how that is read back: the SPPF link table,
the shared packed forest over it, and a depth-safe walk for both.

Deliberately not records: this folder and its callers use plain tuples, `None`
and mutable cursors. Strictness is `ir/`'s contract, not the engine's.
