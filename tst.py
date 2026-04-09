from llama_cpp import Llama
from llama_cpp.llama_grammar import LlamaGrammar, JSON_GBNF
from pathlib import Path

llm = Llama(model_path="/home/mika/SmolLM2.q8.gguf", n_gpu_layers=-1)

# 1. Initialize conversation history with an optional system prompt
messages = [
    {"role": "system", "content": "You are a helpful and concise AI assistant."}
]


grammar_text = Path("spec_built/grammar.gbnf").read_text()


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
