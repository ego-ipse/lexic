# Parallel model stitching

Small, product-neutral structural helpers used after independently parsed
pieces return to the one model orchestration path. Discovery remains under
`parallel/discovery`; policy, parsing, fallback, and worker ownership remain in
`parallel/orchestrate.py`.

`model.py` derives exact model classes/routes and rebuilds immutable ancestors.
`merge.py` reconstructs separator tails around shallow grammatical witnesses
and attaches delegated values to the parsed shell without reparsing their
recursive heads.
`tasks.py` assigns flattened region pieces distinct replica views and records
which region receives each result.
`safety.py` proves separator ownership against the one repeated-item rule that
competes with the tail edge. Only rules the discovery scan itself treats as
opaque or depth-owned are protected by that proof.

It also decides which opaque regions a terminator scan may skip. A region
qualifies either because pairing its delimiter left to right is exact
everywhere, or because it can only open where a unit begins — the arm that
carries it leads with the delimiter and no sibling arm can. `terminates_once`
then reads each arm's tail from where the scan resumes rather than from the
whole arm, and `scan_agrees` refuses a plan whose structural view and parse
grammar derive different delimiters, since only the parse grammar drives the
scan while only the view is proven.
