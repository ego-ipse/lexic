"""
Single-Grammar Structured Generation
======================================

One grammar (Lark EBNF). Three derived artifacts:
  1. Outlines constrains LLM decoding (generate.cfg)
  2. Lark parses the output (Lark + Transformer)
  3. Pydantic models for typed access (generated from grammar)

No GBNF. No XGrammar. No JSON Schema. No translation layers.
"""

from __future__ import annotations

import json
import re
import textwrap
from dataclasses import dataclass, field

from lark import Lark, Transformer, Token


# =============================================================================
# THE GRAMMAR — the only thing you write
# =============================================================================

GRAMMAR = r'''
start: report

report: "REPORT" project_name "BY" auditor NEWLINE finding+ risk_line summary_line

project_name: IDENT
auditor: IDENT

finding: "FINDING" severity "|" title "|" description "|" component "|" recommendation NEWLINE
severity: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL"
title: FREETEXT
description: FREETEXT
component: FILEPATH
recommendation: FREETEXT

risk_line: "RISK" overall_risk NEWLINE
overall_risk: "ACCEPTABLE" | "NEEDS_ATTENTION" | "CRITICAL"

summary_line: "SUMMARY" summary_text
summary_text: FREETEXT

IDENT: /[a-zA-Z_][a-zA-Z0-9_-]*/
FILEPATH: /[a-zA-Z0-9_.\/]+/
FREETEXT: /[^|\n]+/
NEWLINE: /\n/

%ignore /[ \t]+/
'''


# =============================================================================
# GRAMMAR → PYDANTIC MODELS (build-time codegen)
# =============================================================================

TERMINAL_TYPES = {
    "IDENT": "str", "FILEPATH": "str", "FREETEXT": "str",
    "INT": "int", "NUMBER": "float", "FLOAT": "float",
}


@dataclass
class GField:
    name: str
    type_hint: str
    is_list: bool = False

@dataclass
class GRule:
    name: str
    fields: list[GField] = field(default_factory=list)
    is_enum: bool = False
    enum_values: list[str] = field(default_factory=list)
    is_wrapper: bool = False
    wrapper_type: str = ""


def to_class(name: str) -> str:
    return "".join(w.capitalize() for w in name.split("_"))


def introspect(grammar: str) -> dict[str, GRule]:
    """Extract rule structure from Lark EBNF source."""
    rules: dict[str, GRule] = {}

    for line in grammar.strip().split("\n"):
        line = line.strip()
        if not line or line.startswith("%") or line.startswith("//"):
            continue

        m = re.match(r'^([a-z_][a-z_0-9]*)\s*:\s*(.+)$', line)
        if not m:
            continue

        name, body = m.group(1), m.group(2).strip()
        if name == "start":
            continue

        rule = GRule(name=name)

        # Pure string-literal alternation → enum
        alts = [a.strip() for a in body.split("|")]
        if all(re.match(r'^"[^"]*"$', a) for a in alts):
            rule.is_enum = True
            rule.enum_values = [a.strip('"') for a in alts]
            rules[name] = rule
            continue

        # Single terminal → wrapper (collapses into parent's field type)
        if body in TERMINAL_TYPES:
            rule.is_wrapper = True
            rule.wrapper_type = TERMINAL_TYPES[body]
            rules[name] = rule
            continue

        # Extract field references
        for tok in re.findall(r'[a-zA-Z_][a-zA-Z_0-9]*[+*?]?', body):
            base = tok.rstrip("+*?")
            is_list = tok[-1] in "+*" if tok[-1] in "+*?" else False

            if base in ("NEWLINE",):
                continue
            if base in TERMINAL_TYPES:
                fname = base.lower()
                if not any(f.name == fname for f in rule.fields):
                    rule.fields.append(GField(fname, TERMINAL_TYPES[base], is_list))
            elif base[0].islower():
                if not any(f.name == base for f in rule.fields):
                    rule.fields.append(GField(base, to_class(base), is_list))

        rules[name] = rule
    return rules


def generate_pydantic_code(rules: dict[str, GRule]) -> str:
    lines = [
        "# GENERATED FROM GRAMMAR — do not edit",
        "from __future__ import annotations",
        "from enum import Enum",
        "from pydantic import BaseModel",
        "",
    ]

    for r in rules.values():
        if r.is_enum:
            lines.append(f"class {to_class(r.name)}(str, Enum):")
            for v in r.enum_values:
                lines.append(f"    {v.lower()} = {v!r}")
            lines.append("")

    for r in rules.values():
        if r.is_enum or r.is_wrapper or not r.fields:
            continue
        lines.append(f"class {to_class(r.name)}(BaseModel):")
        for f in r.fields:
            th = f.type_hint
            ref = rules.get(f.name)
            if ref and ref.is_wrapper:
                th = ref.wrapper_type
            elif ref and ref.is_enum:
                th = to_class(ref.name)
            if f.is_list:
                th = f"list[{th}]"
            lines.append(f"    {f.name}: {th}")
        lines.append("")

    return "\n".join(lines)


# =============================================================================
# GRAMMAR → LARK TRANSFORMER (parse tree → Pydantic instances)
# =============================================================================

def _is_syntax_token(item) -> bool:
    if not isinstance(item, Token):
        return False
    return item.type not in TERMINAL_TYPES


def build_transformer(rules: dict[str, GRule], ns: dict) -> type:
    methods = {"start": lambda self, items: items[0]}

    for rname, rule in rules.items():
        if rule.is_enum:
            cls = ns[to_class(rname)]
            def mk(c):
                return lambda self, items: c(str(items[0]).strip())
            methods[rname] = mk(cls)

        elif rule.is_wrapper:
            methods[rname] = lambda self, items: str(items[0]).strip()

        elif rule.fields:
            cls = ns.get(to_class(rname))
            if not cls:
                continue

            def mk(c, r):
                def method(self, items):
                    data = [i for i in items if not _is_syntax_token(i)]
                    kwargs, lists = {}, {f.name: [] for f in r.fields if f.is_list}
                    scalars = iter(f for f in r.fields if not f.is_list)
                    for item in data:
                        placed = False
                        for ln in lists:
                            ec = ns.get(to_class(ln))
                            if ec and isinstance(item, ec):
                                lists[ln].append(item)
                                placed = True
                                break
                        if not placed:
                            try:
                                sf = next(scalars)
                                kwargs[sf.name] = str(item).strip() if isinstance(item, Token) else item
                            except StopIteration:
                                pass
                    kwargs.update(lists)
                    return c(**kwargs)
                return method
            methods[rname] = mk(cls, rule)

    return type("GT", (Transformer,), methods)


# =============================================================================
# GRAMMAR → OUTLINES CONSTRAINED GENERATION (same string, no conversion)
# =============================================================================

def outlines_generate(grammar: str, prompt: str):
    """
    Outlines consumes the SAME Lark EBNF string directly.
    No translation. No intermediate format.

    from outlines import models, generate
    model = models.transformers("your-model")
    # OR: outlines.from_llamacpp(Llama("your-model.gguf"))
    generator = generate.cfg(model, grammar)
    result = generator(prompt)
    # result is text guaranteed to match the grammar
    # parse it with Lark + transformer → Pydantic
    """
    pass  # placeholder — needs a GPU model to actually run


# =============================================================================
# DEMO
# =============================================================================

def main():
    print("=" * 60)
    print("THE GRAMMAR")
    print("=" * 60)
    for line in GRAMMAR.strip().split("\n"):
        if line.strip():
            print(f"  {line.rstrip()}")

    rules = introspect(GRAMMAR)

    print("\n" + "=" * 60)
    print("INTROSPECTED → PYDANTIC MODELS")
    print("=" * 60)
    code = generate_pydantic_code(rules)
    print(code)

    # Load models
    ns = {}
    exec(code, ns)
    for r in rules.values():
        c = ns.get(to_class(r.name))
        if c and hasattr(c, "model_rebuild"):
            try: c.model_rebuild(_types_namespace=ns)
            except: pass

    print("=" * 60)
    print("SAMPLE TEXT → PYDANTIC → JSON")
    print("=" * 60)

    sample = textwrap.dedent("""\
        REPORT acme-api BY security-bot
        FINDING CRITICAL | SQL Injection | User input unsanitized | src/routes/users.py | Use parameterized queries
        FINDING MEDIUM | Missing rate limit | No rate limiting on auth | src/middleware/auth.py | Add token-bucket
        RISK CRITICAL
        SUMMARY Two findings identified, one critical
    """).strip()

    print(sample)

    # Parse with Lark (same grammar string)
    parser = Lark(GRAMMAR, parser="earley", keep_all_tokens=True)
    tree = parser.parse(sample)

    # Transform to Pydantic
    TF = build_transformer(rules, ns)
    report = TF().transform(tree)

    print(f"\n  → {type(report).__name__}")
    print(f"    project: {report.project_name}")
    print(f"    auditor: {report.auditor}")
    print(f"    risk:    {report.risk_line.overall_risk.value}")
    for f in report.finding:
        print(f"    [{f.severity.value:>8s}] {f.title} → {f.recommendation}")

    j = report.model_dump_json(indent=2)
    print(f"\n{j}")

    Report = ns["Report"]
    assert Report.model_validate_json(j) == report
    print("\n✓ grammar → Lark → Pydantic → JSON → Pydantic")

    print("\n" + "=" * 60)
    print("ARCHITECTURE")
    print("=" * 60)
    print(textwrap.dedent("""\
    grammar.lark (Lark EBNF)
       │
       │  # Outlines uses it directly — no conversion
       ├─→ outlines.generate.cfg(model, GRAMMAR)
       │     LLM output guaranteed to match grammar
       │
       │  # Lark uses it directly — same string
       ├─→ Lark(GRAMMAR).parse(text)
       │     └─→ Transformer → Pydantic instances
       │
       │  # Introspect rules → codegen
       └─→ introspect(GRAMMAR)
             └─→ generate_pydantic_code() → models.py

    One grammar string. Zero format translations. Zero duplication.

    At runtime:
      generator = outlines.generate.cfg(model, GRAMMAR)
      text = generator(prompt)                     # constrained LLM output
      tree = Lark(GRAMMAR).parse(text)             # parse it
      result = GrammarTransformer().transform(tree) # → Pydantic object
    """))


if __name__ == "__main__":
    main()
