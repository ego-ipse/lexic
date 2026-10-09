"""No module reaches into another module's private names.

A name two modules share is the defining module's public surface: it drops its
underscore there and joins ``__all__``, or it moves to the module that owns the
behaviour. It is never imported across the boundary, read off another module
as an attribute, or reached through a string — ``getattr``, ``setattr``,
``delattr``, ``hasattr`` or a ``monkeypatch`` on a module, a key of its
``vars()`` or ``__dict__``, or a dotted target naming one. Checked over every
``.py`` file of the repository's own packages; ``__dunder__`` names are not
private.

The rule is about a MODULE's private names. A class's or an object's private
attributes are not in it: a test may reach into them to see what a method did
(``monkeypatch.setattr(PdaKernel, "_drive", ...)``, ``vars(Verdicts)[...]``),
and that does not make them public. Outside tests such a reach says a public
interface may be missing, which is a design question rather than a renaming.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OWN = ("lexic", "tests", "tools", "ext")
"""The top-level packages whose names this rule governs, and the trees it scans
(``lexic`` under ``src/``)."""

REACHES = frozenset({"getattr", "setattr", "delattr", "hasattr"})
"""Calls that reach an attribute named by a string: as builtins, and as the
``setattr``/``delattr`` of a ``monkeypatch``."""

DOTTED = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+")
"""A string that is nothing but a dotted name — a patch target's spelling."""


def module_name(path: Path) -> str:
    """The dotted module a file defines (``src/lexic/a/b.py`` → ``lexic.a.b``;
    a package's ``__init__.py`` is the package)."""
    rel = path.relative_to(ROOT / "src" if path.is_relative_to(ROOT / "src") else ROOT)
    parts = rel.with_suffix("").parts
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


def is_module(name: str) -> bool:
    """Whether ``name`` is one of the repository's own modules or packages."""
    if name.split(".")[0] not in OWN:
        return False
    base = (ROOT / "src" if name.startswith("lexic") else ROOT).joinpath(
        *name.split(".")
    )
    return base.with_suffix(".py").is_file() or (base / "__init__.py").is_file()


def private(name: str) -> bool:
    """A single-underscore name; dunders are not private."""
    return name.startswith("_") and not (name.startswith("__") and name.endswith("__"))


def module_aliases(tree: ast.AST) -> dict[str, str]:
    """Each local name bound to one of the repository's modules, and the module."""
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                local = alias.asname or alias.name.split(".")[0]
                aliases[local] = alias.name if alias.asname else local
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            for alias in node.names:
                aliases[alias.asname or alias.name] = f"{node.module}.{alias.name}"
    return {local: mod for local, mod in aliases.items() if is_module(mod)}


def dotted(node: ast.expr, aliases: dict[str, str]) -> str | None:
    """The module an attribute chain names (``a.b`` with ``a`` a module alias),
    or ``None`` when it names no module of the repository."""
    if isinstance(node, ast.Name):
        return aliases.get(node.id)
    if isinstance(node, ast.Attribute):
        head = dotted(node.value, aliases)
        if head is not None and is_module(f"{head}.{node.attr}"):
            return f"{head}.{node.attr}"
    return None


def imported(node: ast.ImportFrom, own: str) -> list[str]:
    """``from <module> import _name`` of another module of the repository."""
    if (
        not node.module
        or node.level
        or node.module == own
        or not is_module(node.module)
    ):
        return []
    return [
        f"from {node.module} import {alias.name}"
        for alias in node.names
        if private(alias.name)
    ]


def reached(node: ast.Call, aliases: dict[str, str], own: str) -> list[str]:
    """``getattr(module, "_name")`` and its kin, on another module."""
    func = node.func
    name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
    if name not in REACHES or len(node.args) < 2:
        return []
    home, key = dotted(node.args[0], aliases), node.args[1]
    if home is None or home == own or not isinstance(key, ast.Constant):
        return []
    return [f"{home}.{key.value}"] if private(str(key.value)) else []


def namespaced(node: ast.Subscript, aliases: dict[str, str], own: str) -> list[str]:
    """``vars(module)["_name"]`` and ``module.__dict__["_name"]``, on another
    module."""
    space, key = node.value, node.slice
    if isinstance(space, ast.Call) and getattr(space.func, "id", None) == "vars":
        space = space.args[0] if len(space.args) == 1 else None
    elif isinstance(space, ast.Attribute) and space.attr == "__dict__":
        space = space.value
    else:
        return []
    home = None if space is None else dotted(space, aliases)
    if home is None or home == own or not isinstance(key, ast.Constant):
        return []
    return [f"{home}.{key.value}"] if private(str(key.value)) else []


def targeted(node: ast.Constant, own: str) -> list[str]:
    """A dotted string target, ``"pkg.module._name"``, naming another module's
    private name."""
    if not isinstance(node.value, str) or not DOTTED.fullmatch(node.value):
        return []
    home, _dot, name = node.value.rpartition(".")
    if home == own or not private(name) or not is_module(home):
        return []
    return [node.value]


def offences(source: str, own: str) -> list[str]:
    """Every reach in ``source``, the text of module ``own``, into another
    module's private names."""
    tree = ast.parse(source)
    aliases = module_aliases(tree)
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            found += imported(node, own)
        elif isinstance(node, ast.Attribute) and private(node.attr):
            home = dotted(node.value, aliases)
            if home is not None and home != own:
                found.append(f"{home}.{node.attr}")
        elif isinstance(node, ast.Call):
            found += reached(node, aliases, own)
        elif isinstance(node, ast.Subscript):
            found += namespaced(node, aliases, own)
        elif isinstance(node, ast.Constant):
            found += targeted(node, own)
    return found


def sources() -> list[Path]:
    """Every ``.py`` file the rule covers."""
    tops = ("src", *(top for top in OWN if top != "lexic"))
    return sorted(
        path
        for top in tops
        for path in (ROOT / top).rglob("*.py")
        if ".venv" not in path.parts
    )


def test_no_module_reaches_another_modules_private_names() -> None:
    """Every name one module takes from another is public there."""
    found = [
        f"{path.relative_to(ROOT)}: {offence}"
        for path in sources()
        for offence in offences(path.read_text(encoding="utf-8"), module_name(path))
    ]
    assert not found, "cross-module private names:\n" + "\n".join(found)


PROBE = """\
import lexic.parsing.products as products
from lexic.parsing import products as also
from lexic.parsing.products import _hidden, earley_model, __all__
products._read
also.earley_model
getattr(products, "_got")
monkeypatch.setattr(also, "_patched", None)
monkeypatch.setattr("lexic.parsing.products._dotted", None)
vars(products)["_keyed"]
also.__dict__["_dicted"]
vars(products)["public"]
setattr(products, "public", None)
"lexic.parsing.products.public"
from tests.integration.lexic.invariants.test_no_private_imports import _mine
"""
"""Every form the rule reads, beside a dunder, public names and an own-module
private, which it does not."""


def test_the_rule_reads_every_form_and_only_those() -> None:
    """Imports, attribute reads, string reaches, namespace keys and dotted
    targets into another module's private names are offences; a dunder, a public name, and a private
    name of the module's own are not."""
    own = "tests.integration.lexic.invariants.test_no_private_imports"
    home = "lexic.parsing.products"  # spelled apart, or this file reaches it
    assert offences(PROBE, own) == [
        f"from {home} import _hidden",
        *(
            f"{home}.{name}"
            for name in ("_read", "_got", "_patched", "_keyed", "_dicted", "_dotted")
        ),
    ]
    assert (
        module_name(ROOT / "src" / "lexic" / "parsing" / "__init__.py")
        == "lexic.parsing"
    )
