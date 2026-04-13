import os
from llama_cpp import Llama
from llama_cpp.llama_grammar import LlamaGrammar


MODEL_PATH = "/home/mika/gemma-4-26B-A4B-it-Q4_K_M.gguf"
GRAMMAR_PATH = "resources/ground_truth/c.gbnf"

# Gemma instruct chat template
SYSTEM_PROMPT = "You are a helpful and concise AI assistant."
GRAMMAR_SYSTEM_PROMPT = (
    "You are a C code generator. Output ONLY raw C function definitions. "
    "No includes, no markdown, no explanations. "
    "Use only int, float, or char as data types. "
    "Start immediately with the function definition."
)
GEMMA_PROMPT = (
    "<bos><start_of_turn>user\n"
    f"{SYSTEM_PROMPT}\n\n{{user_message}}<end_of_turn>\n"
    "<start_of_turn>model\n"
)
GEMMA_GRAMMAR_PROMPT = (
    "<bos><start_of_turn>user\n"
    f"{GRAMMAR_SYSTEM_PROMPT}\n\n{{user_message}}<end_of_turn>\n"
    "<start_of_turn>model\n"
    "<|channel>thought\n<channel|>"  # pre-fill empty think block so Gemma skips thinking
)

# Hard-coded Prompt
PROMPT = "Write a simple C program for calculating Fibonacci numbers."

if not os.path.exists(MODEL_PATH):
    print(f"Error: Model file not found at path: {MODEL_PATH}")
    print("Please download the GGUF file and place it in the correct location.")
    exit(1)

messages = [
    {"role": "system", "content": "You are a helpful and concise AI assistant."},
    {"role": "user", "content": PROMPT},
]


print(f"Loading model from {MODEL_PATH}...")
llm = Llama(model_path=MODEL_PATH, n_gpu_layers=26, n_ctx=4096)

def simple(grammar_txt: str | None = None):
    print(f"\n--- Generating completion with prompt for simple application: '{PROMPT}' ---\n")
    # Use create_completion with the Gemma instruct template so the model sees
    # a properly formatted chat turn, not a raw stringified Python list.
    if grammar_txt:
        prompt = GEMMA_GRAMMAR_PROMPT.format(user_message=PROMPT)
        output = llm.create_completion(
            prompt,
            max_tokens=512,
            grammar=LlamaGrammar.from_string(grammar_txt),
        )
    else:
        prompt = GEMMA_PROMPT.format(user_message=PROMPT)
        output = llm.create_completion(prompt, max_tokens=512)

    print("Model Response (Preview):")
    print(output)
    return output


def chat(grammar_txt: str | None = None):
    print(f"Fake Chat Session Started for prompt: '{PROMPT}'\n")
    if grammar_txt:
        # Grammar constrains generated tokens only, so use create_completion
        # with the chat template already in the prompt.
        prompt = GEMMA_GRAMMAR_PROMPT.format(user_message=PROMPT)
        raw = llm.create_completion(
            prompt,
            max_tokens=1000,
            grammar=LlamaGrammar.from_string(grammar_txt),
        )
        content = raw["choices"][0]["text"]
        print(f"Assistant: {content}\n")
        return raw
    else:
        out = llm.create_chat_completion(
            messages=messages,
            max_tokens=1000,
        )
        print(f"Assistant: {out['choices'][0]['message']['content']}\n")
        return out

print(f"\n--- Generating completion without grammar constraints ---\n")
no_grammar_simple = simple()

print("Generating with grammar constraints...")
grammar_text = open(GRAMMAR_PATH).read()
with_grammar_simple = simple(grammar_text)


print("\n--- Starting chat session without grammar constraints ---\n")
no_grammar_chat = chat()

print("\n--- Starting chat session with grammar constraints ---\n")
with_grammar_chat = chat(grammar_text)


print("\n--- All tests completed ---\n")
print("No grammar simple output preview:")
print(no_grammar_simple) # This produces nonsense output.

print("With grammar simple output preview:")
print(with_grammar_simple) # This produces empty content.

print("No grammar chat output preview:")
print(no_grammar_chat) # This produces meaningful output.

print("With grammar chat output preview:")
print(with_grammar_chat) # This produces nonsense output.