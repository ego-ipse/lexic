"""Every identity-keyed module-level dict is registered with the cache registry.

An ``id()``-keyed dict that never passes through
:func:`lexic.parsing.caches.memo` is invisible to :func:`~lexic.parsing.caches.release`
— it pins its key object immortal exactly the way the pre-I10 memos did.
This is a floor, not a type-checker: it flags a module-level ``dict`` whose
declared key type MENTIONS ``int`` (the shape every ``id(...)`` key takes),
then asserts its initializer is a ``memo(...)`` call. It cannot tell an
``int``-typed key that is an object-identity address apart from one that
merely happens to be a small integer — the one miss that needs an explicit,
named, justified exemption rather than a silent pass.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
SRC = ROOT / "src" / "lexic"
SCAN_ROOTS = (SRC / "parsing", SRC / "compile")

REGISTRY_MODULE = SRC / "parsing" / "caches.py"
"""Excluded by file identity: the registry's own bookkeeping (``_ADOPTED``)
is the release mechanism itself, not a candidate memo -- there is nowhere
upstream of it to register it with."""

NOT_IDENTITY_KEYED = frozenset({("parsing/parallel/pool.py", "_IDLE")})
"""Module-level dicts whose key type mentions ``int`` but is not an object
identity (``id(...)``) at all.

``_IDLE`` is keyed by WORKER COUNT -- a small, bounded natural number, not an
address subject to reuse -- and already carries its own seam
(:func:`~lexic.parsing.parallel.pool.reset_pools`, capped by ``RETAINED``).
Nothing here pins an id() alive, so :func:`~lexic.parsing.caches.memo` does
not apply; the exemption is what keeps the guard honest rather than blind.
"""


def _mentions_int(node: ast.expr) -> bool:
    """Whether ``int`` appears anywhere inside a type annotation expression."""
    return any(isinstance(n, ast.Name) and n.id == "int" for n in ast.walk(node))


def _key_type(annotation: ast.expr) -> ast.expr | None:
    """The ``K`` in a ``dict[K, V]`` annotation; ``None`` for a non-dict."""
    if not isinstance(annotation, ast.Subscript):
        return None
    if not (isinstance(annotation.value, ast.Name) and annotation.value.id == "dict"):
        return None
    sl = annotation.slice
    return sl.elts[0] if isinstance(sl, ast.Tuple) else sl


def _is_memo_call(value: ast.expr) -> bool:
    """Whether an assignment's RHS is a bare call to ``memo(...)``."""
    return isinstance(value, ast.Call) and (
        isinstance(value.func, ast.Name) and value.func.id == "memo"
    )


def _int_keyed_module_dicts(path: Path) -> list[tuple[int, str, bool]]:
    """``(lineno, name, registered)`` for every int-keyed top-level dict."""
    out: list[tuple[int, str, bool]] = []
    tree = ast.parse(path.read_text())
    for node in tree.body:
        if not (isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)):
            continue
        key = _key_type(node.annotation)
        if key is None or not _mentions_int(key):
            continue
        registered = node.value is not None and _is_memo_call(node.value)
        out.append((node.lineno, node.target.id, registered))
    return out


def test_every_identity_keyed_module_dict_is_registered_with_memo():
    """No future ``_CACHE: dict[int, ...] = {}`` can silently skip the registry.

    Scans every ``.py`` under ``lexic.parsing`` and ``lexic.compile`` (future
    modules are covered by construction via ``rglob``, not by remembering to
    extend a list) for a module-level dict whose key type mentions ``int``,
    and asserts it was declared via ``memo(...)`` rather than a bare ``{}``.
    """
    offenders: list[str] = []
    for root in SCAN_ROOTS:
        for path in sorted(root.rglob("*.py")):
            if path == REGISTRY_MODULE:
                continue
            rel = path.relative_to(SRC).as_posix()
            for lineno, name, registered in _int_keyed_module_dicts(path):
                if (rel, name) in NOT_IDENTITY_KEYED:
                    continue
                if not registered:
                    offenders.append(f"{rel}:{lineno}: {name}")
    assert not offenders, (
        "int-keyed module dict not registered with lexic.parsing.caches.memo "
        f"(a silently immortal identity cache): {offenders}"
    )


def test_the_registration_guard_catches_a_planted_violation(tmp_path: Path):
    """A guard nobody has seen fail is a guard nobody knows works.

    ``src/`` is clean, so the test above passes whether or not the scan does
    anything. So plant a violation, a registered sibling, an int buried
    inside a tuple key, and a dict whose int lives only in the VALUE type —
    the last one must NOT be flagged.
    """
    sample = tmp_path / "sample.py"
    sample.write_text(
        "from lexic.parsing.caches import memo\n"
        "\n"
        "_GOOD: dict[int, str] = memo({})\n"
        "_BAD: dict[int, str] = {}\n"
        "_TUPLE_KEY_BAD: dict[tuple[int, str], str] = {}\n"
        "_STR_KEYED: dict[str, int] = {}\n"
    )
    found = _int_keyed_module_dicts(sample)
    flagged = {name for _, name, registered in found if not registered}
    assert flagged == {"_BAD", "_TUPLE_KEY_BAD"}
