from outlines.types import CFG
import outlines
from llama_cpp import Llama

output_type = CFG("""
root ::= answer
answer ::= "yes" | "no"
""")


# 1. Initialize conversation history with an optional system prompt
messages = [
    {"role": "system", "content": "You are a helpful and concise AI assistant."}
]

llm = Llama(model_path="/home/mika/SmolLM2.q8.gguf", n_gpu_layers=-1)
model = outlines.from_llamacpp(llm)

result = model("Are you feeling good today?", output_type)
print(result) # 'yes'
