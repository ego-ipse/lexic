"""The benchmark's languages — one grammar each, handed to every engine.

Every bench is built the same way: grammar TEXT through `compile_text`, giving a
canonical AST and a fold. Every engine then answers the same question over the
same language, and each builds its own natural parse product from it — lexic a
typed model, Lark a `Tree`, ANTLR a `ParserRuleContext`.

Two asymmetries used to live here and both are gone by construction:

**No reducer.** The meta row used to hand lexic a flavour's `Reducer` and run the
reduce path — grammar text straight to IR with semantic actions attached — while
every competitor got a bare grammar and built a generic tree. Those are not the
same job. A flavour's self-grammar round-trips to text, so it compiles through
the ordinary path like everything else and lexic builds a model from it, with no
actions anyone else was denied.

**No `@non-semantic`.** It marks rules skippable noise and lexic's codegen pass
relaxes references to them, so a grammar carrying one is a grammar lexic parses
more loosely than it reads. No bench carries one — the test pins that — which
is why `grammar` and `codegen_grammar` describe the same language and the
translation is honest without any per-tool compensation. `@start` is different
in kind: it only names the start rule, the emitters read the resolved
``ast.start``, and every engine parses from the same rule — so a grammar may
carry one (vyx does).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import NamedTuple

from lexic.compile import CompiledGrammar, compile_text
from lexic.grammars import ABNF_FLAVOUR, GBNF_FLAVOUR
from lexic.ir import IrAst
from tools.benchmark.cases.corpora import (
    announced_corpus,
    arith_corpus,
    backtrack_corpus,
    csv_corpus,
    dense_earley_corpus,
    ground_truth,
    interior_climb_corpus,
    interior_exact_corpus,
    island_corpus,
    json_corpus,
    lexrun_corpus,
    markdown_corpus,
    meta_corpus,
    mixedends_corpus,
    nested_corpus,
    paren_arith_corpus,
    reopening_corpus,
    split_nullable_corpus,
    start_fallback_corpus,
    two_mark_corpus,
    vyx_corpus,
    wrapped_unit_corpus,
)
from tools.benchmark.cases.directives import DIRECTIVES, validate_directives
from tools.benchmark.cases.engine_reach import (
    DENSE_EARLEY,
    INTERIOR_CLIMB,
    INTERIOR_EXACT,
    ISLAND_EARLEY,
    RELAY_CLIMB,
    RELAY_EXACT,
    RELAY_FALLBACK,
    START_FALLBACK,
)
from tools.benchmark.cases.split_shapes import (
    ANNOUNCED,
    MIXEDENDS,
    REOPENING,
    SPLIT_NULLABLE,
    TWO_MARK,
    WRAPPED_UNIT,
)

_ROOT = Path(__file__).resolve().parents[3]
_ONLY_BENCHMARK = os.environ.get("LEXIC_BENCHMARK_GRAMMAR")
"""Worker-only selector: skip compiling every unrelated benchmark grammar."""


class Bench(NamedTuple):
    """One language: the grammar every engine gets, and the input they parse.

    :ivar name: The row label.
    :ivar ast: The single source of truth — what lexic compiles, and what every
        competitor's grammar is mechanically derived from.
    :ivar corpus: The input, sized so a row is dominated by parsing.
    :ivar full: The same language at document scale — what the mt rows
        always parse (a split needs several chunks above the policy floor
        to be visible), and what every row parses under ``--full``. Kept
        apart from :attr:`corpus` because the slow engines pay seconds per
        pass here, a price the default run should not charge per round.
    :ivar accepts: Inputs beyond the corpus the grammar DOES accept, chosen to
        stress the lexical layer — a keyword inside a string, a space two
        character classes both hold. A corpus is one sentence, and a two-tier
        lexer only goes wrong on the sentences nobody sampled.
    :ivar rejects: Inputs the grammar must NOT accept. Checking both directions
        is the point: a translation that accepts everything passes an
        accept-only check, and one that refuses everything passes the other.
    :ivar compiled: lexic's own artefact, carrying the product it parses with.
    :ivar lexical: The case's declared `@lexical` rule names — what the variant
        rows compile with, fixed by the case rather than by engine eligibility.
    :ivar non_semantic: The case's declared `@non-semantic` rule names.
    """

    name: str
    ast: IrAst
    corpus: str
    accepts: tuple[str, ...]
    rejects: tuple[str, ...]
    compiled: CompiledGrammar
    source: str
    flavour: str
    full: str
    lexical: tuple[str, ...]
    non_semantic: tuple[str, ...]


class Samples(NamedTuple):
    """One bench's two documents — the same language at two scales.

    :ivar corpus: The default sample every row times.
    :ivar full: The document-scale sample the mt rows always time.
    """

    corpus: str
    full: str


def declared_marks(bench: Bench) -> tuple[frozenset[str], frozenset[str]]:
    """One case's declared directive sets, for lexic and competitors alike.

    Every seat that claims to face "the grammar's own directives" must face the
    SAME ones lexic's variant rows compile with, or the two are not comparable.
    There is one declaration and this is the only way to read it.
    """
    return frozenset(bench.lexical), frozenset(bench.non_semantic)


def _bench(
    name: str,
    source: str,
    samples: Samples,
    good: tuple[str, ...],
    bad: tuple[str, ...],
) -> Bench | None:
    """Compile ``source`` and pair it with the inputs that pin its language.

    The flavour is read off the source, so a self-grammar row compiles in its
    own notation without an extra parameter.
    """
    if _ONLY_BENCHMARK is not None and name != _ONLY_BENCHMARK:
        return None
    flavour = "abnf" if name.endswith("abnf-meta") else "gbnf"
    compiled = compile_text(source, cache_key=f"bench-{name}", flavour=flavour)
    lexical, non_semantic = DIRECTIVES[name]
    validate_directives(name, compiled.grammar, lexical, non_semantic)
    return Bench(
        name,
        compiled.grammar,
        samples.corpus,
        good,
        bad,
        compiled,
        source,
        flavour,
        samples.full,
        lexical,
        non_semantic,
    )


_ARITH = """root ::= expr
expr ::= term (addop term)*
term ::= factor (mulop factor)*
factor ::= number | "(" expr ")"
number ::= digit+
digit ::= [0-9]
addop ::= "+" | "-"
mulop ::= "*" | "/"
"""

_CSV = """root ::= row (nl row)*
row ::= field (comma field)*
field ::= chars
chars ::= [a-zA-Z0-9 ]+
comma ::= ","
nl ::= "\\n"
"""

# Whitespace on ONE side of each token, never both, so no two nullable runs are
# ever adjacent. The RFC's own shape is ambiguous and belongs in the correctness
# fixtures, not in a timing row.
_JSON = """root ::= ws value
value ::= object | array | string | number | "true" | "false" | "null"
object ::= "{" ws members "}" ws
members ::= member (comma member)*
member ::= string colon value
array ::= "[" ws items "]" ws
items ::= value (comma value)*
string ::= quote chars quote ws
chars ::= [a-zA-Z0-9 ]*
number ::= digit+ ws
digit ::= [0-9]
quote ::= "\\""
colon ::= ":" ws
comma ::= "," ws
ws ::= [ \\t\\n\\r]*
"""


_MARKDOWN = """document ::= block+
block ::= heading | fence | rule | quote | bullet | numbered | paragraph | blank
heading ::= hashes " " inline nl
hashes ::= "#" | "##" | "###" | "####" | "#####" | "######"
rule ::= "---" nl
fence ::= tick3 info nl fenceline* tick3 nl
info ::= [a-z]*
fenceline ::= plainline nl
plainline ::= [^`\\n]*
quote ::= "> " inline nl
bullet ::= "- " inline nl
numbered ::= digit+ ". " inline nl
digit ::= [0-9]
paragraph ::= opener inline nl
blank ::= nl
opener ::= [^#>\\-`*!\\[0-9\\n]
inline ::= text? (marked text?)*
marked ::= strong | emphasis | code | image | link
strong ::= star2 runtext star2
emphasis ::= star1 runtext star1
code ::= tick1 codetext tick1
image ::= "!" link
link ::= "[" runtext "]" "(" url ")"
url ::= [^)\\n]*
text ::= plain+
plain ::= [^*`!\\[\\n]
runtext ::= [^*`\\]\\n]+
codetext ::= [^`\\n]+
star1 ::= "*"
star2 ::= "**"
tick1 ::= "`"
tick3 ::= "```"
nl ::= "\\n"
"""
"""A CommonMark SUBSET, authored here rather than taken from the fixture set —
eight block kinds and six inline kinds, which is enough structure for the row
to price real document parsing rather than a two-rule toy.

Three restrictions make it unambiguous, and each is stated because each is a
real narrowing of CommonMark: a paragraph may not OPEN with a character that
opens another block (the spec decides those by lookahead this CFG cannot
express); a fenced block's content lines carry no backtick, so the closing
fence is decidable; and emphasis spans carry no nested markup, so `*a*b*` has
one reading rather than two.

A line INTERLEAVES plain runs with marked ones rather than repeating a chunk.
Repeating would let two adjacent plain runs carve one run of text two ways —
an ambiguity the PDA answers and the gated engine refuses, which is a bug in
the grammar, not in either engine."""

_NESTED = """root ::= node
node ::= leaf | group
group ::= "(" node (comma node)* ")"
comma ::= ","
leaf ::= [a-z]+
"""
"""Deep recursive structure. Every level is a frame the PDA pushes and an
Earley item set that cannot be flattened, so this row prices DEPTH where the
others price width."""

_LEXRUNS = """root ::= entry (nl entry)*
entry ::= name eq value
name ::= [a-zA-Z_] [a-zA-Z0-9_]*
eq ::= "="
value ::= quoted | word | number
quoted ::= dquote qchars dquote
qchars ::= [^"\\n]*
word ::= [a-zA-Z] [a-zA-Z0-9._/-]*
number ::= [0-9]+
dquote ::= "\\""
nl ::= "\\n"
"""
"""Long terminals, few structures. `value`'s arms are disjoint on their first
character, so the decisions are trivial and nearly all the work is character
consumption — the population every table/`value_str` lever targets."""

_BACKTRACK = """root ::= stmt+
stmt ::= block | bind
block ::= def name lparen rparen " {" word "}" nl
bind ::= def name lparen rparen " = " word ";" nl
def ::= "def "
name ::= [a-z] [a-z0-9]*
word ::= [a-z0-9]+
lparen ::= "("
rparen ::= ")"
nl ::= "\\n"
"""
"""Two arms sharing an UNBOUNDED prefix: `def`, a name of any length, then
`()` — only the character after that separates them. No fixed-k window can
decide it, so the row prices the attempt/rollback tier directly."""


def _vyx_packet(body: str) -> str:
    """A block-body vyx packet wrapping ``body`` with an exact L-budget."""
    return f"!I o:wf L{len(body.encode())}<\n{body}>"


def _self_grammar_source(flavour) -> str:
    """A flavour's own self-grammar, as text in that flavour.

    The flavour carries its self-grammar as IR; emitting it back to text is what
    lets the meta row compile through the ordinary path, so lexic parses grammar
    text into a MODEL exactly as the other rows parse their inputs — no reducer,
    no semantic actions, nothing a competitor was not offered.
    """
    return str(flavour.apply(flavour.grammar))


_FALLBACK_INPUTS = (
    Samples(start_fallback_corpus(2400), start_fallback_corpus(9600)),
    ("a", "aa", "aaa", "ab", "abba"),
    ("", "b", "ba", "a\n"),
)
_EXACT_INPUTS = (
    Samples(interior_exact_corpus(2400), interior_exact_corpus(9600)),
    ("a\n", "aa\n", "aaa\n", "ab\n", "abba\n"),
    ("", "a", "\n", "ba\n", "a\n\n"),
)
_CLIMB_INPUTS = (
    Samples(interior_climb_corpus(2400), interior_climb_corpus(9600)),
    ("zzz\n", "zazz\n", "zaazz\n", "zbzz\n", "zabzz\n"),
    ("", "z\n", "zz\n", "zazz", "azz\n"),
)
"""The engine-reach languages' samples and probes, shared by each language's
direct row and its relay row, so the two read against each other on one text."""


_DEFINED_BENCHES = (
    _bench(
        "arithmetic",
        _ARITH,
        Samples(arith_corpus(4000), arith_corpus(32 * 1024)),
        ("1+2", "(1)", "12*3", "1/2-3", "((1+2))"),
        ("1+", "()", "1++2", "", "1 + 2"),
    ),
    # The same language with the whole expression in ONE paren group: the run
    # its terms make is separated by a SET of leads (`addop ::= "+" | "-"`)
    # inside a bracket, where no top-level plan can cut. The region path cuts
    # at either lead and never at the terms' own `*` and `/`.
    _bench(
        "paren-arithmetic",
        _ARITH,
        Samples(paren_arith_corpus(4000), paren_arith_corpus(32 * 1024)),
        ("1+2", "(1)", "12*3", "1/2-3", "((1+2))"),
        ("1+", "()", "1++2", "", "1 + 2"),
    ),
    _bench(
        "csv",
        _CSV,
        Samples(csv_corpus(220), csv_corpus(560)),
        ("x", "1,2", "a b,c", "a\nb"),
        (",", "a,,b", "a\n\nb", "", "a;b"),
    ),
    _bench(
        "json",
        _JSON,
        Samples(json_corpus(60), json_corpus(790)),
        # each of these is a place a fixed token set has to guess: `true` inside
        # a string, a space both `ws` and `chars` hold, digits both `number` and
        # `chars` hold. They are what proved the ANTLR translation was
        # describing a SMALLER language than the grammar.
        ('{"true": "x"}', '{"a": " "}', '{"a": 123}', '{ "a":"b" }', '{"a": [1, 2]}'),
        ('{"a"}', "[", "", '{"a": }', "tru"),
    ),
    # The meta row: parsing GRAMMAR text with GBNF's own self-grammar — the one
    # workload where lexic's input is the thing lexic is for. It is an ordinary
    # row now, model and all.
    _bench(
        "gbnf-meta",
        _self_grammar_source(GBNF_FLAVOUR),
        Samples(ground_truth("json.gbnf"), meta_corpus("json.gbnf", 24)),
        ('# a b c\nroot ::= "x"\n', "root ::= [a-z]+\n", 'root ::= "a" | "b"\n'),
        # each must be refused by the GRAMMAR, not by a later pipeline stage:
        # `root ::=` is grammatical GBNF (an empty body) that lexic rejects at
        # compile, and listing it here would fail a faithful translation
        ("::= x", "root x", '"unterminated', "root ::= [", "@", "((("),
    ),
    _bench(
        "abnf-meta",
        _self_grammar_source(ABNF_FLAVOUR),
        Samples(ground_truth("json.abnf"), meta_corpus("json.abnf", 16)),
        ('a = "x"\r\n', "a = 1*2DIGIT\r\n", '; note here\r\na = "y"\r\n'),
        ("a =", "= b", "a b", "a = %", "a = <"),
    ),
    # The vyx D-layer packet grammar (`# @start packet`) — an agent-protocol
    # language authored as pure CFG (ordered choice spelled by charset
    # subtraction) over the full Unicode alphabet. The corpus is one packet
    # with a template definition and a mixed block body; the accepts pin the
    # envelope forms, pipes, V22 empty values and non-ASCII content; the
    # rejects pin the ruled-out shapes (V24 bare "|" in an unquoted value,
    # V25 bare "&" kv value) plus non-packets.
    _bench(
        "vyx",
        ground_truth("vyx.gbnf"),
        Samples(vyx_corpus(24), vyx_corpus(230)),
        (
            "!I o:inv ^003\n",
            "!I o:env s:@weather L22< city=Porto temp=22 >\n",
            _vyx_packet("deps=^ref tags=|a|b|c\n"),
            _vyx_packet(' ship/addr: st="x" city=Porto\n'),
            _vyx_packet("debug-field= mean-unrounded= optional=1\n"),
            _vyx_packet('note="arrow → café §"\n'),
            "T:w=o:inv s:@buyer r:@supplier\n!I %w n:7\n",
        ),
        (
            "",
            "!Z o:inv\n",
            "?I\n",
            _vyx_packet("container: type=list|record mix=error\n"),
            _vyx_packet("create-or-join: key=& tag-exists=join tag-new=create\n"),
        ),
    ),
    # A document format, and the widest authored grammar here after the two
    # self-grammars: eight block kinds and six inline kinds, so the row prices
    # a real dispatch fan-out rather than a two-rule toy.
    _bench(
        "markdown",
        _MARKDOWN,
        Samples(markdown_corpus(30), markdown_corpus(135)),
        (
            "# h\n",
            "---\n",
            "> q\n",
            "- b\n",
            "7. n\n",
            "x *em* **strong** `c`\n",
            "x [a](u) ![i](p)\n",
            "```py\ncode\n```\n",
            "\n",
        ),
        (
            "",
            "no newline",
            "#no space\n",
            "*unclosed\n",
            "x *a\n",
            "```\nunclosed\n",
            "-x\n",
        ),
    ),
    # Depth, not width: 200 nested levels per row. The only bench whose cost is
    # dominated by how far DOWN a parse goes.
    _bench(
        "nested",
        _NESTED,
        Samples(nested_corpus(200, 3), nested_corpus(200, 61)),
        ("x", "(x)", "(x,y)", "((x),y)", "(((z)))", "(x,y,z)"),
        ("", "(", "()", "(x,)", "x)", "(x))"),
    ),
    # Long terminals, trivial decisions — the population P4.2's licence work
    # targets, isolated from structure.
    _bench(
        "lexruns",
        _LEXRUNS,
        Samples(lexrun_corpus(120), lexrun_corpus(420)),
        ('a="x"', "a=b", "a=1", 'a="a b c"', "_k=path/to.x", "z9=0123456789"),
        ("", "a=", "=b", "a b", 'a="unterminated', "1a=b"),
    ),
    # An unbounded shared prefix between two arms: the attempt/rollback tier
    # with nothing else in the way.
    _bench(
        "backtrack",
        _BACKTRACK,
        Samples(backtrack_corpus(90), backtrack_corpus(860)),
        (
            "def a() {b}\n",
            "def a() = b;\n",
            "def aaaaaaaaaaaaaaaaaaaa1() {x}\n",
            "def n() = v;\ndef m() {w}\n",
        ),
        ("", "def a() {b}", "def () {b}", "def a() ?b;\n", "def a() = b\n"),
    ),
    # A repetition with no STATIC cut: three record kinds, three different
    # closers, so no terminator or separator proof reaches it. Its cuts are
    # proposed and then verified — the standing witness for the shapes the
    # certified speculative route exists to reach.
    _bench(
        "mixedends",
        MIXEDENDS,
        Samples(mixedends_corpus(60), mixedends_corpus(560)),
        ("%k=v;", "<a:1>", "x\n", "a b c\n", "%a_b=c/d.e;<z:9>w one\n"),
        ("", "%k=v", "<a:1", "no newline", "%k=v;extra;", "<A:1>"),
    ),
    # The same gap's harder half: a section ends where the next one BEGINS, so
    # no occurrence of the boundary character is a boundary on its own and a cut
    # can only be proposed and then verified. Declines today, in the open.
    _bench(
        "announced",
        ANNOUNCED,
        Samples(announced_corpus(30), announced_corpus(300)),
        ("#h\n", "#h\nbody\n", "#a\nb\n#c\n", "#h with spaces\n"),
        ("", "no hash\n", "#h", "#h\nx", "#H\n"),
    ),
    # The split-ambiguous repetition: a nullable item body and a tail spelled
    # like the item's own terminator. Decided by the split rule, not by any
    # window — the one shape no lookahead tier reaches.
    _bench(
        "split-nullable",
        SPLIT_NULLABLE,
        Samples(split_nullable_corpus(60), split_nullable_corpus(480)),
        ("\n\n", "a\n\n", "a\nb\n\n", "\n\n\n", "a\n\n\nb\n\n"),
        ("", "\n", "a\n", "a", "A\n\n"),
    ),
    # The same unit wrapped — a fixed prefix, a fixed closer, and the
    # repetition in a rule of its own.
    _bench(
        "wrapped-unit",
        WRAPPED_UNIT,
        Samples(wrapped_unit_corpus(60), wrapped_unit_corpus(480)),
        ("<<<\n\n\n>>>\n", "<<<\na\n\n>>>\n", "<<<\na\nb\n\n\n\n>>>\n"),
        ("", "<<<\n>>>\n", "\n\n", "<<<\na\n\n", "a\n\n>>>\n"),
    ),
    # An envelope whose separator is also a value's continuation: every newline
    # is a loop boundary the next line settles, on the predictive path, by the
    # live set. Also a split source, so its mt rows run the boundary in workers.
    _bench(
        "two-mark",
        TWO_MARK,
        Samples(two_mark_corpus(450), two_mark_corpus(4150)),
        (
            "ka = v",
            "ka = v\n w",
            "ka = v\tkb = w",
            "; c\nka = v\n",
            "ka = v\n; c\nkb = w",
        ),
        ("", "ka =", "ka = v\n\n\nkb", "KA = v", "ka = v\t"),
    ),
    # Pairs that reopen: `(0),(1)` is one long pair or two short ones, an arm
    # choice whose readings both complete and are ranked by the decider. Its mt
    # rows decline in the open — a comma inside a long pair makes no cut provable.
    _bench(
        "reopening",
        REOPENING,
        Samples(reopening_corpus(600), reopening_corpus(5000)),
        ("[(0)]", "[(0),(1)]", "[(0),(1),(2)]", "[(12),(3),(45),(6)]"),
        ("[]", "[(0),]", "[(0)(1)]", "(0)", "[(a)]"),
    ),
    # Three languages written directly, which the multi-arm fold runs
    # predictively, and the same three written through a relay rule, which
    # reach the gated engine: the whole-parse fallback, an exact-width island
    # and a climbing one. The relay rows assert their counters in
    # `tests/integration/lexic/parity/test_engine_reach.py`, so a row that
    # stops reaching the engine it is named for FAILS instead of going quiet.
    _bench("start-fallback", START_FALLBACK, *_FALLBACK_INPUTS),
    _bench("interior-exact", INTERIOR_EXACT, *_EXACT_INPUTS),
    _bench("interior-climb", INTERIOR_CLIMB, *_CLIMB_INPUTS),
    _bench("relay-fallback", RELAY_FALLBACK, *_FALLBACK_INPUTS),
    _bench("relay-exact", RELAY_EXACT, *_EXACT_INPUTS),
    _bench("relay-climb", RELAY_CLIMB, *_CLIMB_INPUTS),
    # The DENSE counterpart: same engine, every column occupied, so a
    # per-column change cannot report a sparse chart's saving unopposed.
    _bench(
        "dense-earley",
        DENSE_EARLEY,
        Samples(dense_earley_corpus(2000), dense_earley_corpus(4800)),
        ("a\n", "a+b\n", "a+b+c\n", "z\nz\n", "a+b\nc+d\n"),
        ("", "a", "a+\n", "+a\n", "a++b\n", "A\n", "a b\n"),
    ),
    _bench(
        "island-earley",
        ISLAND_EARLEY,
        Samples(island_corpus(32), island_corpus(300)),
        ("a\n", "a + b\n", "af1(x.y,1)\n", "a + bf1(p/q) - c\n", "a_1 - b\n"),
        ("", "a", "a +\n", "a ++ b\n", "1a\n", "af1(x\n", "A\n"),
    ),
)
BENCHES: tuple[Bench, ...] = tuple(
    bench for bench in _DEFINED_BENCHES if bench is not None
)
"""Every benchmarked language. Adding one is a row here, not a per-tool grammar."""
