"""GrammarModel: base class for all generated Pydantic models.

Provides to_text(), to_grammar(), and semantic_dump() driven entirely by
__grammar__: RuleSpec on each concrete subclass.
Knows nothing about codegen, Lark, or GBNF parsing.

Note: to_grammar() uses get_adapter() from lexic.grammars — the deliberate
runtime→codegen seam described in 2_ARCHITECTURE.md §Layering rules.
"""

from __future__ import annotations

from typing import Any, ClassVar

from pydantic import BaseModel

from lexic.grammars import get_adapter
from lexic.ir import LiteralAtom, RuleRefAtom, RuleSpec
from lexic.grammars.gbnf.syntax import decode_gbnf_escapes


class GrammarModel(BaseModel):
    """Abstract base for all generated grammar model classes.

    Each subclass must define:
        __grammar__: ClassVar[RuleSpec]

    to_text() reconstructs the original grammar text from instance field values.
    The algorithm walks __grammar__.items in order:
      - LiteralAtom  → emit atom.value directly (no field needed)
      - atom index in field_map → getattr(self, field_name) → emit
    Whitespace is preserved because ws fields are regular RuleRefAtom fields.
    """

    __grammar__: ClassVar[RuleSpec]

    def to_text(self) -> str:
        """Reconstruct the original grammar text for this instance."""
        spec = self.__grammar__
        if spec.kind == "value_str":
            return str(getattr(self, "value", ""))
        if spec.kind == "alternation":
            raise NotImplementedError(
                f"{type(self).__name__} is abstract — call to_text() on a concrete subclass"
            )

        inv: dict[int, str] = {idx: name for name, idx in spec.field_map.items()}
        parts: list[str] = []

        for i, atom in enumerate(spec.items):
            if isinstance(atom, LiteralAtom):
                # Decode GBNF escape sequences stored as 2-char sequences
                # (e.g. "\\n" → actual newline) before emitting.
                decoded = decode_gbnf_escapes(atom.value)
                parts.append(decoded)
                continue
            if i not in inv:
                continue
            field_name = inv[i]
            val = getattr(self, field_name, None)
            if val is None:
                continue
            if isinstance(val, list):
                parts.append(
                    "".join(
                        item.to_text() if isinstance(item, GrammarModel) else str(item)
                        for item in val
                    )
                )
            elif isinstance(val, GrammarModel):
                parts.append(val.to_text())
            else:
                parts.append(str(val))

        return "".join(parts)

    def to_grammar(self, flavour: str = "gbnf") -> str:
        """Reconstruct the grammar rule text for this class.

        Default flavour is "gbnf". The emitter is resolved via the flavours
        registry at call time so ADAPTERS populate regardless of import order.
        Uses the FlavourEmitter protocol's emit(specs) — single-rule output
        strips the trailing newline.
        """
        adapter = get_adapter(flavour)
        return adapter.emitter.emit([self.__grammar__]).rstrip("\n")

    def semantic_dump(self) -> dict[str, Any]:
        """model_dump() excluding fields that map to RuleRefAtom('ws') in __grammar__.

        Used by S04 translate() to extract cross-grammar-portable data.
        """
        spec = self.__grammar__
        ws_fields: set[str] = set()
        for fname, idx in spec.field_map.items():
            atom = spec.items[idx]
            if isinstance(atom, RuleRefAtom) and atom.rule_name == "ws":
                ws_fields.add(fname)
        return self.model_dump(exclude=ws_fields)
