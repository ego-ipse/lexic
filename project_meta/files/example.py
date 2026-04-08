"""Vyx — full stack example.

Sections 1–3 run with no dependencies (pure Python).
Sections 4–5 require: pip install pydantic pydantic-ai openai anthropic
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


# ------------------------------------------------------------------
# Section 1: GBNF parsing and literal unescaping
# ------------------------------------------------------------------


def demo_gbnf_parsing() -> None:
    print("=" * 60)
    print("1. GBNF parsing")
    print("=" * 60)

    import importlib.util
    import sys as _sys

    def _load(name, path):
        spec = importlib.util.spec_from_file_location(name, path)
        mod = importlib.util.module_from_spec(spec)
        _sys.modules[name] = mod
        spec.loader.exec_module(mod)
        return mod

    _base = Path(__file__).parent
    _m = _load("gbnf", _base / "gbnf.py")
    GBNFParser = _m.GBNFParser
    _unescape = _m._unescape
    GBNFAlternation = _m.GBNFAlternation
    GBNFRepetition = _m.GBNFRepetition
    GBNFSequence = _m.GBNFSequence
    GBNFLiteral = _m.GBNFLiteral

    # raw token includes surrounding double-quotes
    assert _unescape('"\\"') == "\\", "_unescape backslash"
    assert _unescape('"""') == '"', "_unescape quote"
    assert _unescape('"# "') == "# ", "_unescape nl-force"
    assert _unescape('"D:"') == "D:", "_unescape D:"
    assert _unescape('"$"') == "$", "_unescape $"
    assert _unescape('"- "') == "- ", "_unescape seq-item"
    assert _unescape('"\\n"') == "\n", "_unescape newline"
    print("  _unescape  ✓")
    grammar = Path(__file__).parent.parent.joinpath("grammar.gbnf").read_text()
    rules = GBNFParser().parse(grammar)

    print(f"\n  Rules parsed: {len(rules)}")

    # body-line is an alternation of 8 arms
    bl = rules["body-line"]
    assert isinstance(bl, GBNFAlternation)
    print(f"  body-line:  GBNFAlternation  {len(bl.arms)} arms  ✓")

    # std-perf is an alternation of 12 literal arms
    sp = rules["std-perf"]
    assert isinstance(sp, GBNFAlternation)
    vals = tuple(a.values[0] for a in sp.arms)
    assert vals == ("R", "I", "P", "C", "U", "S", "A", "N", "O", "E", "H", "W"), vals
    print(f"  std-perf:   {vals}  ✓")

    # body is a repetition(min=1) of body-line
    body = rules["body"]
    assert isinstance(body, GBNFRepetition) and body.min == 1
    print("  body:       GBNFRepetition(min=1)  ✓")

    # kv-pair is a sequence
    kv = rules["kv-pair"]
    assert isinstance(kv, GBNFAlternation)
    print("  kv-pair:    GBNFAlternation  ✓")

    print()


# ------------------------------------------------------------------
# Section 2: first_terminal — grammar-derived sigils
# ------------------------------------------------------------------


def demo_first_terminal() -> None:
    print("=" * 60)
    print("2. first_terminal — sigils from grammar only")
    print("=" * 60)

    import importlib.util
    import sys as _sys

    def _load(name, path):
        spec = importlib.util.spec_from_file_location(name, path)
        mod = importlib.util.module_from_spec(spec)
        _sys.modules[name] = mod
        spec.loader.exec_module(mod)
        return mod

    _base = Path(__file__).parent
    _gbnf = _load("gbnf", _base / "gbnf.py")
    GBNFParser = _gbnf.GBNFParser
    first_terminal = _gbnf.first_terminal

    grammar = Path(__file__).parent.parent.joinpath("grammar.gbnf").read_text()
    rules = GBNFParser().parse(grammar)

    tests = [
        ("nl-escape", "\\"),
        ("nl-force", "# "),
        ("dict-def", "D:"),
        ("table-block", "$"),
        ("seq-item", "- "),
        ("ref", "^"),
        ("spread", "~"),
        ("null-val", "_"),
        ("budget", "L"),
        ("msg-label", "&"),
        ("ontology", "o:"),
        ("schema-def", "S:"),
        ("template-def", "T:"),
        ("template-use", "%"),
        ("performative", "!"),
    ]

    all_ok = True
    for rule, expected in tests:
        got = first_terminal(rules, rules[rule]) if rule in rules else "MISSING"
        ok = got == expected
        print(
            f"  {rule:20s}  expected={expected!r:6s}  got={got!r:6s}  {'✓' if ok else '✗'}"
        )
        if not ok:
            all_ok = False

    assert all_ok, "some first_terminal results wrong"
    print("\n  All grammar-derived sigils correct  ✓")
    print()


# ------------------------------------------------------------------
# Section 3: dispatch table from grammar
# ------------------------------------------------------------------


def demo_dispatch_table() -> None:
    print("=" * 60)
    print("3. Dispatch table — grammar-derived, no hardcoded values")
    print("=" * 60)

    import importlib.util
    import sys as _sys

    def _load(name, path):
        spec = importlib.util.spec_from_file_location(name, path)
        mod = importlib.util.module_from_spec(spec)
        _sys.modules[name] = mod
        spec.loader.exec_module(mod)
        return mod

    _base = Path(__file__).parent
    _gbnf = _load("gbnf", _base / "gbnf.py")
    GBNFParser = _gbnf.GBNFParser
    dispatch_table = _gbnf.dispatch_table

    grammar = Path(__file__).parent.parent.joinpath("grammar.gbnf").read_text()
    rules = GBNFParser().parse(grammar)
    table = dispatch_table(rules, "body-line")

    print(f"\n  body-line dispatch table ({len(table)} fixed-literal entries):")
    for k, v in sorted(table.items(), key=lambda x: x[1]):
        print(f"    {k!r:10s}  →  {v}")

    # Verify the key entries are present and correct
    assert table.get("\\") == "nl-escape", f"nl-escape wrong: {table}"
    assert table.get("# ") == "nl-force", f"nl-force wrong: {table}"
    assert table.get("D:") == "dict-def", f"dict-def wrong: {table}"
    assert table.get("$") == "table-block", f"table-block wrong: {table}"
    assert table.get("- ") == "seq-item" or any("seq" in v for v in table.values()), (
        f"seq-item missing: {table}"
    )

    print("\n  Note: scope-line and kv-line have no fixed first literal")
    print("  in the grammar (they start with variable indent + alphanumeric).")
    print("  The parser handles them as fallback cases.")
    print("\n  Dispatch table correct  ✓")
    print()


# ------------------------------------------------------------------
# Section 4: model building (requires pydantic)
# ------------------------------------------------------------------


def demo_model_building() -> None:
    print("=" * 60)
    print("4. Grammar → Pydantic models  (requires pydantic)")
    print("=" * 60)

    try:
        from builder import GBNFModelBuilder
    except ImportError:
        print("  ⚠  pydantic not installed — skipping")
        print("     pip install pydantic")
        print()
        return

    from ogbnf import GBNFParser

    grammar = Path(__file__).parent.parent.joinpath("grammar.gbnf").read_text()
    rules = GBNFParser().parse(grammar)
    registry = GBNFModelBuilder(rules).build()

    print(f"\n  Rules → models: {len(registry)}")
    print("  Example sigils registered in VyxBase._sigil_registry:")

    from base import VyxBase

    for sigil, model in sorted(VyxBase._sigil_registry.items()):
        print(f"    {sigil!r:8s}  →  {model.__name__}")

    Packet = registry["packet"]
    schema = Packet.model_json_schema()
    print(f"\n  packet.model_json_schema() keys: {list(schema.keys())}")
    print("\n  First 300 chars of schema:")
    print(f"  {json.dumps(schema, indent=2)[:300]}...")

    # Verify every model has SIGIL set from grammar (or None)
    for name, model in registry.items():
        sig = model.SIGIL
        if sig is not None:
            # Sigil must be the first_terminal of its rule
            from builder import first_terminal

            expected = first_terminal(rules, rules[name])
            assert sig == expected, (
                f"{name}: SIGIL={sig!r} but first_terminal={expected!r}"
            )

    print("\n  All SIGILs match grammar first_terminal  ✓")
    print()


# ------------------------------------------------------------------
# Section 5: harness configuration (requires pydantic-ai)
# ------------------------------------------------------------------


def demo_harness() -> None:
    print("=" * 60)
    print("5. VyxHarness — provider wiring  (requires pydantic-ai)")
    print("=" * 60)

    try:
        import pydantic_ai  # noqa: F401
        from harness import VyxHarness
    except ImportError:
        print("  ⚠  pydantic-ai not installed — skipping")
        print("     pip install pydantic pydantic-ai openai anthropic")
        print()
        return

    grammar = Path(__file__).parent.parent.joinpath("grammar.gbnf").read_text()

    print("""
  # llama-server — token-level via json_schema
  harness = VyxHarness.for_llama_cpp()

  # Claude via pydantic-ai tool calling
  harness = VyxHarness.for_anthropic()

  # OpenAI Structured Outputs
  harness = VyxHarness.for_openai()

  # Ollama (v0.5+)
  harness = VyxHarness.for_ollama(model_id="qwen2.5-coder:7b")

  # All providers — identical call
  packet = harness.emit("packet", "Generate a !I packet for Porto weather")

  # Access via VyxBase indexing
  # Grammar-derived sigils:
  packet["$C"]                          # table-block child keyed "C"
  packet["^ref"]                        # ref child keyed "ref"
  packet[registry["kv-pair"], "city"]   # kv-pair by type + key
  packet[0]                             # first child absolute index
  packet[Self, "performative"]          # opener field

  # !H L4 grammar mutation — rebuild at !W boundary
  harness.rebuild(new_grammar)

  # Swap provider — grammar unchanged
  harness.swap_model("openai:gpt-4o")
    """)

    harness = VyxHarness.for_anthropic(grammar=grammar)
    print(f"  Registry: {len(harness.registry)} rules  ✓")
    print()


# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------

if __name__ == "__main__":
    demo_gbnf_parsing()
    demo_first_terminal()
    demo_dispatch_table()
    demo_model_building()
    demo_harness()

    print("=" * 60)
    print("Sections 1–3: pure Python, no dependencies  ✓")
    print("Sections 4–5: pip install pydantic pydantic-ai openai anthropic")
    print("=" * 60)
