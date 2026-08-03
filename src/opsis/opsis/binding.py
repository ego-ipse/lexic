"""Where a class and its fields COME FROM — the binding, and the fold.

Two windows over the middle of the compile, and the answer to the same
question asked twice. The binding says what each rule became: a class, a
kind, and a field name per bound part. The fold says how one is BUILT:
per rule, the constructor and the parts it takes.

Field names are the thing people ask about most, so the point of both
windows is that the answer is derivable and shown, never guessed.
"""

from __future__ import annotations

from lexic.compile import CompiledGrammar
from lexic.ir import IrDoc
from lexic.parsing import compile_tables
from lexic.parsing.earley.lexruns import run_candidates
from opsis.opsis.canvas import el
from opsis.opsis.canvas import text as _text
from opsis.opsis.engine import walked
from opsis.opsis.views import facts, grid, panel, refusal
from opsis.praxis.reading import FOREIGN

__all__ = ["binding_view", "fold_view", "runs_of"]


def binding_view(compiled: CompiledGrammar) -> IrDoc:
    """Per rule: the class it became, and what its fields are called.

    A generated field name is not arbitrary and is not stored anywhere
    else — it falls out of the bound part's own type. Seeing the rule
    and the name side by side is what makes that checkable.
    """
    rows = [(str(name), _bound(body)) for name, body in compiled.fold.bodies.items()]
    if not rows:
        return refusal("this grammar bound nothing — it has no fold bodies")
    return panel(
        f"{len(rows)} rules bound · rule → the class it became, and its fields",
        grid(rows),
    )


def _bound(body: object) -> str:
    """One fold body as the class and field names it produces."""
    ctor = getattr(body, "ctor", None)
    kind = getattr(body, "kind", "")
    fields = getattr(body, "fields", ())
    names = ", ".join(str(getattr(f, "name", "?")) for f in fields) or "no fields"
    return f"{_ctor_name(ctor)} · {kind} · {names}"


def _ctor_name(ctor: object) -> str:
    """What a fold body constructs, by name."""
    if ctor is None:
        return "—"
    inner = getattr(ctor, "fn", None) or getattr(ctor, "cls", None)
    return getattr(inner, "__name__", None) or str(ctor)[:40]


def fold_view(compiled: CompiledGrammar) -> IrDoc:
    """How an instance is built: per rule, the constructor and its parts.

    The middle of the field-to-rule story — a row here names both the
    rule it fires on and the model field it fills, which is why the same
    hover lights up both sides.
    """
    rows: list[IrDoc] = []
    for name, body in compiled.fold.bodies.items():
        for field in getattr(body, "fields", ()):
            rows.append(
                el(
                    "div",
                    {"class": "cell", "data-rule": str(name)},
                    el("code", None, _text(f"{name}.{getattr(field, 'name', '?')}")),
                    el("span", None, _text(_field(field))),
                )
            )
    if not rows:
        return refusal("this grammar's fold takes no fields")
    return panel(
        f"{len(rows)} fields, over {len(compiled.fold.bodies)} rules · "
        "each row is a rule AND the model field it fills",
        el("div", {"class": "grid"}, *rows),
    )


def _field(field: object) -> str:
    """One field fold, as what it takes and from where."""
    item = getattr(field, "item", "?")
    mode = getattr(field, "mode", "?")
    lo = getattr(field, "lo", "?")
    return f"part {item} · {mode} · min {lo}"


def _shape(shape: tuple[frozenset[str], bool, int]) -> str:
    """One run terminal, as what it accepts and whether it may be empty."""
    chars, empty, _rid = shape
    return f"{len(chars)} chars{' · may be empty' if empty else ''}"


def runs_of(compiled: CompiledGrammar) -> IrDoc:
    """The lexical layer this grammar DERIVES — where its runs are.

    Not a layer anybody declared: run terminals are found in the
    grammar, and finding them is what makes a resume refuse later. So
    the window that shows them is also the explanation for that refusal.
    """
    try:
        tables = compile_tables(walked(compiled))
        found = run_candidates(tables)
    except FOREIGN as exc:
        return refusal(f"{type(exc).__name__}: {exc}")
    if not found:
        return panel(
            "no run terminals: this grammar has no derived lexical layer, so "
            "a resumable parse over it can be extended"
        )
    rows = [
        (name, _shape(shape), "collapsed into one terminal")
        for name, shape in sorted(found.items())
    ]
    return facts(
        rows,
        el(
            "div",
            {"class": "claim no"},
            _text(
                f"{len(rows)} run-collapsed rule{'s' if len(rows) != 1 else ''} — a "
                "resumable parse over this "
                "grammar refuses `extend`, and this is why"
            ),
        ),
    )
