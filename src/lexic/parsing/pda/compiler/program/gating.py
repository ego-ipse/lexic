"""What admits the next character — the gates, and the selection that reads them.

The flat records say what a clone IS; this says whether the input at the
cursor lets it continue, and which arm it continues into. The two are one
subject each and the dependency runs one way: a gate reads a
:class:`~lexic.parsing.pda.compiler.program.flatten.FlatClone`, never the
reverse.

Distinct from two neighbours that share the word. The analysis package's
``gates/`` DECIDES at compile time which gate a decision point carries;
``runtime/admission.py`` tests whether an ARM is admissible once a frame is
entered. This module executes a compiled gate against the text.

``WideSelect`` stays with the record: it is the declared type of
``FlatClone.wide_selectors``, so a clone cannot be described without it.
"""

from __future__ import annotations

from typing import Any, NamedTuple

from lexic.exceptions import EngineInvariantError
from lexic.parsing.pda.compiler.program.flatten import FlatClone
from lexic.parsing.pda.compiler.program.opcodes import (
    GATE_ATTEMPT,
    GATE_GREEDY,
    GATE_KWIN,
    GATE_PEEK,
    GATE_STOP,
)
from lexic.parsing.pda.core.errors import PdaFail, ProbeFork
from lexic.parsing.pda.core.scanner import scan_gate_take


def window_admits(text: str, pos: int, windows: Any, at_eof: bool = False) -> bool:
    """Whether the input at ``pos`` is EOF-exactly consistent with a k-window.

    The runtime test for a ``k``-window gate (Task 6.3 part c) — a loop
    take/skip gate (:data:`GATE_KWIN`) or an arm selector
    (:class:`KWindowSelect`). ``windows`` is a set of ``≤k``-length
    windows, each a tuple of pre-resolved ``(chars, negated)`` position sets.
    A position at or past end-of-input is the EOF sentinel ``""``, matched by a
    positive set carrying it and — only under ``at_eof`` — by a co-finite set
    that does not exclude it. A consumer iterating a gate charset as characters
    must expect the sentinel: ``ord("")`` raises. Consistency with any one
    window admits; the demoted branches are pairwise separable, so at most one
    side's windows can be consistent with a given lookahead.

    :param text: The whole input.
    :param pos: The cursor position the window is peeked from.
    :param windows: The ``taken`` / arm windows — a tuple of
        ``((chars, negated), ...)`` tuples.
    :param at_eof: Let a co-finite position match the EOF sentinel. OFF by
        default: unconditionally on, an earlier arm matches at end of input and
        SHADOWS a later one that would have parsed (87 more whole-parse
        fallbacks across the ground-truth corpora). :func:`select_gated` turns
        it on only for a rescue pass.
    :returns: ``True`` iff the lookahead is consistent with some window.
    """
    n = len(text)
    for win in windows:
        ok = True
        for j, (chars, negated) in enumerate(win):
            p = pos + j
            char = text[p] if p < n else ""
            member = (
                ((at_eof or char != "") and char not in chars)
                if negated
                else char in chars
            )
            if not member:
                ok = False
                break
        if ok:
            return True
    return False


def _skip_noise(text: str, pos: int, chars: frozenset, negated: bool) -> int:
    """The position past the maximal ``W``-noise run at ``pos`` (non-consuming).

    The P3 peek's first half: ``(chars, negated)`` is the pre-resolved
    skippable alphabet ``W``; the caller inspects the char at the returned
    position without ever moving the real cursor.
    """
    n = len(text)
    while pos < n:
        ch = text[pos]
        member = (ch not in chars) if negated else (ch in chars)
        if not member:
            break
        pos += 1
    return pos


def _peek_admits(text: str, pos: int, gate: Any) -> bool:
    """Whether a P3 peek gate (:data:`GATE_PEEK`) takes another iteration.

    Skips the maximal noise run, then tests the first post-noise char against
    the ``take`` set — end-of-input is never a member (the loop exits).
    """
    (w_chars, w_negated), (t_chars, t_negated) = gate
    p = _skip_noise(text, pos, w_chars, w_negated)
    ch = text[p : p + 1]
    if t_negated:
        return ch != "" and ch not in t_chars
    return ch in t_chars


def gate_take(text: str, pos: int, gk: int, gate: Any) -> bool:
    """Whether a flat loop gate of kind ``gk`` admits another iteration at ``pos``.

    :data:`GATE_ATTEMPT` here is the TERMINAL attempt loop's decision (the
    driver routes non-terminal attempt items to
    :meth:`PdaKernel._attempt_iteration` before consulting a gate): take while
    the char is in the FIRST alone, and a char viable for BOTH the FIRST and
    the stored soft continuation is an arm choice in loop clothing — with no
    sub-run to consult, the terminal loop bails to the gated engine.

    :raises PdaFail: A terminal attempt boundary whose char both sets accept.
    """
    if gk == GATE_STOP:
        ch = text[pos : pos + 1]
        chars, negated = gate
        return (ch != "" and ch not in chars) if negated else ch in chars
    if gk == GATE_ATTEMPT:
        return _attempt_admits(text, pos, gate)
    return _wide_gate_take(text, pos, gk, gate)


def _wide_gate_take(text: str, pos: int, gk: int, gate: Any) -> bool:
    """The gates that read more than two characters.

    Split from :func:`gate_take` so the three one- and two-character kinds —
    the ones a hot loop consults per iteration — keep their comparison and
    return with nothing in front of them. A gate that is about to scan a window,
    a noise run or a whole tail can afford the call it costs to get here.
    """
    if gk == GATE_GREEDY:
        return not _at_the_unit_end(text, pos, gate)
    if gk == GATE_KWIN:
        return window_admits(text, pos, gate)
    if gk == GATE_PEEK:
        return _peek_admits(text, pos, gate)
    return scan_gate_take(text, pos, gate)  # GATE_SCAN — the ScanGate itself


def _attempt_admits(text: str, pos: int, gate: Any) -> bool:
    """The TERMINAL attempt loop's decision — take while the char is FIRST-only.

    :raises PdaFail: A boundary whose char both the FIRST and the stored soft
        continuation accept is an arm choice in loop clothing, and a terminal
        loop has no sub-run to consult, so it bails to the gated engine.
    """
    ch = text[pos : pos + 1]
    chars, negated = gate[0]
    take = (ch != "" and ch not in chars) if negated else ch in chars
    if take:
        fchars, fnegated = gate[1]
        if (ch != "" and ch not in fchars) if fnegated else ch in fchars:
            raise ProbeFork(
                f"attempt loop at {pos}: taking and stopping are both viable", pos
            )
    return take


def _at_the_unit_end(text: str, pos: int, gate: Any) -> bool:
    """Is what remains the unit's tail and its certified continuation?

    The split-greedy licence's whole predicate. The loop runs greedily because
    the leftmost chain does, so the only place it may stop is where no further
    item could be carved without leaving the unit no tail to end with.

    ``starters`` present means the continuation's first characters cannot begin
    an item: the tail followed by one of them locates where the continuation
    BEGINS, and the continuation is parsed normally from there. Absent, the
    continuation is matched by spelling to the end of the input — its own
    characters could otherwise start an item, and a FIRST set is not an
    occurrence boundary.

    Answering ``False`` says only "not here": ordinary item recognition and the
    loop's minimum decide whether another iteration actually parses.
    """
    tail, close, starters = gate
    if not text.startswith(tail, pos):
        return False
    after = pos + len(tail)
    if starters is None:
        # Length FIRST, then a bounded startswith. `text[after:] == close`
        # copies the whole remaining suffix every time the tail matches, which
        # on a run of terminators is O(n) boundaries × O(n) copy — quadratic
        # character work, from a gate whose entire claim is that it reads a
        # bounded window.
        return after + len(close) == len(text) and text.startswith(close, after)
    return after == len(text) or text[after] in starters


def arm_expected(clone: FlatClone) -> tuple[tuple[str, ...], bool]:
    """The characters that would have selected some arm of ``clone``.

    A no-arm refusal's expected set: the union of the FIRST-gated selectors. A
    single negated selector is reported with its polarity intact rather than
    enumerated; a mix of polarities cannot be unioned honestly in one pair, so
    it reports nothing rather than something wrong.
    """
    if clone.wide_selectors is not None:
        return (), False
    negated = [neg for _chars, neg, _arm in clone.selectors]
    if not negated or any(negated) != all(negated):
        return (), False
    merged: set[str] = set()
    for chars, _neg, _arm in clone.selectors:
        merged |= chars
    return tuple(sorted(merged)), negated[0]


class KWindowSelect(NamedTuple):
    """Arms chosen by an EOF-exact match over ``≤k``-length position windows.

    :ivar entries: ``(windows, arm)`` pairs, where ``windows`` is a tuple of
        ``((chars, negated), ...)`` position windows.
    """

    entries: tuple[tuple[Any, Any], ...]

    label = "k-window"

    @property
    def arms(self) -> tuple[Any, ...]:
        """Every arm this selection can choose, gate stripped."""
        return tuple(arm for _windows, arm in self.entries)

    def with_payloads(self, payloads: tuple[Any, ...]) -> "KWindowSelect":
        """This selection over new payloads, the window sets unchanged.

        :param payloads: New payloads, in :attr:`arms` order.
        :returns: A fresh :class:`KWindowSelect`.
        """
        return KWindowSelect(
            tuple(
                (windows, payload)
                for (windows, _arm), payload in zip(self.entries, payloads, strict=True)
            )
        )

    def select(self, text: str, pos: int) -> Any:
        """The payload whose window set matches at ``pos``, or ``None``."""
        for windows, candidate in self.entries:
            if window_admits(text, pos, windows):
                return candidate
        # Headed for a fallback: a co-finite window position cannot spell "any
        # character, OR the end", so an arm that legitimately ends the input is
        # unselectable. Retry admitting the sentinel — second pass, never
        # first, so it can only rescue a selection.
        for windows, candidate in self.entries:
            if window_admits(text, pos, windows, at_eof=True):
                return candidate
        return None


class NoiseSkipSelect(NamedTuple):
    """Arms chosen by the first character past a skipped ``W``-noise run.

    The skip does not consume: the winning arm re-parses its own noise, so the
    peek is recognition-only and a wrong pick fails the parse rather than
    silently mis-building.

    :ivar noise: ``(chars, negated)`` — the run skipped before peeking.
    :ivar entries: ``(chars, negated, arm)`` triples over the post-noise char.
    """

    noise: tuple[frozenset[str], bool]
    entries: tuple[tuple[frozenset[str], bool, Any], ...]

    label = "prefix negation"

    @property
    def arms(self) -> tuple[Any, ...]:
        """Every arm this selection can choose, gate stripped."""
        return tuple(arm for _chars, _negated, arm in self.entries)

    def with_payloads(self, payloads: tuple[Any, ...]) -> "NoiseSkipSelect":
        """This selection over new payloads, the peek gates unchanged.

        :param payloads: New payloads, in :attr:`arms` order.
        :returns: A fresh :class:`NoiseSkipSelect`.
        """
        return NoiseSkipSelect(
            self.noise,
            tuple(
                (chars, negated, payload)
                for (chars, negated, _arm), payload in zip(
                    self.entries, payloads, strict=True
                )
            ),
        )

    def select(self, text: str, pos: int) -> Any:
        """The payload admitting the first post-noise character, or ``None``."""
        at = _skip_noise(text, pos, self.noise[0], self.noise[1])
        char = text[at : at + 1]
        for chars, negated, candidate in self.entries:
            if (char != "" and char not in chars) if negated else char in chars:
                return candidate
        return None


def select_gated(text: str, pos: int, clone: FlatClone) -> Any:
    """The gated arm of a k-window or noise-skip alternation at ``pos``.

    Which of the two it is, is the selection's own business: both answer
    :meth:`~KWindowSelect.select`, so nothing here asks. The gate sets are
    pairwise separable, so at most one arm can match.

    :raises PdaFail: When no arm's gate matches and there is no default.
    """
    wide = clone.wide_selectors
    if wide is None:
        # Only reached through a `wide_selectors is not None` guard. Raised
        # rather than falling through to the default, which would turn an
        # impossible state into a quietly WRONG arm the moment that guard
        # moves. `RuntimeError` for the reason `frames_copy` uses it: the
        # engine seam catches `PdaFail` and would hide this behind an Earley
        # parse that succeeds.
        raise EngineInvariantError(
            f"select_gated: {clone.name!r} has no wide selection"
        )
    got = wide.select(text, pos)
    if got is None and clone.default is None:
        raise PdaFail(
            f"no arm at {pos}", pos, rule=clone.name, wanted=arm_expected(clone)
        )
    return got if got is not None else clone.default
