# Parallel model stitching

Small, product-neutral structural helpers used after independently parsed
pieces return to the one model orchestration path. Discovery remains under
`parallel/discovery`; policy, parsing, fallback, and worker ownership remain in
`parallel/orchestrate.py`.

`model.py` derives exact model classes/routes and rebuilds immutable ancestors.
`tasks.py` assigns flattened region pieces distinct replica views and records
which region receives each result.
