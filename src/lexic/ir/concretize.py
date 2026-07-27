"""concretize — resolve an :class:`~lexic.ir.nodes.IrAlphabet`'s spelling to an id.

A text-form token is authored as ``IrAlphabet(enc, IrLiteral("<think>"))`` — the
spelling, not the id, because the vocab is unknown when the grammar is parsed.
:func:`concretize` binds a grammar to an encoding registry and rewrites each
alphabet's inner from its spelling to the ordinal the encoding resolves it to:
``IrAlphabet(enc, IrLiteral("<think>"))`` → ``IrAlphabet(enc, IrCharClass(
IrChr(1000)))``. Id-form alphabets (already ``IrCharClass`` inners) are validated
against the encoding's universe and otherwise passed through; negation composes.

This is the resolution operation of the encoding model. It is registry-driven
(runtime vocab data), so it is a language-level rewrite rather than a
flavour-neutral normal form — a token grammar is tokenizer-specific once
concretized. The per-atom :func:`concretize_atom` is what an engine resolves
lazily at match time; :func:`concretize` is the whole-grammar eager form.
"""

from __future__ import annotations

from lexic.exceptions import UnsupportedConstructError
from lexic.ir.encodings import IrEncoding
from lexic.ir.mapping import IrMap
from lexic.ir.nodes import (
    IrAlphabet,
    IrAlternation,
    IrAst,
    IrCharClass,
    IrLiteral,
    IrRange,
    IrRule,
)
from lexic.ir.operators import IrNot
from lexic.ir.records import IrSeq
from lexic.ir.spine import IrAtom, IrNoneType, IrSelf


def concretize(ast: IrAst, registry: IrMap) -> IrAst:
    """Resolve every :class:`IrAlphabet` in ``ast`` against ``registry``.

    :param ast: The grammar whose token spellings to resolve.
    :param registry: ``IrMap[IrStr, IrEncoding]`` — encodings keyed by name.
    :returns: The grammar with each alphabet's inner resolved to ordinals.
    :raises UnsupportedConstructError: On an unbound encoding, a spelling the
        encoding does not map to one token, or an id outside its universe.
    """
    rules: list[IrRule] = []
    for rule in ast.rules:
        body = _concretize(rule.body, registry)
        assert isinstance(body, IrAlternation)  # a body rewrites to a body
        rules.append(IrRule(rule.name, body, rule.semantic))
    return IrAst(IrSeq(*rules), ast.start)


def _concretize(node: IrSelf, registry: IrMap) -> IrSelf:
    """Rewrite ``node``, resolving any :class:`IrAlphabet`, recursing elsewhere."""
    if isinstance(node, IrAlphabet):
        return concretize_atom(node, registry)
    return node.rebuild([_concretize(child, registry) for child in node.children()])


def concretize_atom(alphabet: IrAlphabet, registry: IrMap) -> IrAlphabet:
    """Resolve one alphabet's inner against its encoding in ``registry``.

    :param alphabet: The alphabet-bound atom to resolve.
    :param registry: The encoding registry.
    :returns: The alphabet with an ordinal-class inner.
    :raises UnsupportedConstructError: On an unbound encoding, an unmappable
        spelling, or an id outside the encoding's universe.
    """
    encoding = registry.get(alphabet.encoding)
    if not isinstance(encoding, IrEncoding):
        raise UnsupportedConstructError(f"no encoding bound for {alphabet.encoding!r}")
    return IrAlphabet(str(alphabet.encoding), _resolve_inner(alphabet.inner, encoding))


def _resolve_inner(inner: IrSelf, encoding: IrEncoding) -> IrAtom:
    """Resolve an alphabet inner (literal / char class / negation) to ordinals."""
    if isinstance(inner, IrNot):
        return IrNot(_resolve_inner(inner[0], encoding))
    if isinstance(inner, IrLiteral):
        ordinal = encoding.resolve(str(inner))
        if isinstance(ordinal, IrNoneType):
            raise UnsupportedConstructError(
                f"{str(inner)!r} is not one token of the bound encoding"
            )
        return IrCharClass(ordinal)
    if isinstance(inner, IrCharClass):
        _check_universe(inner, encoding)
        return inner
    raise UnsupportedConstructError(
        f"cannot resolve {type(inner).__name__} inside an alphabet"
    )


def _check_universe(charclass: IrCharClass, encoding: IrEncoding) -> None:
    """Raise if any id in an id-form class lies outside the encoding's universe.

    ``universe`` is derived, not stored — on a tokenizer it is a max over the
    whole vocab — so it is read ONCE here rather than per member.

    The ceiling is INCLUSIVE: reading it as exclusive refused the ceiling
    value itself, so a grammar naming the highest code point was rejected as
    out of range.
    """
    ceiling = encoding.universe
    for member in charclass:
        top = int(member.hi) if isinstance(member, IrRange) else int(member)
        if top > ceiling:
            raise UnsupportedConstructError(
                f"token id {top} is outside the encoding's universe ({ceiling})"
            )
