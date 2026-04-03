
!R L<
before-all: /home/mika/llama.cpp/examples/pydantic_models_to_grammar.py
~~~
Check that path, the folder it is in before continuing.
~~~
>

Goals:
1- Do the oposite:
    gbnf <-> pydantic model, validated by the avaliable one way

2- Use vyx to contain the abstraction layer surrounding it all
   gbnf file -> gbnf Pydantic classes -> Parse vyx -> compose class semantics.

   vyx text <-> pydantic model <-> json

Constraints:
    Source of truth: gbnf for grammar. Rest of spec for semantics
    Python code: Generative to the largest extent possible.

The goal is that given ANY valid gbnf grammar, and a spec document composed from it, a data structure can be created.
The goal is NOT to generate vyx. The goal is to be able to go back and forward from a language with grammar + spec to:
  - a pydantic model
  - a json payload

Other constraints:
 - ALWAYS ask clarification for ambiguity.
 - DO NOT assume architecture, assume implementation details
 - Pydantic is an accepted dependency. Prompt if any further are needed
   (apart from llama.cpp or pydantic-ai)
 - Be critical. Research.