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
from lexic.ir.nodes import (
    IrAlphabet,
    IrAlternation,
    IrAst,
    IrCharClass,
    IrItem,
    IrLiteral,
    IrQuantifier,
    IrRule,
    IrSeq,
    IrSequence,
)
from lexic.ir.operators import IrNot
from lexic.parsing.earley.kernel import Kernel
from lexic.parsing.earley.normalize import normalize
from lexic.parsing.earley.tables import ParserTables, compile_tables
from lexic.parsing.fold import lift_optional_nullables

TokenSpec = tuple[frozenset[int], bool]
"""A token terminal's ``(id-set, negated)`` — the id test the scan applies."""

_UNIT = IrQuantifier(1, 1)


def split_literals(ast: IrAst) -> IrAst:
    """Split every unquantified multi-char literal into single-char literals.

    The char-heavy mask recognises a candidate token's chars one at a time, so
    the recognizer must be **char-granular**: canonicalization merges a
    ``"d" "o" "g"`` run into one atomic literal (scanned via ``startswith``), and
    a prefix landing mid-literal (``"d"`` of ``"dog"``) can then never advance —
    it reads as dead when it is actually viable. Splitting the literal back to
    single chars restores per-char advancement. Quantified literals are left as
    is (a mid-``"ab"+`` split would change the language); no ground-truth grammar
    quantifies a multi-char literal.

    :param ast: The grammar to make char-granular.
    :returns: An equivalent grammar with unquantified multi-char literals split.
    """

    def expand(item: IrItem) -> list[IrItem]:
        atom = item.atom
        if (
            isinstance(atom, IrLiteral)
            and len(str(atom)) > 1
            and item.quantifier == _UNIT
        ):
            return [IrItem(IrLiteral(ch)) for ch in str(atom)]
        return [item]

    rules = [
        IrRule(
            rule.name,
            IrAlternation(
                *(
                    IrSequence(*(x for item in arm for x in expand(item)))
                    for arm in rule.body
                )
            ),
            rule.semantic,
        )
        for rule in ast.rules
    ]
    return IrAst(IrSeq(*rules), ast.start)


def viable_prefix(tables: ParserTables, text: str) -> bool:
    """Whether ``text`` is a viable prefix of the char grammar — the mask oracle.

    Viable = a complete parse (``accept >= 0``) OR some frontier item still faces
    a symbol (``next_sym != 0``). The items advanced INTO the frontier column by
    the last scan are ungated (only fresh frontier *seeds* are FIRST-gated on the
    absent next char), so ``cols[len(text)]`` witnesses extendability with no
    kernel change — a read-only view over the chart. Requires char-granular
    ``tables`` (see :func:`split_literals`).

    :param tables: Char-granular compiled tables for the grammar.
    :param text: The candidate char prefix.
    :returns: ``True`` when some valid word has ``text`` as a prefix.
    """
    kernel = Kernel(tables, text).run()
    if kernel.accept >= 0:
        return True
    next_sym = tables.codes.next_sym
    bits = kernel.tables.packing.bits
    return any(next_sym[it >> bits] != 0 for it in kernel.cols[len(text)])


def token_term_specs(tables: ParserTables) -> dict[int, TokenSpec]:
    """Map each token terminal's ``term_id`` to its ``(id-set, negated)`` spec.

    A token terminal is always an :class:`~lexic.ir.nodes.IrAlphabet`; negation
    lives INSIDE it — a positive alphabet's inner is the id char class, a negated
    one's inner is an :class:`~lexic.ir.operators.IrNot` of that class. Empty for
    a grammar with no token terminals.

    :param tables: The compiled grammar tables.
    :returns: ``term_id -> (frozenset ids, negated)`` for every token terminal.
    """
    specs: dict[int, TokenSpec] = {}
    for tid, atom in enumerate(tables.terms.atoms):
        if not isinstance(atom, IrAlphabet):
            continue
        inner = atom.inner
        negated = isinstance(inner, IrNot)
        charclass = inner[0] if negated else inner
        if isinstance(charclass, IrCharClass):
            specs[tid] = (frozenset(int(m) for m in charclass.members()), negated)
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

    A grammar with **token terminals** (``IrAlphabet``) uses the token-frontier
    set algebra above. A **char** grammar (no token terminals) instead ranges the
    tokenizer's ids over a char-granular recognizer: a token is admissible iff
    ``prefix+spell(token)`` stays a viable prefix (:func:`viable_prefix`) — the
    complete, sound char-heavy mask. This form reparses per candidate token
    (O(vocab) per step); a resumable recognizer is the perf follow-up.

    :ivar ids: The token ids pushed so far (the generated prefix).
    """

    __slots__ = ("_tables", "_tokenizer", "_specs", "_universe", "_char_tables", "ids")

    def __init__(self, grammar: IrAst, tokenizer: IrTokenizer) -> None:
        """Constrain generation to ``grammar`` under ``tokenizer``.

        :param grammar: The codegen grammar (with resolved token terminals).
        :param tokenizer: The tokenizer whose id space generation ranges over.
        """
        self._tables = compile_tables(normalize(lift_optional_nullables(grammar)))
        self._tokenizer = tokenizer
        self._specs = token_term_specs(self._tables)
        self._universe = frozenset(tokenizer.ids())
        # A char grammar (no token terminals) drives the char-heavy path over a
        # char-granular recognizer; a token grammar leaves this None.
        self._char_tables = (
            None
            if self._specs
            else compile_tables(
                normalize(lift_optional_nullables(split_literals(grammar)))
            )
        )
        self.ids: list[int] = []

    def _run(self) -> tuple[Kernel, int]:
        """Parse the current prefix; return the kernel and its frontier column."""
        text = "".join(str(self._tokenizer.spell(i)) for i in self.ids)
        bounds = {s: (t, e - s) for s, e, t in self._tokenizer.boundaries(text)}
        return TokenKernel(self._tables, text, bounds).run(), len(text)

    def _prefix_text(self) -> str:
        """The generated prefix spelled to characters (the char-heavy path)."""
        return "".join(str(self._tokenizer.spell(i)) for i in self.ids)

    def mask(self) -> set[int]:
        """The set of token ids admissible right after the current prefix.

        :returns: Admissible next-token ids (empty when only end-of-input is
            admissible — see :meth:`accepts`).
        """
        if self._char_tables is not None:
            return self._char_mask()
        kernel, frontier = self._run()
        scannable = kernel.st.scannable[frontier]
        out: set[int] = set()
        for tid, (ids, negated) in self._specs.items():
            if scannable.get(tid):
                out |= (self._universe - ids) if negated else set(ids) & self._universe
        return out

    def _char_mask(self) -> set[int]:
        """Char-heavy mask: every id whose char-expansion stays a viable prefix.

        Viability is prefix-monotonic (``viable(s+x) ⇒ viable(s)``), so a token
        whose FIRST char is already dead is skipped without the full-spelling
        reparse; the per-first-char result is memoised, collapsing the common
        case (most of a large vocab starts with a char no live item admits).
        """
        assert self._char_tables is not None
        tables, prefix = self._char_tables, self._prefix_text()
        first_ok: dict[str, bool] = {}
        out: set[int] = set()
        for tid in self._universe:
            spelling = str(self._tokenizer.spell(tid))
            if not spelling:
                continue
            head = spelling[0]
            if head not in first_ok:
                first_ok[head] = viable_prefix(tables, prefix + head)
            if not first_ok[head]:
                continue
            if len(spelling) == 1 or viable_prefix(tables, prefix + spelling):
                out.add(tid)
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
        if self._char_tables is not None:
            return Kernel(self._char_tables, self._prefix_text()).run().accept >= 0
        kernel, _ = self._run()
        return kernel.accept >= 0
