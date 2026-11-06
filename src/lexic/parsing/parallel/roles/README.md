# `lexic.parsing.parallel.roles` — what a grammar's anchor characters do

Two kinds of object, imported one way, `derive` → `runs`:

- **The role records** (`derive.py`) — opener/closer pairs, repetition
  separators and terminators, derived once per grammar by `roles()`, and the
  leads a bracket's own run reads from them (`run_leads`). The window scan,
  the planner, the cut search and the region plans read these records.
- **The run sites** (`runs.py`) — where a bracket's own run stands: the arms
  that open on one character and close on another (`bracket_arms`), the
  bodies an arm repeats (`repeated_bodies`), the rules that own a bracket's
  run (`run_owners`), and whether an arm holds `head tail*` itself
  (`holds_run`). These walks read only the grammar.

Every role is derived from grammar structure, never named per formulation.
`lexic.parsing.parallel` re-exports `Roles`, `Separator`, `Terminator` and
`roles`; this package has no façade of its own.
