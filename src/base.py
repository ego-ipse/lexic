"""GrammarModel: base class for all generated Pydantic models.

Provides to_text(), to_gbnf(), and semantic_dump() driven entirely by
__grammar__: RuleSpec on each concrete subclass.
Knows nothing about codegen, Lark, or GBNF parsing.
"""
from __future__ import annotations

from typing import Any, ClassVar, get_origin, get_type_hints

from pydantic import BaseModel

from codegen.ir import LiteralAtom, RuleRefAtom, RuleSpec


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
        spec = self.__grammar__
        if spec.kind == "value_str":
            return str(getattr(self, "value", ""))
        if spec.kind == "alternation":
            raise NotImplementedError(
                f"{type(self).__name__} is abstract — call to_text() on a concrete subclass"
            )

        try:
            hints = get_type_hints(type(self))
        except NameError:
            # Fallback for local classes defined in test functions:
            # Build localns from the instance's globals/locals and try again
            hints = {}
            for base in type(self).__mro__[::-1]:
                if hasattr(base, "__annotations__"):
                    hints.update(base.__annotations__)

            # Try to resolve string annotations using the frame where the class was defined
            import inspect
            frame = inspect.currentframe()
            caller_locals = {}
            caller_globals = {}
            if frame and frame.f_back:
                caller_locals = frame.f_back.f_locals
                caller_globals = frame.f_back.f_globals

            resolved_hints = {}
            for k, v in hints.items():
                if isinstance(v, str):
                    try:
                        resolved_hints[k] = eval(v, caller_globals, caller_locals)
                    except Exception:
                        resolved_hints[k] = v
                else:
                    resolved_hints[k] = v
            hints = resolved_hints

        inv: dict[int, str] = {idx: name for name, idx in spec.field_map.items()}
        parts: list[str] = []

        for i, atom in enumerate(spec.items):
            if isinstance(atom, LiteralAtom):
                parts.append(atom.value)
                continue
            if i not in inv:
                continue
            field_name = inv[i]
            val = getattr(self, field_name, None)
            if val is None:
                continue
            hint = hints.get(field_name)
            origin = get_origin(hint)
            if origin is list:
                parts.append("".join(
                    item.to_text() if isinstance(item, GrammarModel) else str(item)
                    for item in val
                ))
            elif isinstance(val, GrammarModel):
                parts.append(val.to_text())
            else:
                parts.append(str(val))

        return "".join(parts)

    def to_gbnf(self) -> str:
        """Reconstruct the GBNF rule for this class's grammar spec."""
        from codegen.gbnf_emitter import GBNFEmitter
        return GBNFEmitter([self.__grammar__]).emit_rule(self.__grammar__)

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
