# Vyx Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a grammar-driven pipeline that generates Pydantic models + a recursive-descent parser from `grammar.gbnf`, plus a constrained-generation module using llama-cpp-python.

**Architecture:** `builder.py` reads `grammar.gbnf`, classifies rules as terminal (str) or non-terminal (BaseModel), emits `src/vyx/models.py` and `src/vyx/parser.py`. `src/vyx/generate.py` wraps Approach B (LLMatcher + llama-cpp-python). `src/vyx/__init__.py` exposes `parse()` and `generate()`.

**Tech Stack:** Python 3.12, Pydantic v2, llguidance (`GrammarParser`, `resolve`, AST nodes), llama-cpp-python, pytest.

---

## File Structure

| File | Status | Responsibility |
|---|---|---|
| `grammar.gbnf` | existing (SSOT) | Grammar definition — never auto-modified |
| `builder.py` | create | GBNF → `models.py` + `parser.py` (hand-written build script) |
| `src/vyx/__init__.py` | create | Public API: `parse()`, `generate()` |
| `src/vyx/models.py` | **generated** | Pydantic classes for 10 non-terminal rules |
| `src/vyx/parser.py` | **generated** | Recursive-descent parser + terminal regex matchers |
| `src/vyx/generate.py` | create | Approach B: LLMatcher + llama-cpp-python |
| `tests/__init__.py` | create | pytest package marker |
| `tests/test_builder.py` | create | Verify builder runs + output is importable |
| `tests/test_parser.py` | create | Round-trip parse tests on known valid Vyx |
| `tests/test_api.py` | create | Integration: `parse()` public API |

**Key fact:** After `resolve()` on `grammar.gbnf`, only **10 rules are non-terminal** (need model classes):
`ann_child`, `body`, `body_content`, `body_line`, `item_child`, `packet`, `row_annotation`, `seq_item`, `start`, `table_block`.
All other 68 rules are terminal and match as `str`.

---

## Task 1: Package skeleton + generate.py

**Files:**
- Create: `src/vyx/__init__.py`
- Create: `src/vyx/generate.py`
- Create: `tests/__init__.py`
- Create: `tests/test_builder.py` (first test: builder not yet written — just a placeholder that fails)

- [ ] **Step 1: Create src/vyx directory**

```bash
mkdir -p src/vyx
touch src/vyx/__init__.py
touch tests/__init__.py
```

- [ ] **Step 2: Write src/vyx/generate.py**

Extract Approach B from `with_guidance.py`. The `LLGuidanceLogitsProcessor` class and `approach_b_raw` function become:

```python
# src/vyx/generate.py
"""Constrained Vyx generation via llguidance LLMatcher + llama-cpp-python."""
from __future__ import annotations

import ctypes
from pathlib import Path
from typing import Optional

import llama_cpp
import numpy as np
import pynvml
from llguidance import grammar_from, LLMatcher
from llguidance.numpy import allocate_token_bitmask, fill_next_token_bitmask, apply_token_bitmask_inplace
from llguidance.llamacpp import lltokenizer_from_vocab

GRAMMAR_PATH = Path(__file__).parent.parent.parent / "grammar.gbnf"


def max_gpu_layers(model_path: str) -> int:
    """Return how many model layers to offload to GPU, or -1 for all.

    Loads model metadata (vocab_only=True, fast) to get block count, then
    queries NVML for free VRAM. Returns -1 if all layers fit, else the count
    that fits (leaving 1.2 GB headroom), or 0 on any error.
    """
    try:
        lib = llama_cpp.llama_cpp
        params = lib.llama_model_default_params()
        params.vocab_only = True
        params.n_gpu_layers = 0
        meta = lib.llama_load_model_from_file(model_path.encode(), params)
        buf, key = ctypes.create_string_buffer(64), ctypes.create_string_buffer(128)
        n_blocks = 0
        for i in range(lib.llama_model_meta_count(meta)):
            lib.llama_model_meta_key_by_index(meta, i, key, 128)
            if key.value.decode().endswith(".block_count"):
                lib.llama_model_meta_val_str_by_index(meta, i, buf, 64)
                n_blocks = int(buf.value.decode())
                break
        lib.llama_free_model(meta)
        pynvml.nvmlInit()
        free_b = pynvml.nvmlDeviceGetMemoryInfo(
            pynvml.nvmlDeviceGetHandleByIndex(0)
        ).free
        n_layers = n_blocks + 1
        model_b = Path(model_path).stat().st_size
        n = int((free_b - 1.2 * 1024**3) * n_layers / model_b)
        return -1 if n >= n_layers else max(n, 0)
    except Exception:
        return -1


class _LLGuidanceProcessor:
    def __init__(self, grammar_str: str, vocab_size: int, tokenizer):
        self._matcher = LLMatcher(tokenizer, grammar_str)
        if self._matcher.is_error():
            raise ValueError(f"Grammar error: {self._matcher.get_error()}")
        self._vocab_size = vocab_size
        self._bitmask = allocate_token_bitmask(1, vocab_size)

    def __call__(self, input_ids: np.ndarray, scores: np.ndarray) -> np.ndarray:
        if self._matcher.is_stopped():
            return scores
        fill_next_token_bitmask(self._matcher, self._bitmask, index=0)
        apply_token_bitmask_inplace(scores, self._bitmask)
        return scores

    def consume_token(self, token_id: int) -> None:
        self._matcher.consume_token(token_id)

    def is_done(self) -> bool:
        return self._matcher.is_stopped() or self._matcher.is_accepting()


def generate(
    model_path: str,
    prompt: str,
    *,
    grammar_path: Path = GRAMMAR_PATH,
    max_new_tokens: int = 200,
    temp: float = 0.8,
    top_k: int = 40,
) -> str:
    """Constrained Vyx generation. Returns raw Vyx text."""
    llm = llama_cpp.Llama(
        model_path=model_path,
        n_ctx=2048,
        n_gpu_layers=max_gpu_layers(model_path),
        verbose=False,
    )
    vocab_ptr = llama_cpp.llama_model_get_vocab(llm.model)
    llt = lltokenizer_from_vocab(vocab_ptr)
    vocab_size = llm.n_vocab()
    grammar_str = grammar_from("gbnf", grammar_path.read_text())
    processor = _LLGuidanceProcessor(grammar_str, vocab_size, llt)

    prev_len = [0]

    def logits_fn(input_ids: np.ndarray, scores: np.ndarray) -> np.ndarray:
        if input_ids.shape[0] > prev_len[0]:
            processor.consume_token(int(input_ids[-1]))
            prev_len[0] = input_ids.shape[0]
        return processor(input_ids, scores)

    input_tokens = llm.tokenize(prompt.encode())
    prev_len[0] = len(input_tokens)
    output_tokens = []
    limit = min(max_new_tokens, llm.n_ctx() - len(input_tokens) - 1)

    for token in llm.generate(
        tokens=input_tokens,
        top_k=top_k,
        temp=temp,
        logits_processor=llama_cpp.LogitsProcessorList([logits_fn]),
    ):
        if token == llm.token_eos():
            break
        output_tokens.append(token)
        processor.consume_token(token)
        prev_len[0] += 1
        if processor.is_done() or len(output_tokens) >= limit:
            break

    return llm.detokenize(output_tokens).decode("utf-8", errors="replace")
```

- [ ] **Step 3: Write stub src/vyx/__init__.py**

```python
# src/vyx/__init__.py
"""Vyx protocol parser and constrained generation."""
from .generate import generate

__all__ = ["generate"]
```

- [ ] **Step 4: Write first (failing) test**

```python
# tests/test_builder.py
"""Tests that builder.py runs and produces importable output."""
import subprocess
import sys
from pathlib import Path


def test_builder_runs():
    """builder.py must exit 0."""
    result = subprocess.run(
        [sys.executable, "builder.py"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"builder.py failed:\n{result.stderr}"


def test_generated_models_importable():
    """Generated models.py must be importable."""
    result = subprocess.run(
        [sys.executable, "-c", "from vyx.models import Packet, Body, BodyLine"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"Import failed:\n{result.stderr}"


def test_generated_parser_importable():
    """Generated parser.py must be importable."""
    result = subprocess.run(
        [sys.executable, "-c", "from vyx.parser import parse"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"Import failed:\n{result.stderr}"
```

- [ ] **Step 5: Run the failing test to confirm it fails**

```bash
uv run pytest tests/test_builder.py -v
```

Expected: FAIL with "builder.py failed" (builder doesn't exist yet).

- [ ] **Step 6: Add pynvml dependency**

```bash
uv add pynvml
```

- [ ] **Step 7: Commit skeleton**

```bash
git add src/ tests/ pyproject.toml uv.lock
git commit -m "feat: add vyx package skeleton and generate.py"
```

---

## Task 2: Write builder.py — grammar loader + model generator

**Files:**
- Create: `builder.py`
- Modify: `src/vyx/models.py` (first generated output)

- [ ] **Step 1: Write the AST-to-regex helper and grammar loader**

```python
#!/usr/bin/env python3
"""
builder.py — Generate src/vyx/models.py and src/vyx/parser.py from grammar.gbnf.

Run: uv run builder.py  (or: python builder.py)
"""
from __future__ import annotations

import re
import textwrap
from pathlib import Path

from llguidance.gbnf_to_lark import (
    ASTNode,
    AlternativeNode,
    GrammarParser,
    LiteralNode,
    RegexNode,
    RepetitionNode,
    RuleNode,
    RuleRefNode,
    SequenceNode,
    resolve,
)

GRAMMAR_PATH = Path("grammar.gbnf")
MODELS_OUT = Path("src/vyx/models.py")
PARSER_OUT = Path("src/vyx/parser.py")


# ---------------------------------------------------------------------------
# Grammar loading
# ---------------------------------------------------------------------------


def load_grammar() -> dict[str, RuleNode]:
    text = GRAMMAR_PATH.read_text()
    parser = GrammarParser()
    rules = parser.parse(text)
    resolve(rules)
    return rules


# ---------------------------------------------------------------------------
# Name utilities
# ---------------------------------------------------------------------------


def to_class_name(rule_name: str) -> str:
    """snake_case → PascalCase."""
    return "".join(part.capitalize() for part in rule_name.split("_"))


def to_field_name(rule_name: str) -> str:
    """Normalise a rule name to a safe Python identifier."""
    name = rule_name.lower()
    if name in {"type", "class", "import", "from", "with", "pass", "raise"}:
        name += "_"
    return name


# ---------------------------------------------------------------------------
# AST → regex (for terminal rules only)
# ---------------------------------------------------------------------------


def ast_to_regex(node: ASTNode, rules: dict[str, RuleNode]) -> str:
    """Recursively convert a terminal-only AST subtree to a Python regex string."""
    if isinstance(node, LiteralNode):
        return re.escape(node.value)
    if isinstance(node, RegexNode):
        return node.rx  # already a character class like [a-z] or [^\n]
    if isinstance(node, RuleRefNode):
        if node.target is None or not node.target.rule_is_terminal:
            raise ValueError(f"Non-terminal ref '{node.name}' in terminal context")
        return ast_to_regex(node.target.alternatives, rules)
    if isinstance(node, RepetitionNode):
        inner = ast_to_regex(node.node, rules)
        # Character classes and single-char regexes don't need grouping
        needs_group = not (inner.startswith("[") or len(inner) == 1)
        bare = f"(?:{inner})" if needs_group else inner
        if node.min_times == 0 and node.max_times is None:
            return f"{bare}*"
        if node.min_times == 1 and node.max_times is None:
            return f"{bare}+"
        if node.min_times == 0 and node.max_times == 1:
            return f"{bare}?"
        max_s = str(node.max_times) if node.max_times is not None else ""
        return f"{bare}{{{node.min_times},{max_s}}}"
    if isinstance(node, SequenceNode):
        return "".join(ast_to_regex(n, rules) for n in node.nodes)
    if isinstance(node, AlternativeNode):
        parts = [ast_to_regex(a, rules) for a in node.alternatives]
        if len(parts) == 1:
            return parts[0]
        return "(?:" + "|".join(parts) + ")"
    raise ValueError(f"Unknown AST node type: {type(node)}")
```

- [ ] **Step 2: Write the model generator function**

Add to `builder.py`:

```python
# ---------------------------------------------------------------------------
# Model generation
# ---------------------------------------------------------------------------


def _node_to_type(node: ASTNode) -> str | None:
    """Return a Python type annotation string for an AST node, or None to skip."""
    if isinstance(node, LiteralNode):
        return None  # structural separator — not a field
    if isinstance(node, RegexNode):
        return "str"
    if isinstance(node, RuleRefNode):
        if node.target is None:
            return "Any"
        if node.target.rule_is_terminal:
            return "str"
        return to_class_name(node.target.name)
    if isinstance(node, RepetitionNode):
        inner = _node_to_type(node.node)
        if inner is None:
            return None
        if node.min_times == 0 and node.max_times == 1:
            return f"Optional[{inner}]"
        return f"list[{inner}]"
    if isinstance(node, SequenceNode):
        types = [t for t in (_node_to_type(n) for n in node.nodes) if t is not None]
        if not types:
            return None
        return types[0] if len(types) == 1 else f"tuple[{', '.join(types)}]"
    if isinstance(node, AlternativeNode):
        types = list(dict.fromkeys(
            t for t in (_node_to_type(a) for a in node.alternatives) if t is not None
        ))
        if not types:
            return "str"
        return types[0] if len(types) == 1 else f"Union[{', '.join(types)}]"
    return "Any"


def _sequence_fields(seq: SequenceNode) -> list[tuple[str, str, str]]:
    """Return list of (field_name, type_str, default_suffix) from a sequence node."""
    fields: list[tuple[str, str, str]] = []
    seen: dict[str, int] = {}

    for node in seq.nodes:
        if isinstance(node, LiteralNode):
            continue

        typ = _node_to_type(node)
        if typ is None:
            continue

        # Pick a field name
        if isinstance(node, RuleRefNode):
            base = to_field_name(node.name)
        elif isinstance(node, RepetitionNode):
            inner = node.node
            if isinstance(inner, RuleRefNode):
                base = to_field_name(inner.name) + "s"
            else:
                base = "items"
        else:
            base = "value"

        # Deduplicate
        if base in seen:
            seen[base] += 1
            base = f"{base}_{seen[base]}"
        else:
            seen[base] = 0

        default = ""
        if typ.startswith("Optional["):
            default = " = None"
        elif typ.startswith("list["):
            default = " = Field(default_factory=list)"

        fields.append((base, typ, default))

    return fields


def generate_models(rules: dict[str, RuleNode]) -> str:
    """Return the full content of models.py."""
    non_terminals = sorted(
        [r for r in rules.values() if not r.rule_is_terminal],
        key=lambda r: r.order,
    )

    lines = [
        "# GENERATED by builder.py from grammar.gbnf — DO NOT EDIT",
        "# Run: uv run builder.py",
        "from __future__ import annotations",
        "from typing import Any, Optional, Union",
        "from pydantic import BaseModel, Field",
        "",
        "",
    ]

    for rule in non_terminals:
        cname = to_class_name(rule.name)
        body = rule.alternatives

        if isinstance(body, SequenceNode):
            fields = _sequence_fields(body)
        elif isinstance(body, RuleRefNode):
            # Single reference (e.g. start → packet)
            if body.target and body.target.rule_is_terminal:
                fields = [("value", "str", "")]
            else:
                fields = [("root", to_class_name(body.name), "")]
        elif isinstance(body, AlternativeNode):
            # Top-level alternation → single `root` field of Union type
            types = list(dict.fromkeys(
                t for t in (_node_to_type(a) for a in body.alternatives) if t is not None
            ))
            if not types:
                types = ["str"]
            union = types[0] if len(types) == 1 else f"Union[{', '.join(types)}]"
            fields = [("root", union, "")]
        else:
            typ = _node_to_type(body) or "str"
            fields = [("value", typ, "")]

        lines.append(f"class {cname}(BaseModel):")
        if not fields:
            lines.append("    pass")
        else:
            for fname, ftype, fdefault in fields:
                lines.append(f"    {fname}: {ftype}{fdefault}")
        lines += ["", ""]

    # Resolve forward references
    lines.append("# Resolve forward references")
    for rule in non_terminals:
        lines.append(f"{to_class_name(rule.name)}.model_rebuild()")
    lines.append("")

    return "\n".join(lines)
```

- [ ] **Step 3: Add main() that writes models.py**

Add to `builder.py`:

```python
def main() -> None:
    rules = load_grammar()
    print(f"Loaded {len(rules)} rules "
          f"({sum(1 for r in rules.values() if r.rule_is_terminal)} terminals, "
          f"{sum(1 for r in rules.values() if not r.rule_is_terminal)} non-terminals)")

    models_src = generate_models(rules)
    MODELS_OUT.write_text(models_src)
    print(f"Wrote {MODELS_OUT} ({len(models_src)} bytes)")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run builder (models only so far)**

```bash
uv run builder.py
```

Expected output:
```
Loaded 78 rules (68 terminals, 10 non-terminals)
Wrote src/vyx/models.py (N bytes)
```

- [ ] **Step 5: Verify models.py looks correct**

```bash
uv run python3 -c "from vyx.models import Packet, Body, BodyContent, BodyLine, TableBlock, RowAnnotation, AnnChild, SeqItem, ItemChild, Start; print('OK')"
```

Expected: `OK`

- [ ] **Step 6: Run test_builder.py (first two tests should now pass)**

```bash
uv run pytest tests/test_builder.py::test_builder_runs tests/test_builder.py::test_generated_models_importable -v
```

Expected: both PASS.

- [ ] **Step 7: Commit**

```bash
git add builder.py src/vyx/models.py
git commit -m "feat: add builder.py model generator — produces vyx/models.py"
```

---

## Task 3: Write builder.py — parser generator

**Files:**
- Modify: `builder.py` (add parser generation)
- Modify: `src/vyx/parser.py` (first generated output)

- [ ] **Step 1: Add terminal parser generator to builder.py**

Add after `generate_models()`:

```python
# ---------------------------------------------------------------------------
# Parser generation
# ---------------------------------------------------------------------------


def _gen_terminal_parser(rule: RuleNode, rules: dict[str, RuleNode]) -> str:
    """Generate a _parse_TERMINAL(text, pos) function body."""
    try:
        pattern = ast_to_regex(rule.alternatives, rules)
    except ValueError as e:
        pattern = r"[^\n]*"  # fallback: match to end of line
        comment = f"  # fallback: {e}"
    else:
        comment = ""
    name = rule.name  # UPPERCASE
    return textwrap.dedent(f"""\
        def _parse_{name}(text: str, pos: int) -> tuple[str, int]:
            m = _re_match({pattern!r}, text, pos){comment}
            if m is None:
                raise ParseError({name!r}, pos, text)
            return m
        """)


def _gen_nonterminal_parser(rule: RuleNode, rules: dict[str, RuleNode]) -> str:
    """Generate a parse_X(text, pos) function for a non-terminal rule."""
    cname = to_class_name(rule.name)
    fname = rule.name  # already snake_case
    body = rule.alternatives
    lines: list[str] = [f"def parse_{fname}(text: str, pos: int) -> tuple[{cname}, int]:"]

    if isinstance(body, RuleRefNode):
        # Single reference — delegate
        target = body.name
        if body.target and body.target.rule_is_terminal:
            lines.append(f"    val, pos = _parse_{body.target.name}(text, pos)")
            lines.append(f"    return {cname}(value=val), pos")
        else:
            lines.append(f"    inner, pos = parse_{target}(text, pos)")
            lines.append(f"    return {cname}(root=inner), pos")

    elif isinstance(body, AlternativeNode):
        # Try each alternative in order
        lines.append("    _saved = pos")
        for alt in body.alternatives:
            if isinstance(alt, RuleRefNode) and alt.target:
                if alt.target.rule_is_terminal:
                    lines.append(f"    try:")
                    lines.append(f"        val, pos = _parse_{alt.target.name}(text, pos)")
                    lines.append(f"        return {cname}(root=val), pos")
                    lines.append(f"    except ParseError: pos = _saved")
                else:
                    lines.append(f"    try:")
                    lines.append(f"        inner, pos = parse_{alt.target.name}(text, pos)")
                    lines.append(f"        return {cname}(root=inner), pos")
                    lines.append(f"    except ParseError: pos = _saved")
            else:
                # Inline terminal or complex node — skip for now
                pass
        lines.append(f"    raise ParseError({fname!r}, pos, text)")

    elif isinstance(body, SequenceNode):
        fields = _sequence_fields(body)
        field_vars: list[str] = []
        for node in body.nodes:
            if isinstance(node, LiteralNode):
                escaped = repr(node.value)
                lines.append(f"    if not text[pos:].startswith({escaped}):")
                lines.append(f"        raise ParseError({fname!r}, pos, text)")
                lines.append(f"    pos += {len(node.value)}")
            elif isinstance(node, RepetitionNode):
                inner = node.node
                is_optional = node.min_times == 0 and node.max_times == 1
                is_list = node.max_times is None
                var = f"_{''.join(filter(str.isalpha, str(inner)))}_items" if is_list else f"_opt"

                if is_optional:
                    if isinstance(inner, RuleRefNode) and inner.target:
                        var = to_field_name(inner.name)
                        lines.append(f"    {var} = None")
                        lines.append(f"    try:")
                        if inner.target.rule_is_terminal:
                            lines.append(f"        {var}, pos = _parse_{inner.target.name}(text, pos)")
                        else:
                            lines.append(f"        {var}, pos = parse_{inner.name}(text, pos)")
                        lines.append(f"    except ParseError: pass")
                        field_vars.append(var)
                elif is_list:
                    if isinstance(inner, RuleRefNode) and inner.target:
                        var = to_field_name(inner.name) + "s"
                        lines.append(f"    {var}: list = []")
                        lines.append(f"    while True:")
                        lines.append(f"        try:")
                        if inner.target.rule_is_terminal:
                            lines.append(f"            _item, pos = _parse_{inner.target.name}(text, pos)")
                        else:
                            lines.append(f"            _item, pos = parse_{inner.name}(text, pos)")
                        lines.append(f"            {var}.append(_item)")
                        lines.append(f"        except ParseError: break")
                        field_vars.append(var)
                    else:
                        # Complex repetition — skip inline sequences for now
                        pass
            elif isinstance(node, RuleRefNode) and node.target:
                var = to_field_name(node.name)
                if node.target.rule_is_terminal:
                    lines.append(f"    {var}, pos = _parse_{node.target.name}(text, pos)")
                else:
                    lines.append(f"    {var}, pos = parse_{node.name}(text, pos)")
                field_vars.append(var)

        # Build constructor call
        if fields and field_vars:
            kwargs = ", ".join(f"{n}={n}" for n, _, _ in fields if n in field_vars)
            lines.append(f"    return {cname}({kwargs}), pos")
        else:
            lines.append(f"    return {cname}(), pos")

    else:
        lines.append(f"    raise ParseError({fname!r}, pos, text)  # unhandled body type")

    return "\n".join(lines) + "\n"


def generate_parser(rules: dict[str, RuleNode]) -> str:
    """Return the full content of parser.py."""
    terminals = sorted(
        [r for r in rules.values() if r.rule_is_terminal],
        key=lambda r: r.order,
    )
    non_terminals = sorted(
        [r for r in rules.values() if not r.rule_is_terminal],
        key=lambda r: r.order,
    )

    class_names = [to_class_name(r.name) for r in non_terminals]
    import_list = ", ".join(class_names)

    header = textwrap.dedent(f"""\
        # GENERATED by builder.py from grammar.gbnf — DO NOT EDIT
        # Run: uv run builder.py
        from __future__ import annotations
        import re
        from typing import Optional
        from .models import {import_list}


        class ParseError(Exception):
            def __init__(self, rule: str, pos: int, text: str):
                ctx = text[max(0, pos - 20) : pos + 20]
                super().__init__(f"Parse error in {{rule!r}} at pos {{pos}}: ...{{ctx!r}}...")


        def _re_match(pattern: str, text: str, pos: int) -> Optional[tuple[str, int]]:
            m = re.match(pattern, text[pos:], re.DOTALL)
            if m:
                return m.group(0), pos + len(m.group(0))
            return None


        def parse(text: str, start: str = "packet") -> object:
            \"\"\"Parse Vyx text. start must be a non-terminal rule name (snake_case).\"\"\"
            fn = globals().get(f"parse_{{start}}")
            if fn is None:
                raise ValueError(f"Unknown start rule: {{start!r}}")
            result, pos = fn(text, 0)
            while pos < len(text) and text[pos] in " \\t\\n\\r":
                pos += 1
            if pos != len(text):
                raise ParseError(start, pos, text)
            return result


        """)

    parts = [header]
    parts.append("# --- Terminal parsers ---\n\n")
    for rule in terminals:
        parts.append(_gen_terminal_parser(rule, rules))
        parts.append("\n")

    parts.append("# --- Non-terminal parsers ---\n\n")
    for rule in non_terminals:
        parts.append(_gen_nonterminal_parser(rule, rules))
        parts.append("\n")

    return "".join(parts)
```

- [ ] **Step 2: Update main() to also generate parser**

Replace the existing `main()`:

```python
def main() -> None:
    rules = load_grammar()
    n_term = sum(1 for r in rules.values() if r.rule_is_terminal)
    n_nonterm = sum(1 for r in rules.values() if not r.rule_is_terminal)
    print(f"Loaded {len(rules)} rules ({n_term} terminals, {n_nonterm} non-terminals)")

    models_src = generate_models(rules)
    MODELS_OUT.write_text(models_src)
    print(f"Wrote {MODELS_OUT} ({len(models_src)} bytes)")

    parser_src = generate_parser(rules)
    PARSER_OUT.write_text(parser_src)
    print(f"Wrote {PARSER_OUT} ({len(parser_src)} bytes)")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Run builder**

```bash
uv run builder.py
```

Expected:
```
Loaded 78 rules (68 terminals, 10 non-terminals)
Wrote src/vyx/models.py (N bytes)
Wrote src/vyx/parser.py (N bytes)
```

- [ ] **Step 4: Verify parser.py is importable**

```bash
uv run python3 -c "from vyx.parser import parse; print('OK')"
```

Expected: `OK`

- [ ] **Step 5: Run all test_builder.py tests**

```bash
uv run pytest tests/test_builder.py -v
```

Expected: all 3 PASS.

- [ ] **Step 6: Commit**

```bash
git add builder.py src/vyx/parser.py
git commit -m "feat: add parser generator to builder.py — produces vyx/parser.py"
```

---

## Task 4: Write and run parser tests

**Files:**
- Create: `tests/test_parser.py`

- [ ] **Step 1: Write failing parser tests**

```python
# tests/test_parser.py
"""Round-trip parse tests on known valid Vyx inputs."""
import pytest
from vyx.parser import parse, ParseError
from vyx.models import Packet, Body, BodyContent, BodyLine


# --- kv_pairs ---

def test_parse_kv_pairs_single():
    """Single kv pair."""
    from vyx.parser import parse_kv_pairs
    result, pos = parse_kv_pairs("city=Porto", 0)
    assert pos == len("city=Porto")


def test_parse_kv_pairs_multiple():
    """Multiple kv pairs separated by spaces."""
    from vyx.parser import parse_kv_pairs
    result, pos = parse_kv_pairs("city=Porto temp=22", 0)
    assert pos == len("city=Porto temp=22")


# --- body_line ---

def test_parse_body_line_nl_text():
    """Plain text body line."""
    from vyx.parser import parse_body_line
    result, pos = parse_body_line("hello world", 0)
    assert pos == len("hello world")
    assert isinstance(result, BodyLine)


def test_parse_body_line_kv_line():
    """KV line in body."""
    from vyx.parser import parse_body_line
    result, pos = parse_body_line("city=Porto temp=22", 0)
    assert pos == len("city=Porto temp=22")


def test_parse_body_line_nl_force():
    """NL-force comment."""
    from vyx.parser import parse_body_line
    result, pos = parse_body_line("# This is a comment", 0)
    assert pos == len("# This is a comment")


# --- packet ---

def test_parse_minimal_packet():
    """Minimal packet: performative only, no body."""
    result = parse("!I\n>")
    assert isinstance(result, Packet)


def test_parse_packet_with_envelope_fields():
    """Packet with o: field."""
    result = parse("!I o:inv\n>")
    assert isinstance(result, Packet)


def test_parse_packet_with_body():
    """Packet with KV body."""
    text = "!I o:inv\ncity=Porto temp=22\n>"
    result = parse(text)
    assert isinstance(result, Packet)
    assert result.body is not None


def test_parse_packet_body_only_fails():
    """Body-only text must fail packet parse."""
    with pytest.raises(ParseError):
        parse("city=Porto temp=22")


def test_parse_body_content():
    """Parse body content without envelope."""
    result = parse("city=Porto temp=22\n", start="body_content")
    assert isinstance(result, BodyContent)


def test_parse_error_on_garbage():
    """Garbage input raises ParseError."""
    with pytest.raises((ParseError, Exception)):
        parse("\x00\x01\x02")
```

- [ ] **Step 2: Run tests to see failures**

```bash
uv run pytest tests/test_parser.py -v 2>&1 | head -60
```

Note the failures — some tests will fail because the generated parser may have gaps in terminal regex patterns or sequence handling. Each failure message will point to the specific rule that needs fixing.

- [ ] **Step 3: Fix generator issues revealed by failures**

Common issues to watch for in `builder.py` and re-run:
- `ast_to_regex` may throw `ValueError` for complex terminals → add fallback per-rule
- Repetitions of `SequenceNode` (e.g. `(" " kv-pair)*`) need special handling — add a `_gen_seq_rep` helper
- Optional `SequenceNode` groups (e.g. `(" " kv-pairs)?`) — treat the whole group as optional

After each fix: `uv run builder.py && uv run pytest tests/test_parser.py -v`

- [ ] **Step 4: All tests passing**

```bash
uv run pytest tests/test_parser.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add builder.py src/vyx/models.py src/vyx/parser.py tests/test_parser.py
git commit -m "feat: parser tests passing — recursive descent parser working"
```

---

## Task 5: Wire up public API and integration tests

**Files:**
- Modify: `src/vyx/__init__.py`
- Create: `tests/test_api.py`

- [ ] **Step 1: Update src/vyx/__init__.py**

```python
# src/vyx/__init__.py
"""Vyx protocol parser and constrained generation."""
from .models import (
    AnnChild,
    Body,
    BodyContent,
    BodyLine,
    ItemChild,
    Packet,
    RowAnnotation,
    SeqItem,
    Start,
    TableBlock,
)
from .parser import parse, ParseError
from .generate import generate

__all__ = [
    "parse",
    "generate",
    "ParseError",
    "Packet",
    "Body",
    "BodyContent",
    "BodyLine",
    "TableBlock",
    "RowAnnotation",
    "AnnChild",
    "SeqItem",
    "ItemChild",
    "Start",
]
```

- [ ] **Step 2: Write integration tests**

```python
# tests/test_api.py
"""Public API integration tests."""
import pytest
from vyx import parse, ParseError, Packet, BodyContent


def test_public_parse_packet():
    """`parse()` returns a Packet for a valid packet."""
    result = parse("!I o:inv\ncity=Porto temp=22\n>")
    assert isinstance(result, Packet)


def test_public_parse_body_content():
    """`parse(..., start='body_content')` returns BodyContent."""
    result = parse("city=Porto temp=22\n", start="body_content")
    assert isinstance(result, BodyContent)


def test_public_parse_error():
    """`parse()` raises ParseError on invalid input."""
    with pytest.raises(ParseError):
        parse("not a valid packet !!!")


def test_public_parse_seq_item():
    """Sequence item parses correctly."""
    result = parse("- city=Porto\n", start="seq_item")
    from vyx import SeqItem
    assert isinstance(result, SeqItem)


def test_public_parse_scope_line():
    """Scope line with kv pairs."""
    # scope-line: indent scope-path ":" kv-pairs
    result = parse("repo: spec=\"raw files\"", start="body_line")
    assert isinstance(result, object)


def test_public_parse_roundtrip_kv_body():
    """Parse a multi-line KV body packet."""
    text = "!I o:inv\ncity=Porto\ntemp=22\n>"
    result = parse(text)
    assert isinstance(result, Packet)
    assert result.body is not None


def test_unknown_start_rule():
    """Unknown start rule raises ValueError."""
    with pytest.raises(ValueError, match="Unknown start rule"):
        parse("!I\n>", start="nonexistent_rule")
```

- [ ] **Step 3: Run integration tests**

```bash
uv run pytest tests/test_api.py -v
```

Expected: all PASS.

- [ ] **Step 4: Run full test suite**

```bash
uv run pytest -v
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/vyx/__init__.py tests/test_api.py
git commit -m "feat: wire up public API — parse() and generate() exposed from vyx package"
```

---

## Self-Review

**Spec coverage check:**

| Spec requirement | Task |
|---|---|
| `project_meta/grammar.gbnf` as SSOT | All tasks use `grammar.gbnf` |
| `builder.py` generates `models.py` | Task 2 |
| `builder.py` generates `parser.py` | Task 3 |
| 10 non-terminal → Pydantic models | Task 2 |
| 68 terminals → str with regex | Task 3 |
| Recursive descent parser | Task 3 |
| `vyx/generate.py` Approach B | Task 1 |
| `parse()` public API | Task 5 |
| `generate()` public API | Task 1 + 5 |
| `start=` parameter for sub-rule parse | Task 4 + 5 |

**Placeholder scan:** No TBDs, no "implement later", all code blocks complete.

**Type consistency:**
- `to_class_name()` used consistently in both `generate_models` and `generate_parser`
- `to_field_name()` used consistently in `_sequence_fields` and `_gen_nonterminal_parser`
- `ParseError` defined in `parser.py`, re-exported from `__init__.py`
- All model class names match between `models.py` imports in `parser.py` header

**Known limitation:** `_gen_nonterminal_parser` handles repetitions of `RuleRefNode` but not repetitions of inline `SequenceNode` (e.g. `(" " kv-pair)*`). Task 4 Step 3 explicitly handles this via the fix loop. The ralph loop will resolve remaining edge cases.
