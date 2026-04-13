import json as _json
import os
import time
from pathlib import Path
from jinja2 import Environment

import llguidance
import numpy as np
import llama_cpp
from llama_cpp import Llama
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
    nl = llm.detokenize([llm.token_nl()]).decode("utf-8", errors="ignore")
    return template.render(messages=msgs, bos_token=bos, eos_token=eos, nl_token=nl, add_generation_prompt=True)


# Shared resources — computed once, reused across approaches
gbnf_text = GRAMMAR_PATH.read_text()
lark_grammar = gbnf_to_lark(gbnf_text)
grammar_str = grammar_from("gbnf", gbnf_text)
llt = lltokenizer_from_vocab(llama_cpp.llama_model_get_vocab(llm.model))


# Stub ChatTemplate passed to GuidanceLlamaCpp to silence its ChatML fallback
# warning. We pre-format all prompts ourselves; guidance never invokes these.
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
        model=llm, echo=False,
        enable_backtrack=False, enable_ff_tokens=False,
        chat_template=_PreformattedTemplate,
    )
    if use_grammar:
        lm = lm + prompt + guidance_lark(lark_grammar, name="out", max_tokens=200)
    else:
        lm = lm + prompt + gen(name="out", max_tokens=512)
    return lm["out"]

# ---------------------------------------------------------------------------
# Approach B — raw llguidance LLInterpreter with a manual generation loop
#
# Drives generation token-by-token: eval prompt, then each step:
#   compute mask → get logits via llama_get_logits → apply mask → sample →
#   commit to interpreter → eval next token
# Stops when grammar is accepting or EOS is sampled.
#
# Note: llm.scores is never written when logits_all=False (the default), so
# logits must be read via llama_get_logits(llm._ctx.ctx) after each eval().
# compute_mask_into requires a bytearray, not a numpy array.
# ---------------------------------------------------------------------------

def approach_b(use_grammar: bool = False) -> str:
    prompt = _format_prompt(grammar_messages if use_grammar else messages)

    if not use_grammar:
        return llm.create_completion(prompt, max_tokens=512)["choices"][0]["text"]

    interp = llguidance.LLInterpreter(
        llt, grammar_str,
        enable_backtrack=False,
        enable_ff_tokens=False,
        log_level=0,
    )
    interp.start_without_prompt()

    prompt_tokens = llm.tokenize(prompt.encode(), add_bos=True, special=True)
    llm.eval(prompt_tokens)

    bitmask = allocate_token_bitmask(1, llm.n_vocab())
    buf = bytearray(bitmask.nbytes)
    generated: list[int] = []
    rng = np.random.default_rng()

    for _ in range(512):
        interp.compute_mask_into(buf)
        np.copyto(bitmask, np.frombuffer(buf, dtype=np.int32).reshape(bitmask.shape))

        logits = np.ctypeslib.as_array(
            llama_cpp.llama_get_logits(llm._ctx.ctx), shape=(llm.n_vocab(),)
        ).copy()
        apply_token_bitmask_inplace(logits, bitmask)

        logits /= 0.75
        logits -= logits.max()
        probs = np.exp(logits)
        probs /= probs.sum()
        token = int(rng.choice(len(probs), p=probs))

        if token == llm.token_eos():
            break

        generated.append(token)
        interp.commit_token(token)

        if interp.is_accepting():
            break

        llm.eval([token])

    return llm.detokenize(generated).decode("utf-8", errors="ignore")

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
