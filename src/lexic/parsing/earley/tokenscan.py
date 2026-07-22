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

from lexic.ir.nodes import IrAlphabet, IrCharClass
from lexic.ir.operators import IrNot
from lexic.parsing.earley.kernel import Kernel
from lexic.parsing.earley.tables import ParserTables

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
