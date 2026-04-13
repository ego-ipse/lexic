import json as _json
import os
import time
from pathlib import Path
from jinja2 import Environment

import llguidance
import numpy as np
import llama_cpp
from llama_cpp import Llama, LogitsProcessorList
from llguidance import grammar_from
from llguidance.gbnf_to_lark import gbnf_to_lark
from llguidance.numpy import allocate_token_bitmask, apply_token_bitmask_inplace
from llguidance.llamacpp import lltokenizer_from_vocab
from guidance.models import LlamaCpp as GuidanceLlamaCpp
from guidance.library import lark as guidance_lark, gen
from guidance.chat import ChatTemplate

MODEL_PATH = "/home/mika/gemma-4-26B-A4B-it-Q4_K_M.gguf"
GRAMMAR_PATH = Path("resources/ground_truth/c.gbnf")

PROMPT = "Write a simple C program for calculating Fibonacci numbers."
messages = [
    {"role": "system", "content": "You are a helpful and concise AI assistant."},
    {"role": "user", "content": PROMPT},
]
grammar_messages = [
    {
        "role": "system",
        "content": (
            "Output ONLY a raw C function definition. "
            "Begin immediately with int, float, or char. "
            "No prose, no markdown, no explanations."
        ),
    },
    {"role": "user", "content": PROMPT},
]

if not os.path.exists(MODEL_PATH):
    print(f"Error: Model not found at {MODEL_PATH}")
    exit(1)

print("Loading model...")
llm = Llama(model_path=MODEL_PATH, n_gpu_layers=26, n_ctx=4096, verbose=False)


def _format_prompt(msgs: list[dict]) -> str:
    template = Environment().from_string(llm.metadata["tokenizer.chat_template"])
    bos = llm.detokenize([llm.token_bos()]).decode("utf-8", errors="ignore")
    eos = llm.detokenize([llm.token_eos()]).decode("utf-8", errors="ignore")
    return template.render(messages=msgs, bos_token=bos, eos_token=eos, add_generation_prompt=True)


# Shared resources — computed once, reused across approaches
gbnf_text = GRAMMAR_PATH.read_text()
lark_grammar = gbnf_to_lark(gbnf_text)
grammar_str = grammar_from("gbnf", gbnf_text)
llt = lltokenizer_from_vocab(llama_cpp.llama_model_get_vocab(llm.model))


# Stub ChatTemplate — silences guidance's ChatML fallback warning.
# We pre-format all prompts ourselves via _format_prompt; guidance never
# invokes get_role_start / get_role_end in this script.
class _PreformattedTemplate(ChatTemplate):
    def get_role_start(self, role_name: str, **kwargs) -> str:
        return ""

    def get_role_end(self, role_name: str | None = None) -> str:
        return ""


# ---------------------------------------------------------------------------
# Approach A — guidance high-level API
# ---------------------------------------------------------------------------

def approach_a(use_grammar: bool = False) -> str:
    prompt = _format_prompt(grammar_messages if use_grammar else messages)
    lm = GuidanceLlamaCpp(
        model=llm, echo=False, enable_backtrack=False, enable_ff_tokens=False,
        chat_template=_PreformattedTemplate,
    )
    if use_grammar:
        lm = lm + prompt + guidance_lark(lark_grammar, name="out", max_tokens=200)
    else:
        lm = lm + prompt + gen(name="out", max_tokens=512)
    return lm["out"]


# ---------------------------------------------------------------------------
# Approach B — raw llguidance LLInterpreter as LogitsProcessor
# ---------------------------------------------------------------------------

class LLGuidanceLogitsProcessor:
    """Grammar-constrained logits processor using LLInterpreter.

    Uses LLInterpreter (same backend as guidance) instead of LLMatcher so that
    per-token temperature recommendations from the grammar engine are honoured.
    When the grammar forces a single token, LLInterpreter returns temperature=0
    and the processor samples greedily; for free positions it returns temperature=1.
    Pass temperature=1.0 to create_completion so llama.cpp does not double-scale.
    """

    def __init__(self):
        self._interp = llguidance.LLInterpreter(
            llt, grammar_str,
            enable_backtrack=False,
            enable_ff_tokens=False,
            log_level=0,
        )
        self._interp.start_without_prompt()
        self._bitmask = allocate_token_bitmask(1, llm.n_vocab())
        self._eos = llm.token_eos()
        self._stopped = False
        self._temperature = 1.0
        self._n_generated = 0
        self._compute_mask()  # pre-compute mask for position 0

    def _compute_mask(self) -> None:
        if self._stopped:
            return
        buf = bytearray(self._bitmask.nbytes)
        resp_json = self._interp.compute_mask_into(buf)
        np.copyto(self._bitmask, np.frombuffer(buf, dtype=np.int32).reshape(self._bitmask.shape))
        resp = _json.loads(resp_json)
        self._temperature = resp.get("temperature", 1.0)
        # Stop after the first complete declaration: root ::= (declaration)* is always
        # accepting, so we force EOS as soon as the grammar reaches an accepting state
        # after at least one token has been generated.
        if resp.get("stop", False) or (self._n_generated > 0 and self._interp.is_accepting()):
            self._stopped = True

    def __call__(self, input_ids: np.ndarray, scores: np.ndarray) -> np.ndarray:
        if self._stopped:
            scores[:] = float("-inf")
            scores[self._eos] = 0.0
            return scores

        apply_token_bitmask_inplace(scores, self._bitmask)

        T = self._temperature
        if T < 1e-6:
            # Forced token: pick argmax deterministically
            best = int(np.argmax(scores))
            scores[:] = float("-inf")
            scores[best] = 0.0
        elif abs(T - 1.0) > 1e-6:
            scores /= T

        return scores

    def consume_token(self, token_id: int) -> None:
        self._interp.commit_token(token_id)
        self._compute_mask()


def approach_b(use_grammar: bool = False) -> str:
    prompt = _format_prompt(grammar_messages if use_grammar else messages)

    if not use_grammar:
        out = llm.create_completion(prompt, max_tokens=512)
        return out["choices"][0]["text"]

    processor = LLGuidanceLogitsProcessor()
    prev_len = [None]

    def logits_fn(input_ids: np.ndarray, scores: np.ndarray) -> np.ndarray:
        if prev_len[0] is None:
            prev_len[0] = input_ids.shape[0]
        elif input_ids.shape[0] > prev_len[0]:
            processor.consume_token(int(input_ids[-1]))
            prev_len[0] = input_ids.shape[0]
        return processor(input_ids, scores)

    out = llm.create_completion(
        prompt,
        max_tokens=512,
        temperature=1.0,  # LLInterpreter controls per-token temperature via processor
        logits_processor=LogitsProcessorList([logits_fn]),
    )
    return out["choices"][0]["text"]


# ---------------------------------------------------------------------------
# Run and time
# ---------------------------------------------------------------------------

scenarios = [
    ("A no grammar", lambda: approach_a(False)),
    ("A grammar",    lambda: approach_a(True)),
    ("B no grammar", lambda: approach_b(False)),
    ("B grammar",    lambda: approach_b(True)),
]
timings = {}
results = {}

for name, fn in scenarios:
    print(f"\nRunning {name}...")
    t0 = time.perf_counter()
    results[name] = fn()
    timings[name] = time.perf_counter() - t0

print("\n--- Results ---\n")
for name, result in results.items():
    print(f"{name}:\n  {result!r}\n")

print("--- Timing ---\n")
for name, elapsed in timings.items():
    print(f"  {name:<15} {elapsed:.2f}s")
