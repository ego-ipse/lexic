"""The split-route shape witnesses — each the smallest grammar a split route
exists for.

Every grammar here prices one way the parallel layer can or cannot cut a
repetition: a split decided by the split rule rather than by lookahead, the same
unit wrapped, record kinds that end three different ways, and sections that end
where the next one begins. Like the engine-reach grammars, they are not
languages anyone would write; their rows live beside the rest in `grammars.py`.
"""

SPLIT_NULLABLE = """root ::= para+
para ::= line+ blank
line ::= [a-z ]* nl
blank ::= nl
nl ::= "\\n"
"""
"""Paragraphs of lines, where a line's body may be EMPTY and the paragraph ends
with the same character a line does.

Every carving of a blank run is the same production over the same span: a blank
line is the paragraph's tail, or one more empty line inside it and the tail
after. That is a SPLIT, not an arm choice, so it has a defined answer — the
leftmost chain — and no ``k`` separates it, because after a newline the next
character being a body character is consistent with both readings.

The row prices the shape where the decision is settled by the split rule rather
than by lookahead. Nothing else here reaches it: every other repetition row is
decided by a first character, an attempt, or a scan."""


WRAPPED_UNIT = """root ::= open body close
body ::= para+
open ::= "<<<" nl
close ::= ">>>" nl
para ::= line+ blank
line ::= [a-z ]* nl
blank ::= nl
nl ::= "\\n"
"""
"""The same split-ambiguous unit, wrapped: a fixed prefix, a fixed closer, and
the repetition factored into a rule of its own.

The wrapper is consumed once, outside every boundary the split decision moves,
so the shape is the same language question with three things around it that a
proof about the repetition must be stated carefully enough to ignore. Kept
beside :data:`SPLIT_NULLABLE` so a revision that decides the bare shape and not
the wrapped one shows up as two different numbers rather than one."""


MIXEDENDS = """root ::= record+
record ::= event | span | note
event ::= "%" key eq value ";"
span ::= "<" key colon digits ">"
note ::= word (sp word)* nl
key ::= [a-z] [a-z0-9_]*
value ::= [a-zA-Z0-9./-]+
digits ::= [0-9]+
word ::= [a-z0-9]+
eq ::= "="
colon ::= ":"
sp ::= " "
nl ::= "\\n"
"""
"""A record stream whose three record kinds end three DIFFERENT ways — ``;``,
``>`` and a newline.

Every other repetition row here can be cut statically: its units share a
terminator, or a separator stands between them. This one cannot. No character
ends every arm, so no terminator derives; the only repeated body with a leading
anchor (``note``'s spaces) is not reachable from the start rule as a container;
and the start rule is a plain repetition, not an envelope. What licenses a cut
here is the certified speculative route rather than a static terminator or
separator proof, so the split engages and the row reports a parallel number.

Nothing about the language is hard: the arms open ``%``, ``<`` and a letter, so
each record is decided by its first character and delimited by its own closer,
which makes the segmentation of ``record+`` unique and leaves no island in the
predictive tables. The boundaries are real and abundant — a cut after any
record's closer is exact — and no static analysis names them today.

That gap is the whole point of the row: it prices a repetition the split cannot
cut, and until a mechanism reaches it the row reports the sequential number
with its mt row declining in the open."""


ANNOUNCED = """root ::= section+
section ::= header line*
header ::= hash text nl
line ::= text nl
text ::= [a-z ]+
hash ::= "#"
nl ::= "\\n"
"""
"""Sections that end where the NEXT one begins — a header line, then body
lines until another header.

The sibling of :data:`MIXEDENDS`, and the harder half of the same gap. There
the boundary character occurs nowhere but at a unit's end, so a scan can read
the boundaries straight off the text. Here it cannot: a section ends at a
newline and is full of newlines, so no occurrence of the boundary character is
a boundary by itself. What makes the segmentation unique is the OPENING —
``FIRST(section)`` is ``#`` and nothing a section can continue with is ``#`` —
and that is a property of the grammar, not of any position in the document.

So a cut here cannot be read; it can only be proposed and then verified. That
is what makes this the shape a certified speculative fallback exists for, where
:data:`MIXEDENDS` is the shape a wider static proof would reach. Both take the
speculative route today, so both engage and report a parallel number."""
