"""Tests for ``lexic.parsing.parallel.roles.runs`` — where a bracket's own run
stands: whether an arm holds ``head tail*``.
"""

from __future__ import annotations

from lexic.compile import compile_text
from lexic.parsing.parallel.roles.runs import holds_run


def _sole_arm(source: str, rule: str):
    grammar = compile_text(source, cache_key=f"holds-run-{hash(source)}").grammar
    rules = {str(r.name): r for r in grammar.rules}
    return tuple(rules[rule].body[0]), rules


def test_an_arm_holds_a_run_where_a_tail_returns_to_its_head() -> None:
    """``"[" e ("," e)* "]"`` holds the list's run, inline or through a rule."""
    arm, rules = _sole_arm('root ::= "[" e ("," e)* "]"\ne ::= [0-9]+\n', "root")
    assert holds_run(arm, rules)
    arm, rules = _sole_arm(
        'root ::= "[" e more* "]"\nmore ::= "," e\ne ::= [0-9]+\n', "root"
    )
    assert holds_run(arm, rules)


def test_unbounded_noise_holds_no_run() -> None:
    """``[ ]*`` repeats, but returns to no head: the arm's run is ``list``'s."""
    source = (
        'root ::= "(" [ ]* list [ ]* ")"\nlist ::= item ("," item)*\nitem ::= [a-z]+\n'
    )
    arm, rules = _sole_arm(source, "root")
    assert not holds_run(arm, rules)
    assert holds_run(*_sole_arm(source, "list"))


def test_a_literal_tail_named_like_a_rule_holds_no_run() -> None:
    """``"y"*`` is a literal, not the rule ``y``: read as the rule, its one arm
    ``"," y`` would return to the head ``y`` and fake a run."""
    source = 'root ::= "(" y "y"* ")"\ny ::= "," y | "z"\nw ::= "," y\n'
    arm, rules = _sole_arm(source, "root")
    rules = {**rules, "y": rules["w"]}  # y read as ITS one arm, as the old reader did
    assert not holds_run(arm, rules)
