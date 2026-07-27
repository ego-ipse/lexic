"""``export_value`` — the artefact, imported the way a reader imports it.

Every test here runs the written module in a CHILD interpreter. In this process
lexic is resident and the value is already built, so nothing about an artefact
can be established from here — which is the whole point of writing one.
"""

from __future__ import annotations

import subprocess
import sys

import pytest

from lexic.compile.payload import export_value, project, render
from lexic.exceptions import UnsupportedConstructError
from lexic.ir.base import IrInt, IrStr, IrTuple
from tests.paths import PROJECT_ROOT

SRC = str(PROJECT_ROOT / "src")


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
    source = render(project(IrTuple(IrStr("a"))))
    assert "ORIGINS = " in source
    assert "lexic.ir.base" in source


def test_the_inlined_reader_carries_no_future_import() -> None:
    """It would be illegal mid-file, and the artefact supplies its own."""
    source = render(project((1, 2)))
    assert source.count("from __future__ import annotations") == 1
    assert source.index("from __future__") < source.index("def decode(")


# ── what the adversarial pass found ───────────────────────────────────────


def test_a_callers_class_named_like_a_spine_one_is_not_routed_to_the_spine() -> None:
    """Route by ORIGIN, never by name.

    A caller may call a class ``IrLiteral``. Sending it to ``lexic.ir`` because
    the NAME matches hands the reader a different class, decoded with no error
    at all — which is why the origin is recorded in the first place.
    """
    mine = type("IrLiteral", (str,), {"__module__": "vocab"})
    source = render(project((mine("x"),)), module="vocab")
    assert "from vocab import IrLiteral as _sym_IrLiteral" in source
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
