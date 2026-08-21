"""Tests for compile/loader.py — the flavour manifest loader.

A manifest is one IR-constructor notation expression (an ``IrMap`` of seven
strict sections); :func:`load_flavour` folds it into an :class:`IrFlavour`.
The gates: a minimal hand-assembled manifest lowers correctly (escape tables,
identity fields, the derived noise map + ``literal=DROP`` — settled 8, asserted
per-dyad BY IDENTITY), a repr-generated GBNF twin drives the real compile
pipeline under its own name (register → compile → parse → ``to_text``
round-trip, behind the cache-reset registry fixture), ``Yield()`` round-trips to
``YIELD`` by identity, the notation grammar is a self-hosting fixpoint, unknown/
missing/mis-typed sections are rejected with ``UnsupportedConstructError``, and
two loads of one text are independent.
"""

from __future__ import annotations

import pytest

import lexic.compile as compile_pkg
from lexic.compile import compile_ast, parse_grammar
from lexic.compile.notation.loader import load_flavour, load_flavour_from_path
from lexic.compile.notation.parse import NOTATION_GRAMMAR, load_ir
from lexic.exceptions import UnsupportedConstructError
from lexic.grammars import GBNF_FLAVOUR, register_flavour
from lexic.grammars.gbnf import (
    GBNF_ACTIONS,
    GBNF_ESCAPES,
    GBNF_GRAMMAR,
    GBNF_REDUCTIONS,
)
from lexic.ir import (
    DROP,
    IR_DEFAULT,
    KEEP_REDUCED,
    YIELD,
    EscapeCodec,
    IrAction,
    IrAlternation,
    IrAst,
    IrEmit,
    IrFlavour,
    IrInt,
    IrItem,
    IrLiteral,
    IrMap,
    IrRule,
    IrRuleRef,
    IrSelf,
    IrSeq,
    IrSequence,
    IrStr,
    IrTuple,
    IrTypeMap,
    Reducer,
)
from tests.paths import GROUND_TRUTH
from tools.gen_manifests import escapes_as_ir

# ── manifest fixtures ────────────────────────────────────────────────────


def mini_escape_dyads() -> list[IrTuple]:
    """The five escape-table dyads — one entry per table."""
    return [
        IrTuple(IrStr("short"), IrMap(IrTuple(IrStr("n"), IrStr("\n")))),
        IrTuple(IrStr("hex"), IrTuple(IrTuple(IrStr("x"), IrInt(2)))),
        IrTuple(IrStr("class-short"), IrMap(IrTuple(IrInt(10), IrStr("\\n")))),
        IrTuple(IrStr("class-meta"), IrTuple(IrStr("\\"), IrStr("]"))),
        IrTuple(IrStr("quote-safe"), IrTuple(IrTuple(IrInt(32), IrInt(126)))),
    ]


def mini_escapes() -> IrMap:
    """Tiny five-table escapes section."""
    return IrMap(*mini_escape_dyads())


def reducer(flavour: IrFlavour) -> Reducer:
    """The flavour's reducer, narrowed to :class:`Reducer` for its policy attrs."""
    result = flavour.reducer
    assert isinstance(result, Reducer)
    return result


def mini_grammar() -> IrAst:
    """A two-rule self-grammar with exactly one ``semantic=False`` rule."""
    return IrAst(
        IrSeq(
            IrRule(
                "start",
                IrAlternation(
                    IrSequence(IrItem(IrLiteral("a")), IrItem(IrRuleRef("ws")))
                ),
            ),
            IrRule("ws", IrAlternation(IrSequence(IrItem(IrLiteral(" ")))), False),
        ),
        "start",
    )


def mini_dyads() -> list[IrTuple]:
    """The seven section dyads of the minimal hand-assembled manifest."""
    return [
        IrTuple(IrStr("name"), IrStr("mini")),
        IrTuple(IrStr("extensions"), IrTuple(IrStr(".mini"))),
        IrTuple(IrStr("line-comment"), IrStr("#")),
        IrTuple(IrStr("escapes"), mini_escapes()),
        IrTuple(IrStr("grammar"), mini_grammar()),
        IrTuple(
            IrStr("reduction"),
            Reducer(
                actions=IrMap(
                    IrTuple(IrRuleRef("start"), YIELD), IrTuple(IR_DEFAULT, YIELD)
                ),
                default=YIELD,
                noise=IrMap(
                    IrTuple(IrRuleRef("ws"), DROP), IrTuple(IR_DEFAULT, KEEP_REDUCED)
                ),
                literal=DROP,
            ),
        ),
        IrTuple(IrStr("actions"), IrTypeMap(IrAction(IrLiteral, IrEmit()))),
    ]


def mini_manifest() -> str:
    """The minimal manifest as notation text (repr of the section map)."""
    return repr(IrMap(*mini_dyads()))


def without(name: str) -> str:
    """The minimal manifest with section ``name`` removed."""
    return repr(IrMap(*(d for d in mini_dyads() if str(d[0]) != name)))


def with_extra(extra: IrTuple) -> str:
    """The minimal manifest with one extra section dyad."""
    return repr(IrMap(*mini_dyads(), extra))


def replacing(name: str, value: object) -> str:
    """The minimal manifest with section ``name``'s value replaced."""
    dyads = [IrTuple(d[0], value) if str(d[0]) == name else d for d in mini_dyads()]
    return repr(IrMap(*dyads))


def gbnf_twin_manifest() -> str:
    """A working GBNF twin (name ``gbnf2``), repr-generated from the singleton."""
    sections = IrMap(
        IrTuple(IrStr("name"), IrStr("gbnf2")),
        IrTuple(IrStr("extensions"), IrTuple(IrStr(".gbnf2"))),
        IrTuple(IrStr("line-comment"), IrStr("#")),
        IrTuple(IrStr("escapes"), escapes_as_ir(GBNF_ESCAPES)),
        IrTuple(IrStr("grammar"), GBNF_GRAMMAR),
        IrTuple(IrStr("reduction"), GBNF_FLAVOUR.reducer),
        IrTuple(IrStr("actions"), GBNF_ACTIONS),
    )
    return repr(sections)


# The ``registry_snapshot`` fixture is shared from ``tests/conftest.py``.


# ── section lowering (§12) ───────────────────────────────────────────────


def test_identity_fields_lower() -> None:
    """name / extensions / line-comment lower to plain values."""
    flavour = load_flavour(mini_manifest())
    assert flavour.name == "mini"
    assert flavour.extensions == (".mini",)
    assert flavour.line_comment == "#"


def test_escape_tables_lower() -> None:
    """The five escape IR-dyad tables lower to the codec record's IR fields."""
    codec = load_flavour(mini_manifest()).escapes
    assert codec.short == IrMap(IrTuple(IrStr("n"), IrStr("\n")))
    assert codec.hexes == IrTuple(IrTuple(IrStr("x"), IrInt(2)))
    assert codec.class_short == IrMap(IrTuple(IrInt(10), IrStr("\\n")))
    assert {str(m) for m in codec.class_meta} == {"\\", "]"}
    assert codec.quote_safe == IrTuple(IrTuple(IrInt(32), IrInt(126)))


def test_escape_codec_is_an_irself_record() -> None:
    """Lowering builds an EscapeCodec record (an IrSelf on the spine), not a
    synthesized subclass."""
    codec = load_flavour(mini_manifest()).escapes
    assert isinstance(codec, EscapeCodec)
    assert isinstance(codec, IrSelf)  # on the IR spine, not an isolated ABC


def test_carried_noise_map_exact_dyads_by_identity() -> None:
    """The noise map is CARRIED, and each dyad is a sentinel BY IDENTITY.

    Identity is the whole question: the engine asks ``body is DROP``, so a
    manifest-loaded policy that merely reprs the same would change how every
    document folds while passing every ``==`` a test could write.
    """
    noise = reducer(load_flavour(mini_manifest())).noise
    view = dict(noise.items())  # order-insensitive key → body
    assert len(view) == 2
    assert view[IrRuleRef("ws")] is DROP
    assert view[IR_DEFAULT] is KEEP_REDUCED


def test_reducer_literal_is_drop() -> None:
    """The derived reducer's ``literal`` policy is the constant DROP sentinel."""
    assert reducer(load_flavour(mini_manifest())).literal is DROP


def test_yield_survives_by_identity() -> None:
    """F-INTERN-1: a manifest spelling ``Yield()`` loads THE ``YIELD`` singleton."""
    assert "Yield()" in mini_manifest()
    actions = reducer(load_flavour(mini_manifest())).actions
    assert actions.get(IrRuleRef("start")) is YIELD


# ── synthesized-class hygiene (§12) ──────────────────────────────────────


def test_synthesized_flavour_hygiene() -> None:
    """The synthesized flavour is an IrFlavour with __qualname__/__module__ set."""
    flavour = load_flavour(mini_manifest())
    assert isinstance(flavour, IrFlavour)
    assert type(flavour).__qualname__ == "LoadedMiniFlavour"
    assert type(flavour).__module__ == "lexic.compile.notation.loader"


def test_actions_resolve_not_the_empty_default() -> None:
    """The ``init=False`` trap: ``actions`` must be the manifest's map, not the
    empty ``IrDispatch`` default that silently resolves when the field is unset."""
    flavour = load_flavour(mini_manifest())
    assert len(flavour.actions) == 1
    assert isinstance(flavour.actions.resolve(IrLiteral("x")), IrEmit)


# ── the bootstrap fixpoint (§11) ─────────────────────────────────────────


def test_notation_grammar_is_a_loadable_fixpoint() -> None:
    """§11: the notation grammar's own repr is a loadable, equal .ir payload."""
    reloaded = load_ir(repr(NOTATION_GRAMMAR))
    assert reloaded == NOTATION_GRAMMAR
    assert isinstance(reloaded, IrAst)
    assert reloaded.non_semantic == NOTATION_GRAMMAR.non_semantic


# ── rejection (§8) ───────────────────────────────────────────────────────


def test_non_map_root_rejected() -> None:
    """A non-IrMap root (an IrAst here) is rejected."""
    with pytest.raises(UnsupportedConstructError, match="root must be an IrMap"):
        load_flavour(repr(mini_grammar()))


@pytest.mark.parametrize("section", ["name", "grammar", "escapes", "reduction"])
def test_missing_section_rejected(section: str) -> None:
    """A manifest missing any required section is rejected."""
    with pytest.raises(UnsupportedConstructError, match="missing required section"):
        load_flavour(without(section))


def test_noise_section_names_the_settled_rule() -> None:
    """A ``noise`` section is rejected with the settled-8 explanation (no noise)."""
    with pytest.raises(UnsupportedConstructError, match="carry no noise section"):
        load_flavour(with_extra(IrTuple(IrStr("noise"), IrMap())))


def test_unknown_section_rejected() -> None:
    """An unknown root section is rejected and named."""
    with pytest.raises(UnsupportedConstructError, match="unknown section 'bogus'"):
        load_flavour(with_extra(IrTuple(IrStr("bogus"), IrStr("x"))))


def test_grammar_wrong_type_rejected() -> None:
    """A ``grammar`` section that is not an IrAst is rejected."""
    with pytest.raises(UnsupportedConstructError, match="'grammar' must be an IrAst"):
        load_flavour(replacing("grammar", IrStr("nope")))


def test_actions_wrong_type_rejected() -> None:
    """An ``actions`` section that is not an IrTypeMap is rejected."""
    with pytest.raises(
        UnsupportedConstructError, match="'actions' must be an IrTypeMap"
    ):
        load_flavour(replacing("actions", IrMap()))


def test_escapes_missing_table_rejected() -> None:
    """An escapes sub-map missing one of the five tables is rejected."""
    escapes = IrMap(*(d for d in mini_escape_dyads() if str(d[0]) != "hex"))
    with pytest.raises(UnsupportedConstructError, match="escapes missing table"):
        load_flavour(replacing("escapes", escapes))


def test_escapes_unknown_table_rejected() -> None:
    """An escapes sub-map with an unknown table key is rejected."""
    escapes = IrMap(*mini_escape_dyads(), IrTuple(IrStr("bogus"), IrTuple()))
    with pytest.raises(UnsupportedConstructError, match="unknown table"):
        load_flavour(replacing("escapes", escapes))


def test_escapes_malformed_hex_dyad_rejected() -> None:
    """A malformed ``hex`` entry (not a pair) is rejected."""
    dyads = [
        IrTuple(IrStr("hex"), IrTuple(IrTuple(IrStr("x")))) if str(d[0]) == "hex" else d
        for d in mini_escape_dyads()
    ]
    with pytest.raises(UnsupportedConstructError, match="hex entry must be"):
        load_flavour(replacing("escapes", IrMap(*dyads)))


# ── GBNF twin conformance + integration (§10 smoke, §12) ─────────────────


def test_gbnf_twin_section_repr_parity() -> None:
    """Each carried section round-trips to canonical-repr equality with the twin."""
    loaded = load_flavour(gbnf_twin_manifest())
    assert repr(loaded.grammar) == repr(GBNF_GRAMMAR)
    assert loaded.grammar.non_semantic == GBNF_GRAMMAR.non_semantic  # C11
    assert repr(reducer(loaded).actions) == repr(GBNF_REDUCTIONS)
    assert repr(loaded.actions) == repr(GBNF_ACTIONS)


def test_gbnf_twin_escape_codec_parity() -> None:
    """The lowered codec matches the authored one behaviorally (settled 9 step 4)."""
    codec = load_flavour(gbnf_twin_manifest()).escapes
    assert codec.encode("\n\t\\") == GBNF_ESCAPES.encode("\n\t\\")
    assert codec.encode_point(10) == GBNF_ESCAPES.encode_point(10)  # class_short
    assert codec.encode_point(93) == GBNF_ESCAPES.encode_point(93)  # ']' class_meta
    assert codec.encode_point(65) == GBNF_ESCAPES.encode_point(65)  # printable


@pytest.mark.parametrize("grammar_file", ["arithmetic.gbnf", "json.gbnf", "list.gbnf"])
def test_gbnf_twin_parse_parity(grammar_file: str) -> None:
    """parse_grammar parity with the authored flavour on GT grammars (step 5)."""
    text = (GROUND_TRUTH / grammar_file).read_text(encoding="utf-8")
    loaded = load_flavour(gbnf_twin_manifest())
    assert parse_grammar(text, loaded) == parse_grammar(text, GBNF_FLAVOUR)


def test_gbnf_twin_emit_parity() -> None:
    """Emitted text parity with the authored flavour on canonical IR (step 6)."""
    text = (GROUND_TRUTH / "arithmetic.gbnf").read_text(encoding="utf-8")
    canonical = parse_grammar(text, GBNF_FLAVOUR)
    loaded = load_flavour(gbnf_twin_manifest())
    assert loaded.apply(canonical) == GBNF_FLAVOUR.apply(canonical)


@pytest.mark.usefixtures("registry_snapshot")
def test_gbnf_twin_drives_the_compile_pipeline() -> None:
    """§10 step 7 under the manifest's own twin name (Fable preflight #6):
    load → register → compile a grammar → parse → exact ``to_text`` round-trip."""
    loaded = load_flavour(gbnf_twin_manifest())
    register_flavour(loaded)
    text = (GROUND_TRUTH / "json.gbnf").read_text(encoding="utf-8")
    cg = compile_pkg.compile_text(text, flavour="gbnf2")
    sample = '{"a": [1, true, "x"]}'
    assert cg.parse(sample).to_text() == sample


# ── idempotence (§12) ────────────────────────────────────────────────────


def test_loads_are_independent() -> None:
    """Two loads of one text are distinct flavours with no shared mutable state."""
    text = gbnf_twin_manifest()
    first, second = load_flavour(text), load_flavour(text)
    assert first is not second
    assert type(first) is not type(second)  # distinct synthesized classes
    # The codec is an immutable EscapeCodec record (no shared mutable state to
    # worry about); two loads yield equal-by-value records.
    assert first.escapes == second.escapes
    # §10 steps 2–6 hold between the two loads.
    assert repr(first.grammar) == repr(second.grammar)
    assert first.grammar.non_semantic == second.grammar.non_semantic
    assert repr(reducer(first).actions) == repr(reducer(second).actions)
    assert repr(first.actions) == repr(second.actions)
    assert first.escapes.encode("\n\t") == second.escapes.encode("\n\t")


# ── path wrapper ─────────────────────────────────────────────────────────


def test_load_flavour_from_path(tmp_path) -> None:
    """The path wrapper reads a UTF-8 manifest file and delegates to load_flavour."""
    manifest = tmp_path / "mini.flavour.ir"
    manifest.write_text(mini_manifest(), encoding="utf-8")
    flavour = load_flavour_from_path(manifest)
    assert flavour.name == "mini"
    assert isinstance(flavour, IrFlavour)


def _manifest_with_noise(noise: IrMap) -> str:
    """The minimal manifest, with only its reduction's noise policy varied."""
    carried = Reducer(
        actions=IrMap(IrTuple(IR_DEFAULT, YIELD)),
        default=YIELD,
        noise=noise,
        literal=DROP,
    )
    return repr(
        IrMap(
            *(
                IrTuple(d[0], carried) if str(d[0]) == "reduction" else d
                for d in mini_dyads()
            )
        )
    )


def test_one_grammar_supports_several_readings() -> None:
    """The reason the reduction is carried rather than derived.

    Deriving the noise map from the grammar's own ``semantic=False`` flags made
    one reading of a grammar the ONLY reading it could have. A reduction is a
    reading, not a property of the grammar, so two manifests differing in
    nothing but their policy fold the same text two ways.
    """
    drops = IrMap(IrTuple(IrRuleRef("ws"), DROP), IrTuple(IR_DEFAULT, KEEP_REDUCED))
    keeps = IrMap(IrTuple(IR_DEFAULT, KEEP_REDUCED))
    dropped = load_flavour(_manifest_with_noise(drops))
    kept = load_flavour(_manifest_with_noise(keeps))
    artifact = compile_ast(dropped.grammar)
    assert artifact.reduce("a ", reducer(dropped)) == IrStr("a")
    assert artifact.reduce("a ", reducer(kept)) == IrStr("a ")
