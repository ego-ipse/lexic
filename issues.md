The vyx.gbnf is FUNDAMENTALLY broken.
- It has issues terminating
- Produces output that should NOT be allowed.
- Does not produce intended output

Take metameta.md and vyx.gbnf as intentions, NOT as ground truths.

USE AS GROUND TRUTH ONLY: /home/mika/projects/vyx_2/resources/ground_truth


- Tst.py and with_guidance.py were steps in the right direction.
- Nonethelesss Approach A sort of works and Approach B produces nonsense
To run them use uv run
you may need to export MODEL_PATH=/home/mika/gemma-4-26B-A4B-it-Q4_K_M.gguf

The implementation is FUNDAMENTALLY BROKEN
- Builder.py
- src/
- demos/
- built/
These will be moved to FAILED_ATTEMPT after you read and test them

The demos chat is WAAAAYYYYY slower than the one in with_guidance or tst
The demos parse is a BROKEN mess.
It tries to ask for a root_rule which is stupid. The root_rule is root, not packet or object or whatever.

The goal should be to:

gbnf grammar
   -> Feed into model to constrain output -> Output can be parsed with pydantic model
   -> Produce pydantic model

Pydantic model can be applied for ANY valid gbnf.
Given a model and a text in that grammar, it can be parsed into the model.
The data model can then transform the text back into the original or into json.
The code that generates this should create classes that inherit properly.
The code should be clean, not the mess we have right now.

otes:
1-Write all code to src/ .
2-Do NOT use worktrees.
3-Json can also be parsed back to pydantic. It's a round trip because:
 printing in json is printing on some other grammar (in this case json).
 A json parsed with json grammar into the pydantic and printed to json would print the
 inital state since input and output grammar match.

In other situations, there would be a translation.