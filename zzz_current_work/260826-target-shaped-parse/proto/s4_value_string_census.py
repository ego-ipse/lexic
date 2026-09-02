"""Census the value-string specialization's ACTUAL headroom, before building it.

The value-string bullet would compile one exact recognizer consult for an
eligible `value_str` occurrence in place of its per-character program. That is
only worth building if the residual — the occurrences the existing run-table
specializations do NOT already serve — is large enough to matter. This counts
it, per ground-truth grammar, before a line of the consult is written.

Four columns, in the order the decision needs them:

* **vstr** — how many contextual clones complete as a value whose text IS its
  own matched extent;
* **served** — how many of those the flat program ALREADY answers without a
  frame, through the chartable, run-arm and inline-reference specializations;
* **eligible** — how many of the rest the authoritative regular proof accepts,
  which is the only licence the bullet permits (not the fail-soft scanner's);
* **residual** — eligible and not already served: the population a consult
  could actually take.

The last column is the one that decides. `docs/STYLE.md` §7 prices a removed
Python call at roughly 40-50 ns against rows running 1800-3000 ns per
character, so a population under about one call per character cannot reach one
percent however often it hits. A residual that cannot reach one percent stops
the bullet there, and saying so with numbers is the point of this file.

Run: `uv run python zzz_current_work/260826-target-shaped-parse/proto/s4_value_string_census.py`
"""

from __future__ import annotations

from pathlib import Path

from lexic.compile import compile_from_path
from lexic.exceptions import LexicError
from lexic.parsing.pda.compiler.program.flatten import FlatClone
from lexic.parsing.pda.compiler.program.opcodes import BUILD_VALUE_STR
from lexic.parsing.pda.core.charsets import CharSet
from lexic.parsing.product import prove_regular
from lexic.parsing.products import _model_product

GROUND_TRUTH = Path(__file__).resolve().parents[3] / "resources" / "ground_truth"
"""The corpus every number below is measured over."""

ANYTHING = CharSet(frozenset(), negated=True)
"""The continuation a census asks under: the proof's obligations against the
widest possible follow set. A real consult would be proved against the
occurrence's own follow, which can only be narrower, so accepting here is the
generous reading and the residual it reports is an UPPER bound."""


class Defect(AssertionError):
    """A claim this census makes that the corpus does not support."""


class Row:
    """One grammar's counts, and the reasons behind them."""

    __slots__ = ("name", "clones", "vstr", "served", "eligible", "residual")

    def __init__(self, name: str) -> None:
        """Start an empty row for one grammar."""
        self.name = name
        self.clones = 0
        self.vstr = 0
        self.served = 0
        self.eligible = 0
        self.residual = 0


def _grammars() -> list[Path]:
    """Every ground-truth fixture, in a stable order."""
    found = sorted(
        path
        for suffix in ("*.gbnf", "*.abnf", "*.ebnf")
        for path in GROUND_TRUTH.glob(suffix)
    )
    if len(found) < 8:
        raise Defect(
            f"s4 value-string census: only {len(found)} fixtures under "
            f"{GROUND_TRUTH} — the sweep is not reading the real corpus"
        )
    return found


def _all_clones(tables: object) -> list[FlatClone]:
    """Every live flat clone the program reaches, from its entry."""
    seen: dict[int, FlatClone] = {}
    stack = [getattr(tables, "program").start]
    while stack:
        clone = stack.pop()
        if not isinstance(clone, FlatClone) or id(clone) in seen:
            continue
        seen[id(clone)] = clone
        arms = [arm for _chars, _negated, arm in clone.selectors]
        if clone.default is not None:
            arms.append(clone.default)
        for arm in arms:
            if hasattr(arm, "payloads"):
                stack.extend(arm.payloads)
    return list(seen.values())


def _already_served(clone: FlatClone) -> bool:
    """Whether the flat program already answers this clone without a frame.

    The three existing specializations, by their own names: a one-character
    language tabled to a dict lookup, a repetition collapsed to one run arm,
    and a clone the entry path marks frame-less.
    """
    return clone.chartable is not None or clone.runarm is not None or clone.leaf


def _census(path: Path) -> Row | None:
    """One grammar's four counts, or ``None`` when it compiles no PDA.

    A token-terminal grammar has no character-level predictive program to
    specialize, so it is reported as skipped rather than counted as zero —
    counting it would quietly shrink the population the decision reads.
    """
    row = Row(path.name)
    compiled = compile_from_path(path)
    try:
        product = _model_product(compiled.codegen_grammar, compiled.product)
    except LexicError:
        return None
    rules = {str(rule.name): rule for rule in compiled.codegen_grammar.rules}
    clones = _all_clones(product.pda)
    row.clones = len(clones)
    for clone in clones:
        if clone.mode != BUILD_VALUE_STR:
            continue
        row.vstr += 1
        served = _already_served(clone)
        row.served += served
        name = str(clone.name or "")
        if name not in rules:
            continue
        if prove_regular(rules, name, ANYTHING) is None:
            continue
        row.eligible += 1
        row.residual += not served
    return row


def _price(residual: int, vstr: int) -> str:
    """What §7's arithmetic says about a residual of this size."""
    if residual == 0:
        return "no consult has anything to take"
    share = residual / vstr if vstr else 0.0
    return f"{residual} occurrence(s), {share:.0%} of the value-string population"


def main() -> None:
    """Count, print, and state what the residual can and cannot reach."""
    paths = _grammars()
    counted = [(path, _census(path)) for path in paths]
    skipped = [path.name for path, row in counted if row is None]
    rows = [row for _p, row in counted if row is not None]
    print(
        f"{'grammar':<22}{'clones':>8}{'vstr':>7}{'served':>8}"
        f"{'eligible':>10}{'residual':>10}"
    )
    for row in rows:
        print(
            f"{row.name:<22}{row.clones:>8}{row.vstr:>7}{row.served:>8}"
            f"{row.eligible:>10}{row.residual:>10}"
        )
    vstr = sum(row.vstr for row in rows)
    served = sum(row.served for row in rows)
    eligible = sum(row.eligible for row in rows)
    residual = sum(row.residual for row in rows)
    print(
        f"\n{'TOTAL':<22}{sum(r.clones for r in rows):>8}{vstr:>7}"
        f"{served:>8}{eligible:>10}{residual:>10}"
    )
    print(f"\nserved\t\t{served} of {vstr} value-string clones need no frame today")
    print(f"eligible\t{eligible} pass the authoritative regular proof")
    print(f"residual\t{_price(residual, vstr)}")
    print(
        "\nprice\t\ta removed Python call is worth ~40-50 ns against rows at "
        "1800-3000 ns/char,\n\t\tso a residual under ~1 call per character "
        "cannot reach 1% however often it hits."
    )
    if skipped:
        print(f"\nskipped\t\t{len(skipped)} grammar(s) compile no PDA: {skipped}")
    print("\ns4 value-string census: OK")


if __name__ == "__main__":
    main()
