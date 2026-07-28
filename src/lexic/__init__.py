"""Lexic — Grammar engine.

A **lazy façade**. Importing any module under ``lexic.`` runs this file first, so
re-exporting the entry points eagerly meant ``import lexic.ir`` — 15 modules of
spine — cost 77, dragging the whole engine in behind it. Every consumer of the
spine paid that, and every compiled payload naming a spine symbol pays it on
every read.

The names resolve on first access instead. The ``TYPE_CHECKING`` block declares
them statically, so ``from lexic import compile_text`` is typed as the function
it is rather than as one return type shared by every name — that block is the
whole reason it can be lazy without degrading the surface, and it re-exports
rather than restates, so there is no signature to drift.

CLAUDE.md's *"no TYPE_CHECKING dodges"* is a **layering** rule: it forbids a
runtime module reaching into the engine behind the type checker's back. This is
the package façade, which has no layer and no arrow to dodge, and the block
gives a lazy re-export the type it already had when it was eager. Authorised
2026-07-27.

REVISIT ON 3.15 — if PEP 810 (explicit lazy imports) lands as expected, this
whole file collapses to six ``lazy from … import …`` lines: the names stay
statically visible with their real types, so the ``TYPE_CHECKING`` block, the
``__getattr__``, the ``_HOMES`` map and the three-way drift pin in
``test_init_lexic`` all go away. Wait for a RELEASE, not a beta —
``requires-python`` is a promise to everyone who installs lexic. Note that
``generate`` would still need checking by hand: its collision with the submodule
``lexic.generate`` is a name-shadowing problem, not a laziness one, and no import
mechanism resolves two things wanting one name.
"""

from importlib import import_module
from typing import TYPE_CHECKING, Callable

# `generate` cannot be lazy: it names BOTH this export and the submodule
# `lexic.generate`, so the moment anything imports the module the attribute
# exists and `__getattr__` — which Python only calls on a MISS — never runs,
# handing a caller the module instead of the function. Binding it here costs
# the spine (16 modules) and not the engine, which is where the 62-module win
# is. Found by the suite running in parallel: import order decides it, so it
# passed in isolation.
from lexic.generate import generate

if TYPE_CHECKING:
    from lexic.compile import (
        compile_from_path,
        compile_text,
        parse_grammar,
        parse_instance,
        parse_instance_from_path,
    )

__all__ = [
    "compile_from_path",
    "compile_text",
    "generate",
    "parse_grammar",
    "parse_instance",
    "parse_instance_from_path",
]

_HOMES = {
    "compile_from_path": "lexic.compile",
    "compile_text": "lexic.compile",
    "parse_grammar": "lexic.compile",
    "parse_instance": "lexic.compile",
    "parse_instance_from_path": "lexic.compile",
}
"""The LAZY entry points and the module that defines each — where
``__getattr__`` looks. ``generate`` is absent because it is bound eagerly above.

The surface is stated three times, once per consumer: the ``TYPE_CHECKING``
block for the type checker, ``__all__`` for the export machinery (and for ruff,
which cannot see a computed one), and this for the runtime lookup.
``test_init_lexic`` pins all three to each other, so a name can only join the
façade by joining all of them."""


def __getattr__(name: str) -> Callable[..., object]:
    """Resolve an entry point on first access.

    Annotated as the callable it IS rather than as the value it returns: the
    static declarations above carry the real signatures, so a caller's call site
    is typed from those and never from this.

    :param name: The attribute being read.
    :returns: The entry point.
    :raises AttributeError: On a name the package does not export.
    """
    home = _HOMES.get(name)
    if home is None:
        raise AttributeError(f"module 'lexic' has no attribute {name!r}")
    return getattr(import_module(home), name)


def __dir__() -> list[str]:
    """The exports, so ``dir()`` and tab-completion still see the surface."""
    return sorted(__all__)
