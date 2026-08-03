"""A reading — the only thing a session contains.

Lexic has one relation, ``product = read(reader, text)``, and opsis
holds nothing else. A :class:`Reading` is that relation with a name: a
text, whatever reads it, and what came back.

Everything the instrument used to need a separate word for falls out of
it, which is why there are no other words here:

- a **reader** is a reading whose product can read — a compiled
  grammar, a loaded flavour, lexic's own module grammar;
- a **tree** is readings naming each other as reader;
- a **lane** is two readings of ONE text by different readers;
- a **loose node** is a reading with no reader named yet;
- a **binding** is a reader parameterised by a vocabulary, which is
  itself just another reading's product.

Nothing about that is a special case, and nothing here decides how any
of it looks.
"""

from __future__ import annotations

from typing import Callable, NamedTuple

from lexic.compile import (
    CompiledGrammar,
    Directives,
    compile_ast,
    compile_text,
    parse_grammar,
)
from lexic.exceptions import LexicError
from lexic.ir import IrAst, IrFlavour, IrTokenizer

__all__ = [
    "FOREIGN",
    "Outcome",
    "Params",
    "Reader",
    "Reading",
    "Source",
    "self_compiled",
]


class Source(NamedTuple):
    """A text and where it came from — the two halves of one input."""

    text: str = ""
    origin: str = ""


class Outcome(NamedTuple):
    """What one read produced — both its readings, the refusal, the cost.

    One record because they are one event: a reading either produced
    what it produced, or refused, and holding the parts separately would
    let a stale product outlive the read that made it.

    ``millis`` is measured. ``shared`` is observed: lexic memoises a
    compile by content, and a memo hit hands back the SAME artefact
    object, so two readings holding one object is the hit itself rather
    than an inference from how long it took.
    """

    instance: object | None = None
    product: object | None = None
    error: str = ""
    millis: float = 0.0
    shared: bool = False


class Params(NamedTuple):
    """The rest of a reading's input — everything beside the text itself.

    Directives are the chips, ``bound`` names the reading whose product
    is this one's vocabulary, a resolver is the answer to an ambiguity,
    an origin is where the text came from. They ride every re-read,
    because they are part of what was read rather than settings applied
    to it.

    A binding is an ident and not a tokenizer, which is what makes it
    survive: editing the vocabulary document re-reads everything bound
    to it, and a saved session can name the binding without carrying a
    hundred thousand entries. Nothing here holds the
    vocabulary itself: what is bound is applied by rebinding the
    artefact, so the artefact is where to ask what it ended up with.

    ``origin`` is not provenance decoration. One artefact — a compiled
    value — is read by IMPORTING it, and a module is imported by path,
    not by source. Its reader needs the path the same way a flavour
    needs its directives.
    """

    directives: Directives = Directives()
    resolver: str = ""
    origin: str = ""
    bound: str = ""


class Reader(NamedTuple):
    """Something that turns a text into a product.

    A reader is never conjured: it is always the product of some
    reading, or one of lexic's own surfaces the session opened. It
    carries its own grammar where it has one, which is what lets a
    reader be inspected exactly like the things it reads.

    :ivar name: What it is called on screen.
    :ivar kind: ``flavour`` / ``grammar`` / ``notation`` / ``module`` /
        ``python`` — what sort of reading it performs.
    :ivar grammar: The grammar it IS, when it has one. Python has none,
        and says so by having none.
    :ivar read: text and params in, product out; it raises to refuse.
    :ivar instance: the FIRST reading a reader may offer of one text —
        a flavour both reduces a grammar to an AST and compiles it, and
        a text read twice is the middle-rung duality, not two nodes.
    :ivar refine: where the two readings are one read in two steps, how
        the second step turns the first into the product. A vocabulary
        document is reduced once and BUILT from that reduction; without
        this, showing both readings would read ten megabytes twice.
    :ivar comments: Whether its surface can spell a ``@directive`` —
        a reader that cannot makes its chips say why.
    :ivar of: The reading this reader came out of, empty for a surface
        lexic ships.
    """

    name: str
    kind: str
    read: Callable[[str, Params], object]
    instance: Callable[[str], object] | None = None
    refine: Callable[[object, Params], object] | None = None
    grammar: IrAst | None = None
    comments: bool = False
    of: str = ""
    flavour: IrFlavour | None = None


class Reading:
    """One text, what reads it, and what came back.

    A reading is re-read whenever anything it depends on changes: its
    own text, its params, or the product of whatever reads it. What it
    produced is held as it came — a model, an AST, a tokenizer, plain
    data — never converted, because converting it would be opsis
    deciding what lexic meant.

    :ivar ident: The name gestures and rails address it by.
    :ivar params: Everything read alongside the text.
    :ivar reader: The ident of the reading whose product reads this
        one, or a shipped surface's name; empty means nothing reads it
        yet, which is a real state and not an error.
    :ivar instance: The first of the two readings, where the reader
        offers one — held, not recomputed, because recomputing it is
        exactly as expensive as the read was.
    :ivar product: What came back, or ``None`` if it refused.
    :ivar error: The refusal, verbatim, when it refused.
    """

    __slots__ = ("ident", "title", "kind", "text", "reader", "params", "outcome")

    def __init__(
        self, ident: str, title: str, kind: str = "text", reader: str = ""
    ) -> None:
        self.ident = ident
        self.title = title
        self.kind = kind
        self.reader = reader
        self.text = ""
        self.params = Params()
        self.outcome = Outcome()

    @property
    def instance(self) -> object | None:
        """The first of the two readings, where its reader offers one."""
        return self.outcome.instance

    @property
    def product(self) -> object | None:
        """What came back, or ``None`` if it refused."""
        return self.outcome.product

    @property
    def error(self) -> str:
        """The refusal, verbatim, when it refused."""
        return self.outcome.error

    @property
    def memo(self) -> str:
        """Whether the last read did the work, or found it already done.

        Not a guess from the clock: a memo hit is another reading
        already holding the very artefact this one got back.
        """
        if not self.text:
            return ""
        spent = f"{self.outcome.millis:.0f}ms"
        return f"memo hit · {spent}" if self.outcome.shared else f"fresh · {spent}"

    # ── what this reading IS, once it has been read ───────────────────

    @property
    def compiled(self) -> CompiledGrammar | None:
        """The artefact this reading produced, if it produced one."""
        return self.product if isinstance(self.product, CompiledGrammar) else None

    @property
    def tokenizer(self) -> IrTokenizer | None:
        """The vocabulary this reading produced, if it produced one."""
        return self.product if isinstance(self.product, IrTokenizer) else None

    @property
    def flavour(self) -> IrFlavour | None:
        """The reader this reading produced, if it produced one."""
        return self.product if isinstance(self.product, IrFlavour) else None

    @property
    def reads(self) -> bool:
        """Whether anything can be read BY this reading's product.

        This is the whole difference between a node that can hold
        children and one that cannot, and it is a fact about the
        product rather than a mode someone set.
        """
        return (
            self.compiled is not None
            or self.flavour is not None
            or isinstance(self.product, Reader)
        )

    def as_reader(self) -> Reader | None:
        """This reading's product, as something that reads.

        A compiled grammar reads texts into models; a loaded flavour
        reads texts into grammars; a product that is already a reader
        is one. Anything else reads nothing, and returns ``None``
        rather than a reader that would refuse everything.
        """
        if isinstance(self.product, Reader):
            # Already one. A reading whose product IS a reader needs no
            # translating — the notation is the case, and it is the top
            # of the ladder rather than an exception to it.
            return self.product
        compiled = self.compiled
        if compiled is not None:
            return Reader(
                self.title,
                "grammar",
                lambda text, params: compiled.parse(text, _resolver(params.resolver)),
                grammar=compiled.grammar,
                comments=False,
                of=self.ident,
            )
        flavour = self.flavour
        if flavour is not None:
            return _flavour_reader(flavour, of=self.ident)
        return None


def _resolver(name: str):
    """The caller's answer to an ambiguity, or ``None`` to refuse one."""
    if name != "first":
        return None
    return lambda tree, _witness: tree


def _flavour_reader(flavour: IrFlavour, of: str = "") -> Reader:
    """A flavour as a reader — it reads texts into grammars.

    Both halves of the duality live here: reading a grammar text gives
    its AST (what the reducer built), and the same text compiles into a
    reader for the level below. The compile is what
    :meth:`Reading.as_reader` picks up.
    """

    def read(text: str, params: Params) -> object:
        # Compiled unbound, always: docking a vocabulary is a rebind of
        # what this produced, and compiling per vocabulary would throw
        # away the memo on every dock.
        return compile_text(text, flavour=flavour, directives=params.directives)

    return Reader(
        str(type(flavour).name),
        "flavour",
        read,
        instance=lambda text: parse_grammar(text, flavour),
        grammar=flavour.grammar,
        comments=bool(flavour.line_comment or flavour.block_comment),
        of=of,
        flavour=flavour,
    )


def refusal_of(exc: BaseException) -> str:
    """A refusal as the sentence it is, not a traceback.

    Every refusal reads the same way whether it came from lexic or from
    foreign code, because a person looking at a red node wants the
    sentence, not the provenance of the exception class.
    """
    return f"{type(exc).__name__}: {exc}"


FOREIGN: tuple[type[BaseException], ...] = (
    ArithmeticError,
    AssertionError,
    AttributeError,
    LexicError,
    LookupError,
    OSError,
    RecursionError,
    TypeError,
    UnicodeError,
    ValueError,
)
"""What running somebody else's reader can raise.

Named rather than caught wholesale. A reader is foreign code — a
flavour loaded from a manifest, a module imported off disk — and it
fails in the ordinary ways any code does. Saying which ways is what
makes the boundary a decision instead of a shrug: a ``KeyboardInterrupt``
or a ``SystemExit`` is not a refusal and must still get through.
"""


_SELVES: dict[int, CompiledGrammar] = {}
"""Self-grammar artefacts, memoised per flavour identity."""


def self_compiled(flavour: IrFlavour) -> CompiledGrammar:
    """A flavour's own self-grammar, compiled.

    The meta ladder's first rung, and not a metaphor: a flavour carries
    the grammar of the language it reads, that grammar goes through the
    same compile as any other, and what comes back has the same fan. A
    flavour IS a grammar, so it gets a grammar's windows.
    """
    key = id(flavour)
    if key not in _SELVES:
        _SELVES[key] = compile_ast(
            flavour.grammar, cache_key=f"self:{type(flavour).name}"
        )
    return _SELVES[key]
