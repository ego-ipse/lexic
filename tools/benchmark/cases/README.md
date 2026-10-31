# Benchmark cases

Canonical grammars, corpora, acceptance fixtures, and their authored directive
variants. Every engine derives its input from these cases.

`grammars.py` holds the roster (`Bench`, `BENCHES`) and the real languages'
sources. The grammars that exist to exercise one route live by family:
`engine_reach.py` the engine routes and the fold rows (island-earley,
dense-earley), `split_shapes.py` the split routes.
