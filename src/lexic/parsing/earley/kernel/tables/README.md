# `lexic.parsing.earley.kernel.tables` — the codegen moment

An `IrAst` goes in, flat int-coded tables come out. Every dotted position of
every arm gets one `code`, laid out dot-dense so advancing a dot is `+ 1` —
after this point the loop never looks at an IR node again.

Three files, in dependency order:

- `atoms` — the primitives the tables are built out of: the packing tiers, how
  a handle's predecessor chain is walked, and what a single terminal atom
  accepts. Knows nothing about a table.
- `records` — what a compiled grammar IS: `CodeTables`, `DecodeTables`,
  `TermTables` and the `ParserTables` bundle over them. Read-only once built.
- `builder` — `TableBuilder` and the `compile_tables` entry point, plus the
  per-arm FIRST seed gates. The only mutable half.

`records` names `TableBuilder` in annotations only — a record is *constructed
from* a builder, so the runtime import would close a loop that the arrows
otherwise keep open.
