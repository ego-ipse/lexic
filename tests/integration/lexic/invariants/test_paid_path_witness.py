"""The parser's per-character loop is pinned; `discovery/` is not.

**The rule.** Split discovery — the region walk, the sweep, the windowed find —
may be rewritten freely. The loop that executes once per input CHARACTER may
not change as a side effect of that work. Those two live in the same package
and are edited in the same efforts, so "did that touch the paid path?" has to
be answerable by something other than the author's recollection.

**What is pinned.** The compiled code object of each function below, as the
SEQUENCE OF ITS INSTRUCTION OPNAMES. Not the source, which reformats; not the
raw `co_code` bytes, which move when a constant is renumbered or a jump target
shifts. The opname sequence changes when an instruction is added, removed or
replaced, and not otherwise — which is exactly the granularity the rule needs.

**When this fails, it is asking a question, not reporting a defect.** A red
row means a pinned loop's instructions changed. If that was deliberate — the
loop itself was the work — regenerate the digests (below) and the diff of this
file is the record that it was intended. If it was not deliberate, something
reached the paid path that should not have.

**Regenerating.** Explicit and documented, never automatic:

    uv run python tests/integration/lexic/invariants/test_paid_path_witness.py

prints the current table. Paste it over `WITNESS` and commit that change on its
own, so the pin's history reads as a list of deliberate decisions.

**Interpreter sensitivity, stated.** Opnames are a property of the CPython
version that compiled them, so an interpreter upgrade will move every row at
once. That signature — all of them, together — is the tell, and the response is
to regenerate rather than to investigate.
"""

from __future__ import annotations

import dis
import hashlib
from collections.abc import Callable

import pytest

from lexic.parsing.earley.kernel.loop.kernel import Kernel
from lexic.parsing.pda.runtime import matchers
from lexic.parsing.pda.runtime.kernel.kernel import PdaKernel

PAID: dict[str, tuple[object, str]] = {
    # The PDA's per-character matching — one call per terminal, looping per char.
    "matchers.match_cc1": (matchers, "match_cc1"),
    "matchers.match_lit": (matchers, "match_lit"),
    "matchers.match_cc": (matchers, "match_cc"),
    "matchers.match_arm": (matchers, "match_arm"),
    "matchers.match_chartable": (matchers, "match_chartable"),
    "matchers.vstr_once": (matchers, "vstr_once"),
    "matchers.run_span_once": (matchers, "run_span_once"),
    "matchers.select_arm": (matchers, "select_arm"),
    # The PDA driver: the loop those matchers are called from.
    "PdaKernel._drive": (PdaKernel, "_drive"),
    "PdaKernel._quant_step": (PdaKernel, "_quant_step"),
    "PdaKernel._match_span": (PdaKernel, "_match_span"),
    # Earley's paid loop, for the route that does not take the PDA.
    "Kernel.run": (Kernel, "run"),
    "Kernel._close": (Kernel, "_close"),
    "Kernel._scan": (Kernel, "_scan"),
    "Kernel._advance_all": (Kernel, "_advance_all"),
}
"""Every function that runs per input character, or drives one that does.

Held as ``(owner, attribute name)`` rather than as references: the witness is
asking what a module or class DEFINES under a name, which is a lookup in that
owner's own table, not a reach into someone's private attribute.

Named individually rather than swept: a sweep would silently start pinning
whatever was added next, and the point is that this list is a decision someone
made.
"""

WITNESS: dict[str, str] = {
    "Kernel._advance_all": "56e7c5a8e276af55",
    "Kernel._close": "2705b7a15a0c4493",
    "Kernel._scan": "f65fdad568fc8431",
    "Kernel.run": "9a328778d4035968",
    "PdaKernel._drive": "ba05ca518cf2dc27",
    "PdaKernel._match_span": "c8e6c3f1fd849ad7",
    "PdaKernel._quant_step": "1c88d7247121a287",
    "matchers.match_arm": "483581add68bea95",
    "matchers.match_cc": "6b78e9f226877ddf",
    "matchers.match_cc1": "93cc598602726811",
    "matchers.match_chartable": "336772203f653b76",
    "matchers.match_lit": "16c3da82cab78248",
    "matchers.run_span_once": "4ad4f40a11fa6667",
    "matchers.select_arm": "ff51ffda2566a8bb",
    "matchers.vstr_once": "12911c3d94372ea8",
}
"""The pinned instruction digests. Regenerate deliberately — see the docstring."""


def paid_function(owner: object, attr: str) -> Callable:
    """The function ``owner`` defines under ``attr``, unbound.

    A class is searched along its own MRO, because the driver's methods are
    split across the mixins the kernel is composed from and which mixin holds
    one is not this test's business.
    """
    for scope in getattr(owner, "__mro__", (owner,)):
        found = vars(scope).get(attr)
        if found is not None:
            return found
    raise AssertionError(f"{owner!r} defines no {attr!r}")


def opnames(fn: Callable) -> tuple[str, ...]:
    """One function's instruction opnames, in order."""
    return tuple(step.opname for step in dis.get_instructions(fn))


def digest_of(names: tuple[str, ...]) -> str:
    """A short, stable digest of an instruction sequence."""
    return hashlib.sha256("\n".join(names).encode()).hexdigest()[:16]


def current() -> dict[str, str]:
    """What the tree compiles to right now."""
    return {
        label: digest_of(opnames(paid_function(owner, attr)))
        for label, (owner, attr) in sorted(PAID.items())
    }


@pytest.mark.parametrize("label", sorted(PAID))
def test_the_paid_path_is_unchanged(label: str) -> None:
    """One pinned loop, one row — so a failure names the function."""
    assert label in WITNESS, f"{label} is paid-path but carries no pinned digest"
    owner, attr = PAID[label]
    assert digest_of(opnames(paid_function(owner, attr))) == WITNESS[label], (
        f"{label}'s instructions changed. If that was the work, regenerate the "
        f"table (see this module's docstring); if it was not, something reached "
        f"the paid path."
    )


def test_the_witness_names_no_function_that_is_gone() -> None:
    """A pinned name that no longer exists is a stale pin, not a pass."""
    assert set(WITNESS) == set(PAID), (
        f"pinned but not paid-path: {sorted(set(WITNESS) - set(PAID))}; "
        f"paid-path but not pinned: {sorted(set(PAID) - set(WITNESS))}"
    )


def test_one_instruction_would_fail_this() -> None:
    """The witness has single-instruction resolution — the sabotage.

    Taking a real pinned loop's instruction sequence and inserting ONE opname
    must change its digest. If it did not, every row above could pass while the
    loop it names had been rewritten.
    """
    for label, (owner, attr) in PAID.items():
        honest = opnames(paid_function(owner, attr))
        assert honest, f"{label} compiled to no instructions"
        for at in (0, len(honest) // 2, len(honest)):
            sabotaged = honest[:at] + ("NOP",) + honest[at:]
            assert digest_of(sabotaged) != digest_of(honest), (label, at)


def test_a_reordering_would_fail_this() -> None:
    """Order is part of the pin, not just the multiset of instructions."""
    for label, (owner, attr) in PAID.items():
        honest = opnames(paid_function(owner, attr))
        if len(set(honest)) < 2:
            continue
        swapped = list(honest)
        for at in range(len(swapped) - 1):
            if swapped[at] != swapped[at + 1]:
                swapped[at], swapped[at + 1] = swapped[at + 1], swapped[at]
                break
        assert digest_of(tuple(swapped)) != digest_of(honest), label


def _scan_plain(text: str, pos: int) -> int:
    """A minimal per-character loop — the sabotage's control."""
    while pos < len(text):
        pos += 1
    return pos


def _scan_with_one_more(text: str, pos: int) -> int:
    """The same loop with ONE more statement inside it."""
    seen = 0
    while pos < len(text):
        pos += 1
        seen += 1
    return pos + seen - seen


def test_a_source_level_edit_moves_the_digest() -> None:
    """The digest tracks SOURCE changes, not just hand-built sequences.

    The sabotages above perturb an instruction tuple. These two functions
    differ by one statement inside the loop, and the witness separates them —
    so a one-line edit inside a pinned loop cannot pass.
    """
    assert digest_of(opnames(_scan_plain)) != digest_of(opnames(_scan_with_one_more))


def regenerated() -> str:
    """The `WITNESS` table as source, for the documented regeneration step."""
    rows = "".join(f'    "{label}": "{value}",\n' for label, value in current().items())
    return f"WITNESS: dict[str, str] = {{\n{rows}}}"


if __name__ == "__main__":  # the documented regeneration step
    print(regenerated())
