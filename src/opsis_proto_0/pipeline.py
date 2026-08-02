"""Pipeline — the compile stages, each emitted and rule-diffed.

Every stage is what lexic's public entry points already produce
(parsed → canonical → codegen → lifted); each renders through the
flavour's own emitter, and consecutive stages diff at RULE granularity —
added, changed, unchanged — the eidolon comparison in its simplest
honest form: canonical emission equality per rule name.
"""

from __future__ import annotations

from html import escape
from typing import Any

from lexic.compile import parse_grammar
from lexic.grammars import get_flavour
from lexic.parsing.fold import lift_optional_nullables

_GBNF = "gbnf"


def pipeline_html(source: str, flavour: str, cg: Any) -> str:
    """The stage-by-stage pipeline view for one compiled grammar.

    The first two stages speak the session's flavour; from codegen on the
    grammar is lexic's own shape and emits as GBNF.
    """
    stages: list[tuple[str, str, dict[str, str]]] = []
    parsed = parse_grammar(source, get_flavour(flavour))
    stages.append(("parsed", flavour, _rules(parsed, flavour)))
    stages.append(("canonical", flavour, _rules(cg.grammar, flavour)))
    stages.append(("codegen", _GBNF, _rules(cg.codegen_grammar, _GBNF)))
    lifted = lift_optional_nullables(cg.codegen_grammar)
    stages.append(("lifted", _GBNF, _rules(lifted, _GBNF)))
    out = []
    previous: dict[str, str] = {}
    for name, flav, rules in stages:
        rows = []
        for rule_name, emitted in rules.items():
            if rule_name not in previous:
                cls = "added" if previous else "same"
            elif previous[rule_name] != emitted:
                cls = "changed"
            else:
                cls = "same"
            rows.append(f'<div class="pl-{cls}">{escape(emitted)}</div>')
        removed = [r for r in previous if r not in rules]
        for rule_name in removed:
            rows.append(f'<div class="pl-removed">{escape(previous[rule_name])}</div>')
        out.append(
            f'<details class="stage" open><summary>{escape(name)} '
            f'<span class="dim">· {len(rules)} rules · {escape(flav)}</span>'
            f"</summary><pre>{''.join(rows)}</pre></details>"
        )
        previous = rules
    return "".join(out)


def _rules(ast: Any, flavour: str) -> dict[str, str]:
    """Rule name → its emitted one-rule text, in grammar order."""
    emitter = get_flavour(flavour)
    return {str(rule.name): str(emitter.apply(rule, None)) for rule in ast.rules}
