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

All three approaches share the same GBNF parser (GrammarParser from llguidance).
A and B use gbnf_to_lark() directly (produces %llguidance Lark dialect).
D uses _gbnf_to_earley_lark() which reuses GrammarParser but forces all rule names
lowercase — Lark's Earley parser needs rules (lowercase) not terminals (UPPERCASE)
to recurse into and build Tree nodes for every construct.

Usage (requires a GGUF model file):
    MODEL_PATH=/path/to/model.gguf python with_guidance.py
"""

from __future__ import annotations

import ctypes
import json
import os
from pathlib import Path
from llguidance import grammar_from, LLMatcher
from llguidance.gbnf_to_lark import GrammarParser, resolve, gbnf_to_lark
import llama_cpp
import pynvml
from guidance.models import LlamaCpp
from guidance.library import lark
import numpy as np
from llguidance.numpy import allocate_token_bitmask
from llguidance.numpy import fill_next_token_bitmask, apply_token_bitmask_inplace
from llguidance.llamacpp import lltokenizer_from_vocab
from lark import Tree, Token, Lark

# ---------------------------------------------------------------------------
# GBNF grammar path
# ---------------------------------------------------------------------------
GRAMMAR_PATH = Path(__file__).parent / "resources" / "json_ws.gbnf"
MODEL_PATH = os.environ.get("MODEL_PATH", "")

# ---------------------------------------------------------------------------
# GPU layer auto-detection
# ---------------------------------------------------------------------------


def max_gpu_layers(model_path: str) -> int:
    """Return how many model layers to offload to GPU, or -1 for all."""
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


LAYERS = max_gpu_layers(MODEL_PATH) if MODEL_PATH else -1
print(f"Using n_gpu_layers={LAYERS} for model at {MODEL_PATH}")
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
    lark_grammar = gbnf_to_lark(gbnf_text)

    # Pre-create the llama instance with a context window guidance can handle.
    llm = llama_cpp.Llama(
        model_path=model_path,
        # n_ctx=2048,
        n_gpu_layers=LAYERS,
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
        # n_ctx=2048,
        n_gpu_layers=LAYERS,
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
# All three approaches now share GrammarParser (from llguidance.gbnf_to_lark)
# for GBNF parsing.  A and B use gbnf_to_lark() as-is (produces the
# %llguidance Lark dialect with UPPERCASE terminal names).  D needs all names
# lowercase so Lark's Earley parser recurses into every rule and builds Tree
# nodes — terminals (UPPERCASE) are opaque leaves that Earley cannot recurse.


def _gbnf_to_earley_lark(gbnf_text: str) -> str:
    """Convert GBNF to a Lark grammar suitable for Earley parsing.

    Uses the same GrammarParser + resolve() pipeline as gbnf_to_lark(), then
    forces every rule name lowercase before serialising.  This makes all rules
    proper Lark rules (not terminals), so Earley descends into every construct
    and Tree nodes appear at every level of the parse tree.
    """
    parser = GrammarParser()
    rules = parser.parse(gbnf_text)
    resolve(rules)  # root→start, -→_, ref linking, terminal detection
    for r in rules.values():
        r.name = r.name.lower()  # override UPPERCASE terminal names
    rlist = sorted(rules.values(), key=lambda r: r.order)
    return "\n".join(str(r) for r in rlist)


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
    lark_grammar = _gbnf_to_earley_lark(GRAMMAR_PATH.read_text())
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
            ("meta", msg),
        ],
    }[root_rule]
    for start, sample in samples:
        try:
            result_d = parse_vyx_to_dict(sample, start=start)
            print(f"  [{start}] {sample!r}")
            print(f"    → {json.dumps(result_d)}")
        except Exception as e:
            print(f"  [{start}] {sample!r} → ERROR: {e}")
