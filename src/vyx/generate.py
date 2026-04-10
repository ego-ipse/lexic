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
