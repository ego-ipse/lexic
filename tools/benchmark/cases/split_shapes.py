"""The split-route shape witnesses — each the smallest grammar a split route
exists for.

Every grammar here prices one way the parallel layer can or cannot cut a
repetition: a split decided by the split rule rather than by lookahead, the same
unit wrapped, record kinds that end three different ways, sections that end
where the next one begins, an envelope whose separators are also a value's
continuation, and pairs that reopen where no separator is provably a cut. Like
the engine-reach grammars, they are not languages anyone would write; their
rows live beside the rest in `grammars.py`.
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


TWO_MARK = """root ::= filler? rule cont* filler?
rule ::= name ws "=" ws value
cont ::= ws cnl filler* rule
cnl ::= comment | crlf | tabsep
filler ::= comment | blank
comment ::= "; " word crlf
blank ::= crlf
tabsep ::= "\\t"
name ::= [a-z]+
ws ::= " "*
value ::= word (crlf ws word)*
word ::= [a-z]+
crlf ::= "\\n"
"""
"""An envelope of ``name = value`` entries, each separated from the next by one
of two marks — a newline or a tab — where a value may also continue across a
newline.

After a newline, the next line either continues the value (an indented word)
or opens the next entry (a name and ``=``), and which one is known only a line
later. That is a both-viable loop boundary on every newline, settled on the
predictive path by the live set: the take reads one more line and dies at its
``=``. The row prices that settlement — before it, the shape went to the gated
engine whole. It is also a split source: the envelope's marks are provable cut
points, so its mt rows divide the document and run the boundary inside
workers."""


REOPENING = """root ::= arr
arr ::= "[" pair ("," pair)* "]"
pair ::= "(" num ")" "," "(" num ")" | "(" num ")"
num ::= [0-9]+
"""
"""An array of pairs, where a pair is one parenthesised number or two joined
by a comma — so ``(0),(1)`` is one long pair or two short ones.

The language is ambiguous and the decider answers it: leftmost-longest keeps
the long pair. On the predictive path each pair is an arm choice whose two
readings both complete; the live set carries both, meets them, and ranks them
as the gated engine would. Before it, the shape went to the gated engine whole,
where the chart grows faster than the document.

The mt rows DECLINE, in the open: a comma both separates pairs and sits inside
a long pair, so no comma is provably a cut, and the region split declines at
every core count. The row is not eligible for a split, and reports its
sequential number there."""
