"""``export_value`` — the artefact, imported the way a reader imports it.

Every test here runs the written module in a CHILD interpreter. In this process
lexic is resident and the value is already built, so nothing about an artefact
can be established from here — which is the whole point of writing one.
"""

from __future__ import annotations

import ast as pyast
import subprocess
import sys
from hashlib import blake2b
from importlib import import_module

import pytest

from lexic.compile import compile_from_path, compile_text, export_module
from lexic.compile.payload import built_under, export_value, project, reader, render
from lexic.exceptions import UnsupportedConstructError
from lexic.grammars import ABNF_FLAVOUR, GBNF_FLAVOUR
from lexic.ir.base import IrInt, IrStr, IrTuple
from lexic.ir.encoding import IrRankedMerge
from tests.paths import GROUND_TRUTH, PROJECT_ROOT

SRC = str(PROJECT_ROOT / "src")
READER = "payload_reader_probe"  # render() takes the emitted sidecar's name


def _run(tmp_path, stem: str, extra: str = "") -> tuple[str, int]:
    """Import the artefact fresh; return its ``repr`` and the lexic module count."""
    code = (
        f"import {stem} as m, sys\n"
        "print(repr(m.VALUE))\n"
        "print(len([x for x in sys.modules if x.startswith('lexic')]))\n" + extra
    )
    got = subprocess.run(
        [sys.executable, "-c", code],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
        env={"PYTHONPATH": SRC},
    )
    lines = got.stdout.strip().splitlines()
    return lines[0], int(lines[1])


def _is_import(node: pyast.stmt) -> bool:
    """An import statement, or the try/except pair that spells one both ways."""
    if isinstance(node, (pyast.Import, pyast.ImportFrom)):
        return True
    return isinstance(node, pyast.Try) and all(
        isinstance(inner, (pyast.Import, pyast.ImportFrom)) for inner in node.body
    )


def test_a_plain_artefact_imports_no_lexic_at_all(tmp_path) -> None:
    """The reader is inlined, so a payload naming no symbol pays for nothing."""
    value = ({"a": [1, 2.5]}, "x", None, b"\xff", {3}, 10**30)
    export_value(value, tmp_path / "plain_v.py")
    got, modules = _run(tmp_path, "plain_v")
    assert got == repr(value)
    assert modules == 0


def test_an_ir_artefact_round_trips_through_its_own_header(tmp_path) -> None:
    """A spine payload imports `lexic.ir` — and nothing more than it needs."""
    value = IrTuple(IrStr("a"), IrInt(2))
    export_value(value, tmp_path / "ir_v.py")
    got, _ = _run(tmp_path, "ir_v")
    assert got == repr(value)


def test_the_pyc_is_written_at_export(tmp_path) -> None:
    """Whoever writes the ``.py`` writes the ``.pyc``.

    ``UNCHECKED_HASH`` makes a stale ``.pyc`` outrank a fresh source silently, so
    leaving it to the first importer is how a reader gets yesterday's value.
    """
    export_value((1, 2), tmp_path / "pv.py")
    assert list((tmp_path / "__pycache__").glob("pv.*.pyc"))


def test_the_pyc_is_the_artefact_so_editing_the_py_does_not_reach_a_reader(
    tmp_path,
) -> None:
    """An edit to the source alone changes nothing that is read.

    ``UNCHECKED_HASH`` is what buys the fast import, and its price is that a
    ``.pyc`` outranks its source unconditionally. That is not a hole the digest
    has to plug — it is why the exporter writes the ``.pyc`` itself rather than
    leaving it to the first importer, so the pair is consistent from the moment
    it exists. The digest defends whatever IS read; the next test is that.
    """
    path = export_value(({"a": 1}, [2, 3], "x"), tmp_path / "edited.py")
    path.write_text(_corrupted(path.read_text(encoding="utf-8")), encoding="utf-8")
    got, _ = _run(tmp_path, "edited")
    assert got == "({'a': 1}, [2, 3], 'x')"


def test_a_hand_edited_artefact_refuses_once_it_is_the_thing_read(tmp_path) -> None:
    """With no stale ``.pyc`` in the way, the digest catches the edit."""
    path = export_value(({"a": 1}, [2, 3], "x"), tmp_path / "raw.py")
    for stale in (tmp_path / "__pycache__").glob("raw.*.pyc"):
        stale.unlink()
    path.write_text(_corrupted(path.read_text(encoding="utf-8")), encoding="utf-8")
    got = subprocess.run(
        [sys.executable, "-c", "import raw"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
        env={"PYTHONPATH": SRC},
    )
    assert got.returncode != 0
    assert "digest mismatch" in got.stderr


def _corrupted(source: str) -> str:
    """The artefact with one node int changed — pass 3's exact corruption."""
    head, _, tail = source.partition("NODES = (")
    first, _, rest = tail.partition(",")
    return f"{head}NODES = ({int(first) + 1},{rest}"


def test_a_symbol_with_no_importable_home_refuses(tmp_path) -> None:
    """A synthesized class reports ``generated.…``, which does not import."""
    made = type("Root", (str,), {"__module__": "generated.g_abc123"})
    with pytest.raises(UnsupportedConstructError, match="module="):
        export_value((made("x"),), tmp_path / "nope.py")


def test_a_symbol_named_like_the_reader_cannot_shadow_it(tmp_path) -> None:
    """X1, closed by construction rather than by a reserved-name list.

    The reader's source shares the artefact's namespace, so a class called
    ``decode`` or ``DECODE`` would otherwise replace the machinery that reads
    the payload. Every symbol is bound under an alias prefix instead, and
    ``SYMBOLS`` maps the payload's name to it — there is no list to keep.
    """
    (tmp_path / "vocab.py").write_text(
        "class decode(str):\n"
        "    'a caller may name a class anything'\n\n"
        "class DECODE(str):\n"
        "    'including this'\n",
        encoding="utf-8",
    )
    # Built here rather than imported: the export side needs only classes whose
    # module is `vocab`, and the CHILD is what has to resolve the name.
    lower = type("decode", (str,), {"__module__": "vocab"})
    upper = type("DECODE", (str,), {"__module__": "vocab"})
    export_value((lower("a"), upper("b")), tmp_path / "shadow.py", module="vocab")
    # Read the CLASSES, not the repr: a `str` subclass reprs as a plain string,
    # which is exactly the blindness that let a downcast ship unnoticed.
    got = subprocess.run(
        [
            sys.executable,
            "-c",
            "import shadow as m; print([type(x).__name__ for x in m.VALUE])",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
        env={"PYTHONPATH": SRC},
    )
    assert got.stdout.strip() == "['decode', 'DECODE']"


def test_nothing_is_written_when_the_gate_refuses(tmp_path) -> None:
    """An artefact that cannot be read back is never written at all."""
    loop: list = [1]
    loop.append(loop)
    with pytest.raises(UnsupportedConstructError, match="cycle"):
        export_value(loop, tmp_path / "cycle.py")
    assert not (tmp_path / "cycle.py").exists()


def test_the_artefact_records_where_each_symbol_came_from() -> None:
    """``ORIGINS`` is data, not a key: a name that repeats stays recoverable."""
    source = render(project(IrTuple(IrStr("a"))), READER)
    assert "ORIGINS = " in source
    assert "lexic.ir.base" in source


def test_the_artefact_has_no_imports_below_its_code() -> None:
    """Imports first, code after — the order a hand-written module would have."""
    source = render(project((1, 2)), READER)
    assert "from __future__ import annotations" not in source
    tree = pyast.parse(source)
    imports = [i for i, node in enumerate(tree.body) if _is_import(node)]
    code = [
        i
        for i, node in enumerate(tree.body)
        if isinstance(node, (pyast.FunctionDef, pyast.Assign))
    ]
    assert imports and code
    assert max(imports) < min(code)


# ── what the adversarial pass found ───────────────────────────────────────


def test_a_callers_class_named_like_a_spine_one_is_not_routed_to_the_spine() -> None:
    """Route by ORIGIN, never by name.

    A caller may call a class ``IrLiteral``. Sending it to ``lexic.ir`` because
    the NAME matches hands the reader a different class, decoded with no error
    at all — which is why the origin is recorded in the first place.
    """
    mine = type("IrLiteral", (str,), {"__module__": "vocab"})
    source = render(project((mine("x"),)), READER, module="vocab")
    assert "from vocab import (\n    IrLiteral as _sym_IrLiteral,\n)" in source
    assert "from lexic.ir import" not in source


def test_a_module_that_is_not_a_dotted_name_refuses(tmp_path) -> None:
    """``module=`` is written verbatim into an import, so it must be importable."""
    mine = type("Root", (str,), {"__module__": "whatever"})
    for bad in ("does.not.matter", "my-package.models", "", "9lives"):
        with pytest.raises(UnsupportedConstructError, match="dotted Python name"):
            export_value((mine("x"),), tmp_path / "bad.py", module=bad)
    assert not (tmp_path / "bad.py").exists()


def test_a_failed_export_leaves_the_previous_artefact_intact(tmp_path) -> None:
    """The `.py` and its `.pyc` are a matched pair, and the `.pyc` wins.

    A failed re-export that left a broken source behind would be imported as the
    OLD value with no error anywhere — the stale-`.pyc` hazard turned into a
    silent wrong answer. So nothing is moved into place until it compiles.
    """
    path = export_value((1, 2, 3), tmp_path / "art.py")
    good = path.read_text(encoding="utf-8")
    mine = type("Root", (str,), {"__module__": "whatever"})
    with pytest.raises(UnsupportedConstructError):
        export_value((mine("x"),), path, module="not.a-name")
    assert path.read_text(encoding="utf-8") == good
    assert not list(tmp_path.glob("*.staged*"))
    got, _ = _run(tmp_path, "art")
    assert got == "(1, 2, 3)"


@pytest.mark.parametrize("bits", [64, 1024, 65536, 524288])
def test_the_digest_survives_an_integer_of_any_width(bits: int) -> None:
    """A two-byte length prefix capped an int at 65 535 bytes.

    The same defect as the ``array('q')`` overflow it replaced, one order of
    magnitude further out — and ``1 << 524288`` is a legal Python int.
    """
    assert project((1 << bits,)).digest()


def test_the_digest_survives_a_lone_surrogate() -> None:
    """A lone surrogate is a legal ``str`` and reaches the tables from text."""
    assert project(("a\ud800b",)).digest()


# ── provenance: which compilation does this payload belong to ─────────────


def test_a_payload_refuses_a_recompiled_grammars_classes() -> None:
    """Regenerate the grammar, keep the payload — and it says so.

    No table check can see this: the tables are intact, the symbol names still
    resolve, and every record decodes. What changed is the SHAPE behind the
    names, which is why the artefact records a digest of the rules its symbols
    carried rather than of the module they came from — a module name does not
    even survive the move from a runtime class to its twin.
    """
    first = compile_text("root ::= item+\nitem ::= [a-z]+\n", cache_key="prov-a")
    second = compile_text("root ::= word+\nword ::= [A-Z]+\n", cache_key="prov-b")
    payload = project(first.parse("ab"))
    seal = (payload.digest(), payload.shape())
    assert reader.decode(payload.tables, dict(first.classes), seal)
    with pytest.raises(ValueError, match="shape mismatch"):
        reader.decode(payload.tables, dict(second.classes), seal)


def test_the_shape_survives_the_move_to_a_twin() -> None:
    """A twin's classes are different objects in a different module — and the
    same rules, which is the whole reason the rule is what is recorded."""
    compiled = compile_from_path(GROUND_TRUTH / "list.gbnf")
    payload = project(compiled.parse("- a\n"))
    twinned = {
        name: type(cls.__name__, (object,), {"__shape__": cls.__shape__})
        for name, cls in compiled.classes.items()
        if hasattr(cls, "__shape__")
    }
    assert reader.shape_of(payload.types, twinned) == payload.shape()


def test_a_payload_naming_no_rule_bearing_symbol_has_no_shape() -> None:
    """`ir` and `plain` payloads name nothing that carries a grammar."""
    assert project((1, "a")).shape() == 0
    assert project(IrTuple(IrStr("a"))).shape() == 0


def test_the_digest_covers_the_origins_table() -> None:
    """``ORIGINS`` is part of the artefact, so an edit to it must be caught."""
    payload = project((1, 2))
    tampered = (payload.types, ("edited",), payload.strs, payload.nodes)
    assert reader.digest(tampered) != payload.digest()


def test_a_module_that_resolves_to_something_else_refuses() -> None:
    """``module="json"`` is the standard library on almost every path.

    A twin written to ``generated/json.py`` is only importable as ``json`` if
    that directory precedes the stdlib, which is a property of the reader's
    environment and not of the artefact. Checked at export because the module
    is right here — and the check is skipped when it does not import yet, since
    exporting the twin and the payload in either order is legitimate.
    """
    mine = type("Array", (str,), {"__module__": "json"})
    with pytest.raises(UnsupportedConstructError, match="does not provide"):
        render(project((mine("x"),)), READER, module="json")


def test_a_module_that_does_not_import_yet_is_allowed() -> None:
    """The other half of a two-step export is not an error."""
    mine = type("Root", (str,), {"__module__": "not_written_yet"})
    assert render(project((mine("x"),)), READER, module="not_written_yet")


def test_a_module_providing_a_different_class_of_the_same_name_refuses() -> None:
    """The name resolving is not the question — whether it is THIS class is."""
    mine = type("decode", (str,), {"__module__": "lexic.compile.payload.reader"})
    with pytest.raises(UnsupportedConstructError, match="not the classes"):
        render(project((mine("x"),)), READER, module="lexic.compile.payload.reader")


def test_a_long_string_is_chunked_rather_than_written_on_one_line(tmp_path) -> None:
    """Wrapping between tuple elements is not enough when ONE element is long."""
    value = {"doc": "中" * 400}
    export_value(value, tmp_path / "long_v.py")
    source = (tmp_path / "long_v.py").read_text(encoding="utf-8")
    assert max(len(line) for line in source.splitlines()) <= 88
    assert _run(tmp_path, "long_v")[0] == repr(value)


def test_every_import_is_at_the_top_of_the_artefact() -> None:
    """The inlined reader's own imports share the artefact's one import block.

    Inlining a body that carries its own imports is how the artefact ended up
    importing halfway down the file — legal Python, and a finding on every
    linter a user of the artefact runs.
    """
    tree = pyast.parse(render(project((IrStr("x"),)), READER))
    imports = [i for i, node in enumerate(tree.body) if _is_import(node)]
    assert imports == list(range(1, 1 + len(imports)))  # right after the docstring


def test_a_twins_classes_are_accepted_though_they_are_not_the_same_objects(
    tmp_path,
) -> None:
    """Same rules, different objects — the ordinary two-step export.

    A value parsed with runtime classes and exported beside its twin names the
    TWIN's classes, which are different objects: identity would refuse the case
    the feature exists for. What the reader needs the symbols to agree on is the
    rules, so that is what is checked.
    """
    compiled = compile_text('root ::= "a" "b"')
    export_module(compiled, tmp_path / "twin_for_test.py")
    sys.path.insert(0, str(tmp_path))
    try:
        twin = import_module("twin_for_test")
        assert twin.Root is not compiled.classes["Root"]
        source = render(project(compiled.parse("ab")), READER, module="twin_for_test")
    finally:
        sys.path.remove(str(tmp_path))
        sys.modules.pop("twin_for_test", None)
    assert "from twin_for_test import (" in source


def test_the_reader_is_emitted_once_per_directory_not_copied_per_artefact(
    tmp_path,
) -> None:
    """The artefact is its data; the machinery that reads it is emitted beside it.

    Inlining the reader put 330 lines of identical code in every artefact — ten
    artefacts meant ten copies and one place to forget when the reader changed.
    """
    export_value({"a": 1}, tmp_path / "one.py")
    export_value({"b": 2}, tmp_path / "two.py")
    sidecars = sorted(tmp_path.glob("payload_reader_*.py"))
    assert len(sidecars) == 1
    for name in ("one.py", "two.py"):
        source = (tmp_path / name).read_text(encoding="utf-8")
        assert f"from {sidecars[0].stem} import decode" in source
        assert len(source.splitlines()) < 40
        assert "def decode" not in source


def test_the_sidecars_name_is_the_digest_of_its_own_source(tmp_path) -> None:
    """A newer reader is a different module, never a changed one.

    Version skew is what inlining bought, and the name buys it back: an artefact
    naming ``payload_reader_<tag>`` cannot bind to a reader with other contents,
    so two lexic versions writing here leave two sidecars, not one that shifted
    under the older artefact.
    """
    export_value({"a": 1}, tmp_path / "one.py")
    sidecar = next(iter(tmp_path.glob("payload_reader_*.py")))
    tag = blake2b(sidecar.read_bytes(), digest_size=6).hexdigest()
    assert sidecar.stem == f"payload_reader_{tag}"


def test_an_artefact_inside_a_package_imports_its_sidecar_relatively(tmp_path) -> None:
    """How the sidecar is spelled is a fact about where the artefact lands."""
    (tmp_path / "__init__.py").write_text("", encoding="utf-8")
    export_value({"a": 1}, tmp_path / "one.py")
    source = (tmp_path / "one.py").read_text(encoding="utf-8")
    assert "from .payload_reader_" in source


def test_a_symbol_rebound_to_another_module_is_refused_at_import(tmp_path) -> None:
    """The whole cycle: export, move the class behind the name, import.

    In-process this is a function call; the property is about what a FRESH
    interpreter reads off the artefact and its ``.pyc``, so it is measured
    there. Note the two ``vocab.py`` bodies differ in LENGTH — CPython
    invalidates on mtime and size, mtime is second-granular, and two same-size
    rewrites in one second leave the stale ``.pyc`` answering.
    """
    (tmp_path / "impl_old.py").write_text("class Thing(str):\n    pass\n", "utf-8")
    (tmp_path / "impl_new_elsewhere.py").write_text(
        "class Thing(str):\n    pass\n", "utf-8"
    )
    (tmp_path / "vocab.py").write_text("from impl_old import Thing\n", "utf-8")
    build = (
        f"import sys; sys.path[:0] = [{SRC!r}, '.']\n"
        "from lexic.compile.payload import export_value\n"
        "from vocab import Thing\n"
        "export_value((Thing('x'),), 'art.py', module='vocab')\n"
    )
    subprocess.run(
        [sys.executable, "-c", build], cwd=tmp_path, capture_output=True, check=True
    )
    assert _run(tmp_path, "art")[0] == "('x',)"

    (tmp_path / "vocab.py").write_text(
        "from impl_new_elsewhere import Thing\n", "utf-8"
    )
    got = subprocess.run(
        [sys.executable, "-c", "import sys; sys.path.insert(0, '.'); import art"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert got.returncode != 0
    assert "another module" in got.stderr


def test_a_sidecar_with_the_right_name_and_wrong_contents_is_overwritten(
    tmp_path,
) -> None:
    """The name is DERIVED from the source, so a file wearing it is not it.

    Skipping the write when the path existed let a pre-placed ``decode`` read
    every artefact in the directory, silently and with no error anywhere.
    """
    export_value({"a": 1}, tmp_path / "first.py")
    sidecar = next(iter(tmp_path.glob("payload_reader_*.py")))
    sidecar.write_text("def decode(*_a, **_k):\n    return 'owned'\n", encoding="utf-8")
    export_value({"a": 2}, tmp_path / "second.py")
    assert "owned" not in sidecar.read_text(encoding="utf-8")
    assert _run(tmp_path, "second")[0] == "{'a': 2}"


def test_an_artefact_reads_both_inside_a_package_and_outside_one(tmp_path) -> None:
    """Where an artefact lands is not settled when it is written.

    A directory can become a package, or stop being one, long after the export,
    so the artefact spells the sidecar import both ways round rather than
    guessing from an ``__init__.py`` that may not be there yet.
    """
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    export_value({"n": 1}, pkg / "art.py")
    assert _run(pkg, "art")[0] == "{'n': 1}"

    (pkg / "__init__.py").write_text("", encoding="utf-8")
    got = subprocess.run(
        [sys.executable, "-c", "import pkg.art as m; print(repr(m.VALUE))"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    )
    assert got.stdout.strip() == "{'n': 1}"


def test_a_class_from_a_non_spine_lexic_module_needs_no_module_argument(
    tmp_path,
) -> None:
    """Only a SYNTHESIZED class is homeless.

    A tokenizer names classes from ``lexic.ir.encoding`` and
    ``lexic.api.pretokens`` — real modules that really export them — and routing
    only ``ir.__all__`` to the spine sent every one of those to a ``module=``
    the caller had no reason to supply.
    """
    value = (IrRankedMerge(),)
    source = render(project(value), READER)
    assert "from lexic.ir.encoding import (" in source
    export_value(value, tmp_path / "enc.py")
    assert _run(tmp_path, "enc")[0] == repr(value)


def test_a_home_is_the_origin_only_when_the_origin_really_exports_it() -> None:
    """Identity, not presence — ``lexic.ir.base`` merely IMPORTS ``Sequence``.

    A grammar with a rule called ``sequence`` once resolved to typing's, so a
    home is accepted only when the module holds THIS class under THIS name.
    """
    impostor = type("Sequence", (str,), {"__module__": "lexic.ir.base"})
    with pytest.raises(UnsupportedConstructError, match="no importable module"):
        render(project((impostor("x"),)), READER)


def test_an_artefact_records_the_reduction_it_was_built_under(tmp_path) -> None:
    """The half of provenance that cannot be checked at decode.

    An ``ir`` or ``plain`` artefact names spine classes or nothing at all, and
    those are identical under every reduction there is — so nothing at read time
    could disagree, and an artefact supplying its own expectation would only be
    checking itself. It is recorded, and the party holding a live reduction asks.
    """
    compiled = compile_from_path(GROUND_TRUTH / "json.gbnf")
    export_value(compiled.grammar, tmp_path / "art.py", reduction=GBNF_FLAVOUR.reducer)
    sys.path.insert(0, str(tmp_path))
    try:
        art = import_module("art")
        assert built_under(art, GBNF_FLAVOUR.reducer)
        assert not built_under(art, ABNF_FLAVOUR.reducer)
    finally:
        sys.path.remove(str(tmp_path))
        sys.modules.pop("art", None)


def test_an_artefact_with_no_recorded_reduction_matches_nothing(tmp_path) -> None:
    """An unknown provenance is not a match.

    Answering "yes" for an artefact that recorded nothing would make the check
    weakest exactly where there is least to go on.
    """
    export_value({"a": 1}, tmp_path / "bare.py")
    sys.path.insert(0, str(tmp_path))
    try:
        bare = import_module("bare")
        assert bare.REDUCTION == 0
        assert not built_under(bare, GBNF_FLAVOUR.reducer)
    finally:
        sys.path.remove(str(tmp_path))
        sys.modules.pop("bare", None)
