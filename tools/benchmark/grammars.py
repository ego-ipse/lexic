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
import re
from pathlib import Path
from typing import NamedTuple

from lexic.compile import CompiledGrammar, compile_text
from lexic.exceptions import UnsupportedConstructError
from lexic.grammars import ABNF_FLAVOUR, GBNF_FLAVOUR
from lexic.ir import IrAst, IrRuleRef, census, inline_refs
from lexic.parsing.fold import ModelFold

_ROOT = Path(__file__).resolve().parents[2]
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
    :ivar compiled: lexic's own artefact, carrying the fold it parses with.
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

    @property
    def fold(self) -> ModelFold:
        """The positional fold lexic builds its model through."""
        return self.compiled.fold


class Samples(NamedTuple):
    """One bench's two documents — the same language at two scales.

    :ivar corpus: The default sample every row times.
    :ivar full: The document-scale sample the mt rows always time.
    """

    corpus: str
    full: str


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
    )


_NOISE_NAMES = frozenset({"ws", "sp", "wsp", "c-wsp", "c-nl", "nl"})
"""The benchmark's authored noise vocabulary — rule names the `-ns` variant
marks `@non-semantic` where the grammar spells one. Authored HERE, per fixture
set, exactly as a grammar's author would write the directive; a grammar with no
such rule gets an empty set and its `-ns` engine honestly equals its `-lex`
one. Never consulted by engine code — noise is a declaration, not a heuristic.
"""


def _refs_of(rule) -> set[str]:
    """The rule names ``rule``'s body references."""
    return {
        str(entry.node)
        for entry in census(rule.body)
        if isinstance(entry.node, IrRuleRef)
    }


def variant_marks(ast: IrAst) -> tuple[frozenset[str], frozenset[str]]:
    """The variant engines' directive sets, derived from the grammar alone.

    The ``@lexical`` set is SELECTIVE, matching where the directive measurably
    pays: a rule is marked iff it has refs (there is something to inline), its
    every ref targets a LEAF rule with no refs of its own (one level of lexical
    depth — the tier whose per-occurrence models are pure overhead), and
    :func:`~lexic.ir.inline_refs` accepts it. Marking maximally was measured
    SLOWER on the deep self-grammars: wholesale inlining bloats alternation
    bodies and degrades the PDA's decisions, so breadth costs what depth buys.
    The ``@non-semantic`` set is the noise vocabulary above intersected with
    the grammar's own rule names.

    :param ast: The bench's canonical grammar.
    :returns: ``(lexical, non_semantic)`` rule-name sets.
    """
    refs = {str(rule.name): _refs_of(rule) for rule in ast.rules}
    leaves = {name for name, targets in refs.items() if not targets}
    lexical: set[str] = set()
    for rule in ast.rules:
        name = str(rule.name)
        if not refs[name] or not refs[name] <= leaves:
            continue
        try:
            inline_refs(ast, frozenset({name}))
        except UnsupportedConstructError:
            continue
        lexical.add(name)
    names = {str(rule.name) for rule in ast.rules}
    return frozenset(lexical), frozenset(_NOISE_NAMES & names)


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


_ANNOUNCED = """root ::= section+
section ::= header line*
header ::= hash text nl
line ::= text nl
text ::= [a-z ]+
hash ::= "#"
nl ::= "\\n"
"""
"""Sections that end where the NEXT one begins — a header line, then body
lines until another header.

The sibling of :data:`_MIXEDENDS`, and the harder half of the same gap. There
the boundary character occurs nowhere but at a unit's end, so a scan can read
the boundaries straight off the text. Here it cannot: a section ends at a
newline and is full of newlines, so no occurrence of the boundary character is
a boundary by itself. What makes the segmentation unique is the OPENING —
``FIRST(section)`` is ``#`` and nothing a section can continue with is ``#`` —
and that is a property of the grammar, not of any position in the document.

So a cut here cannot be read; it can only be proposed and then verified. That
is what makes this the shape a certified speculative fallback exists for, where
:data:`_MIXEDENDS` is the shape a wider static proof would reach. Both decline
today and both report the sequential number with their mt rows declining in
the open."""


def _announced_corpus(sections: int) -> str:
    """Sections of a header and four body lines, with no readable boundary."""
    letters = "abcdefghijklmnopqrstuvwxyz"
    out: list[str] = []
    for n in range(sections):
        out.append(f"#section {letters[n % 26] * 3} heading\n")
        for k in range(4):
            out.append(
                f"body line {letters[k]} of section {letters[(n + k) % 26] * 2} here\n"
            )
    return "".join(out)


_MIXEDENDS = """root ::= record+
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
and the start rule is a plain repetition, not an envelope. The split seam finds
no eligible work and the document parses sequentially however many workers are
offered.

Nothing about the language is hard: the arms open ``%``, ``<`` and a letter, so
each record is decided by its first character and delimited by its own closer,
which makes the segmentation of ``record+`` unique and leaves no island in the
predictive tables. The boundaries are real and abundant — a cut after any
record's closer is exact — and no static analysis names them today.

That gap is the whole point of the row: it prices a repetition the split cannot
cut, and until a mechanism reaches it the row reports the sequential number
with its mt row declining in the open."""


def _mixedends_corpus(rows: int) -> str:
    """A stream interleaving all three record kinds, none of them separated."""
    out: list[str] = []
    for n in range(rows):
        out.append(f"%key{n % 40}_a=value/{n}.{n % 7};")
        out.append(f"<span{n % 30}:{n * 3}>")
        out.append(f"note{n} carries {n % 11} words here\n")
    return "".join(out)


def _markdown_corpus(sections: int) -> str:
    """A document exercising every block and inline kind this subset defines."""
    out: list[str] = ["# Release notes\n", "\n"]
    for n in range(sections):
        out.append(f"## Section {n}\n")
        out.append(f"Prose for section {n} with *stress*, **weight** and `code`.\n")
        out.append(
            f"See [the docs](http://example.test/{n}) or ![figure](img/{n}.png).\n"
        )
        out.append(f"- bullet {n} carrying `inline` and *accent*\n")
        out.append(f"{n % 9 + 1}. numbered {n} with **weight**\n")
        out.append(f"> quoted remark {n}\n")
        if n % 4 == 0:
            out.append("```python\n")
            out.append(f"value = compute({n})\n")
            out.append("return value\n")
            out.append("```\n")
        if n % 5 == 0:
            out.append("---\n")
        out.append("\n")
    return "".join(out)


def _nested_corpus(depth: int, rows: int) -> str:
    """Nesting to ``depth`` at the spine, with breadth at each level."""
    out: list[str] = []
    for r in range(rows):
        inner = f"leaf{'' if r % 2 else 'x'}".replace("0", "o")
        text = "".join(ch for ch in inner if ch.isalpha())
        for d in range(depth):
            text = f"({text},{'ab'[d % 2]})" if d % 3 == 0 else f"({text})"
        out.append(text)
    return ",".join(out).join("()")


def _lexrun_corpus(rows: int) -> str:
    """Entries whose terminals are long — the inverse of the arithmetic row."""
    out: list[str] = []
    for n in range(rows):
        name = "field_" + "n" * (n % 40 + 8) + f"_{n}"
        if n % 3 == 0:
            value = '"' + ("text value " * (n % 6 + 3)).strip() + '"'
        elif n % 3 == 1:
            value = "path/to/some." + "segment" * (n % 5 + 2)
        else:
            value = str(n) * (n % 12 + 4)
        out.append(f"{name}={value}")
    return "\n".join(out)


def _backtrack_corpus(rows: int) -> str:
    """Statements whose arm is decided only after an unbounded shared prefix."""
    out: list[str] = []
    for n in range(rows):
        name = "n" + "a" * (n % 30 + 2) + str(n)
        if n % 2:
            out.append(f"def {name}() {{body{n}}}\n")
        else:
            out.append(f"def {name}() = value{n};\n")
    return "".join(out)


def _arith_corpus(target: int) -> str:
    """A left-nested arithmetic expression of roughly ``target`` characters."""
    parts: list[str] = ["1"]
    size = 1
    ops = ("+", "*", "-", "/")
    while size < target:
        step = len(parts)
        term = f"({step % 97 + 1}+{step % 89 + 2})"
        parts.append(ops[step % 4])
        parts.append(term)
        size += 1 + len(term)
    return "".join(parts)


def _csv_corpus(rows: int) -> str:
    """A rectangular CSV body — no quoting, so the grammar stays unambiguous."""
    return "\n".join(",".join(f"cell {r}{c}" for c in range(6)) for r in range(rows))


def _json_corpus(items: int) -> str:
    """A nested json document of ``items`` records."""
    body = ", ".join(
        f'{{"id{n}": "row {n}", "tags": ["a", "b"]}}' for n in range(items)
    )
    return f'{{"rows": [{body}], "ok": "yes"}}'


def _vyx_packet(body: str) -> str:
    """A block-body vyx packet wrapping ``body`` with an exact L-budget."""
    return f"!I o:wf L{len(body.encode())}<\n{body}>"


def _vyx_corpus(rows: int) -> str:
    """A template-carrying vyx packet whose block body mixes the line types.

    Each row contributes one kv-line, one indented scope-line, one seq-item and
    one nl-text prose line — the D.17 body shapes a real packet interleaves.
    """
    lines: list[str] = []
    for n in range(rows):
        lines.append(f"id=ORD-{n:04d} qty={n % 9 + 1} note=_")
        lines.append(f" ship: meth=express carr=DHL leg={n % 5}")
        lines.append(f'- type=feature idx={n} title="Widget {n}"')
        lines.append("free prose line about the widget catalogue")
    body = "\n".join(lines) + "\n"
    return f"T:w=o:inv s:@buyer r:@supplier\n!I %w n:7 L{len(body.encode())}<\n{body}>"


def _self_grammar_source(flavour) -> str:
    """A flavour's own self-grammar, as text in that flavour.

    The flavour carries its self-grammar as IR; emitting it back to text is what
    lets the meta row compile through the ordinary path, so lexic parses grammar
    text into a MODEL exactly as the other rows parse their inputs — no reducer,
    no semantic actions, nothing a competitor was not offered.
    """
    return str(flavour.apply(flavour.grammar))


def _ground_truth(stem: str) -> str:
    """A ground-truth grammar file — the meta row's input."""
    return (_ROOT / "resources" / "ground_truth" / stem).read_text(encoding="utf-8")


def _meta_corpus(stem: str, copies: int) -> str:
    """A large grammar file: the ground-truth grammar, concatenated.

    Each copy's rule names get a ``c<k>-`` prefix — references included, so
    every copy stays a well-formed grammar fragment and the whole keeps a
    real file's shape rather than inventing rules. Quoted literals are left
    alone: ``true`` is a rule name AND a spelled keyword, and renaming the
    keyword would change the described language mid-corpus.
    """
    source = _ground_truth(stem)
    quoted = re.compile(r'"(?:\\.|[^"\\])*"')
    names = re.findall(r"^([A-Za-z][A-Za-z0-9-]*)\s*(?:::=|=)", source, re.MULTILINE)
    rename = re.compile(
        r"\b(" + "|".join(sorted(set(names), key=len, reverse=True)) + r")\b"
    )
    out: list[str] = []
    for copy in range(copies):
        at = 0
        pieces: list[str] = []
        for match in quoted.finditer(source):
            pieces.append(rename.sub(rf"c{copy}-\1", source[at : match.start()]))
            pieces.append(match.group())
            at = match.end()
        pieces.append(rename.sub(rf"c{copy}-\1", source[at:]))
        out.append("".join(pieces))
    return "".join(out)


_DEFINED_BENCHES = (
    _bench(
        "arithmetic",
        _ARITH,
        Samples(_arith_corpus(4000), _arith_corpus(32 * 1024)),
        ("1+2", "(1)", "12*3", "1/2-3", "((1+2))"),
        ("1+", "()", "1++2", "", "1 + 2"),
    ),
    _bench(
        "csv",
        _CSV,
        Samples(_csv_corpus(220), _csv_corpus(560)),
        ("x", "1,2", "a b,c", "a\nb"),
        (",", "a,,b", "a\n\nb", "", "a;b"),
    ),
    _bench(
        "json",
        _JSON,
        Samples(_json_corpus(60), _json_corpus(790)),
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
        Samples(_ground_truth("json.gbnf"), _meta_corpus("json.gbnf", 24)),
        ('# a b c\nroot ::= "x"\n', "root ::= [a-z]+\n", 'root ::= "a" | "b"\n'),
        # each must be refused by the GRAMMAR, not by a later pipeline stage:
        # `root ::=` is grammatical GBNF (an empty body) that lexic rejects at
        # compile, and listing it here would fail a faithful translation
        ("::= x", "root x", '"unterminated', "root ::= [", "@", "((("),
    ),
    _bench(
        "abnf-meta",
        _self_grammar_source(ABNF_FLAVOUR),
        Samples(_ground_truth("json.abnf"), _meta_corpus("json.abnf", 16)),
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
        _ground_truth("vyx.gbnf"),
        Samples(_vyx_corpus(24), _vyx_corpus(230)),
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
        Samples(_markdown_corpus(30), _markdown_corpus(135)),
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
        Samples(_nested_corpus(200, 3), _nested_corpus(200, 61)),
        ("x", "(x)", "(x,y)", "((x),y)", "(((z)))", "(x,y,z)"),
        ("", "(", "()", "(x,)", "x)", "(x))"),
    ),
    # Long terminals, trivial decisions — the population P4.2's licence work
    # targets, isolated from structure.
    _bench(
        "lexruns",
        _LEXRUNS,
        Samples(_lexrun_corpus(120), _lexrun_corpus(420)),
        ('a="x"', "a=b", "a=1", 'a="a b c"', "_k=path/to.x", "z9=0123456789"),
        ("", "a=", "=b", "a b", 'a="unterminated', "1a=b"),
    ),
    # An unbounded shared prefix between two arms: the attempt/rollback tier
    # with nothing else in the way.
    _bench(
        "backtrack",
        _BACKTRACK,
        Samples(_backtrack_corpus(90), _backtrack_corpus(860)),
        (
            "def a() {b}\n",
            "def a() = b;\n",
            "def aaaaaaaaaaaaaaaaaaaa1() {x}\n",
            "def n() = v;\ndef m() {w}\n",
        ),
        ("", "def a() {b}", "def () {b}", "def a() ?b;\n", "def a() = b\n"),
    ),
    # A repetition with no derivable cut: three record kinds, three different
    # closers. The split seam declines it, so the row reports the sequential
    # number and its mt row says why — the standing witness for the shapes a
    # certified speculative fallback is meant to reach.
    _bench(
        "mixedends",
        _MIXEDENDS,
        Samples(_mixedends_corpus(60), _mixedends_corpus(560)),
        ("%k=v;", "<a:1>", "x\n", "a b c\n", "%a_b=c/d.e;<z:9>w one\n"),
        ("", "%k=v", "<a:1", "no newline", "%k=v;extra;", "<A:1>"),
    ),
    # The same gap's harder half: a section ends where the next one BEGINS, so
    # no occurrence of the boundary character is a boundary on its own and a cut
    # can only be proposed and then verified. Declines today, in the open.
    _bench(
        "announced",
        _ANNOUNCED,
        Samples(_announced_corpus(30), _announced_corpus(300)),
        ("#h\n", "#h\nbody\n", "#a\nb\n#c\n", "#h with spaces\n"),
        ("", "no hash\n", "#h", "#h\nx", "#H\n"),
    ),
)
BENCHES: tuple[Bench, ...] = tuple(
    bench for bench in _DEFINED_BENCHES if bench is not None
)
"""Every benchmarked language. Adding one is a row here, not a per-tool grammar."""
