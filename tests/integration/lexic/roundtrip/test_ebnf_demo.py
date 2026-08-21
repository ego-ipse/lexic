"""EBNF cross-flavour parity + the generated-manifest regression guard.

``lexic.grammars.ebnf`` ships the full ISO-family EBNF flavour as a Python
module (``EBNF_FLAVOUR`` — see ``grammars/ebnf.py`` and its unit mirror
``tests/unit/lexic/grammars/test_ebnf.py`` for the flavour's own parse/emit
surface). ``grammars/resources/ebnf.flavour.ir`` is generated from that
singleton (``tools/gen_manifests.py``) — a loadable-from-pure-text artefact
that must stay behaviourally equivalent to the module it was generated from;
this module's one manifest test guards exactly that (there is no longer a
demo flavour with "no shipped Python module" — the manifest is a derived
artefact, not the source of truth).

The remaining tests exercise the shipped flavour directly: both
``arithmetic.ebnf`` and ``json.ebnf`` parse to the SAME canonical IR as
their GBNF ground-truth siblings, proving canonicalisation collapses two
genuinely distinct concrete syntaxes to one flavour-agnostic tree (exit
criterion 4), and the flavour round-trips its own emission.
"""

from __future__ import annotations

from lexic.compile import parse_grammar
from lexic.compile.notation.loader import load_flavour_from_path
from lexic.grammars import GBNF_FLAVOUR
from lexic.grammars.ebnf import EBNF_FLAVOUR
from lexic.ir import IrAst, IrFlavour, canonicalize
from tests.paths import GRAMMARS, GROUND_TRUTH


def manifest_ebnf() -> IrFlavour:
    """The GENERATED EBNF manifest, freshly loaded from disk."""
    return load_flavour_from_path(GRAMMARS / "resources" / "ebnf.flavour.ir")


def gbnf_canonical(stem: str) -> IrAst:
    """The canonicalized GBNF ground-truth grammar named ``stem``."""
    text = (GROUND_TRUTH / f"{stem}.gbnf").read_text(encoding="utf-8")
    return canonicalize(parse_grammar(text, GBNF_FLAVOUR))


def ebnf_canonical(stem: str) -> IrAst:
    """The canonicalized EBNF ground-truth grammar named ``stem``, parsed
    via the shipped :data:`EBNF_FLAVOUR` singleton."""
    text = (GROUND_TRUTH / f"{stem}.ebnf").read_text(encoding="utf-8")
    return canonicalize(parse_grammar(text, EBNF_FLAVOUR))


def test_ebnf_manifest_loads_and_matches_the_shipped_flavour() -> None:
    """The generated manifest still loads to a flavour with the same
    identity metadata as the shipped ``EBNF_FLAVOUR`` singleton it was
    generated from — the checked-in manifest hasn't drifted from its source."""
    manifest_flavour = manifest_ebnf()
    assert isinstance(manifest_flavour, IrFlavour)
    assert manifest_flavour.name == EBNF_FLAVOUR.name
    assert manifest_flavour.extensions == EBNF_FLAVOUR.extensions


def test_ebnf_manifest_grammar_matches_the_shipped_grammar() -> None:
    """The manifest's self-grammar section is byte-for-byte the shipped
    singleton's ``EBNF_GRAMMAR`` — the repr-generation licence held."""
    assert manifest_ebnf().grammar == EBNF_FLAVOUR.grammar


def test_ebnf_arithmetic_canonical_equals_gbnf() -> None:
    """Exit criterion 4: arithmetic.ebnf -> the SAME canonical IR as arithmetic.gbnf."""
    assert ebnf_canonical("arithmetic") == gbnf_canonical("arithmetic")


def test_ebnf_arithmetic_canonical_repr_equals_gbnf() -> None:
    """The repr (canonical codegen form) matches too — no hidden semantic drift."""
    assert repr(ebnf_canonical("arithmetic")) == repr(gbnf_canonical("arithmetic"))


def test_ebnf_json_canonical_equals_gbnf() -> None:
    """json.ebnf -> the SAME canonical IR as json.gbnf — parity holds on a
    second, larger ground-truth grammar too."""
    assert ebnf_canonical("json") == gbnf_canonical("json")


def test_ebnf_json_canonical_repr_equals_gbnf() -> None:
    """The repr matches for json too — no hidden semantic drift on the
    larger grammar either."""
    assert repr(ebnf_canonical("json")) == repr(gbnf_canonical("json"))


def test_ebnf_emit_round_trips() -> None:
    """The shipped flavour emits its own canonical IR back to text that
    reparses equal."""
    canonical = gbnf_canonical("arithmetic")
    emitted = EBNF_FLAVOUR.apply(canonical)
    reparsed = canonicalize(parse_grammar(emitted, EBNF_FLAVOUR))
    assert reparsed == canonical
