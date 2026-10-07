"""Every composed build still agrees with the plan it was composed from.

``clone.build`` is composed from ``clone.plan`` once, at bake, and never
consulted again — so the two are a coupling with no runtime check behind it.
A later pass that rewrote ``plan`` after the bake would leave a builder
reading the old one and produce silently wrong records: same class, same
width, wrong values. THREE modules write that state today — ``product.py``,
``flatten.py`` and ``lower.py``, at ``bake_product_build``, ``clear_build``
and the attempt-sub copy — each writing both together, and this is what says
so.

The scope is DERIVED, not listed: :func:`pda_sources` walks the PDA tree for
the modules that write it, so one that starts writing is scanned the day it
lands.

Two gates, deliberately different in kind. The corpus walk runs every clone
of every ground-truth grammar through a synthetic capture state and checks the
record against an independent reading of that clone's own plan. The static
check refuses a new writer of ``.plan`` that does not also write ``.build``,
which the walk cannot see because an un-baked pass leaves no trace in a
compiled artefact.
"""

from __future__ import annotations

import re

import pytest

from lexic.compile import compile_from_path
from lexic.parsing.pda.compiler.program.flatten import FlatClone, no_shape_build
from lexic.parsing.products import pda_tables
from tests.build_tail_helpers import every_clone, plan_means
from tests.paths import (
    ABNF_GRAMMARS,
    GBNF_GRAMMARS,
    GROUND_TRUTH,
    PROJECT_ROOT,
)

NEEDS_VOCABULARY = frozenset({"think.gbnf"})
"""Grammars whose token terminals cannot concretize without a tokenizer.

Excluded because they cannot be COMPILED here at all, not because their
builders are exempt: a bound vocabulary is a fixture this gate does not need.
"""

PDA_ROOT = PROJECT_ROOT / "src" / "lexic" / "parsing" / "pda"

WRITES_PLAN = re.compile(r"\.plan\s*=")
WRITES_BUILD = re.compile(r"\.build\s*=")
"""The writer spellings. :func:`pda_sources` and the per-module assertion read
these same two compiled patterns, so what the gate SCANS cannot drift from
what it CHECKS.

**These two spellings ARE the contract**, declared rather than inferred: a
write reaching ``plan`` or ``build`` by any other spelling — an augmented
``.plan +=``, a name-built ``setattr`` — is outside this gate BY DECLARATION,
not by oversight. Neither exists under the tree today, and widening the
pattern to chase them would trade a stated boundary for a vaguer one.
:func:`test_no_setattr_escape` closes the one variant easy to write by
accident.
"""

SETATTR_ESCAPE = re.compile(
    r"""setattr\((?:[^()]|\([^()]*\))*?,\s*["'](?:plan|build)["']""", re.S
)
r"""A ``setattr`` naming ``plan`` or ``build`` as its ATTRIBUTE argument.

Matched on that argument alone, never on the whole line: ``builder``,
``rebuild`` and ``plans`` all contain the words and none is an escape.

Searched over the WHOLE source with ``re.S``, not line by line, because the
formatter wraps a long call and ``setattr(`` then sits on a different line
from the name it sets — a per-line search reads such a call as absent.

The gap is ``(?:[^()]|\([^()]*\))*?``, not ``.*?``: an unbounded gap crosses
the closing paren, so a ``setattr`` naming something else and a later ``,
"plan"`` anywhere in the file match TOGETHER. Bounding it to the call — while
still admitting one level of nesting — keeps a first argument that is itself a
call with a comma.

**One level, by declaration.** A first argument nested two deep is out of
scope here, as an unrecognised spelling is: the boundary is stated rather
than chased.
"""


def pda_modules() -> tuple[tuple[str, str], ...]:
    """Every PDA module as ``(path relative to the project, its source)``.

    One walk, read once each, serving both the scope derivation and the
    ``setattr`` guard.
    """
    return tuple(
        (str(one.relative_to(PROJECT_ROOT)), one.read_text(encoding="utf-8"))
        for one in sorted(PDA_ROOT.rglob("*.py"))
    )


KNOWN_WRITERS = frozenset(
    {
        "src/lexic/parsing/pda/compiler/program/bake/product.py",
        "src/lexic/parsing/pda/compiler/program/flatten.py",
        "src/lexic/parsing/pda/compiler/program/lower.py",
    }
)
"""The modules matching :data:`WRITES_PLAN` or :data:`WRITES_BUILD` today.

**A SHRINK GUARD, not the scope list** — :func:`pda_sources` decides what is
scanned, and this refuses a scan that finds LESS than this.

``specialize/passes.py`` and ``specialize/frameless.py`` match NEITHER
pattern, so scanning them asserts nothing. What they write is other clone
state — ``clone.mode``, ``clone.selectors``, ``clone.default`` in `frameless`,
``arm.kinds`` and ``arm.n`` in `passes` — and **this gate pairs ``plan`` with
``build`` and nothing else**, so they are outside the floor.
"""


def pda_sources() -> tuple[str, ...]:
    """Every module under the PDA that writes clone build state.

    DERIVED, and the distinction is the point: a hand list is a SCOPE, so a
    module missing from it is never scanned and the gate FAILS OPEN. Walking
    for the writers makes staleness go RED — a module that stops writing drops
    out and the shrink guard complains — instead of silently checking less.

    The rule: declare when staleness fails loudly, derive when staleness
    quietly checks less.
    """
    return tuple(
        path
        for path, source in pda_modules()
        if WRITES_PLAN.search(source) or WRITES_BUILD.search(source)
    )


PDA_SOURCES = pda_sources()
"""Every module that may write clone build state, found by walking for them."""


def test_no_setattr_escape() -> None:
    """No module reaches ``plan`` or ``build`` through ``setattr``.

    The one spelling a writer might reach for without meaning to evade the
    gate, and the reason :data:`WRITES_PLAN`'s declared contract can be a
    contract: a name-built write would be invisible to the scan and to the
    per-module assertion alike.

    **There is no ``setattr`` call under the tree, so a green run here says
    nothing about the pattern.** What the pattern does is established by
    probing it directly: a four-line wrapped call on ``"plan"`` matches, an
    inline one matches, one whose first argument is a call containing a comma
    matches, and a file holding an unrelated ``setattr`` beside a later
    ``, "plan"`` does NOT.
    """
    for path, source in pda_modules():
        found = SETATTR_ESCAPE.search(source)
        assert found is None, (
            f"{path}:{source.count(chr(10), 0, found.start()) + 1} sets plan "
            "or build by name — the declared spellings are `.plan =` and "
            "`.build =`"
        )


def test_the_derived_scope_still_covers_what_it_did() -> None:
    """The derivation cannot silently shrink.

    A pattern that matches nothing empties the scope, and every parametrised
    case then vanishes into a green run. This is what refuses that.
    """
    assert PDA_SOURCES, "the writer scan found no module — the gate would be empty"
    missing = KNOWN_WRITERS - set(PDA_SOURCES)
    assert not missing, (
        f"the scan does not find {sorted(missing)} — either they no longer "
        "write build state, or the patterns no longer match what they write"
    )


def capture_state(width: int):
    """A ``(text, ends, sinks)`` wide enough for any plan of ``width`` fields.

    The values are arbitrary and distinct — what matters is that reading the
    wrong item, or the wrong lane, cannot coincide with reading the right one.
    """
    return (
        "abcdefghijklmnopqrstuvwxyz",
        list(range(width + 2)),
        [[object()] for _ in range(width + 2)],
    )


@pytest.mark.parametrize(
    "name",
    [n for n in (*GBNF_GRAMMARS, *ABNF_GRAMMARS) if n not in NEEDS_VOCABULARY],
)
def test_every_clone_s_build_agrees_with_its_own_plan(name: str) -> None:
    """Across the whole corpus, no builder reads a plan other than its own."""
    compiled = compile_from_path(GROUND_TRUTH / name)
    tables = pda_tables(compiled.codegen_grammar, compiled.product)
    seen: dict[int, FlatClone] = {}
    every_clone(tables.program.start, seen)

    checked = 0
    for clone in seen.values():
        if clone.build is no_shape_build or not clone.plan:
            continue
        width = max(item for _m, item, _lo, _d in clone.plan) + 1
        text, ends, sinks = capture_state(width)
        built = clone.build(text, ends, sinks)
        assert list(built) == plan_means(clone.plan, text, ends, sinks), (
            f"{name}: {clone.name} builds something its plan does not say"
        )
        checked += 1
    assert checked, f"{name} composed no builder — the walk proved nothing"


@pytest.mark.parametrize("path", PDA_SOURCES)
def test_a_writer_of_plan_also_writes_build(path: str) -> None:
    """``plan`` and ``build`` are written together or not at all.

    Static, because the failure this guards is a pass that rewrites ``plan``
    AFTER the bake — which leaves a consistent-looking artefact and shows up
    only as wrong values much later.
    """
    lines = (PROJECT_ROOT / path).read_text(encoding="utf-8").splitlines()
    writes_plan = {at for at, line in enumerate(lines) if WRITES_PLAN.search(line)}
    writes_build = {at for at, line in enumerate(lines) if WRITES_BUILD.search(line)}
    for at in sorted(writes_plan):
        near = range(at - 12, at + 13)
        assert any(other in near for other in writes_build), (
            f"{path}:{at + 1} writes .plan with no .build beside it — a builder "
            "composed from the old plan would silently outlive it"
        )
