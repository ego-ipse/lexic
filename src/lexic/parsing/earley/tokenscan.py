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

from abc import ABC, abstractmethod

from lexic.ir import (
    IrAlphabet,
    IrAlternation,
    IrAst,
    IrCharClass,
    IrItem,
    IrLiteral,
    IrNot,
    IrQuantifier,
    IrRule,
    IrSeq,
    IrSequence,
    IrTokenizer,
)
from lexic.parsing.earley.kernel import Kernel
from lexic.parsing.earley.normalize import normalize
from lexic.parsing.earley.resume import ResumableKernel
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


def frontier_viable(kernel: Kernel) -> bool:
    """Whether a finished kernel's text is a viable prefix of its grammar.

    Viable = a complete parse (``accept >= 0``) OR some frontier item still faces
    a symbol (``next_sym != 0``). The items advanced INTO the frontier column by
    the last scan are ungated (only fresh frontier *seeds* are FIRST-gated on the
    absent next char), so ``cols[len(text)]`` witnesses extendability with no
    kernel change — a read-only view over the chart.

    :param kernel: A kernel whose :meth:`~lexic.parsing.earley.kernel.Kernel.run`
        (or resumable extension) has finished.
    :returns: ``True`` when some valid word has the kernel's text as a prefix.
    """
    if kernel.accept >= 0:
        return True
    next_sym = kernel.tables.codes.next_sym
    bits = kernel.tables.packing.bits
    return any(next_sym[it >> bits] != 0 for it in kernel.cols[len(kernel.text)])


def viable_prefix(tables: ParserTables, text: str) -> bool:
    """Whether ``text`` is a viable prefix of the char grammar — the mask oracle.

    One fresh recognition run read through :func:`frontier_viable`. Requires
    char-granular ``tables`` (see :func:`split_literals`); the resumable mask
    path answers the same question incrementally, and the differential tests
    hold the two equal.

    :param tables: Char-granular compiled tables for the grammar.
    :param text: The candidate char prefix.
    :returns: ``True`` when some valid word has ``text`` as a prefix.
    """
    return frontier_viable(Kernel(tables, text).run())


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


class TokenKernel(ResumableKernel):
    """A :class:`Kernel` that also scans token terminals at boundary columns.

    Subclasses :class:`~lexic.parsing.earley.resume.ResumableKernel`, so a token
    chart can also grow (`extend`) across generation steps — the mask cursor's
    ``push(id)`` reuse; a plain one-shot parse never calls the resume surface.

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


TrieNode = tuple[dict[str, "TrieNode"], list[int]]
"""One spelling-trie node — ``(edges by next char, token ids ending here)``."""


def spelling_trie(tokenizer: IrTokenizer, universe: frozenset[int]) -> TrieNode:
    """The char trie over every token's spelling — the mask DFS substrate.

    Built once per cursor; shared prefixes across the vocab collapse to one
    path, which is exactly what makes the resumable mask per-token
    O(spelling length) instead of O(prefix + spelling) reparses.

    :param tokenizer: The tokenizer whose spellings to index.
    :param universe: The token ids to include (empty spellings are skipped —
        an empty token consumes nothing and is never admissible).
    :returns: The trie root.
    """
    root: TrieNode = ({}, [])
    for tid in universe:
        spelling = str(tokenizer.spell(tid))
        if not spelling:
            continue
        node = root
        for char in spelling:
            child = node[0].get(char)
            if child is None:
                child = node[0][char] = ({}, [])
            node = child
        node[1].append(tid)
    return root


class TokenMaskCursor[K: ResumableKernel](ABC):
    """Generation-time admissible-next-token mask over a grammar (capability C).

    The cursor holds the token ids generated so far ON A LIVE CHART — one
    :class:`ResumableKernel` parses the whole generation exactly once:
    :meth:`push` extends it by the accepted token's spelling (never rolled
    back — the E6-3 reuse), :meth:`mask` explores candidate continuations
    with mark/extend/rollback and :meth:`accepts` reads the chart's accept.
    Generation is inherently id-space, so this cursor — not a second parse
    interface — is capability C's surface.

    Two grammars, two cursors (:meth:`of` picks): :class:`TokenTermCursor`
    reads the mask straight off the frontier's live token-terms, while
    :class:`CharTrieCursor` explores a spelling trie on a char-granular
    recognizer. This base owns everything that does not differ — the prefix
    state, the chart sync, :meth:`push` and :meth:`accepts`.

    ``ids`` is the public prefix state and may be assigned directly (the
    stateless-recompute contract): every read syncs the chart to it — a
    common-prefix rollback plus extension, so an unchanged prefix costs one
    list compare and a normal generation step extends by one token.

    Generic in ``K``, the recognizer it drives, so a subclass that needs the
    token kernel's own surface (the boundary map) reads it off ``_kern``
    directly instead of re-narrowing.

    :ivar ids: The token ids pushed so far (the generated prefix).
    """

    __slots__ = ("_tokenizer", "_universe", "_kern", "_committed", "ids")

    _kern: K

    def __init__(self, tokenizer: IrTokenizer, kern: K) -> None:
        """Bind the cursor to a started kernel over the empty prefix.

        :param tokenizer: The tokenizer whose id space generation ranges over.
        :param kern: The live recognizer, already ``run()`` at ``""``.
        """
        self._tokenizer = tokenizer
        self._universe = frozenset(tokenizer.ids())
        self._kern = kern
        self._committed: list[tuple[int, int]] = []  # (token id, char end)
        self.ids: list[int] = []

    @staticmethod
    def of(grammar: IrAst, tokenizer: IrTokenizer) -> TokenMaskCursor:
        """The cursor for ``grammar`` — token-term or char-trie.

        A grammar carrying token terminals (:class:`~lexic.ir.nodes.IrAlphabet`)
        gets the frontier set algebra; any other grammar gets the trie DFS over
        a char-granular recognizer.

        :param grammar: The codegen grammar (with resolved token terminals).
        :param tokenizer: The tokenizer whose id space generation ranges over.
        :returns: A fresh cursor at the empty prefix.
        """
        tables = compile_tables(normalize(lift_optional_nullables(grammar)))
        specs = token_term_specs(tables)
        if specs:
            return TokenTermCursor(tokenizer, TokenKernel(tables, "", {}).run(), specs)
        char_tables = compile_tables(
            normalize(lift_optional_nullables(split_literals(grammar)))
        )
        return CharTrieCursor(tokenizer, ResumableKernel(char_tables, "", False).run())

    @abstractmethod
    def mask(self) -> set[int]:
        """The set of token ids admissible right after the current prefix.

        :returns: Admissible next-token ids (empty when only end-of-input is
            admissible — see :meth:`accepts`).
        """

    def _purge(self, cut: int) -> None:
        """Drop per-cursor state for chart positions at or past ``cut``.

        Nothing to drop by default; :class:`TokenTermCursor` purges its
        boundary map.
        """

    def _record(self, token_id: int, spelling: str) -> None:
        """Note the token about to be appended at the chart's current end.

        A no-op by default; :class:`TokenTermCursor` files the boundary its
        scan reads.
        """

    def _sync(self) -> None:
        """Bring the live chart in line with :attr:`ids` (no-op when equal).

        Shares the longest committed prefix: later tokens roll back (pure
        truncation — per-cursor state purges with them), missing ones extend.
        """
        committed = self._committed
        if [tid for tid, _ in committed] == self.ids:
            return
        ids = list(self.ids)
        k = 0
        while k < len(committed) and k < len(ids) and committed[k][0] == ids[k]:
            k += 1
        if len(committed) > k:
            cut = committed[k - 1][1] if k else 0
            self._kern.rollback(cut)
            del committed[k:]
            self._purge(cut)
        for tid in ids[k:]:
            self._extend_token(tid)

    def _extend_token(self, token_id: int) -> None:
        """Grow the committed chart by one token's spelling."""
        kern = self._kern
        spelling = str(self._tokenizer.spell(token_id))
        self._record(token_id, spelling)
        kern.extend(spelling)
        self._committed.append((token_id, len(kern.text)))

    def push(self, token_id: int) -> None:
        """Extend the generated prefix by one token — the chart grows in place.

        :param token_id: The generated token's id.
        """
        self.ids.append(token_id)
        self._sync()

    def accepts(self) -> bool:
        """Whether the current token sequence is a complete parse (end-of-input).

        :returns: ``True`` when the grammar accepts the prefix as-is.
        """
        self._sync()
        return self._kern.accept >= 0


class TokenTermCursor(TokenMaskCursor[TokenKernel]):
    """Mask cursor for a grammar with token terminals — frontier set algebra.

    The mask reads straight off the frontier column's live token-terms: no
    exploration, no rollback. The kernel is a :class:`TokenKernel`, so the
    cursor also files each committed token's boundary for its scan.
    """

    __slots__ = ("_specs",)

    def __init__(
        self,
        tokenizer: IrTokenizer,
        kern: TokenKernel,
        specs: dict[int, TokenSpec],
    ) -> None:
        """Bind to a started :class:`TokenKernel` and its token-term specs."""
        super().__init__(tokenizer, kern)
        self._specs = specs

    def _purge(self, cut: int) -> None:
        """Drop boundary entries for the rolled-back tail."""
        bounds = self._kern.bounds
        for pos in [p for p in bounds if p >= cut]:
            del bounds[pos]

    def _record(self, token_id: int, spelling: str) -> None:
        """File the boundary the token scan reads at the chart's current end."""
        kern = self._kern
        kern.bounds[len(kern.text)] = (token_id, len(spelling))

    def mask(self) -> set[int]:
        """The admissible ids — the frontier's waiting token-terms, unioned."""
        self._sync()
        kernel = self._kern
        scannable = kernel.st.scannable[len(kernel.text)]
        out: set[int] = set()
        for tid, (ids, negated) in self._specs.items():
            if scannable.get(tid):
                out |= (self._universe - ids) if negated else set(ids) & self._universe
        return out


class CharTrieCursor(TokenMaskCursor[ResumableKernel]):
    """Mask cursor for a char grammar — trie DFS over the vocab's spellings.

    Shared prefixes extend once, dead branches prune on an empty column, and a
    token is admitted iff the chart stays viable at its spelling's end
    (:func:`frontier_viable`) — the same admitted set as the stateless
    per-token :func:`viable_prefix` recompute, at per-token O(spelling length).
    """

    __slots__ = ("_trie",)

    def __init__(self, tokenizer: IrTokenizer, kern: ResumableKernel) -> None:
        """Bind to a started char-granular recognizer and build the trie."""
        super().__init__(tokenizer, kern)
        self._trie = spelling_trie(tokenizer, self._universe)

    def mask(self) -> set[int]:
        """Explore spellings on the live chart, rolling each back.

        Iterative DFS with an explicit frame stack (edge iterator + the mark
        taken before descending). A char whose extension leaves the new
        column empty is a dead branch for every continuation — prune; a node
        holding ids admits them iff the chart is viable there.
        """
        self._sync()
        kern = self._kern
        out: set[int] = set()
        stack = [(iter(self._trie[0].items()), kern.mark())]
        while stack:
            edges, m = stack[-1]
            step = next(edges, None)
            if step is None:
                stack.pop()
                kern.rollback(m)
                continue
            char, (child_edges, child_ids) = step
            inner = kern.mark()
            kern.extend(char)
            if not kern.cols[len(kern.text)]:
                kern.rollback(inner)  # no item consumed the char — dead branch
                continue
            if child_ids and frontier_viable(kern):
                out.update(child_ids)
            if child_edges:
                stack.append((iter(child_edges.items()), inner))
            else:
                kern.rollback(inner)
        return out
