from pathlib import Path
from llama_cpp.llama_grammar import LlamaGrammar
from gbnf import GBNF

grammar_text = Path("spec_built/grammar.gbnf").read_text()
print(grammar_text)
print("--- llama_cpp LlamaGrammar ---")
g = LlamaGrammar.from_string(grammar_text)
print("OK")


print("--- gbnf GBNF ---")
g2 = GBNF(grammar_text)
print("OK")


l = g2("")
print(l)
