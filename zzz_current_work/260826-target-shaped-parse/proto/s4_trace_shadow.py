"""Witness — the watched kernel shadows the real completion surfaces.

`parsing/trace.py` is a public `PdaKernel` subclass whose whole correctness
rests on two structural facts, neither of which a behavioural test can see:

1. **Every override shadows a method that exists**, with the base's own
   signature. A watched run is a RE-RUN of the ordinary path, so an override
   whose name or arity has drifted away from its base stops intercepting and
   the account silently loses events instead of failing. Type-variable names
   are allowed to differ — the subclass binds `M` where the mixin spells
   `Carry` — but nothing else is.

2. **Nothing under `pda/` imports the trace.** That is what makes "the
   unwatched path pays nothing" a property of the arrow rather than a claim:
   if the runtime cannot see this module, no flag of it can reach the paid
   loop.

It also pins the third fact this round moved: the watched kernel's island
channel is the bound product's `ProductExecutor`, not a fold, and it reaches
the base constructor unchanged.

Run: `uv run python zzz_current_work/260826-target-shaped-parse/proto/s4_trace_shadow.py`
"""

from __future__ import annotations

import inspect
import pathlib
import re
from typing import Any

from lexic.parsing.pda.runtime.kernel.kernel import PdaKernel
from lexic.parsing.product import ProductExecutor
from lexic.parsing.trace import WatchedKernel, watch

SRC = pathlib.Path(__file__).resolve().parents[3] / "src" / "lexic"
"""The source tree this witness reads for the import-arrow check."""

OWN_HELPERS = frozenset({"_at", "_flush", "_here", "_note", "watched_run"})
"""Methods the watch adds rather than shadows — its own recording vocabulary."""

TYPE_VARS = re.compile(r"\b(?:Carry|M)\b")
"""The two spellings of the one carrier parameter, normalised before compare."""


class Defect(AssertionError):
    """A structural claim this witness makes that the tree does not support."""


def _normalised(signature: inspect.Signature) -> str:
    """One signature with its carrier type-variable spelling erased."""
    return TYPE_VARS.sub("<carry>", str(signature))


def _overrides(watch_class: type) -> list[str]:
    """One watch class's shadowing methods — its recording helpers excluded."""
    return sorted(
        name
        for name, value in vars(watch_class).items()
        if callable(value) and not name.startswith("__") and name not in OWN_HELPERS
    )


def every_override_shadows_a_real_method(watch_class: type = WatchedKernel) -> int:
    """Each override names a base method and matches its signature."""
    overrides = _overrides(watch_class)
    if not overrides:
        raise Defect("s4 trace shadow: the watch overrides nothing at all")
    for name in overrides:
        base = getattr(PdaKernel, name, None)
        if base is None:
            raise Defect(
                f"s4 trace shadow: {name!r} shadows nothing — the base method it "
                "was written against is gone, so the watch no longer intercepts it"
            )
        sub_sig = _normalised(inspect.signature(getattr(watch_class, name)))
        base_sig = _normalised(inspect.signature(base))
        if sub_sig != base_sig:
            raise Defect(
                f"s4 trace shadow: {name!r} has drifted from its base\n"
                f"    watch: {sub_sig}\n    base : {base_sig}"
            )
    print(f"overrides\t{len(overrides)} shadow a real method with the base signature")
    return len(overrides)


def the_watch_carries_no_erasure(watch_class: type = WatchedKernel) -> None:
    """No override widens the carrier to ``Any`` where its base is generic."""
    widened = []
    for name in _overrides(watch_class):
        base = getattr(PdaKernel, name, None)
        if base is None:
            continue
        sub_sig = str(inspect.signature(getattr(watch_class, name)))
        base_sig = str(inspect.signature(base))
        if "Any" in sub_sig and "Any" not in base_sig:
            widened.append(f"{name}: {sub_sig}")
    if widened:
        raise Defect(
            "s4 trace shadow: these overrides erase a carrier their base keeps "
            "generic — " + "; ".join(widened)
        )
    print("carrier\t\tno override widens a generic base to Any")


def the_runtime_cannot_see_the_watch() -> None:
    """Nothing under ``pda/`` imports the trace module."""
    modules = sorted((SRC / "parsing" / "pda").rglob("*.py"))
    # A wrong root would make this scan find nothing and pass saying nothing,
    # which is the whole failure mode a structural check has.
    if len(modules) < 20:
        raise Defect(
            f"s4 trace shadow: only {len(modules)} modules under {SRC}/parsing/pda "
            "— the scan is not reading the real tree, so its verdict is vacuous"
        )
    offenders = [
        str(path.relative_to(SRC))
        for path in modules
        if "lexic.parsing.trace" in path.read_text()
    ]
    if offenders:
        raise Defect(
            "s4 trace shadow: the predictive runtime imports the trace, so the "
            "unwatched path can no longer be free by construction — "
            + ", ".join(offenders)
        )
    print(f"arrow\t\tnone of {len(modules)} pda/ modules imports the trace")


def the_island_channel_is_the_bound_product() -> None:
    """The watch's third parameter is the product executor, not a fold."""
    for owner, function in (
        ("WatchedKernel", WatchedKernel.__init__),
        ("watch", watch),
    ):
        annotation = str(inspect.signature(function).parameters["executor"].annotation)
        if "ProductExecutor" not in annotation:
            raise Defect(
                f"s4 trace shadow: {owner}'s island channel is {annotation!r}, "
                "not the bound product's ProductExecutor"
            )
    if not hasattr(ProductExecutor, "splice"):
        raise Defect(
            "s4 trace shadow: the executor has no occurrence completion, so an "
            "island that produces no value cannot be told from one producing None"
        )
    print("channel\t\tthe watch splices islands through the bound product")


class _DriftedWatch(WatchedKernel):
    """Control — an override whose arity no longer matches what it shadows."""

    def _complete(self, frame: list, extra: int = 0) -> None:
        """One argument more than the base; the seeded drift."""
        super()._complete(frame)


class _ErasedWatch(WatchedKernel):
    """Control — an override that widens a carrier its base keeps generic."""

    def _enter(self, clone: Any, out: list[Any]) -> bool:
        """The base's ``FlatClone[Carry]`` / ``list[Carry]``, erased."""
        return super()._enter(clone, out)


def the_seeded_controls_are_caught() -> None:
    """Both checks refuse a seeded defect — so neither passes vacuously."""
    for label, seeded, check in (
        ("an arity drift", _DriftedWatch, every_override_shadows_a_real_method),
        ("a carrier erasure", _ErasedWatch, the_watch_carries_no_erasure),
    ):
        try:
            check(seeded)
        except Defect:
            continue
        raise Defect(
            f"s4 trace shadow: the check admitted {label}, so its green says nothing"
        )
    print("control\t\ta seeded arity drift and a seeded erasure are both refused")


def main() -> None:
    """Run every structural claim; any disagreement raises."""
    every_override_shadows_a_real_method()
    the_watch_carries_no_erasure()
    the_runtime_cannot_see_the_watch()
    the_island_channel_is_the_bound_product()
    the_seeded_controls_are_caught()
    print("\ns4 trace shadow: OK")


if __name__ == "__main__":
    main()
