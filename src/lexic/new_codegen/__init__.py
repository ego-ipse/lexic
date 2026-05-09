"""new_codegen — IR → Pydantic Python source.

Target-shape codegen rebuilt from scratch during the parallel-track IR
cutover. Emits module-level type aliases, Annotated[str, StringConstraints]
for pattern fields, Literal[...] for pure-literal alternations, Tier 2/3
positional naming, and __grammar__ at module footer.

Renamed to lexic.codegen at cutover (Slice 4).
"""

from lexic.new_codegen.aliases import collect_aliases

__all__ = ["collect_aliases"]
