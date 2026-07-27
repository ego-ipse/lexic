# `lexic.compile.payload` — a parsed value as flat literals

What a compiled *text* is, as opposed to a compiled grammar: `TYPES`,
`ORIGINS`, `STRS` and `NODES` — four flat literals and no objects. The grammar's
classes are the schema; the payload references them by index.

- `codec` — the table, one row per kind, carrying BOTH directions. A kind is
  added here once, not in an encoder and again in a reader.
- `encode` — value → the four tables. The lexic side of the projection.
- `export` — `export_value`: that projection as an importable, self-contained
  module, with a `payload_reader_<tag>.py` sidecar emitted beside it.
- `reader` — the sidecar's source. **Zero lexic imports**, by design and by
  test: a payload must be readable by something that has never heard of this
  package.

The sidecar's tag is a digest of its own source, so a payload and a reader that
disagree cannot be spelled. `built_under` checks provenance on the producing
side, where the reduction is still in hand.
