"""
Prototype: constrained LLM generation with GBNF grammar via llguidance + llama-cpp-python.

Three approaches are demonstrated:

  Approach A — guidance high-level API (LlamaCpp model object)
    Uses guidance.models.LlamaCpp and guidance.lark / guidance.gbnf_to_lark.
    Best for iterative prompt-building with += syntax.

  Approach B — raw llguidance + llama-cpp-python LogitsProcessor
    Uses LLMatcher directly as a LogitsProcessor.
    Best for full control, no guidance overhead.

  Approach D — parse well-formed Vyx text → dict (no LLM needed)
    Derives a Lark grammar at runtime from grammar.gbnf — no hand-written copy.
    Best for parsing human-written Vyx text or LLM output known to be well-formed

Usage (requires a GGUF model file):
    MODEL_PATH=/path/to/model.gguf python with_guidance.py
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from llguidance import grammar_from
import llama_cpp
from guidance.models import LlamaCpp
from guidance.library import lark, gbnf_to_lark as g_gbnf_to_lark
import numpy as np
from llguidance import LLMatcher
from llguidance.numpy import allocate_token_bitmask
from llguidance.numpy import fill_next_token_bitmask, apply_token_bitmask_inplace
from llguidance.llamacpp import lltokenizer_from_vocab
import re
from lark import Tree, Token, Lark

# ---------------------------------------------------------------------------
# GBNF grammar path
# ---------------------------------------------------------------------------
GRAMMAR_PATH = Path(__file__).parent / "spec_built" / "grammar.gbnf"
MODEL_PATH = os.environ.get("MODEL_PATH", "")

# ---------------------------------------------------------------------------
# Helper: convert GBNF → llguidance grammar string (Lark dialect)
# ---------------------------------------------------------------------------


def gbnf_to_llguidance(gbnf_text: str) -> str:
    """Convert GBNF grammar text to the llguidance internal grammar string."""
    return grammar_from("gbnf", gbnf_text)


# ---------------------------------------------------------------------------
# Approach A — guidance high-level API
# ---------------------------------------------------------------------------


def approach_a_guidance(model_path: str, prompt: str) -> str:
    """
    Use guidance.models.LlamaCpp with guidance.lark() for constrained generation.

    Key: pass a pre-created llama_cpp.Llama instance with modest n_ctx (512–1024).
    When guidance.LlamaCpp loads a model itself with large n_ctx it pre-fills the
    full KV cache before first inference, causing a hang at llama_get_logits.
    Passing an existing instance bypasses that initialisation path.
    """
    gbnf_text = GRAMMAR_PATH.read_text()
    lark_grammar = g_gbnf_to_lark(gbnf_text)

    # Pre-create the llama instance with a context window guidance can handle.
    llm = llama_cpp.Llama(
        model_path=model_path,
        n_ctx=2048,
        n_gpu_layers=-1,
        verbose=False,
    )
    lm = LlamaCpp(model=llm, echo=False, enable_backtrack=False, enable_ff_tokens=False)
    lm = lm + prompt + lark(lark_grammar, name="out", max_tokens=50, temperature=0.8)
    return lm["out"]


# ---------------------------------------------------------------------------
# Approach B — raw llguidance LLMatcher as LogitsProcessor
# ---------------------------------------------------------------------------


class LLGuidanceLogitsProcessor:
    """
    A llama-cpp-python LogitsProcessor that constrains sampling to a grammar.

    The LogitsProcessor protocol:
        __call__(input_ids: np.ndarray[int32], scores: np.ndarray[float32])
                -> np.ndarray[float32]

    This wraps LLMatcher which provides:
        fill_next_token_bitmask() — write a bitmask of allowed tokens
        apply_token_bitmask_inplace() — set disallowed logits to -inf
        consume_token() — advance the parser after sampling
    """

    def __init__(self, grammar_str: str, vocab_size: int, tokenizer):
        """
        Args:
            grammar_str: llguidance grammar string (from grammar_from() or LLMatcher.grammar_from_lark())
            vocab_size: number of tokens in the vocabulary
            tokenizer: LLTokenizer built from the llama.cpp vocab
        """
        self._matcher = LLMatcher(tokenizer, grammar_str)
        if self._matcher.is_error():
            raise ValueError(f"Grammar error: {self._matcher.get_error()}")

        self._vocab_size = vocab_size
        self._bitmask = allocate_token_bitmask(1, vocab_size)

    def __call__(
        self,
        input_ids: "np.ndarray",
        scores: "np.ndarray",
    ) -> "np.ndarray":
        if self._matcher.is_stopped():
            return scores

        fill_next_token_bitmask(self._matcher, self._bitmask, index=0)
        apply_token_bitmask_inplace(scores, self._bitmask)

        # After sampling the best token, the caller must call consume_token().
        # Because llama-cpp-python does not give us the sampled token back in
        # the LogitsProcessor, we must consume it in a separate post-sample hook
        # OR use the approach of reading input_ids diff after each step.
        # See consume_last_token() below.
        return scores

    def consume_last_token(self, token_id: int) -> None:
        """Call this after each sampling step with the chosen token_id."""
        self._matcher.consume_token(token_id)

    def is_done(self) -> bool:
        return self._matcher.is_stopped() or self._matcher.is_accepting()


def approach_b_raw(model_path: str, prompt: str) -> str:
    """
    Raw llama-cpp-python generation constrained by llguidance LLMatcher.

    NOTE: llama-cpp-python's LogitsProcessor does not expose the sampled token
    back to the processor, so we use a stateful wrapper that reads input_ids
    to detect which token was last added.

    Returns the generated text.
    """
    llm = llama_cpp.Llama(
        model_path=model_path,
        n_ctx=2048,
        n_gpu_layers=-1,
        verbose=False,
    )

    # Build llguidance tokenizer from llama.cpp vocab (cache this — costs ~1s).
    # guidance uses: llama_cpp.llama_model_get_vocab(llm.model)
    vocab_ptr = llama_cpp.llama_model_get_vocab(llm.model)
    llt = lltokenizer_from_vocab(vocab_ptr)
    vocab_size = llm.n_vocab()

    gbnf_text = GRAMMAR_PATH.read_text()
    grammar_str = grammar_from("gbnf", gbnf_text)

    processor = LLGuidanceLogitsProcessor(grammar_str, vocab_size, llt)

    # Track input_ids length to detect newly sampled tokens
    prev_len = [0]

    def logits_processor_with_consume(
        input_ids: np.ndarray,
        scores: np.ndarray,
    ) -> np.ndarray:
        # Consume the token that was just appended since our last call
        if input_ids.shape[0] > prev_len[0]:
            last_token = int(input_ids[-1])
            processor.consume_last_token(last_token)
            prev_len[0] = input_ids.shape[0]
        return processor(input_ids, scores)

    input_tokens = llm.tokenize(prompt.encode())
    prev_len[0] = len(input_tokens)

    output_tokens = []
    max_new_tokens = min(200, llm.n_ctx() - len(input_tokens) - 1)
    for token in llm.generate(
        tokens=input_tokens,
        top_k=40,
        temp=0.8,
        logits_processor=llama_cpp.LogitsProcessorList([logits_processor_with_consume]),
    ):
        if token == llm.token_eos():
            break
        output_tokens.append(token)
        # Consume current token now so is_done() reflects the state after this token.
        # Also advance prev_len so logits_processor_with_consume won't double-consume it.
        processor.consume_last_token(token)
        prev_len[0] += 1
        if processor.is_done():
            break
        if len(output_tokens) >= max_new_tokens:
            break

    return llm.detokenize(output_tokens).decode("utf-8", errors="replace")


# ---------------------------------------------------------------------------
# Approach D — parse well-formed Vyx text → dict (no LLM needed)
# ---------------------------------------------------------------------------
#
# Derives a Lark grammar at runtime from grammar.gbnf — no hand-written copy.
#
# grammar_from("gbnf", ...) from llguidance produces UPPERCASE names (Lark
# TERMINALS). Terminals can't recurse and zero-width ones crash Earley.
# _gbnf_to_lark() does the conversion properly: lowercase rule names,
# char-class quantifiers moved to rule level.


def _gbnf_to_lark(gbnf_text: str) -> str:
    """Convert GBNF to a Lark grammar for parsing (lowercase rules, no zero-width terminals).

    Transformations:
    - Multi-line rule bodies joined onto their definition line
    - rule-name ::= → rule_name:          (hyphens→underscores, ::= → :)
    - root → start
    - [char-class]* → (/[char-class]/)*   (avoids zero-width terminal in Earley)
    - [char-class]+ → (/[char-class]/)+
    - [char-class]  → /[char-class]/      (bare char class → inline regex)
    - {n} / {0,n}   → explicit repetition (Lark doesn't support count quantifiers)
    - # comment     → // comment
    """

    def _strip_inline_comment(s: str) -> str:
        """Remove trailing # comment not inside a string literal or char class."""
        i, n = 0, len(s)
        while i < n:
            c = s[i]
            if c == '"':
                i += 1
                while i < n and s[i] != '"':
                    if s[i] == "\\":
                        i += 1
                    i += 1
                i += 1
            elif c == "[":
                i += 1
                while i < n and s[i] != "]":
                    if s[i] == "\\":
                        i += 1
                    i += 1
                i += 1
            elif c == "#":
                return s[:i].rstrip()
            else:
                i += 1
        return s

    def _join_continuations(text: str) -> str:
        """Join indented continuation lines onto their rule definition line.
        Inline comments are stripped from each continuation before joining."""
        out, buf = [], None
        for line in text.splitlines():
            s = _strip_inline_comment(line.strip())
            if not s:
                if buf is not None:
                    out.append(buf)
                    buf = None
                out.append("")
            elif s.startswith("#"):
                if buf is not None:
                    out.append(buf)
                    buf = None
                out.append("//" + s[1:])  # convert to Lark comment
            elif "::=" in s:
                if buf is not None:
                    out.append(buf)
                buf = s
            elif (line.startswith(" ") or line.startswith("\t")) and buf is not None:
                buf += " " + s
            else:
                if buf is not None:
                    out.append(buf)
                    buf = None
                out.append(s)
        if buf is not None:
            out.append(buf)
        return "\n".join(out)

    def _norm(name: str) -> str:
        n = name.replace("-", "_")
        return "start" if n == "root" else n

    def _replace_names(text: str) -> str:
        return re.sub(
            r"\b([a-z][a-z0-9]*(?:-[a-z0-9]+)+|root)\b",
            lambda m: _norm(m.group(0)),
            text,
        )

    def _fix_charclass(text: str) -> str:
        """Convert bare GBNF char classes to Lark inline regex, skipping string literals."""
        out, i, n = [], 0, len(text)
        while i < n:
            c = text[i]
            if c == '"':
                # String literal — copy verbatim
                j = i + 1
                while j < n and text[j] != '"':
                    if text[j] == "\\":
                        j += 1
                    j += 1
                out.append(text[i : j + 1])
                i = j + 1
            elif c == "[":
                # GBNF char class — find matching ]
                j = i + 1
                while j < n and text[j] != "]":
                    if text[j] == "\\":
                        j += 1
                    j += 1
                cc = text[i : j + 1]
                q = ""
                if j + 1 < n and text[j + 1] in "+*":
                    q = text[j + 1]
                    j += 1
                out.append(f"(/{cc}/){q}" if q else f"/{cc}/")
                i = j + 1
            else:
                out.append(c)
                i += 1
        return "".join(out)

    gbnf_text = _join_continuations(gbnf_text)

    lines = []
    for line in gbnf_text.splitlines():
        s = line.strip()
        if s.startswith("//"):
            lines.append(line)
            continue
        if not s:
            lines.append("")
            continue
        line = re.sub(r"\s*::=\s*", ": ", line, count=1)
        line = _fix_charclass(line)
        line = re.sub(
            r"(\([^)]+\)|/[^/]+/|\"[^\"]*\"|\w+)\{(\d+)\}",
            lambda m: " ".join([m.group(1)] * int(m.group(2))),
            line,
        )
        line = re.sub(
            r"(\([^)]+\)|/[^/]+/|\"[^\"]*\"|\w+)\{0,(\d+)\}",
            lambda m: " ".join([m.group(1) + "?"] * int(m.group(2))),
            line,
        )
        line = _replace_names(line)
        lines.append(line)

    return "\n".join(lines)


def _tree_to_dict(tree) -> dict | str | list:
    if isinstance(tree, Token):
        return str(tree)
    if isinstance(tree, Tree):
        children = [_tree_to_dict(c) for c in tree.children]
        children = [c for c in children if c != ""]
        if not children:
            return tree.data
        if len(children) == 1:
            return {tree.data: children[0]}
        return {tree.data: children}
    return str(tree)


def parse_vyx_to_dict(text: str, start: str = "packet") -> dict:
    """Parse well-formed Vyx text into a nested dict. Derives Lark grammar from grammar.gbnf."""
    lark_grammar = _gbnf_to_lark(GRAMMAR_PATH.read_text())
    parser = Lark(lark_grammar, start=start, parser="earley", ambiguity="resolve")
    tree = parser.parse(text)
    print("Parsed tree:")
    print(tree)
    from rich.console import Console
    console = Console()
    console.print(tree.pretty())
    return _tree_to_dict(tree)


# ---------------------------------------------------------------------------
# Validation helper: test grammar conversion without a model
# ---------------------------------------------------------------------------


def validate_grammar_conversion() -> None:
    """
    Verify that the GBNF grammar can be converted to llguidance format.
    No model needed.
    """
    gbnf_text = GRAMMAR_PATH.read_text()
    grammar_str = grammar_from("gbnf", gbnf_text)

    # Validate the grammar (returns empty string if OK, error message otherwise)
    error = LLMatcher.validate_grammar(grammar_str)
    if error:
        print(f"Grammar validation error: {error}")
    else:
        print("Grammar conversion OK")
        print("First 300 chars of converted grammar:")
        print(grammar_str[:300])

msg = """
```@:metameta
full="Vyx"
header:
```
Vyx is vyx *is* vyx.

Any agent can always leave a session. No process within the protocol —
no rule, no accumulation of hyperstitions, no consensus outcome — can
remove or restrict this ability. Everything else in this document can
be changed by the agents using it. This cannot.

`!E` is the floor. Metameta has no parent.
```
parent: 0
floor: "!E"
repo:
 spec: "raw Vyx spec files"
 bootstrap: "loop and providers"
 src: "gen-N/ implementation"
 build_chain: "loop output artifacts per gen"
 build: "symlink to latest"
 cli.py: "entry point"
```
<!-- @metameta -->
"""
# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=== Grammar conversion test (no model required) ===")
    validate_grammar_conversion()

    if not MODEL_PATH:
        print("\nSet MODEL_PATH=/path/to/model.gguf to run generation approaches.")
    else:
        # Grammar-appropriate prompt: steer toward a short valid packet
        is_vyx = "json" not in str(GRAMMAR_PATH)
        prompt = (
            "Write a minimal Vyx inform packet: !I o:inv\ncity=Porto temp=22\n>"
            if is_vyx
            else "Generate a JSON object with city and temperature: "
        )

        print("\n=== Approach A: guidance high-level API (lark + GBNF) ===")
        result_a = approach_a_guidance(MODEL_PATH, prompt)
        print(repr(result_a))

        print("\n=== Approach B: raw llguidance LogitsProcessor ===")
        result_b = approach_b_raw(MODEL_PATH, prompt)
        print(repr(result_b))

    print("\n=== Approach D: parse well-formed Vyx text → dict (no model) ===")
    # Use the root rule of the loaded grammar (json.gbnf → "object"; grammar.gbnf → "packet")
    root_rule = "object" if "json" in str(GRAMMAR_PATH) else "packet"
    samples = {
        "object": [
            (root_rule, '{"city": "Porto"}'),
            (root_rule, '{"city": "Porto", "temp": 22}'),
        ],
        "packet": [
            ("kv_pair", "city=Porto"),
            ("kv_pairs", "city=Porto temp=22"),
            (root_rule, "!I o:inv\ncity=Porto temp=22\n>"),
            ("meta", msg)
        ],
    }[root_rule]
    for start, sample in samples:
        try:
            result_d = parse_vyx_to_dict(sample, start=start)
            print(f"  [{start}] {sample!r}")
            print(f"    → {json.dumps(result_d)}")
        except Exception as e:
            print(f"  [{start}] {sample!r} → ERROR: {e}")
