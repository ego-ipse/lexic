"""Files entering the instrument, probed without silently running code.

Classification is a set of answers, not a winning branch.  Every applicable
pure Lexic reader runs and keeps either its live value or its exact refusal.
Python payload execution is different: probing can only offer it, and an
explicit gesture must cross that boundary.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from collections.abc import Callable, Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from time import monotonic

from lexic.compile import load_ir, parse_module
from lexic.compile.notation import load_flavour
from lexic.ir import IrSelf
from lexic.model import GrammarModel

from praxis.graph import digest
from praxis.reading import probe as probe_grammar

__all__ = [
    "FileProbe",
    "FileSubject",
    "Ingress",
    "IngressEntry",
    "Landing",
    "Payload",
    "import_payload",
    "land",
    "probe_file",
]

GRAMMAR_SUFFIXES = {".abnf", ".ebnf", ".gbnf"}


@dataclass(frozen=True, slots=True)
class FileProbe:
    """One file reader's retained answer."""

    reader: str
    state: str
    value: object | None = None
    words: str = ""

    @property
    def accepted(self) -> bool:
        return self.state == "accepted"

    @property
    def offered(self) -> bool:
        return self.state == "offered"


@dataclass(frozen=True, slots=True)
class FileSubject:
    """One content-addressed file and all applicable reader answers."""

    path: Path
    sid: str
    chars: int
    text: str | None
    probes: tuple[FileProbe, ...]

    @property
    def accepted(self) -> tuple[FileProbe, ...]:
        return tuple(answer for answer in self.probes if answer.accepted)

    @property
    def offered(self) -> tuple[FileProbe, ...]:
        return tuple(answer for answer in self.probes if answer.offered)


@dataclass(frozen=True, slots=True)
class Landing:
    """The files at ingress, or honest empty-landing doors when there are none."""

    subjects: tuple[FileSubject, ...]
    doors: tuple[Path, ...] = ()


@dataclass(frozen=True, slots=True)
class Payload:
    """A deliberately executed module and its Lexic-bearing public exports."""

    module_name: str
    module: ModuleType
    exports: tuple[str, ...]


def _answer(reader: str, work: Callable[[], object]) -> FileProbe:
    """Run one pure reader and retain its exact answer."""
    try:
        value = work()
    except Exception as refusal:  # noqa: BLE001 — the refusal is the result
        return FileProbe(reader, "refused", words=str(refusal))
    return FileProbe(reader, "accepted", value=value)


def _suffix(path: Path) -> str:
    """The significant extension, preserving the two-part flavour suffix."""
    name = path.name.casefold()
    return ".flavour.ir" if name.endswith(".flavour.ir") else path.suffix.casefold()


def probe_file(path: str | Path) -> FileSubject:
    """Ask every applicable pure reader and never import Python.

    The order is the safety boundary: extension narrows applicable readers;
    notation and manifest readers run before the module self-grammar; payload
    import is represented only as an offered explicit action.
    """
    source = Path(path)
    raw = source.read_bytes()
    sid = digest("file", raw.decode("latin-1"))
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as refusal:
        return FileSubject(
            source,
            sid,
            len(raw),
            None,
            (FileProbe("utf-8 text", "refused", words=str(refusal)),),
        )

    suffix = _suffix(source)
    answers: list[FileProbe] = []
    if suffix in (".ir", ".flavour.ir"):
        answers.append(_answer("IR notation", lambda: load_ir(text)))
    if suffix == ".flavour.ir":
        answers.append(_answer("flavour manifest", lambda: load_flavour(text)))
    if suffix == ".py":
        answers.append(_answer("module self-grammar", lambda: parse_module(text)))
        answers.append(
            FileProbe(
                "Python payload",
                "offered",
                words="identifying a payload module means running it",
            )
        )

    if suffix in GRAMMAR_SUFFIXES:
        for answer in probe_grammar(text):
            answers.append(
                FileProbe(
                    f"{answer.flavour.upper()} grammar",
                    "accepted" if answer.accepted else "refused",
                    value=answer.machine,
                    words=answer.words,
                )
            )
    return FileSubject(source, sid, len(text), text, tuple(answers))


def land(paths: Sequence[str | Path], doors: tuple[Path, ...] = ()) -> Landing:
    """Probe every named file, or expose supplied doors on an empty landing."""
    if not paths:
        return Landing((), doors)
    return Landing(tuple(probe_file(path) for path in paths))


def _exports(module: ModuleType) -> tuple[str, ...]:
    """Public values with Lexic provenance; plain Python is not a payload."""
    found: list[str] = []
    for name, value in vars(module).items():
        if name.startswith("_"):
            continue
        if isinstance(value, IrSelf):
            found.append(name)
            continue
        if (
            isinstance(value, type)
            and issubclass(value, GrammarModel)
            and getattr(value, "__grammar__", None) is not None
        ):
            found.append(name)
    return tuple(sorted(found))


def import_payload(subject: FileSubject) -> FileProbe:
    """Execute one explicitly chosen Python subject under a digest name.

    The caller is the explicit gesture.  Failure remains a probe answer and a
    module without an IR value or bound model class is refused after execution
    rather than being promoted as an untyped subject.
    """
    if _suffix(subject.path) != ".py":
        return FileProbe(
            "Python payload",
            "refused",
            words=f"payload import requires a .py file, got {subject.path.name!r}",
        )
    stem = re.sub(r"\W+", "_", subject.path.stem).strip("_") or "module"
    module_name = f"opsis_payload_{stem}_{subject.sid[:12]}"
    spec = importlib.util.spec_from_file_location(module_name, subject.path.resolve())
    if spec is None or spec.loader is None:
        return FileProbe(
            "Python payload",
            "refused",
            words=f"payload import could not load {subject.path}",
        )
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception as refusal:  # noqa: BLE001 — the refusal is the result
        sys.modules.pop(module_name, None)
        return FileProbe("Python payload", "refused", words=str(refusal))

    exports = _exports(module)
    if not exports:
        sys.modules.pop(module_name, None)
        return FileProbe(
            "Python payload",
            "refused",
            words="payload module exports no IR value or bound model class",
        )
    return FileProbe(
        "Python payload",
        "accepted",
        value=Payload(module_name, module, exports),
    )

@dataclass(slots=True)
class IngressEntry:
    """One path while its pure readers run, and after they have answered."""

    path: Path
    future: Future[tuple[FileSubject, float]]
    started: float
    subject: FileSubject | None = None
    seconds: float = 0.0
    words: str = ""
    payload_future: Future[FileProbe] | None = None
    payload: FileProbe | None = None

    @property
    def pending(self) -> bool:
        return self.subject is None and not self.words

    @property
    def payload_pending(self) -> bool:
        return self.payload_future is not None and self.payload is None


class Ingress:
    """Worker-owned file ingress whose pending state is visible and pollable."""

    __slots__ = ("_executor", "doors", "entries")

    def __init__(
        self,
        paths: Sequence[str | Path],
        doors: tuple[Path, ...] = (),
        reader: Callable[[str | Path], FileSubject] = probe_file,
    ) -> None:
        self.doors = doors
        self._executor = ThreadPoolExecutor(
            max_workers=max(1, min(4, len(paths) or 1)),
            thread_name_prefix="opsis-ingress",
        )
        self.entries = []
        for named in paths:
            path = Path(named)
            started = monotonic()
            future = self._executor.submit(_timed_probe, reader, path)
            self.entries.append(IngressEntry(path, future, started))

    def poll(self) -> bool:
        """Promote completed work; return whether the visible map changed."""
        changed = False
        for entry in self.entries:
            if entry.subject is None and not entry.words and entry.future.done():
                try:
                    entry.subject, entry.seconds = entry.future.result()
                except Exception as refusal:  # noqa: BLE001 — drawn as refusal
                    entry.words = str(refusal)
                    entry.seconds = monotonic() - entry.started
                changed = True
            if entry.payload_future is not None and entry.payload is None:
                if entry.payload_future.done():
                    try:
                        entry.payload = entry.payload_future.result()
                    except Exception as refusal:  # noqa: BLE001 — drawn as refusal
                        entry.payload = FileProbe(
                            "Python payload", "refused", words=str(refusal)
                        )
                    changed = True
        return changed

    def import_at(self, at: int) -> bool:
        """Start the explicit payload boundary once; never on classification."""
        if at < 0 or at >= len(self.entries):
            return False
        entry = self.entries[at]
        if entry.subject is None or entry.payload_future is not None:
            return False
        if not any(answer.offered for answer in entry.subject.probes):
            return False
        entry.payload_future = self._executor.submit(import_payload, entry.subject)
        return True

    def close(self) -> None:
        """Release workers without waiting for deliberately slow ingress."""
        self._executor.shutdown(wait=False, cancel_futures=True)


def _timed_probe(
    reader: Callable[[str | Path], FileSubject], path: Path
) -> tuple[FileSubject, float]:
    """One worker result with the cost the map must disclose."""
    started = monotonic()
    return reader(path), monotonic() - started
