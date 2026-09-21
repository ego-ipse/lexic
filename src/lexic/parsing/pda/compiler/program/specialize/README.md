# Post-flatten specialisation

Two modules with a one-way dependency, and the boundary between them is what this folder is
for.

**`passes.py` — the specialisation passes.** A pass rewrites the flat artefact
once it exists, in place, without changing the language it accepts: exactly-once
terminals take their loop-free op-codes, `value_str` references inline, char
tables are baked, run terminals are consulted, calls and leaf references take
their specialised codes. Each is a rewrite whose licence the module states and
whose refusals it pins — an over-broad licence here is a silently wrong parse,
not a slow one.

**`frameless.py` — frame-less entry.** Not a pass but the question a pass asks:
*can this clone be entered without pushing a frame*. It holds what qualifies
(`convert_dispatch`, which rewrites a pass-through alternation into a dispatch),
and the licences that read the result (`vstr_inlinable`, `vdisp_landing`,
`vdisp_target`, `dispatch_chartable`). They live together because they are one
subject: splitting them by caller put a cycle between the halves, and left the
licences in a different module from the rewrite that creates what they licence.

The dependency is **one-way, and acyclic by construction**: `frameless` is a leaf over the flat records and the
op-codes; `passes` imports it and it imports nothing back. So the package marker
is a marker — importers name the module they want, and there is no facade to
keep in step with either.
