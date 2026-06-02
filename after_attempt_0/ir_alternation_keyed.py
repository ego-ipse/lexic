"""PROTOTYPE — future IrAlternation as a keyed collection.

Not wired in. Explores the shape reached in the 2026-05-29 discussion:

  * A variadic node is a *keyed* collection, not a dataclass-with-a-tuple-field.
  * The **keying strategy** is the single axis that distinguishes ordered from
    unordered alternation — ordered keys positionally, unordered keys by content
    hash (set semantics, dedup for free).
  * Slotted, hashable, content-eq, and `repr(node)` reproduces its constructor
    call (the `repr`-is-codegen / file-≡-repr property).

This file is standalone (re-declares minimal protocol stand-ins) so it runs
without importing the live tree; names mirror `ir/nodes.py` intent.

Key findings baked in (all verified on py3.14):
  - `__slots__` is illegal on a `tuple` subtype only when *non-empty*; `()` is fine.
  - A `tuple` subtype with `__slots__=()` cannot carry a scalar attr at all — which
    is *why* ordered (pure-variadic) and record nodes must stay distinct kinds.
  - Therefore: ordered alternation IS-A tuple (no scalar, positional keys);
    set alternation IS-A tuple too but its *identity* is content-keyed.
"""

from __future__ import annotations

from abc import abstractmethod
from collections.abc import Sequence
from typing import ClassVar, Self


# ── minimal protocol stand-ins (mirror ir/nodes.py) ───────────────────────────
class _IrSelf:
    """Identity + protocol root (trimmed)."""

    def __call__(self, d, n, nc, /) -> Self:  # noqa: ANN001
        return self

    def eval(self, d, n, nc, /):  # noqa: ANN001
        return self(d, n, nc)

    def children(self) -> Sequence["_IrSelf"]:
        return ()

    def rebuild(self, new_children: Sequence["_IrSelf"]) -> Self:
        return self


# ── the keyed collection base ─────────────────────────────────────────────────
class IrKeyed(_IrSelf, tuple):
    """A variadic node that IS-A tuple of children, addressable by a key.

    The element storage is the tuple itself (ordered, hashable, slotted-empty).
    The *key* of each child is produced by `key_of`, which subclasses override
    to choose a keying discipline. `children`/`rebuild`/`eval` are uniform;
    only `key_of` (and, for sets, canonicalisation in `__new__`) varies.
    """

    __slots__ = ()
    _str_name: ClassVar[str] = "KEYED"

    def __new__(cls, *children: _IrSelf) -> Self:
        return super().__new__(cls, cls._canonical(children))

    # -- keying strategy: the one axis that varies between subclasses --
    @classmethod
    def _canonical(cls, children: tuple[_IrSelf, ...]) -> tuple[_IrSelf, ...]:
        """Hook: ordered keeps order; set dedups by content key. Default: ordered."""
        return children

    @abstractmethod
    def key_of(self, index: int, child: _IrSelf) -> object:
        """The hashable key under which `child` is addressed."""
        raise NotImplementedError

    # -- uniform protocol over the tuple payload --
    def children(self) -> Sequence[_IrSelf]:
        return tuple(self)

    def rebuild(self, new_children: Sequence[_IrSelf]) -> Self:
        return type(self)(*new_children)

    def eval(self, d, n, nc, /) -> Self:  # noqa: ANN001
        return type(self)(*(c.eval(d, n, nc) for c in self))

    def keyed(self) -> dict[object, _IrSelf]:
        """The node viewed as {key: child}. Ordered nodes → positional keys;
        set nodes → content keys (and so duplicates are already collapsed)."""
        return {self.key_of(i, c): c for i, c in enumerate(self)}

    def __repr__(self) -> str:
        return f"{type(self).__name__}({', '.join(map(repr, self))})"


# ── ordered alternation: keys are positions ──────────────────────────────────
class IrAlternation(IrKeyed):
    """Ordered choice (PEG first-match-wins). Children keyed by position;
    order is identity, duplicates are preserved (they may differ by priority)."""

    _str_name: ClassVar[str] = "ALT"

    def key_of(self, index: int, child: _IrSelf) -> object:
        return index


# ── set alternation: keys are content; dedup + order-independence fall out ────
class IrSetAlternation(IrKeyed):
    """Unordered choice. Children keyed by *content* — so the node is a set:
    duplicates collapse at construction, and two set-alternations are equal
    regardless of arm order. (Disjointness is a parser-side obligation, not
    represented here.)"""

    _str_name: ClassVar[str] = "SET-ALT"

    @classmethod
    def _canonical(cls, children: tuple[_IrSelf, ...]) -> tuple[_IrSelf, ...]:
        # dedup by content key, then sort by it so arm-order is not identity
        seen: dict[object, _IrSelf] = {}
        for c in children:
            seen.setdefault(_content_key(c), c)
        return tuple(v for _, v in sorted(seen.items(), key=lambda kv: repr(kv[0])))

    def key_of(self, index: int, child: _IrSelf) -> object:
        return _content_key(child)


def _content_key(node: _IrSelf) -> object:
    """Canonical, structure-only key for a subtree.

    PROTOTYPE: uses repr as the canonical form. The real implementation needs a
    cached, bottom-up structural hash (hash-consing) so equal subtrees share a
    key in O(1) and construction order can't affect it. That intern table is the
    one heavy dependency set-keying drags in — deferred until IrSetAlternation
    is actually built.
    """
    return repr(node)


# ── demo leaves ──────────────────────────────────────────────────────────────
class _Lit(_IrSelf):
    __slots__ = ("v",)

    def __init__(self, v: str) -> None:
        self.v = v

    def eval(self, d, n, nc, /):  # noqa: ANN001
        return self

    def __repr__(self) -> str:
        return f"_Lit({self.v!r})"


if __name__ == "__main__":
    a, b, c = _Lit("a"), _Lit("b"), _Lit("c")

    ordered = IrAlternation(a, b, c)
    print("ordered repr  :", repr(ordered))
    print("  is-a tuple  :", isinstance(ordered, tuple), "| len", len(ordered))
    print("  keyed       :", {k: r.v for k, r in ordered.keyed().items()})
    print("  hashable    :", hash(ordered) is not None)
    print("  eval rebuilds:", repr(ordered.eval(None, None, ())))
    print("  order is id  :", IrAlternation(a, b) != IrAlternation(b, a))

    print()
    set1 = IrSetAlternation(a, b, c)
    set2 = IrSetAlternation(c, b, a, a)  # reordered + duplicate
    print("set1 repr     :", repr(set1))
    print("set2 repr     :", repr(set2), "(dup 'a' collapsed)")
    print("  order NOT id :", set1 == set2)
    print("  keyed (set)  :", {str(k)[:12] + "…": r.v for k, r in set1.keyed().items()})
    print("  len dedup    :", len(IrSetAlternation(a, a, a)))
