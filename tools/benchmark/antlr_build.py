"""Run the ANTLR tool over an emitted grammar, once, outside the timed region.

ANTLR is the only competitor that does not accept a grammar at runtime: a Java
tool generates source, which is then compiled or imported. That build is part of
using ANTLR — as `Lark(...)` construction is part of using Lark — so it happens
once per grammar and never inside a timed round.

Generated code lands in a temporary directory that lives as long as the process,
because the import machinery needs the files to stay put.
"""

from __future__ import annotations

import importlib
import subprocess
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

from antlr4 import CommonTokenStream, InputStream

from lexic.ir import IrAst
from tools.benchmark.directives import NO_MARKS, Marks
from tools.benchmark.emit import antlr_grammar

BUILD_ROOT = Path(tempfile.mkdtemp(prefix="lexic-antlr-"))
"""Where generated parsers live. Kept for the process, not per call."""

TOOL_VERSION = "4.13.2"
"""The ANTLR tool version, PINNED.

`antlr4-tools` resolves "latest" by listing an already-populated Maven repo, so
on a machine that has never run ANTLR it fails on `~/.m2` rather than
downloading anything. Naming a version makes the first run fetch the jar — and
pins what the benchmark measured, which a floating "latest" would not.
"""


class _Strict:
    """Turn ANTLR's recover-and-continue default into a refusal.

    ANTLR reports a syntax error and then carries on with a repaired parse, so a
    parser left on its defaults ACCEPTS almost anything — it would pass the
    accept half of the differential while describing a different language. A
    benchmark row for a parser that never refuses is meaningless.

    Not a subclass of `ErrorListener`: `addErrorListener` only appends to a list
    and the proxy calls its hooks positionally, so the base contributes nothing
    but six-parameter signatures this needs three values out of.

    The hook NAMES are ANTLR's to choose, so the real methods are spelled the
    way this codebase spells methods and the camelCase names are bound to them
    as the attributes ANTLR looks up.
    """

    def refuse_syntax(self, *report):
        """ANTLR's hook: `(recognizer, symbol, line, column, message, error)`."""
        raise SyntaxError(f"{report[2]}:{report[3]} {report[4]}")

    def refuse_ambiguity(self, *report):
        """ANTLR reporting that a span derives more than one way.

        Refused rather than reported, for the same reason lexic refuses it: a
        row timing a parser that silently picked between meanings is not timing
        the grammar it was given.
        """
        raise SyntaxError(f"ambiguous span: {report[2]}..{report[3]}")

    def note_prediction(self, *report):
        """ANTLR escalating SLL prediction to full context, or resolving it.

        Both are prediction-strategy notes, not verdicts about the input: the
        parse continues and lands on one alternative. Ignored deliberately —
        but the hooks must EXIST, because the proxy calls every listener
        method it has and a missing one crashes the run rather than the parse.
        A grammar whose decisions escalate is exactly the interesting case, so
        the harness must survive it to report a number.
        """

    syntaxError = refuse_syntax
    reportAmbiguity = refuse_ambiguity
    reportAttemptingFullContext = note_prediction
    reportContextSensitivity = note_prediction


def generate(ast: IrAst, name: str, language: str, marks: Marks = NO_MARKS) -> Path:
    """Run the ANTLR tool over ``ast`` for one target language.

    :param ast: The one canonical grammar, as for every other competitor.
    :param name: An identifier grammar name; also the generated file prefix.
    :param language: An ANTLR target — `Python3` or `Java`.
    :returns: The directory the generated sources landed in.
    :raises RuntimeError: When the ANTLR tool itself refuses the grammar — a
        capability result, reported rather than worked around.
    """
    target = BUILD_ROOT / language / name
    target.mkdir(parents=True, exist_ok=True)
    source = target / f"{name}.g4"
    source.write_text(antlr_grammar(ast, name, marks), encoding="utf-8")
    done = subprocess.run(
        [
            "antlr4",
            "-v",
            TOOL_VERSION,
            f"-Dlanguage={language}",
            "-o",
            str(target),
            str(source),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    # ANTLR exits non-zero for WARNINGS too, and a warning is not a refusal —
    # treating it as one would report a capability limit that does not exist.
    errors = [line for line in done.stderr.splitlines() if line.startswith("error(")]
    if errors:
        raise RuntimeError(errors[0])
    suffix = "py" if language == "Python3" else language.lower()
    if not (target / f"{name}Parser.{suffix}").exists():
        tail = done.stderr.strip().splitlines()
        raise RuntimeError(tail[-1] if tail else "no parser generated")
    return target


def antlr_parser(
    ast: IrAst, name: str, marks: Marks = NO_MARKS
) -> Callable[[str], object]:
    """Generate, import and return a ``parse(text)`` on the PYTHON runtime.

    The lexer and parser objects are built once and re-fed per call. A freshly
    generated Python parser rebuilds its whole `decisionsToDFA` array in
    `__init__`, so constructing one per parse throws away the ATN simulator's
    cache every time and times a cold prediction — an artefact of how we drove
    the tool, not a property of ANTLR. The Java target has no equivalent: there
    the DFA array is static and shared across instances.

    :param ast: The one canonical grammar, as for every other competitor.
    :param name: A Python-identifier grammar name; also the module prefix.
    :returns: A callable parsing a whole input, raising on any syntax error.
    :raises RuntimeError: When the ANTLR tool refuses the grammar.
    """
    target = generate(ast, name, "Python3", marks)
    if str(target) not in sys.path:
        sys.path.insert(0, str(target))
    lexer = getattr(importlib.import_module(f"{name}Lexer"), f"{name}Lexer")
    parser = getattr(importlib.import_module(f"{name}Parser"), f"{name}Parser")
    lex = lexer(InputStream(""))
    stream = CommonTokenStream(lex)
    run = parser(stream)
    for recognizer in (lex, run):
        recognizer.removeErrorListeners()
        recognizer.addErrorListener(_Strict())

    def parse(text: str) -> object:
        """Parse ``text`` whole, refusing on the first syntax error."""
        lex.inputStream = InputStream(text)
        lex.reset()
        stream.setTokenSource(lex)
        run.setTokenStream(stream)
        return run.entry_()

    return parse
