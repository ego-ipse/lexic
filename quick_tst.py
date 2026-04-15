import os
import time
from jinja2 import Environment
from llama_cpp import Llama
from llama_cpp.llama_grammar import LlamaGrammar


MODEL_PATH = "/home/mika/gemma-4-26B-A4B-it-Q4_K_M.gguf"
GRAMMAR_PATH = "resources/ground_truth/c.gbnf"

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
    print(f"Error: Model file not found at path: {MODEL_PATH}")
    exit(1)

print(f"Loading model from {MODEL_PATH}...")
llm = Llama(model_path=MODEL_PATH, n_gpu_layers=26, n_ctx=4096)


def _format_prompt(msgs: list[dict]) -> str:
    """Apply the model's own chat template to produce a raw prompt string."""
    template = Environment().from_string(llm.metadata["tokenizer.chat_template"])
    bos = llm.detokenize([llm.token_bos()]).decode("utf-8", errors="ignore")
    eos = llm.detokenize([llm.token_eos()]).decode("utf-8", errors="ignore")
    return template.render(
        messages=msgs, bos_token=bos, eos_token=eos, add_generation_prompt=True
    )


def simple(grammar_txt: str | None = None):
    print(f"\n--- Generating completion: '{PROMPT}' ---\n")
    prompt = _format_prompt(grammar_messages if grammar_txt else messages)
    output = llm.create_completion(
        prompt,
        max_tokens=512,
        grammar=LlamaGrammar.from_string(grammar_txt) if grammar_txt else None,
    )
    print("Model Response:")
    print(output)
    return output


def chat(grammar_txt: str | None = None):
    print(f"\n--- Chat session: '{PROMPT}' ---\n")
    out = llm.create_chat_completion(
        messages=grammar_messages if grammar_txt else messages,
        max_tokens=1000,
        grammar=LlamaGrammar.from_string(grammar_txt) if grammar_txt else None,
    )
    print(f"Assistant: {out['choices'][0]['message']['content']}\n")
    return out


grammar_text = open(GRAMMAR_PATH).read()

timings = {}

t0 = time.perf_counter()
no_grammar_simple = simple()
timings["simple (no grammar)"] = time.perf_counter() - t0
t0 = time.perf_counter()
with_grammar_simple = simple(grammar_text)
timings["simple (grammar)"] = time.perf_counter() - t0
t0 = time.perf_counter()
no_grammar_chat = chat()
timings["chat (no grammar)"] = time.perf_counter() - t0
t0 = time.perf_counter()
with_grammar_chat = chat(grammar_text)
timings["chat (grammar)"] = time.perf_counter() - t0

print("\n--- Timing ---\n")
for label, elapsed in timings.items():
    tokens = (
        no_grammar_simple
        if label == "simple (no grammar)"
        else with_grammar_simple
        if label == "simple (grammar)"
        else no_grammar_chat
        if label == "chat (no grammar)"
        else with_grammar_chat
    )["usage"]["completion_tokens"]
    print(
        f"  {label:<22}  {elapsed:6.2f}s  {tokens} tokens  ({tokens / elapsed:.1f} tok/s)"
    )

print("\n--- Results ---\n")
print("No grammar simple:", no_grammar_simple)
print("With grammar simple:", with_grammar_simple)
print("No grammar chat:", no_grammar_chat)
print("With grammar chat:", with_grammar_chat)
