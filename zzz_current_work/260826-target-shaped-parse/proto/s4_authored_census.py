"""Census the authored surfaces' completions, and the channel they resolve through.

The three compile-time surfaces — the IR-constructor notation, the generated
self-grammar, and templating's span product — author their rules in the
product vocabulary and nothing else. This witness holds that to its two
load-bearing claims.

**Every transform is reachable by name.** An authored record holds a registry
KEY, never a callable, and lowering resolves that key through the surface's own
whitelist. So the census walks every authored rule, collects the symbol each
one names, and proves the name resolves — which is what makes the no-``eval``
boundary a property of the data rather than a convention. A key that resolved
to nothing would be a completion that cannot run, discovered at parse time.

**The shared idioms are accounted for by name.** `passthrough`, `first_rest`,
`decode_int`, `absent_tail` and its `ABSENT` sentinel are the vocabulary the
surfaces share; this prints who names each one, so a deletion that orphans an
idiom, or an idiom that quietly lost its last caller, is visible rather than
inferred.

Run: `uv run python zzz_current_work/260826-target-shaped-parse/proto/s4_authored_census.py`
"""

from __future__ import annotations

from collections import Counter

import lexic.compile.module.selfgrammar as selfgrammar
import lexic.compile.notation.parse as notation
from lexic.compile.foldkit import ABSENT, FOLD_SYMBOLS, AuthoredRule

SHARED = ("passthrough", "first_rest", "decode_int", "absent_tail")
"""The shared idiom keys this effort's foldkit bullet must account for."""


class Defect(AssertionError):
    """A claim this witness makes that the surfaces do not support."""


def _check(claim: str, held: bool) -> None:
    """Print one claim's verdict, and raise when it does not hold."""
    print(f"  {'ok ' if held else 'BAD'}\t{claim}")
    if not held:
        raise Defect(f"s4 authored census: {claim}")


def _census(
    label: str,
    rules: dict[str, AuthoredRule],
    registry: dict[str, object],
) -> Counter:
    """One surface's symbol usage, proved resolvable against its registry."""
    named = Counter(rule.symbol for rule in rules.values() if rule.symbol)
    passthroughs = sum(1 for rule in rules.values() if not rule.symbol)
    unresolved = sorted(key for key in named if key not in registry)
    print(
        f"\n{label}\t{len(rules)} rules, {passthroughs} alternation pass-throughs, "
        f"{len(named)} distinct transforms over {sum(named.values())} rules"
    )
    _check(
        f"{label}: every named transform resolves in its own registry",
        not unresolved,
    )
    return named


def the_authored_surfaces_name_only_resolvable_transforms() -> Counter:
    """Both parse surfaces' rules name transforms their registry carries."""
    total = Counter()
    total += _census("notation", notation.NOTATION_RULES, notation.NOTATION_SYMBOLS)
    total += _census("module", selfgrammar.MODULE_RULES, selfgrammar.MODULE_SYMBOLS)
    return total


def no_authored_record_holds_a_callable() -> None:
    """A rule's transform is a string key — the boundary, as data."""
    for label, rules in (
        ("notation", notation.NOTATION_RULES),
        ("module", selfgrammar.MODULE_RULES),
    ):
        holders = sorted(
            name for name, rule in rules.items() if not isinstance(rule.symbol, str)
        )
        _check(f"{label}: no authored rule holds a callable", not holders)


def the_shared_idioms_are_accounted_for(named: Counter) -> None:
    """Each shared idiom is in the registry, and its callers are named."""
    print()
    for key in SHARED:
        users = named.get(key, 0)
        print(f"idiom\t{key}: registered={key in FOLD_SYMBOLS} named-by={users} rules")
        _check(f"the shared idiom {key!r} is registered", key in FOLD_SYMBOLS)
    _check(
        "the ABSENT sentinel is a distinct object the surfaces can test against",
        ABSENT is not None and ABSENT is not False,
    )


def the_symbol_channel_is_the_registry_the_effort_must_preserve() -> None:
    """`FOLD_SYMBOLS` is the no-`eval` channel this effort requires kept intact."""
    print(f"\nsymbols\tFOLD_SYMBOLS names {sorted(FOLD_SYMBOLS)}")
    _check("the shared registry is non-empty", bool(FOLD_SYMBOLS))
    _check(
        "every registered symbol is callable",
        all(callable(value) for value in FOLD_SYMBOLS.values()),
    )
    _check(
        "the module registry extends the notation one rather than replacing it",
        set(notation.NOTATION_SYMBOLS) <= set(selfgrammar.MODULE_SYMBOLS),
    )


def the_seeded_controls_are_caught() -> None:
    """An unresolvable key is refused — so the census is not decoration."""
    seeded = dict(notation.NOTATION_RULES)
    seeded["--seeded"] = AuthoredRule("no_such_transform")
    try:
        _census("control", seeded, notation.NOTATION_SYMBOLS)
    except Defect:
        print("control\tan unresolvable transform key is refused")
        return
    raise Defect(
        "s4 authored census: an unresolvable key passed, so the census says nothing"
    )


def main() -> None:
    """Run the census, its claims and its control; any disagreement raises."""
    named = the_authored_surfaces_name_only_resolvable_transforms()
    no_authored_record_holds_a_callable()
    the_shared_idioms_are_accounted_for(named)
    the_symbol_channel_is_the_registry_the_effort_must_preserve()
    the_seeded_controls_are_caught()
    print("\ns4 authored census: OK")


if __name__ == "__main__":
    main()
