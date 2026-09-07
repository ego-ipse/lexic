# External engines

Construction and lifecycle adapters for generated ANTLR targets and shared
competitor refusal handling. Generated artifacts remain temporary.

`seats.py` is where a competitor engine LANDS: one constructor per seat, the
candidate table naming them, and the build-then-judge pass that gives a seat a
parse entry or the reason it has none. Adding an engine touches nothing that
decides what a row means.
