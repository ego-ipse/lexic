"""The complete artefact family of a reading, each loaded back and witnessed.

Licences are cheap names.  Witnesses are the expensive export + runtime-load
work and belong to a relation-owned worker.  Runtime module names end in the
reading's content digest; loading by a shared stem is never allowed.
"""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Lock, Thread
from types import ModuleType

from lexic.compile import CompiledGrammar, bind_module, verify_module
from lexic.compile.module.export import export_module, export_source
from lexic.compile.notation import emit_ir, load_ir
from lexic.compile.payload import export_value
from lexic.exceptions import LexicError
from lexic.model import GrammarModel

__all__ = ["Artefact", "Artefacts", "FORMS", "keep", "licences"]


@dataclass(frozen=True, slots=True)
class Artefact:
    """One written form, its load-back verdict, and its runtime identity."""

    name: str
    chars: int
    witness: str
    words: str
    module: str = ""

    def line(self) -> str:
        return f"{self.name} · {self.chars:,} chars · {self.witness} — {self.words}"


FORMS = (
    "the twin module",
    "the IR notation",
    "the grammar payload",
    "the model payload",
    "the dump payload",
    "the reduced payload",
)
_MISSING = object()
_MODULE_LOCK = Lock()
Builder = Callable[[CompiledGrammar, str, str, int], list[Artefact]]


def licences(_compiled: CompiledGrammar) -> tuple[str, ...]:
    """The cheap forms a compiled grammar can offer before witnessing."""
    return FORMS


def _refused(name: str, refusal: object, chars: int = 0) -> Artefact:
    return Artefact(name, chars, "refused", str(refusal)[:180])


def _load(
    path: Path,
    module_name: str,
    previous: dict[str, ModuleType | None],
) -> ModuleType:
    """Execute exactly this path under a digest-suffixed runtime identity."""
    spec = importlib.util.spec_from_file_location(module_name, path.resolve())
    if spec is None or spec.loader is None:
        raise ImportError(f"could not create a module spec for {path}")
    module = importlib.util.module_from_spec(spec)
    previous.setdefault(module_name, sys.modules.get(module_name))
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        old = previous[module_name]
        if old is None:
            sys.modules.pop(module_name, None)
        else:
            sys.modules[module_name] = old
        raise
    return module


def _sidecars(directory: Path, previous: dict[str, ModuleType | None]) -> None:
    """Load payload readers by their own source digest before payloads."""
    for path in sorted(directory.glob("payload_reader_*.py")):
        if path.stem not in previous:
            _load(path, path.stem, previous)


def _notation(compiled: CompiledGrammar) -> Artefact:
    name = "the IR notation"
    try:
        text = emit_ir(compiled.grammar)
        back = load_ir(text)
    except (LexicError, RecursionError, TypeError, ValueError) as refusal:
        return _refused(name, refusal, len(locals().get("text", "")))
    same = back == compiled.grammar
    return Artefact(
        name,
        len(text),
        "holds" if same else "FAILS",
        "load_ir reads back equal to the canonical grammar"
        if same
        else "load_ir returned a different value",
    )


def _payload(
    name: str,
    value: object,
    path: Path,
    module_name: str,
    previous: dict[str, ModuleType | None],
    holds: Callable[[object], bool],
    words: str,
    *,
    owner: str | None = None,
) -> Artefact:
    try:
        export_value(value, path, module=owner)
        _sidecars(path.parent, previous)
        loaded = _load(path, module_name, previous)
        back = getattr(loaded, "VALUE")
        same = holds(back)
    except Exception as refusal:  # noqa: BLE001 — a refusal is the room's answer
        chars = len(path.read_text()) if path.is_file() else 0
        return _refused(name, refusal, chars)
    return Artefact(
        name,
        len(path.read_text()),
        "holds" if same else "FAILS",
        words if same else "the digest-named load-back differed from its source",
        module_name,
    )


def keep(
    compiled: CompiledGrammar,
    text: str,
    subject: str,
    generation: int = 0,
    reduced: object = _MISSING,
) -> list[Artefact]:
    """Export and load back every form licensed for one reading.

    ``reduced`` is deliberately not inferred.  A reduction is an attachment
    relation, not a property of a grammar; until one is docked its family row
    is an explicit refusal instead of a fabricated value.
    """
    tag = subject[:12]
    twin_name = f"opsis_twin_{tag}"
    model_name = f"opsis_model_{tag}"
    grammar_name = f"opsis_grammar_{tag}"
    dump_name = f"opsis_dump_{tag}"
    reduced_name = f"opsis_reduced_{tag}"
    previous: dict[str, ModuleType | None] = {}
    made: list[Artefact] = []

    with _MODULE_LOCK, TemporaryDirectory(prefix=f"opsis-family-{tag}-") as tmp:
        directory = Path(tmp)
        twin_path = directory / f"{twin_name}.py"
        model: GrammarModel | None = None
        try:
            model = compiled.parse(text)
        except Exception:
            pass

        try:
            source = export_source(compiled, stem=twin_name)
            verify_module(compiled, source)
            export_module(compiled, twin_path, stem=twin_name)
            twin_module = _load(twin_path, twin_name, previous)
            grammar = getattr(twin_module, "GRAMMAR")
            bind_module(grammar, vars(twin_module))
            classes = [
                value
                for value in vars(twin_module).values()
                if isinstance(value, type)
                and issubclass(value, GrammarModel)
                and value is not GrammarModel
            ]
            distinct = model is None or type(model) not in classes
            same = grammar == compiled.grammar and bool(classes) and distinct
            made.append(
                Artefact(
                    "the twin module",
                    len(source),
                    "holds" if same else "FAILS",
                    "verify_module + bind_module hold; structural twin classes "
                    "are distinct from runtime classes"
                    if same
                    else "the runtime load did not preserve the twin contract",
                    twin_name,
                )
            )
        except Exception as refusal:  # noqa: BLE001 — drawn in the room
            made.append(_refused("the twin module", refusal))

        made.append(_notation(compiled))
        made.append(
            _payload(
                "the grammar payload",
                compiled.grammar,
                directory / f"{grammar_name}.py",
                grammar_name,
                previous,
                lambda value: value == compiled.grammar,
                "digest-named import returned IR equal to the canonical grammar",
            )
        )

        if model is None:
            words = "the document did not produce a model for this payload"
            made.append(_refused("the model payload", words))
            made.append(_refused("the dump payload", words))
        else:
            made.append(
                _payload(
                    "the model payload",
                    model,
                    directory / f"{model_name}.py",
                    model_name,
                    previous,
                    lambda value: (
                        isinstance(value, GrammarModel)
                        and value.to_text() == text
                        and type(value) is not type(model)
                    ),
                    "re-emits byte-identical text through distinct twin classes",
                    owner=twin_name,
                )
            )
            dumped = model.dump()
            made.append(
                _payload(
                    "the dump payload",
                    dumped,
                    directory / f"{dump_name}.py",
                    dump_name,
                    previous,
                    lambda value: value == dumped and type(value) is type(dumped),
                    "digest-named import returned the same plain-data dump",
                )
            )

        if reduced is _MISSING:
            made.append(
                Artefact(
                    "the reduced payload",
                    0,
                    "not licensed",
                    "no reducer is docked on this reading",
                )
            )
        else:
            made.append(
                _payload(
                    "the reduced payload",
                    reduced,
                    directory / f"{reduced_name}.py",
                    reduced_name,
                    previous,
                    lambda value: value == reduced,
                    "digest-named import returned the attached reduced value",
                )
            )

        for name, old in reversed(tuple(previous.items())):
            if old is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = old
    return made


class Artefacts:
    """One relation's background family witness, keyed by content generation."""

    __slots__ = ("_builder", "_key", "_result", "done")

    def __init__(self, builder: Builder = keep) -> None:
        self._builder = builder
        self._key: tuple[int, str, int] | None = None
        self._result: tuple[Artefact, ...] = ()
        self.done = False

    @property
    def pending(self) -> bool:
        return self._key is not None and not self.done

    def ask(
        self,
        machine: CompiledGrammar | None,
        text: str,
        subject: str,
        generation: int,
    ) -> None:
        """Start this generation once; never block the room frame."""
        if machine is None:
            return
        key = (id(machine), subject, generation)
        if key == self._key:
            return
        self._key = key
        self._result = ()
        self.done = False
        Thread(
            target=self._run,
            args=(machine, text, subject, generation, key),
            daemon=True,
            name="opsis-artefacts",
        ).start()

    def _run(
        self,
        machine: CompiledGrammar,
        text: str,
        subject: str,
        generation: int,
        key: tuple[int, str, int],
    ) -> None:
        try:
            result = tuple(self._builder(machine, text, subject, generation))
        except Exception as refusal:  # noqa: BLE001 — retain a visible answer
            result = (_refused("the artefact family", refusal),)
        if key != self._key:
            return
        self._result = result
        self.done = True

    def line(self) -> tuple[Artefact, ...] | None:
        """None while pending; the complete retained answer after promotion."""
        return self._result if self.done else None
