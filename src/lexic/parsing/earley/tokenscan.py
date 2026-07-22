"""The token-scanning kernel — Earley over a token-segmented input.

:class:`TokenKernel` is the :class:`~lexic.parsing.earley.kernel.Kernel`
specialisation that parses a grammar with **token terminals** against text
lexic has segmented into tokens. The base kernel is untouched (char grammars
never construct a ``TokenKernel``): this subclass adds one ``_scan`` branch —
the atomic-jump twin of the multi-char-literal scan, with ``startswith`` swapped
for an id test — plus the two per-parse fields it needs (the boundary map and
the token-term specs). This is I5's design: the char-driven PDA never matches
tokens, so a token grammar's rules island and this Earley kernel is the single
token-matching engine.
"""

from __future__ import annotations

from lexic.ir.encoding import IrTokenizer
from lexic.ir.nodes import IrAlphabet, IrAst, IrCharClass
from lexic.ir.operators import IrNot
from lexic.parsing.earley.kernel import Kernel
from lexic.parsing.earley.normalize import normalize
from lexic.parsing.earley.tables import ParserTables, compile_tables
from lexic.parsing.fold import lift_optional_nullables

TokenSpec = tuple[frozenset[int], bool]
"""A token terminal's ``(id-set, negated)`` — the id test the scan applies."""


def token_term_specs(tables: ParserTables) -> dict[int, TokenSpec]:
    """Map each token terminal's ``term_id`` to its ``(id-set, negated)`` spec.

    A token terminal is an :class:`~lexic.ir.nodes.IrAlphabet` (positive) or an
    :class:`~lexic.ir.operators.IrNot` of one (negated) whose inner char class
    holds the token ids. Empty for a grammar with no token terminals.

    :param tables: The compiled grammar tables.
    :returns: ``term_id -> (frozenset ids, negated)`` for every token terminal.
    """
    specs: dict[int, TokenSpec] = {}
    for tid, atom in enumerate(tables.terms.atoms):
        negated = isinstance(atom, IrNot)
        alpha = atom[0] if negated else atom
        if isinstance(alpha, IrAlphabet) and isinstance(alpha.inner, IrCharClass):
            specs[tid] = (frozenset(int(m) for m in alpha.inner.members()), negated)
    return specs


class TokenKernel(Kernel):
    """A :class:`Kernel` that also scans token terminals at boundary columns.

    :ivar bounds: char position → ``(token_id, char_len)`` — lexic's own token
        segmentation of the input (from :meth:`~lexic.ir.encoding.IrTokenizer
        .boundaries`).
    :ivar tok_terms: ``term_id`` → ``(id-set, negated)`` for the grammar's token
        terminals (resolved once from the tables).
    """

    __slots__ = ("bounds", "tok_terms")

    bounds: dict[int, tuple[int, int]]
    tok_terms: dict[int, TokenSpec]

    def __init__(
        self,
        tables: ParserTables,
        text: str,
        bounds: dict[int, tuple[int, int]],
        record_links: bool = False,
    ) -> None:
        """Prepare a token-aware parse of ``text``.

        :param tables: The compiled grammar (with token terminals).
        :param text: The input string.
        :param bounds: char position → ``(token_id, char_len)`` segmentation.
        :param record_links: Record SPPF provenance (off for recognition).
        """
        super().__init__(tables, text, record_links)
        self.bounds = bounds
        self.tok_terms = token_term_specs(tables)

    def _scan(self, i: int) -> None:
        """Char-scan as usual, then jump a whole token at a boundary column.

        At boundary ``i`` a waiting token term whose id test holds
        (``(id in ids) != negated``) lands ``token_len`` columns ahead — the
        multi-char-literal branch with ``startswith`` swapped for an id test.
        Off a boundary token terms never fire, so a char terminal freely crosses
        token boundaries while a token terminal only matches token-aligned. The
        consumed span records like a literal scan, so the SPPF/decode/fold
        downstream is untouched.

        :param i: The column (char position) being scanned.
        """
        super()._scan(i)
        tok = self.bounds.get(i)
        if tok is None:
            return
        tok_id, tlen = tok
        scannable_i = self.st.scannable[i]
        for tid, (ids, negated) in self.tok_terms.items():
            bucket = scannable_i.get(tid)
            if bucket and ((tok_id in ids) != negated):
                j = i + tlen
                self._advance_all(j, bucket)
                if self.record_links:
                    self._record_scans(i, j, bucket)


class TokenMaskCursor:
    """Generation-time admissible-next-token mask over a token grammar (capab. C).

    The cursor holds the token ids generated so far. :meth:`mask` reads the set
    of admissible next-token ids off the frontier column's live token-terms
    (token-frontier set algebra — no chart re-work beyond the prefix run);
    :meth:`push` extends by one token; :meth:`accepts` tests whether the current
    sequence is a complete parse (end-of-input). It recomputes from the prefix
    each step, so the mask equals a stateless recompute (fp9's correctness gate).
    Generation is inherently id-space, so this cursor — not a second parse
    interface — is capability C's surface.

    :ivar ids: The token ids pushed so far (the generated prefix).
    """

    __slots__ = ("_tables", "_tokenizer", "_specs", "_universe", "ids")

    def __init__(self, grammar: IrAst, tokenizer: IrTokenizer) -> None:
        """Constrain generation to ``grammar`` under ``tokenizer``.

        :param grammar: The codegen grammar (with resolved token terminals).
        :param tokenizer: The tokenizer whose id space generation ranges over.
        """
        self._tables = compile_tables(normalize(lift_optional_nullables(grammar)))
        self._tokenizer = tokenizer
        self._specs = token_term_specs(self._tables)
        self._universe = frozenset(int(i) for i in tokenizer.decode.keys())
        self.ids: list[int] = []

    def _run(self) -> tuple[Kernel, int]:
        """Parse the current prefix; return the kernel and its frontier column."""
        text = "".join(str(self._tokenizer.spell(i)) for i in self.ids)
        bounds = {s: (t, e - s) for s, e, t in self._tokenizer.boundaries(text)}
        return TokenKernel(self._tables, text, bounds).run(), len(text)

    def mask(self) -> set[int]:
        """The set of token ids admissible right after the current prefix.

        :returns: Admissible next-token ids (empty when only end-of-input is
            admissible — see :meth:`accepts`).
        """
        kernel, frontier = self._run()
        scannable = kernel.st.scannable[frontier]
        out: set[int] = set()
        for tid, (ids, negated) in self._specs.items():
            if scannable.get(tid):
                out |= (self._universe - ids) if negated else set(ids) & self._universe
        return out

    def push(self, token_id: int) -> None:
        """Extend the generated prefix by one token.

        :param token_id: The generated token's id.
        """
        self.ids.append(token_id)

    def accepts(self) -> bool:
        """Whether the current token sequence is a complete parse (end-of-input).

        :returns: ``True`` when the grammar accepts the prefix as-is.
        """
        kernel, _ = self._run()
        return kernel.accept >= 0
