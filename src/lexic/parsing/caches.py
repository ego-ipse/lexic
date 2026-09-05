"""Cache lifetime — identity memos bounded by the artefact that owns them.

The engine memoises almost everything it derives per **object identity**: a
grammar's tables, a ``(grammar, fold)`` pair's model product, a grammar's
split plans, its interiors, its per-worker replicas. Identity is the right
key — the alternative is deep-hashing tuples the size of a grammar on every
parse — but a bare ``dict`` keyed on ``id(...)`` must pin its key object to
stay correct against address reuse, and a pinned key is an immortal key.

Immortality is invisible while one process compiles one grammar. It stops
being invisible the moment grammars are DERIVED at run time:
:meth:`~lexic.compile.CompiledGrammar.bind` mints a fresh codegen grammar per
vocabulary and a reducer mints a variant artefact per policy, so a service
that rebinds per request grows every one of these memos without bound.

The fix is ownership, declared rather than guessed:

- a memo registers itself with :func:`memo`, saying which key positions hold
  an owner identity;
- a derived object that lives inside a memo's value is :func:`adopt`\\ ed
  under that entry's own identity, so the chain — artefact → codegen grammar
  → tables → run analysis — releases transitively from one root;
- an owner calls :func:`track` once, and a weakref finalizer runs
  :func:`release` when it dies.

Every registered memo is a **pure memo**: dropping an entry costs a
recomputation and changes no answer. That is what makes eviction safe even
when an identity is released while some other holder still uses the object.
"""

from __future__ import annotations

import weakref
from typing import Any, NamedTuple

__all__ = ["adopt", "cached_entries", "memo", "release", "reset_caches", "track"]


class _Memo(NamedTuple):
    """One registered identity memo and where its keys carry owner identity.

    :ivar entries: The live dict the owning module reads and writes.
    :ivar ids: Key tuple positions holding an owner ``id``; empty means the
        key IS the identity.
    """

    entries: dict[Any, Any]
    ids: tuple[int, ...]


_MEMOS: list[_Memo] = []
"""Every registered memo, in import order. Appended at import time only."""

_ADOPTED: dict[int, set[int]] = {}
"""owner id → the identities minted under it, for transitive release."""

_CLAIMED: set[int] = set()
"""Identities a live owner has claimed — see :func:`track`. Bounded by the
number of live owners, and drained by :func:`release`."""


def memo[T: dict[Any, Any]](entries: T, *ids: int) -> T:
    """Register an identity-keyed memo and hand it straight back.

    The dict is passed in rather than minted here so the declaration keeps
    its own key and value types; it stays an ordinary ``dict``, so the read
    path is still a plain subscript.

    :param entries: The (empty) dict to memoise into.
    :param ids: Key tuple positions holding an owner ``id``. Pass nothing
        when the key is the identity itself.
    :returns: ``entries``, unchanged.
    """
    _MEMOS.append(_Memo(entries, ids))
    return entries


def adopt(owner: int, *derived: object) -> None:
    """Declare that ``derived``'s identities live and die with ``owner``'s.

    Called where a memo stores a derived object as its VALUE: the object is
    reachable only from that entry, so releasing the entry must release
    whatever is keyed on the object in turn.

    :param owner: The identity the storing entry is keyed by.
    :param derived: The objects that entry brings into existence.
    """
    _ADOPTED.setdefault(owner, set()).update(id(obj) for obj in derived)


def track(owner: object, *identities: object) -> None:
    """Bind ``identities``' memo entries to ``owner``'s lifetime.

    **First claimant owns it.** Artefacts share: a rebound grammar reuses its
    source's authored AST and fold, and a reducer variant borrows the source's
    analysis grammar. Letting the second holder claim them too would make the
    SHORTER-lived object evict entries the longer-lived one is still using —
    turning a leak into a thrash. So an identity already spoken for is skipped,
    and its claim is returned when the claimant releases it.

    Only the ``id`` values are retained, never the objects — the finalizer's
    arguments must not be a second pin on the very graph it exists to free.

    :param owner: A weak-referenceable object whose death releases the rest.
    :param identities: The objects whose memo entries ``owner`` may own.
    """
    fresh = tuple(
        dict.fromkeys(id(obj) for obj in identities if id(obj) not in _CLAIMED)
    )
    if not fresh:
        return
    _CLAIMED.update(fresh)
    final = weakref.finalize(owner, release, fresh)
    final.atexit = False


def _owned(key: object, ids: tuple[int, ...], dropped: frozenset[int]) -> bool:
    """Whether ``key`` names one of the released identities."""
    if not ids:
        return key in dropped
    assert isinstance(key, tuple)
    return any(key[at] in dropped for at in ids)


def _expand(roots: tuple[int, ...]) -> frozenset[int]:
    """``roots`` plus everything adopted under them, transitively."""
    out = set(roots)
    frontier = list(roots)
    while frontier:
        for ident in _ADOPTED.pop(frontier.pop(), ()):
            if ident not in out:
                out.add(ident)
                frontier.append(ident)
    return frozenset(out)


def release(identities: tuple[int, ...]) -> None:
    """Drop every memo entry owned by ``identities`` or adopted under one.

    Runs from a finalizer, so it may land on any thread while another parse
    reads the same memos. It sweeps a private ``copy()`` and deletes with
    ``pop``: a concurrent write is then either kept or re-derived, never a
    mutation-during-iteration error.

    :param identities: The released owner ``id`` values.
    """
    dropped = _expand(identities)
    _CLAIMED.difference_update(dropped)
    # An identity can be adopted by more than one owner — a replica's binding
    # is minted under its grammar AND released on its own when the thread that
    # held it exits. Releasing it must clear the record the OTHER owner still
    # keeps, or that owner accumulates one dead id per released child for as
    # long as it lives, and a recycled address later reads as still owned.
    for owned in tuple(_ADOPTED.copy().values()):
        owned.difference_update(dropped)
    for entry in _MEMOS:
        for key in tuple(entry.entries.copy()):
            if _owned(key, entry.ids, dropped):
                entry.entries.pop(key, None)


def reset_caches() -> None:
    """Test seam: empty every registered memo and the ownership bookkeeping."""
    for entry in _MEMOS:
        entry.entries.clear()
    _ADOPTED.clear()
    _CLAIMED.clear()


def cached_entries() -> int:
    """How many entries every registered memo holds — the leak probe's meter."""
    return sum(len(entry.entries) for entry in _MEMOS)
