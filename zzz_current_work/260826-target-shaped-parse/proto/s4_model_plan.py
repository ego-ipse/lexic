"""Prove the authored model product agrees with the fold it replaces.

§4 migrates generated-model parsing onto the common ABI. Before any consumer
switches, the new authoring has to say the SAME thing the old one does — same
rules, same field order, same capture per bind mode, same validation-skip
licence, same class. This is that differential, run over every ground-truth
grammar rather than a chosen one.

Two properties matter and neither is provable by reading the code:

* **Agreement.** For every rule, `model_plan`'s captures and constructor
  correspond exactly to `fold_config`'s `ModelBody` — item order, field names,
  modes, and licence.
* **Absence is carried.** A `gtext` bind whose item can match nothing is
  recorded as an OPTIONAL capture. `CaptureSpec` has no room for a
  quantifier, so if that did not survive authoring, every optional literal
  group would start arriving as `""` instead of absent — a wrong model, not a
  crash.

Uncommitted evidence, not a test. Luna owns the committed suite.
"""

from __future__ import annotations

from pathlib import Path

from lexic.compile import compile_from_path
from lexic.compile.pipeline.binding import compute_binding
from lexic.compile.foldkit import ALT_PRODUCT
from lexic.parsing.product import RecordOp
from lexic.compile.pipeline.synthesis import fold_config, model_plan
from lexic.parsing.product import CaptureMode

GROUND_TRUTH = Path(__file__).resolve().parents[3] / "resources" / "ground_truth"
STEMS = (
    "json.gbnf",
    "arithmetic.gbnf",
    "list.gbnf",
    "chess.gbnf",
    "c.gbnf",
    "markdown.gbnf",
    "json_ws.gbnf",
    "json_arr.gbnf",
)

MODE_FOR = {
    "text": CaptureMode.TEXT,
    "gtext": CaptureMode.TEXT,
    "model": CaptureMode.ONE,
    "models": CaptureMode.MANY,
    "span": CaptureMode.EXTENT,
}


def _check(claim: str, held: bool) -> None:
    """Refuse the witness the moment one claim stops holding."""
    if not held:
        raise AssertionError(f"s4 model plan: {claim}")


def _agree(label: str, compiled: object) -> tuple[int, int]:
    """Compare the authored plan against the fold for one compiled grammar."""
    grammar = compiled.codegen_grammar  # type: ignore[attr-defined]
    classes = compiled.classes  # type: ignore[attr-defined]
    binding = compute_binding(grammar)
    bodies = fold_config(grammar, binding, classes)
    plan = model_plan(grammar, binding, classes)

    folds = {str(ref): body for ref, body in bodies.items()}
    _check(
        f"{label}: the plan covers {len(plan.codes)} rules, the fold {len(folds)}",
        set(plan.codes) == set(folds),
    )

    optionals = 0
    constructors = 0
    for name, code in plan.codes.items():
        body = folds[name]
        product = plan.rules[code]

        # An alternation constructs nothing: it hands its matched arm's one
        # model on, so it takes the shared pass-through and occupies no
        # constructor row. The fold says the same thing with a stand-in ctor
        # it never calls.
        if body.kind == "alternation":
            _check(
                f"{label}/{name}: an alternation does not pass its child through",
                product == ALT_PRODUCT,
            )
            continue
        ctor = plan.constructors[constructors]
        constructors += 1

        _check(
            f"{label}/{name}: arm width {product.n_items}, the fold's "
            f"{body.n_items}",
            product.n_items == body.n_items,
        )
        _check(
            f"{label}/{name}: captured {len(product.captures)} of "
            f"{len(body.fields)} bound fields",
            len(product.captures) == len(body.fields),
        )
        for at, field in enumerate(body.fields):
            spec = product.captures[at]
            _check(
                f"{label}/{name}.{field.name}: capture reads item "
                f"{spec.slot}, the fold reads {field.item}",
                spec.slot == field.item,
            )
            _check(
                f"{label}/{name}.{field.name}: mode {spec.mode} does not "
                f"match bind {field.mode!r}",
                spec.mode == int(MODE_FOR[field.mode]),
            )
            _check(
                f"{label}/{name}.{field.name}: the plan names {ctor.names[at]!r}",
                ctor.names[at] == field.name,
            )
            # The absence rule: a gtext bind over an item that can match
            # nothing must be optional, and nothing else may be.
            expected = field.mode == "gtext" and field.lo == 0
            _check(
                f"{label}/{name}.{field.name}: optional is "
                f"{at in ctor.optional}, expected {expected}",
                (at in ctor.optional) == expected,
            )
            optionals += int(expected)

        _check(
            f"{label}/{name}: the licence disagrees with the fold",
            ctor.licensed == (body.fast is not None),
        )
        # A `value_str` rule captures nothing and states instead WHICH field
        # its own matched text fills — the one construction fact the bound
        # fields cannot carry, since there is no item to point at.
        _check(
            f"{label}/{name}: matched_field is {ctor.matched_field!r} for a "
            f"{body.kind} rule",
            bool(ctor.matched_field) == (body.kind == "value_str"),
        )
        _check(
            f"{label}/{name}: the plan constructs a different class",
            ctor.cls is body.ctor.eval,
        )
    _check(
        f"{label}: {constructors} constructor rows for a table of "
        f"{len(plan.constructors)}",
        constructors == len(plan.constructors),
    )
    return len(plan.codes), optionals


def every_ground_truth_grammar_agrees() -> None:
    """The differential, over the whole corpus rather than a chosen grammar."""
    total_rules = 0
    total_optional = 0
    for stem in STEMS:
        compiled = compile_from_path(GROUND_TRUTH / stem)
        rules, optionals = _agree(stem, compiled)
        total_rules += rules
        total_optional += optionals
        print(f"agrees\t{stem:<16}\trules={rules}\toptional-gtext={optionals}")
    _check(
        "no grammar carried an optional gtext — the rule is untested",
        total_optional > 0,
    )
    print(
        f"total\t{len(STEMS)} grammars\trules={total_rules}\toptional={total_optional}"
    )


def the_absence_rule_is_carried() -> None:
    """A real optional-gtext field is recorded optional; a required one is not.

    `json_ws.gbnf`'s `number` binds `dot` and `ee` through gtext over items
    that can match nothing — the actual shape the absence rule exists for.
    Using it rather than a contrived grammar means the case under test is one
    the corpus really contains.
    """
    compiled = compile_from_path(GROUND_TRUTH / "json_ws.gbnf")
    binding = compute_binding(compiled.codegen_grammar)
    plan = model_plan(compiled.codegen_grammar, binding, compiled.classes)
    bodies = fold_config(compiled.codegen_grammar, binding, compiled.classes)
    folds = {str(ref): body for ref, body in bodies.items()}

    # The constructor table is sparse in rules — an alternation occupies no
    # row — so a rule's constructor is the one its completion NAMES.
    completion = plan.rules[plan.codes["number"]].completion
    assert isinstance(completion, RecordOp)
    ctor = plan.constructors[completion.constructor]
    fold = folds["number"]
    optional_names = {ctor.names[at] for at in ctor.optional}
    expected = {f.name for f in fold.fields if f.mode == "gtext" and f.lo == 0}
    _check(
        f"optional set {sorted(optional_names)} does not match the fold's "
        f"{sorted(expected)}",
        optional_names == expected,
    )
    _check(
        "the real optional-gtext fields did not survive authoring", bool(optional_names)
    )
    _check(
        "a required field was marked optional",
        all(ctor.names[at] in expected for at in ctor.optional),
    )
    print(f"absence\tjson_ws number: optional {sorted(optional_names)} carried")


def main() -> None:
    """Run the differential; any disagreement raises."""
    every_ground_truth_grammar_agrees()
    the_absence_rule_is_carried()
    print("s4 model plan\tPASS\tauthored product agrees with the fold it replaces")


if __name__ == "__main__":
    main()
