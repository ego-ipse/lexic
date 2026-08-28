"""Type the reducer-bearing and reducer-free forms of one ``reduce`` seam."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import NamedTuple, assert_type, overload

from lexic.exceptions import UnsupportedConstructError
from lexic.grammars.json import JSON_REDUCER
from lexic.ir import IrSelf, IrStr
from lexic.ir.reduction import Reducer
from lexic.model import GrammarModel
from lexic.parsing import Resolver

AUTO = 0

type RawSpec = Mapping[str, "IrSelf | RawSpec"]


class CertifiedExtent(NamedTuple):
    """One parser-certified half-open source extent."""

    start: int
    end: int


class RawSelection[Item](NamedTuple):
    """Declaration-ordered raw paths with one exact selected item type."""

    rows: tuple[tuple[tuple[str, ...], Item], ...]


class ReductionMorphism[Result](NamedTuple):
    """Immutable signature-bearing declaration data; ``Result`` is exact."""

    signature: tuple[str, ...]
    operations: tuple[int, ...]


class GrammarMorphism[Result](NamedTuple):
    """Immutable grammar-demand declaration data; ``Result`` is exact."""

    entry: str
    paths: tuple[str, ...]
    capture: int


class _BoundProduct[Result](NamedTuple):
    """Private artefact-owned executor bound before either engine starts."""

    run: Callable[[str], Result]


class ModelCapture:
    """Raw selection retains round-trippable generated models."""


class ExtentCapture:
    """Raw selection retains certified source extents and no models."""


MODEL = ModelCapture()
EXTENT = ExtentCapture()


@overload
def select_raw(
    entry: str,
    spec: RawSpec,
) -> GrammarMorphism[RawSelection[GrammarModel]]: ...


@overload
def select_raw(
    entry: str,
    spec: RawSpec,
    *,
    capture: ModelCapture,
) -> GrammarMorphism[RawSelection[GrammarModel]]: ...


@overload
def select_raw(
    entry: str,
    spec: RawSpec,
    *,
    capture: ExtentCapture,
) -> GrammarMorphism[RawSelection[CertifiedExtent]]: ...


def select_raw(
    entry: str,
    spec: RawSpec,
    *,
    capture: ModelCapture | ExtentCapture = MODEL,
) -> (
    GrammarMorphism[RawSelection[GrammarModel]]
    | GrammarMorphism[RawSelection[CertifiedExtent]]
):
    """Declare one raw-key selection with an exact capture codomain."""
    if not entry or not spec:
        raise UnsupportedConstructError(
            "surface prototype: raw selection needs an entry and demand"
        )
    kind = 1 if isinstance(capture, ExtentCapture) else 0
    return GrammarMorphism(entry, tuple(spec), kind)


def _python_tree() -> ReductionMorphism[dict[str, int]]:
    """Declare a signature-bearing Python target with no executor attached."""
    return ReductionMorphism(("json-value",), (1, 2, 3))


def _bind_python(
    target: ReductionMorphism[dict[str, int]],
    reducer: Reducer,
) -> _BoundProduct[dict[str, int]]:
    """Bind declaration data to one private runner."""
    if not target.signature or not isinstance(reducer, Reducer):
        raise UnsupportedConstructError("surface prototype: invalid reduction")
    return _BoundProduct(lambda text: {"length": len(text)})


def _bind_extents(
    target: GrammarMorphism[RawSelection[CertifiedExtent]],
) -> _BoundProduct[RawSelection[CertifiedExtent]]:
    """Bind one extent declaration to a private exact-result runner."""
    if target.capture != 1:
        raise UnsupportedConstructError("surface prototype: extent capture lost")
    path = tuple(target.paths)
    return _BoundProduct(
        lambda text: RawSelection(((path, CertifiedExtent(0, len(text))),))
    )


class Compiled:
    """The three exact overloads required by the two source contracts."""

    @overload
    def reduce(
        self,
        text: str,
        reducer: Reducer,
        *,
        resolve: Resolver | None = None,
        cores: int = AUTO,
    ) -> IrSelf: ...

    @overload
    def reduce[Result](
        self,
        text: str,
        reducer: Reducer,
        *,
        into: ReductionMorphism[Result],
        resolve: Resolver | None = None,
        cores: int = AUTO,
    ) -> Result: ...

    @overload
    def reduce[Result](
        self,
        text: str,
        *,
        into: GrammarMorphism[Result],
        resolve: Resolver | None = None,
        cores: int = AUTO,
    ) -> Result: ...

    def reduce[Result](
        self,
        text: str,
        reducer: Reducer | None = None,
        *,
        into: ReductionMorphism[Result] | GrammarMorphism[Result] | None = None,
        resolve: Resolver | None = None,
        cores: int = AUTO,
    ) -> IrSelf | Result:
        """Pin only the public overloads; private binding owns execution."""
        del text, reducer, into, resolve, cores
        raise UnsupportedConstructError(
            "surface prototype: execution belongs to a bound product"
        )


def _model_typing(compiled: Compiled) -> None:
    """Pin the model-retaining grammar-morphism result without executing it."""
    models = compiled.reduce("{}", into=select_raw("member", {'"x"': IrStr("keep")}))
    assert_type(models, RawSelection[GrammarModel])


def _typing_witness() -> None:
    """Pin exact result inference without executing the public stub."""
    compiled = Compiled()
    default = compiled.reduce("{}", JSON_REDUCER)
    assert_type(default, IrSelf)
    python = compiled.reduce("{}", JSON_REDUCER, into=_python_tree())
    assert_type(python, dict[str, int])
    extents = compiled.reduce(
        "{}",
        into=select_raw("member", {'"x"': IrStr("keep")}, capture=EXTENT),
    )
    assert_type(extents, RawSelection[CertifiedExtent])


def _binding_witness() -> None:
    """Execute private bound runners while public morphisms remain inert data."""
    python = _bind_python(_python_tree(), JSON_REDUCER)
    if python.run("{}")["length"] != 2:
        raise AssertionError("surface prototype changed the bound Python result")
    declared = select_raw(
        "member",
        {'"x"': IrStr("keep")},
        capture=EXTENT,
    )
    extents = _bind_extents(declared).run("{}")
    if extents.rows[0][1] != CertifiedExtent(0, 2):
        raise AssertionError("surface prototype changed the extent result")


if __name__ == "__main__":
    _binding_witness()
    print("surface\tthree exact overloads\tdeclarations inert; bound runners exact")
