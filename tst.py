import ctypes
import pynvml
from llama_cpp import Llama, llama_cpp as _lib
from llama_cpp.llama_grammar import LlamaGrammar
from pathlib import Path

MODEL_PATH = "/home/mika/gemma-4-26B-A4B-it-Q4_K_M.gguf"


def _max_gpu_layers(model_path: str) -> int:
    """Return how many model layers to offload to GPU, or -1 for all."""
    try:
        params = _lib.llama_model_default_params()
        params.vocab_only = True
        params.n_gpu_layers = 0
        meta = _lib.llama_load_model_from_file(model_path.encode(), params)
        buf, key = ctypes.create_string_buffer(64), ctypes.create_string_buffer(128)
        n_blocks = 0
        for i in range(_lib.llama_model_meta_count(meta)):
            _lib.llama_model_meta_key_by_index(meta, i, key, 128)
            if key.value.decode().endswith(".block_count"):
                _lib.llama_model_meta_val_str_by_index(meta, i, buf, 64)
                n_blocks = int(buf.value.decode())
                break
        _lib.llama_free_model(meta)
        pynvml.nvmlInit()
        free_b = pynvml.nvmlDeviceGetMemoryInfo(pynvml.nvmlDeviceGetHandleByIndex(0)).free
        n_layers = n_blocks + 1
        model_b = Path(model_path).stat().st_size
        n = int((free_b - 1.2 * 1024**3) * n_layers / model_b)
        return -1 if n >= n_layers else max(n, 0)
    except Exception:
        return -1


llm = Llama(model_path=MODEL_PATH, n_gpu_layers=_max_gpu_layers(MODEL_PATH), n_ctx=4096)

# 1. Initialize conversation history with an optional system prompt
messages = [
    {"role": "system", "content": "You are a helpful and concise AI assistant."}
]


grammar_text = Path("resources/ground_truth/c.gbnf").read_text()


print("--- Chat Session Started ---")
print("Type 'exit' or 'quit' to end.\n")

while True:
    user_input = input("You: ")

    if user_input.lower() in ["exit", "quit"]:
        break

    # 2. Append the user's new message to the history
    messages.append({"role": "user", "content": user_input})

    # 3. Pass the entire history to the chat completion endpoint
    out = llm.create_chat_completion(
        messages=messages,
        max_tokens=1000,
        temperature=0.75,
        grammar=LlamaGrammar.from_string(grammar_text),
    )

    # 4. Extract the assistant's reply
    response = out["choices"][0]["message"]["content"].strip()
    print(f"\nSmolLM2: {response}\n")

    # 5. Save the assistant's reply to the history so it remembers it for the next turn
    messages.append({"role": "assistant", "content": response})
