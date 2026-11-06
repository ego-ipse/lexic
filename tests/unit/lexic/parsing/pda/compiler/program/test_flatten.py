"""Tests for lexic.parsing.pda.compiler.program.flatten — the flat int-coded runtime program.

:mod:`lexic.parsing.pda.compiler.program.flatten` is the leaf half of the PDA compiler: it
defines the flat runtime shapes (:class:`~lexic.parsing.pda.compiler.program.flatten.FlatArm`,
:class:`~lexic.parsing.pda.compiler.program.flatten.FlatClone`,
:class:`~lexic.parsing.pda.compiler.program.flatten.PdaProgram`) and the post-flatten
optimizer passes (:func:`~lexic.parsing.pda.compiler.program.flatten.optimize_program` and its
five sub-passes) that :func:`~lexic.parsing.pda.compiler.clones.flatten_program`
drives once per :func:`~lexic.parsing.pda.compiler.clones.compile_pda`.

Every case here is built through the public compile path — small
hand-authored GBNF snippets compiled to a real :class:`PdaTables` and
inspected via ``.program`` — following ``test_clones.py``'s idiom. Every
name below (the module's own internals) is imported directly rather than
reached through ``module._name`` attribute access, matching
``test_lexruns.py``'s precedent; ``pda_from_text``/``pda_for`` come from
``test_clones`` rather than duplicated (pylint R0801).
"""

from __future__ import annotations

import pytest

from lexic.compile import compile_text
from lexic.exceptions import EngineInvariantError
from lexic.ir import BIND_MODES
from lexic.parsing.earley.kernel.tables.decider import LEFTMOST_LONGEST
from lexic.parsing.pda.compiler.program.flatten import (
    NESTING_CHAIN,
    FlatArm,
    FlatClone,
    PdaProgram,
    all_clones,
    attempt_subs,
    check_entry_shape,
    lands_on,
    mark_sub_roots,
)
from lexic.parsing.pda.compiler.program.opcodes import (
    BUILD_ALT,
    BUILD_DISPATCH,
    BUILD_SEQ,
    BUILD_TRANSPARENT,
    BUILD_VALUE_STR,
    DISPATCH_EMPTY,
    GATE_ATTEMPT,
    GATE_KWIN,
    GATE_STOP,
    HI_UNBOUNDED,
    M_GTEXT,
    M_MODEL,
    M_MODELS,
    M_SPAN,
    M_TEXT,
    MODE_CODE,
    OP_CC,
    OP_CC1,
    OP_FAIL,
    OP_GRP,
    OP_ISLAND,
    OP_LIT,
    OP_LIT1,
    OP_REF,
    OP_REF1,
    OP_VSTR,
    TERMINAL_OPS,
)
from tests.unit.lexic.parsing.pda.compiler.test_clones import only_arm, pda_from_text
from tests.unit.lexic.parsing.pda.runtime.flat_support import flat_arm, flat_clone
from tools.benchmark.cases.grammars import BENCHES


def test_op_codes_are_pairwise_distinct():
    """Every base + specialised op-code is a distinct int."""
    ops = [
        OP_LIT,
        OP_CC,
        OP_REF,
        OP_GRP,
        OP_ISLAND,
        OP_FAIL,
        OP_LIT1,
        OP_CC1,
        OP_VSTR,
        OP_REF1,
    ]
    assert len(ops) == len(set(ops))


def test_terminal_ops_are_the_four_terminal_op_codes():
    """TERMINAL_OPS is exactly the base + specialised literal/charclass codes."""
    assert TERMINAL_OPS == {OP_LIT, OP_CC, OP_LIT1, OP_CC1}


def test_gate_codes_are_distinct():
    """The stop-set and window gate codes are distinct."""
    assert GATE_STOP != GATE_KWIN


def test_build_mode_codes_are_pairwise_distinct():
    """Every model clone build-mode is a distinct int."""
    modes = [
        BUILD_TRANSPARENT,
        BUILD_VALUE_STR,
        BUILD_ALT,
        BUILD_SEQ,
        BUILD_DISPATCH,
    ]
    assert len(modes) == len(set(modes))


def test_mode_code_matches_bind_modes_order():
    """MODE_CODE maps BIND_MODES, in order, to the _M_* int codes."""
    assert [MODE_CODE[mode] for mode in BIND_MODES] == [
        M_TEXT,
        M_GTEXT,
        M_MODEL,
        M_MODELS,
        M_SPAN,
    ]


def test_hi_unbounded_is_the_negative_sentinel():
    """The flat ``his`` sentinel for an unbounded upper bound is -1."""
    assert HI_UNBOUNDED == -1


def test_dispatch_empty_sentinel_is_distinguishable_from_none():
    """DISPATCH_EMPTY is a real object, distinct from None and a target clone."""
    assert isinstance(DISPATCH_EMPTY, object)
    assert DISPATCH_EMPTY is not None


def test_flatarm_declares_exactly_the_parallel_per_item_arrays():
    """FlatArm carries exactly the seven parallel per-item arrays, no extras."""
    expected = {"n", "kinds", "payloads", "los", "his", "gate_kinds", "gate_data"}
    assert set(FlatArm.__slots__) == expected


def test_flatclone_declares_exactly_the_selector_and_build_fields():
    """FlatClone carries exactly the arm-selector + build fields, no extras.

    The count is the point, not the names. Every clone of every grammar
    carries this record, so a field added for one feature is paid for by all
    of them — the left-recursion fold's per-clone state briefly lived here, a
    slot on every clone of every grammar to serve the few rules that fold. It
    is carried in the fields its own build mode frees up instead.

    ``longest`` is the exception stated: a ``value_str`` clone's build reads
    every field its mode leaves, and the check it holds decides whether a span
    is the island's answer at all, so it cannot ride in one of them.
    ``sub_root`` is the other: a both-viable fork reads it on every frame of
    the stack, whatever the frame's mode, to find the attempt sub-runs it sits
    inside without asking each frame for a start it mostly never had.
    ``entry`` is the third: every entry that would walk its selectors reads it
    first, and the arm it names is the clone's own, which no build field holds.
    """
    expected = {"name", "selectors", "wide_selectors", "default"}
    expected |= {"struct_arm", "attempt"}
    expected |= {"mode", "ctor", "matched", "n_items", "fields", "plan"}
    expected |= {"fast", "build", "defaults", "leaf", "chartable", "chartotal"}
    expected |= {"runarm", "needs_ends", "longest", "sub_root", "entry"}
    assert set(FlatClone.__slots__) == expected


def test_a_clone_carries_the_rule_name_it_stands_for():
    """The flat artifact names itself — no reaching back into the binding view."""
    pda = pda_from_text('root ::= lit "x"\nlit ::= "a" | "b"\n')
    root = pda.program.start
    assert root.name == "root"
    assert only_arm(root).payloads[0].name == "lit"


def test_an_inline_group_clone_has_an_empty_name():
    """A group stands for no rule the grammar named, and says so."""
    pda = pda_from_text('root ::= (a "y" | b) "c"\na ::= "x"\nb ::= "z"\n')
    group = only_arm(pda.program.start).payloads[0]
    assert isinstance(group, FlatClone)
    assert group.name == ""


def test_pdaprogram_declares_start_delegates_grants_and_nests_slots():
    """PdaProgram carries the entry clone (or island opt-out), the delegate
    source, the licences it was compiled under, and whether its sub-runs nest."""
    assert PdaProgram.__slots__ == ("start", "delegates", "grants", "nests")


def test_pdaprogram_init_binds_start_verbatim():
    """PdaProgram.__init__ is a plain wrap — no processing of its argument."""
    sentinel = object()
    program = PdaProgram(sentinel)
    assert program.start is sentinel
    assert program.delegates is None  # default; the artifact attaches the source
    assert program.grants is LEFTMOST_LONGEST.grants  # the default decider's


def _plain() -> FlatClone:
    """A clone that pushes only itself."""
    return flat_clone(attempt=None)


def _dispatch(*targets: FlatClone) -> FlatClone:
    """A dispatch clone selecting ``targets``, the last also its default."""
    return flat_clone(
        BUILD_DISPATCH,
        attempt=None,
        wide_selectors=None,
        default=targets[-1],
        selectors=tuple((frozenset("x"), False, target) for target in targets[:-1]),
    )


def test_a_clone_lands_where_its_dispatch_and_attempt_hops_reach():
    """Entering a clone can push a frame of the clone itself, of any target a
    dispatch chases to — through further dispatches, its default included —
    and of any attempt entry's sub-clone; never of a clone none of those
    reach, and a cycle of hops ends."""
    plain, deep, other = _plain(), _plain(), _plain()
    inner = _dispatch(other, deep)
    outer = _dispatch(inner)
    attempt = flat_clone(attempt=((), ((None, False, None, None, plain),)))
    looped = _dispatch(other)
    looped.selectors = ((frozenset("y"), False, looped),)
    assert lands_on(plain, plain) and not lands_on(plain, deep)
    assert lands_on(outer, deep) and lands_on(outer, other)
    assert not lands_on(outer, plain)
    assert lands_on(attempt, plain) and not lands_on(attempt, deep)
    assert not lands_on(looped, deep)


# ── one complete walk: a root behind an exactly-once group is marked ────────


def _rule(name: str, *items: tuple[int, int, object], **lanes: object) -> FlatClone:
    """A one-arm clone whose arm holds ``items`` as ``(kind, gate, payload)``."""
    arm = flat_arm(
        len(items),
        kinds=tuple(kind for kind, _gate, _payload in items),
        gate_kinds=tuple(gate for _kind, gate, _payload in items),
        payloads=tuple(payload for _kind, _gate, payload in items),
    )
    fields: dict[str, object] = {
        "name": name,
        "attempt": None,
        "wide_selectors": None,
        "struct_arm": None,
        "default": None,
        "leaf": False,
        "selectors": ((frozenset("x"), False, arm),),
    }
    fields.update(lanes)
    mode = fields.pop("mode", 0)
    clone = flat_clone(mode if isinstance(mode, int) else 0)
    for lane, value in fields.items():
        setattr(clone, lane, value)
    return clone


@pytest.mark.parametrize("depth", [1, 2], ids=["one-group-deep", "two-groups-deep"])
def test_a_root_behind_an_exactly_once_group_is_marked(depth: int) -> None:
    """Call specialisation rewrites an exactly-once group to ``OP_REF1``; the
    walk follows it, so an attempt-gated loop inside one — however deep —
    still marks its payload a sub-run root."""
    target = _rule("t")
    holder = _rule("", (OP_REF, GATE_ATTEMPT, target))
    for _ in range(depth - 1):
        holder = _rule("", (OP_REF1, 0, holder))
    mark_sub_roots([_rule("s", (OP_REF1, 0, holder))])
    assert target.sub_root


def test_an_attempt_clones_entries_behind_a_group_are_marked_where_it_forks() -> None:
    """An attempt clone behind an exactly-once group, beside an attempt-gated
    loop elsewhere: its entries are roots, and the walk reaches them."""
    entry = _rule("e")
    group = _rule(
        "",
        (OP_REF, GATE_STOP, _rule("t")),
        attempt=(None, ((None, False, None, None, entry),)),
    )
    mark_sub_roots(
        [_rule("s", (OP_REF1, 0, group), (OP_REF, GATE_ATTEMPT, _rule("u")))]
    )
    assert entry.sub_root


# ── one entry shape per clone ───────────────────────────────────────────────


@pytest.mark.parametrize(
    ("lanes", "refused"),
    [
        ({"leaf": True}, False),
        ({"attempt": (None, ())}, False),
        ({"struct_arm": object()}, False),
        ({"attempt": (None, ()), "leaf": True}, True),
        ({"wide_selectors": object(), "leaf": True}, True),
        ({"mode": BUILD_DISPATCH, "wide_selectors": object()}, False),
    ],
    ids=[
        "leaf",
        "attempt",
        "gated",
        "attempt-and-leaf",
        "gated-and-leaf",
        "dispatch-and-wide",
    ],
)
def test_a_clone_enters_as_at_most_one_shape(
    lanes: dict[str, object], refused: bool
) -> None:
    """Attempt, gated selection and leaf exclude each other; a dispatch clone
    is exempt, its own selection read by the chase."""
    clone = _rule("c", **lanes)
    if refused:
        with pytest.raises(EngineInvariantError, match="at most one"):
            check_entry_shape(clone)
    else:
        check_entry_shape(clone)


def test_the_gbnf_self_grammars_cc_neg_is_a_dispatch_clone_with_a_wide_selection() -> (
    None
):
    """The witness for the dispatch exemption: compiled, ``cc-neg`` is chased
    and carries a wide selection of its own, and passes the check."""
    tables = next(b for b in BENCHES if b.name == "gbnf-meta").compiled.pda_tables()
    cc_neg = [c for c in all_clones([tables.program.start]) if c.name == "cc-neg"]
    assert cc_neg and all(
        c.mode == BUILD_DISPATCH and c.wide_selectors is not None for c in cc_neg
    )
    for clone in cc_neg:
        check_entry_shape(clone)


def _nests(source: str) -> bool:
    """Whether ``source``'s compiled program counts its sub-runs, once it has
    attempt sub-clones to count."""
    program = compile_text(source).pda_tables().program
    assert any(attempt_subs(clone) for clone in all_clones([program.start]))
    return program.nests


def _chain(levels: int) -> str:
    """A grammar whose attempt sub-runs nest ``levels`` deep, with no cycle:
    each level's two arms run the next level before they differ."""
    rules = [f'r{k} ::= x r{k + 1} ";" | x r{k + 1} "."' for k in range(levels - 1)]
    rules.append(f'r{levels - 1} ::= x ";" | x "."')
    return "\n".join([*rules, 'x ::= "a" [b-z]+', ""])


@pytest.mark.parametrize(
    "source",
    [
        'root ::= x root | x\nx ::= "a" [b-z]+ ";"\n',
        'root ::= x | x root\nx ::= "a" [b-z]+ ";"\n',
    ],
    ids=["recursive-first", "recursive-last"],
)
def test_a_right_recursion_through_an_attempt_nests(source: str) -> None:
    """An attempt edge on a cycle: a document can nest its sub-runs without
    bound, so the program counts its sub-runs."""
    assert _nests(source)


@pytest.mark.parametrize("levels", [NESTING_CHAIN, NESTING_CHAIN + 1])
def test_a_chain_nests_only_past_the_default_depth(levels: int) -> None:
    """With no cycle, the deepest chain decides: one as long as the default
    in-place depth is driven uncounted, one longer counts."""
    assert _nests(_chain(levels)) == (levels > NESTING_CHAIN)


@pytest.mark.parametrize("bench", BENCHES, ids=[b.name for b in BENCHES])
def test_no_bench_program_counts_its_sub_runs(bench) -> None:
    """No bench row's program can nest its sub-runs past the default depth, so
    none pays for the count: the cost premise of gating it."""
    assert not bench.compiled.pda_tables().program.nests
