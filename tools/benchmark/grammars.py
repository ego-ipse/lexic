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

from pathlib import Path
from typing import NamedTuple

from lexic.compile import CompiledGrammar, compile_text
from lexic.grammars import ABNF_FLAVOUR, GBNF_FLAVOUR
from lexic.ir import IrAst
from lexic.parsing.fold import ModelFold

_ROOT = Path(__file__).resolve().parents[2]


class Bench(NamedTuple):
    """One language: the grammar every engine gets, and the input they parse.

    :ivar name: The row label.
    :ivar ast: The single source of truth — what lexic compiles, and what every
        competitor's grammar is mechanically derived from.
    :ivar corpus: The input, sized so a row is dominated by parsing.
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

    @property
    def fold(self) -> ModelFold:
        """The positional fold lexic builds its model through."""
        return self.compiled.fold


def _bench(
    name: str,
    source: str,
    corpus: str,
    good: tuple[str, ...],
    bad: tuple[str, ...],
) -> Bench:
    """Compile ``source`` and pair it with the inputs that pin its language.

    The flavour is read off the source, so a self-grammar row compiles in its
    own notation without a sixth parameter.
    """
    flavour = "abnf" if name.endswith("abnf-meta") else "gbnf"
    compiled = compile_text(source, cache_key=f"bench-{name}", flavour=flavour)
    return Bench(name, compiled.grammar, corpus, good, bad, compiled)


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


def _arith_corpus(target: int) -> str:
    """A left-nested arithmetic expression of roughly ``target`` characters."""
    parts: list[str] = ["1"]
    ops = ("+", "*", "-", "/")
    while sum(len(part) for part in parts) < target:
        step = len(parts)
        parts.append(ops[step % 4])
        parts.append(f"({step % 97 + 1}+{step % 89 + 2})")
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


BENCHES: tuple[Bench, ...] = (
    _bench(
        "arithmetic",
        _ARITH,
        _arith_corpus(4000),
        ("1+2", "(1)", "12*3", "1/2-3", "((1+2))"),
        ("1+", "()", "1++2", "", "1 + 2"),
    ),
    _bench(
        "csv",
        _CSV,
        _csv_corpus(220),
        ("x", "1,2", "a b,c", "a\nb"),
        (",", "a,,b", "a\n\nb", "", "a;b"),
    ),
    _bench(
        "json",
        _JSON,
        _json_corpus(60),
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
        _ground_truth("json.gbnf"),
        ('# a b c\nroot ::= "x"\n', "root ::= [a-z]+\n", 'root ::= "a" | "b"\n'),
        # each must be refused by the GRAMMAR, not by a later pipeline stage:
        # `root ::=` is grammatical GBNF (an empty body) that lexic rejects at
        # compile, and listing it here would fail a faithful translation
        ("::= x", "root x", '"unterminated', "root ::= [", "@", "((("),
    ),
    _bench(
        "abnf-meta",
        _self_grammar_source(ABNF_FLAVOUR),
        _ground_truth("json.abnf"),
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
        _vyx_corpus(24),
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
)
"""Every benchmarked language. Adding one is a row here, not a per-tool grammar."""
