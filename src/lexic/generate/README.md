# Generation

Random documents OF a grammar, walked from its canonical rules. `__init__.py`
is the free walk and the public `generate`; `sizing.py` steers that walk toward
a document of about N characters when `size=` is given. The dependency runs one
way: the walk hands its arms and count distribution to the steering, which
imports nothing back. No grammar is named here and no formulation is privileged.
