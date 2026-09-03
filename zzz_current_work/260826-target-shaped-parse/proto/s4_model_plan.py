"""The ported validation-skip licence grants exactly what the deleted one did.

`model_plan` used to compute a rule's validation-skip licence by calling the
FOLD's `_fast_ctor` over reconstructed `FieldFold`s. The fold is deleted, so
the predicate was ported to `_fast_licence`, which asks the same question from
the captures and the optional set the constructor is actually built from.

A ported predicate is a claim, and the claim is not "it looks equivalent" —
it is that the licence SET is identical, rule by rule, over the whole
ground-truth corpus. So this runs the STARTING COMMIT's own `_fast_ctor` and
`_fold_fields`, taken by `git show` rather than transcribed, against the live
`_fast_licence`, and compares.

Only the two record types the old code named (`FastCtor`, `FieldFold`) are
re-declared here, because they were deleted with the fold; both were plain
NamedTuples and the old ALGORITHM is executed verbatim from the commit. That
is what keeps this a control rather than a comparison of my new code with my
own paraphrase of the old.

Run: `uv run python zzz_current_work/260826-target-shaped-parse/proto/s4_model_plan.py`
"""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path
from typing import Any, Callable, Mapping, NamedTuple, Sequence

from lexic.compile import compile_from_path
from lexic.compile.pipeline.naming import VALUE_FIELD
from lexic.compile.pipeline.synthesis import _fast_licence, _model_captures
from lexic.model import GrammarModel

BASE = "dffa821f"
"""The starting commit whose licence this port must reproduce exactly."""

SOURCE = "src/lexic/compile/pipeline/synthesis.py"
"""Where the deleted predicate lived at that commit."""

REPO = Path(__file__).resolve().parents[3]
GROUND_TRUTH = REPO / "resources" / "ground_truth"


class Defect(AssertionError):
    """A claim this witness makes that the two predicates do not support."""


class FastCtor(NamedTuple):
    """The deleted licence record, re-declared so the old code can run."""

    make: Callable[[list[object]], object]
    defaults: Mapping[str, object]
    fields: tuple[str, ...] = ()


class FieldFold(NamedTuple):
    """The deleted bound-field record, re-declared so the old code can run."""

    item: int
    mode: str
    name: str
    lo: int


def _old_predicates() -> tuple[Callable[..., Any], Callable[..., Any]]:
    """`_fast_ctor` and `_fold_fields` as the starting commit defined them.

    Parsed out of the commit's own source text and executed here, so the
    comparison runs the real deleted logic rather than a paraphrase of it.
    """
    done = subprocess.run(
        ["git", "show", f"{BASE}:{SOURCE}"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    if done.returncode != 0:
        raise Defect(f"s4 model plan: cannot read {SOURCE} at {BASE}")
    tree = ast.parse(done.stdout)
    wanted = {"_fast_ctor", "_fold_fields"}
    found = [
        n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in wanted
    ]
    if len(found) != 2:
        raise Defect(
            f"s4 model plan: {BASE} defines {sorted(f.name for f in found)}, "
            f"not both of {sorted(wanted)} — the control is not reading the "
            "predicate it claims to"
        )
    namespace: dict[str, Any] = {
        "FastCtor": FastCtor,
        "FieldFold": FieldFold,
        "GrammarModel": GrammarModel,
        "VALUE_FIELD": VALUE_FIELD,
        "Sequence": Sequence,
    }
    # The two functions are executed from the commit's own text rather than
    # transcribed, which is the whole point: a re-typed predicate would only
    # prove the port agrees with my reading of it. This is witness code under
    # `proto/`, never `src`, and the repository's no-`exec` rule is about the
    # shipped engine.
    runner = compile(ast.Module(body=found, type_ignores=[]), SOURCE, "exec")
    exec(runner, namespace)
    return namespace["_fast_ctor"], namespace["_fold_fields"]


def _grammars() -> list[Path]:
    """Every ground-truth fixture, in a stable order."""
    found = sorted(
        path
        for suffix in ("*.gbnf", "*.abnf", "*.ebnf")
        for path in GROUND_TRUTH.glob(suffix)
    )
    if len(found) < 8:
        raise Defect(f"s4 model plan: only {len(found)} fixtures — not the corpus")
    return found


def the_ported_licence_is_the_deleted_one(
    old_fast_ctor: Callable[..., Any], old_fold_fields: Callable[..., Any]
) -> tuple[int, int]:
    """Both predicates grant the same licence on every rule of every grammar."""
    rules = granted = 0
    for path in _grammars():
        compiled = compile_from_path(path)
        by_name = {str(r.name): r for r in compiled.codegen_grammar.rules}
        for bound in compiled.moments.binding:
            if bound.kind == "alternation":
                continue
            arms = [arm for arm in by_name[bound.rule_name].body if arm]
            items = arms[0] if bound.kind == "sequence" and arms else ()
            cls = compiled.classes[bound.class_name]
            _specs, names, optional = _model_captures(bound, items)
            new = _fast_licence(cls, bound.kind, names, optional) is not None
            old = (
                old_fast_ctor(cls, bound.kind, old_fold_fields(bound, items))
                is not None
            )
            if new != old:
                raise Defect(
                    f"s4 model plan: {path.name}/{bound.rule_name}: the port "
                    f"grants {new} where {BASE} granted {old}"
                )
            rules += 1
            granted += new
    return rules, granted


def both_refuse_the_same_way(
    old_fast_ctor: Callable[..., Any], old_fold_fields: Callable[..., Any]
) -> int:
    """The two predicates also agree where the licence must be REFUSED.

    The corpus grants uniformly, so the rule-by-rule sweep above only exercises
    the granting path. This drives the refusing branches deliberately: a field
    the completion may leave unset with no default to fall back on is the exact
    case the licence exists to catch, and skipping validation there would build
    a model with a hole in it.
    """
    checked = 0
    for path in _grammars():
        compiled = compile_from_path(path)
        by_name = {str(r.name): r for r in compiled.codegen_grammar.rules}
        for bound in compiled.moments.binding:
            if bound.kind != "sequence":
                continue
            arms = [arm for arm in by_name[bound.rule_name].body if arm]
            if not arms:
                continue
            items = arms[0]
            cls = compiled.classes[bound.class_name]
            _specs, names, optional = _model_captures(bound, items)
            defaults = cls.fast_construct()[1]
            # Only a gtext/model bind can be absent at all, so only those may be
            # made absent-admitting: forcing it on a text bind would put the two
            # predicates in a state the pipeline never builds, and the
            # disagreement would be the probe's, not the port's.
            without = tuple(
                name
                for name, bind in bound.fields.items()
                if name in names
                and name not in defaults
                and bind.mode in ("gtext", "model")
            )
            if not without or len(names) != len(set(names)):
                continue
            at = names.index(without[0])
            new = (
                _fast_licence(cls, bound.kind, names, tuple(sorted({*optional, at})))
                is not None
            )
            fields = tuple(
                field._replace(lo=0) if field.name == without[0] else field
                for field in old_fold_fields(bound, items)
            )
            old = old_fast_ctor(cls, bound.kind, fields) is not None
            if new != old:
                raise Defect(
                    f"s4 model plan: {path.name}/{bound.rule_name}: on a "
                    f"defaultless optional the port says {new}, {BASE} says {old}"
                )
            checked += 1
    if checked < 10:
        raise Defect(
            f"s4 model plan: only {checked} refusal cases reached — the "
            "refusing branch is not being exercised"
        )
    return checked


def the_control_is_live(
    old_fast_ctor: Callable[..., Any], old_fold_fields: Callable[..., Any]
) -> None:
    """A seeded divergence is caught — so agreement is not vacuous.

    The seed withdraws the class-level half from the OLD predicate only. If the
    comparison could not see one side change, it would agree with anything.
    """
    compiled = compile_from_path(GROUND_TRUTH / "json.gbnf")
    by_name = {str(r.name): r for r in compiled.codegen_grammar.rules}
    for bound in compiled.moments.binding:
        if bound.kind == "alternation":
            continue
        arms = [arm for arm in by_name[bound.rule_name].body if arm]
        items = arms[0] if bound.kind == "sequence" and arms else ()
        cls = compiled.classes[bound.class_name]
        _specs, names, optional = _model_captures(bound, items)
        if not _fast_licence(cls, bound.kind, names, optional):
            continue
        # the same call with the kind forced to the one branch that refuses
        seeded = old_fast_ctor(cls, "alternation", old_fold_fields(bound, items))
        if seeded is None:
            print("control\ta seeded refusal diverges from the live grant")
            return
    raise Defect("s4 model plan: the seeded divergence was not observable")


def main() -> None:
    """Run the licence differential and its control; any divergence raises."""
    old_fast_ctor, old_fold_fields = _old_predicates()
    rules, granted = the_ported_licence_is_the_deleted_one(
        old_fast_ctor, old_fold_fields
    )
    print(
        f"licence\t{rules} rules across the corpus, {granted} granted — "
        f"identical to {BASE} rule by rule"
    )
    refusals = both_refuse_the_same_way(old_fast_ctor, old_fold_fields)
    print(
        f"refusal\t{refusals} defaultless-optional cases — both predicates "
        "agree on the branch the licence exists to catch"
    )
    the_control_is_live(old_fast_ctor, old_fold_fields)
    print("\ns4 model plan\tPASS\tthe ported licence IS the deleted one")


if __name__ == "__main__":
    main()
