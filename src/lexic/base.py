"""GrammarModel: base class for all generated Pydantic models."""

from __future__ import annotations

from typing import Any, ClassVar

from pydantic import BaseModel

from lexic.grammars import get_flavour
from lexic.ir.nodes import IrItem, IrLiteral
from lexic.ir.spec import RuleSpec


class GrammarModel(BaseModel):
    """Abstract base for all generated grammar model classes.

    Each subclass defines ``__grammar__: ClassVar[RuleSpec]``.

    ``to_text()`` walks ``__grammar__.items`` in order:
      - item index in field_map → emit getattr(self, field_name)
      - else IrItem with IrLiteral atom → emit the literal value
      - else → skip (structural / non-emitting)
    """

    __grammar__: ClassVar[RuleSpec]

    def to_text(self) -> str:
        """Emit grammar text for this model instance."""
        spec = self.__grammar__
        if spec.kind == "alternation":
            raise NotImplementedError(
                f"to_text() is undefined on abstract alternation class "
                f"{type(self).__name__}; call it on a concrete arm instance."
            )
        if spec.kind == "value_str":
            return str(getattr(self, "value", ""))
        inv: dict[int, str] = {idx: name for name, idx in spec.field_map.items()}
        parts: list[str] = []
        for i, item in enumerate(spec.items):
            if not isinstance(item, IrItem):
                continue
            if i in inv:
                val = getattr(self, inv[i], None)
                if val is None:
                    continue
                if isinstance(val, list):
                    parts.append(
                        "".join(
                            v.to_text() if isinstance(v, GrammarModel) else str(v)
                            for v in val
                        )
                    )
                elif isinstance(val, GrammarModel):
                    parts.append(val.to_text())
                else:
                    parts.append(str(val))
            elif isinstance(item.atom, IrLiteral):
                parts.append(item.atom.value)
        return "".join(parts)

    def to_grammar(self, flavour: str = "gbnf") -> str:
        """Emit grammar text for this model instance."""
        return str(get_flavour(flavour).apply(self.__grammar__.to_ir_rule()))

    def semantic_dump(self) -> dict[str, Any]:
        """Dump only semantic fields."""
        return self.model_dump(exclude=set(self.__grammar__.non_semantic_fields))
