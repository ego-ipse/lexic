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

from typing import Callable

from lexic.compile import CompiledGrammar, Directives, Vocabulary
from lexic.ir import IrAst, IrFlavour, IrTokenizer

__all__ = ["Params", "Reader", "Reading"]


class Params:
    """The rest of a reading's input — everything beside the text itself.

    Directives are the chips, ``bound`` names the reading whose product
    is this one's vocabulary, a resolver is the answer to an ambiguity,
    an origin is where the text came from. They ride every re-read,
    because they are part of what was read rather than settings applied
    to it.

    A binding is an ident and not a tokenizer, which is what makes it
    survive: editing the vocabulary document re-reads everything bound
    to it, and a saved session can name the binding without carrying a
    hundred thousand entries. ``vocabulary`` is what ``bound`` resolved
    to on the last read — derived, never declared.

    ``origin`` is not provenance decoration. One artefact — a compiled
    value — is read by IMPORTING it, and a module is imported by path,
    not by source. Its reader needs the path the same way a flavour
    needs its directives.
    """

    __slots__ = ("directives", "resolver", "origin", "bound", "vocabulary")

    def __init__(self, origin: str = "") -> None:
        self.directives = Directives()
        self.resolver: str = ""
        self.origin = origin
        self.bound: str = ""
        self.vocabulary = Vocabulary()


class Reader:
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

    __slots__ = (
        "name",
        "kind",
        "grammar",
        "read",
        "instance",
        "refine",
        "comments",
        "of",
        "flavour",
    )

    def __init__(
        self,
        name: str,
        kind: str,
        read: Callable[[str, Params], object],
        *,
        instance: Callable[[str], object] | None = None,
        refine: Callable[[object, Params], object] | None = None,
        grammar: IrAst | None = None,
        comments: bool = False,
        of: str = "",
        flavour: IrFlavour | None = None,
    ) -> None:
        self.name = name
        self.kind = kind
        self.read = read
        self.instance = instance
        self.refine = refine
        self.grammar = grammar
        self.comments = comments
        self.of = of
        self.flavour = flavour


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

    __slots__ = (
        "ident",
        "title",
        "kind",
        "text",
        "reader",
        "params",
        "instance",
        "product",
        "error",
        "x",
        "y",
    )

    def __init__(
        self,
        ident: str,
        title: str,
        kind: str = "text",
        reader: str = "",
        text: str = "",
        origin: str = "",
    ) -> None:
        self.ident = ident
        self.title = title
        self.kind = kind
        self.reader = reader
        self.text = text
        self.params = Params(origin)
        self.instance: object | None = None
        self.product: object | None = None
        self.error: str = ""
        self.x = 0
        self.y = 0

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
        return self.compiled is not None or self.flavour is not None

    def as_reader(self) -> Reader | None:
        """This reading's product, as something that reads.

        A compiled grammar reads texts into models; a loaded flavour
        reads texts into grammars. Anything else reads nothing, and
        returns ``None`` rather than a reader that would refuse
        everything.
        """
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
    from lexic.compile import compile_text, parse_grammar

    def read(text: str, params: Params) -> object:
        return compile_text(
            text,
            flavour=flavour,
            vocabulary=params.vocabulary,
            directives=params.directives,
        )

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
