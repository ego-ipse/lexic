"""VyxBase — single parent for all grammar-derived node models.

This file contains only the indexing machinery and the sigil registry.
No Vyx structure lives here — models are created by builder.py from
the grammar.

Two namespaces per node:
    opener  — the node's own Pydantic fields (dot access or Self sentinel)
    body    — ordered body children (sigil-qualified __getitem__)

Access forms:
    node.name                  opener field — dot notation
    node[Self, "name"]         opener field — explicit long form
    node[SomeModel, "key"]     body child by type + key
    node[SomeModel, 0]         body child by type + index
    node[0]                    body child by absolute document position
    node["$C"]                 body child by sigil-prefixed shorthand
"""

from __future__ import annotations

from typing import Any, ClassVar, Iterator

from pydantic import BaseModel, PrivateAttr


class Self:
    """Sentinel for explicit opener-attribute access.

    node[Self, "name"] is the long form of node.name.
    Never instantiated — used only as a type identity in __getitem__.
    """


class VyxBase(BaseModel):
    """Single base for all grammar-derived Vyx models.

    Subclasses declare SIGIL: ClassVar[str | None] = "<char>".
    __init_subclass__ registers it in _sigil_registry automatically.
    The builder sets SIGIL on dynamically created models.

    _children holds the ordered body. Body children are appended by
    the parser via _append_child. Opener KVs are Pydantic fields on
    the subclass, accessed via dot notation or node[Self, "name"].
    """

    model_config = {
        "extra": "forbid",
        "frozen": True,
        "populate_by_name": True,
    }

    # Set by each subclass; registered automatically
    SIGIL: ClassVar[str | None] = None

    # Shared across all subclasses — populated by __init_subclass__
    _sigil_registry: ClassVar[dict[str, type[VyxBase]]] = {}

    # Mutable despite frozen=True — PrivateAttr lives outside model fields
    _children: list[VyxBase] = PrivateAttr(default_factory=list)

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if cls.SIGIL is not None:
            VyxBase._sigil_registry[cls.SIGIL] = cls

    # ------------------------------------------------------------------
    # Identity — overridden by grammar-derived models that have a key
    # ------------------------------------------------------------------

    def _key(self) -> str | None:
        """Lookup key within a parent's body. None = positional only."""
        return None

    # ------------------------------------------------------------------
    # Opener access — Pydantic handles dot notation for declared fields.
    # __getattr__ is reached only for names Pydantic does not recognise.
    # ------------------------------------------------------------------

    def __getattr__(self, name: str) -> Any:
        raise AttributeError(
            f"{type(self).__name__!r} has no opener attribute {name!r}"
        )

    # ------------------------------------------------------------------
    # Body access — four forms dispatched through one match statement
    # ------------------------------------------------------------------

    def __getitem__(self, key: Any) -> Any:
        children = self._children

        match key:
            case (t, str(name)) if t is Self:
                # Explicit opener — identical to dot access.
                # Checked by identity (t is Self), not isinstance.
                try:
                    return getattr(self, name)
                except AttributeError:
                    raise KeyError(f"no opener attribute {name!r}")

            case (type() as t, str(name)):
                # Body child by type + key.
                for child in children:
                    if isinstance(child, t) and child._key() == name:
                        return child
                raise KeyError(f"no {t.__name__!r} child keyed {name!r}")

            case (type() as t, int(i)):
                # Body child by type + positional index within that type.
                typed = [c for c in children if isinstance(c, t)]
                try:
                    return typed[i]
                except IndexError:
                    raise KeyError(f"no {t.__name__!r} child at index {i}")

            case int(i):
                # Absolute document position.
                try:
                    return children[i]
                except IndexError:
                    raise KeyError(f"no child at absolute index {i}")

            case str(s) if s and s[0] in VyxBase._sigil_registry:
                # Sigil-prefixed shorthand: "$C"  "^ref"  "- "
                t = VyxBase._sigil_registry[s[0]]
                name = s[1:]
                for child in children:
                    if isinstance(child, t) and child._key() == name:
                        return child
                raise KeyError(f"no {t.__name__!r} child keyed {name!r}")

            case _:
                raise KeyError(f"unrecognised key form: {key!r}")

    # ------------------------------------------------------------------
    # Iteration and length — always over body children
    # ------------------------------------------------------------------

    def __iter__(self) -> Iterator[VyxBase]:
        return iter(self._children)

    def __len__(self) -> int:
        return len(self._children)

    # ------------------------------------------------------------------
    # Parser interface — populate body after construction
    # ------------------------------------------------------------------

    def _append_child(self, child: VyxBase) -> None:
        """Append one body child. Called by the parser."""
        self._children.append(child)
