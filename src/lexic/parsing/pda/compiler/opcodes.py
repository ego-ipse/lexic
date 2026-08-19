"""The flat program's vocabulary — op-codes, build-modes, gate and field codes.

The int codes every layer of the PDA's flat half agrees on: the compiler's
lowering and post-flatten passes cut them, the runtime driver dispatches on them,
and the tests pin them. A leaf by construction — it imports nothing, so the
record shapes (:mod:`~lexic.parsing.pda.compiler.flatten`) and the runtime
matchers can both read the vocabulary without either depending on the other.
"""

from __future__ import annotations

OP_LIT, OP_CC, OP_REF, OP_GRP, OP_ISLAND, OP_FAIL = 0, 1, 2, 3, 4, 5
"""Flat item op-codes: literal, char class, clone reference, inline group,
parse-island reference, fail-island reference."""

OP_LIT1, OP_CC1, OP_VSTR, OP_REF1 = 6, 7, 8, 9
"""Specialised op-codes cut by the post-flatten passes: an exactly-once
(``lo == hi == 1``) literal / char class (no quantifier loop, no gate); a
reference to a terminal-only ``value_str`` clone the runtime matches inline —
whole quantifier loop, arm selection, span slice and model build — without
pushing a frame; and an exactly-once clone entry (ref or group) in an arm that
keeps no item ends, so the driver advances past it before descending (no
count bookkeeping, no resume re-check)."""

TERMINAL_OPS = frozenset((OP_LIT, OP_CC, OP_LIT1, OP_CC1))
"""Every op-code that consumes text directly rather than through a clone.

The specialised pair is NOT ordinally adjacent to the plain pair, so a reader
asking "is this item a terminal" has to ask this set rather than compare. The
reduce completion learned that the expensive way: testing ``kind <= OP_CC``
read a specialised terminal as a clone reference and looked for children it
had no sink for, which is why the reduce path skipped terminal specialisation
altogether and stepped a quantifier loop per character."""

OP_VRUN, OP_V1 = 10, 11
"""Exactly-once ``OP_VSTR`` reference op-codes (:func:`_specialize_vruns`).

An item whose quantifier is ``{1,1}`` has no loop for the loop driver to run, so
it calls its matcher directly: :data:`OP_VRUN` when the target is span-tabled
(:attr:`FlatClone.runarm`, matched by one ``run_span_once``), :data:`OP_V1`
otherwise (one ``vstr_once``, which consults a char table itself). Both are
COMPILE-time facts, so they earn codes rather than a per-occurrence test —
which is the whole point: a test would tax every item that never qualifies."""

OP_VDISP = 12
"""A reference to a DISPATCH alternation whose every target is an inlinable
``value_str`` — matched inline, no frame and no table (:func:`vdisp_target`).

A tabled dispatch answers the chase with a lookup, which needs the targets'
language to be one character wide. A multi-character target has no key, but the
chase is still a lead-char walk — so the SELECTION inlines even where the MODEL
cannot be tabled."""

OP_LEAF1 = 13
"""An exactly-once reference to a FRAME-LESS LEAF clone — run inline.

``_enter`` would ask four compile-time questions (gated selection, the leaf
flag, the build mode) and then call ``_run_leaf``; this code says the answers
already. Numbered above :data:`OP_VRUN` so the driver's span branch routes it
with no comparison of its own.

**Every consumer that sees THROUGH a reference must list this code beside**
:data:`OP_REF1` — dispatch conversion (``_unit_ref_target``) and admission
prefixes (``lower._arm_prefix_steps``) both do. An omission there does not slow
the parse: it silently costs an alternation its frame-less chase, or an attempt
its skip, which is a frame and a model per occurrence."""

GATE_STOP, GATE_PAIR, GATE_KWIN, GATE_PEEK, GATE_SCAN, GATE_ATTEMPT = 0, 1, 2, 3, 4, 5
"""Flat loop-gate codes: single-char stop-set, LL(2) 2-char pair set, the
``k``-window gate (Task 6.3 part c) — a set of ``≤k``-length pre-resolved
``(chars, negated)`` position windows the runtime matches EOF-exactly against
``text[pos:pos+k]`` (the P2 demotion of a loop the single-char stop-set /
LL(2) pair could not separate) — and the P3 noise-skip peek gate (Task 6.4):
``((w_chars, w_negated), (take_chars, take_negated))`` — skip the maximal
``W``-noise run *without consuming*, take another iteration iff the first
post-noise char is in ``take`` (the iteration then re-parses the noise
normally — the peek is recognition-only, so a wrong take fails the parse
rather than silently mis-building) — and the P3 *structured* / P5 gate
(:data:`GATE_SCAN`, Task 6.6), a :class:`~lexic.parsing.pda.core.scanner.ScanGate`
the runtime consults via
:func:`~lexic.parsing.pda.core.scanner.scan_gate_take` (folding-aware
comment-bearing noise, and the rulename probe)."""

BUILD_TRANSPARENT, BUILD_VALUE_STR, BUILD_ALT, BUILD_SEQ = 0, 1, 2, 3
"""Flat clone build-modes — how a completed frame folds to a model (or, for
``transparent``, funnels its children through without building)."""

BUILD_DISPATCH = 4
"""A frame-less ``alternation`` clone: after hoist_arms every arm is a single
unit ruleref, and the alternation itself is a pass-through (the matched arm's
sub-model reports straight to the parent sink) — so the post-flatten pass
rewrites qualifying clones into dispatch tables whose selectors carry the
target :class:`FlatClone` directly and the runtime chases them in
:meth:`~lexic.parsing.pda.runtime.kernel.kernel.PdaKernel._enter` without a frame."""

BUILD_REDUCE = 5
"""The grammar-text (reducer) completion mode — the b1 twin of the model build
modes. A reduce clone captures every child into an ordered ``parts`` list and,
on completion, feeds the reducer's cleaned children to its reduction
``body.eval`` (:data:`R_KEEP`), contributes nothing (:data:`R_DROP`, a
DROP-noise rule its subtree is dropped from), or splices its parts straight
into the caller (:data:`R_SPLICE`, an inline group). One PDA compilation, one
frame/island stack — only this completion callback differs from the model
modes; see :mod:`lexic.parsing.pda.runtime.kernel.kernel`."""

R_KEEP, R_DROP, R_SPLICE = 0, 1, 2
"""Reduce completion kinds (:data:`BUILD_REDUCE` clones): KEEP evaluates the
rule's reduction body over its cleaned children; DROP (a DROP-noise rule)
recognises and consumes but yields nothing to its parent; SPLICE (an inline
group / synthetic clone) flattens its ordered children into the caller."""

DISPATCH_EMPTY = object()
"""The ``default`` sentinel of a dispatch clone whose alternation carried an
empty (nullable) arm — on a selector miss the runtime consumes nothing and
produces nothing, exactly as the empty arm's zero-item frame would."""

M_TEXT, M_GTEXT, M_MODEL, M_MODELS, M_SPAN = 0, 1, 2, 3, 4
"""Int-coded field-bind modes (:data:`~lexic.ir.spine.bind.BIND_MODES`, in order) —
what :attr:`FlatClone.fields` carries so the fused build never compares mode
strings."""

M_CONST, M_VALUE = 5, 6
"""The two plan-only modes. :data:`M_CONST` is a class field no bound field
supplies (the plan carries its default outright); :data:`M_VALUE` is a
``value_str`` rule's matched span. Neither is a :data:`BIND_MODES` entry —
they exist because :attr:`FlatClone.plan` covers every field of the class,
not just the bound ones."""

MODE_CODE = {
    "text": M_TEXT,
    "gtext": M_GTEXT,
    "model": M_MODEL,
    "models": M_MODELS,
    "span": M_SPAN,
}
"""Bind-mode string → flat int code."""

HI_UNBOUNDED = -1
"""The flat ``his`` sentinel for an unbounded (``None``) quantifier upper bound."""
