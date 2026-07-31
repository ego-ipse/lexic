"""Praxis — session state and lexic invocation.

Holds intent, invokes lexic's public entry points, keeps the rendered
sections. Never transforms IR: a compile is one ``compile_text`` call,
and every section is rendered by :mod:`opsis.graphic` from what lexic
returned. There is no serialization layer anywhere in opsis — sections
are HTML fragments and travel as such.
"""

from __future__ import annotations

from typing import Any

from html import escape

from lexic.compile import compile_text, export_source
from lexic.exceptions import LexicError

from opsis.eidolon import Topology
from opsis.graphic import railroad_html, topology_svg
from opsis.instance import ambiguity_note, instance_html
from opsis.pipeline import pipeline_html
from opsis.trace import engine_html
from opsis.verdict import verdicts_html


class Praxis:
    """One opsis session: the current source, flavour, and rendered state."""

    def __init__(self) -> None:
        self.source: str = ""
        self.flavour: str = "gbnf"
        self.input: str = ""
        self.compiled: Any = None
        self.sections: dict[str, str] = {}

    def compile(self, text: str, flavour: str = "gbnf") -> dict[str, str]:
        """Compile ``text``; return rendered sections, or ``{"error": …}``.

        A failed compile keeps the previous compiled state and sections —
        the shell keeps the last good views under the error banner.
        """
        self.source = text
        self.flavour = flavour
        try:
            cg = compile_text(text, cache_key=("opsis", flavour, hash(text)), flavour=flavour)
        except LexicError as exc:
            return {"error": f"{type(exc).__name__}\n{exc}"}
        except RecursionError:
            return {"error": "RecursionError\ngrammar too deep for the renderer"}
        self.compiled = cg
        ast = cg.grammar
        self.sections = {
            "status": f"ok · {len(list(ast.rules))} rules · {len(text)} chars",
            "topology": topology_svg(Topology(ast)),
            "railroad": railroad_html(ast),
            "verdicts": verdicts_html(cg),
            "pipeline": pipeline_html(text, flavour, cg),
            "module": f'<pre class="pysrc">{escape(export_source(cg))}</pre>',
        }
        if self.input:
            self.sections.update(self.parse(self.input))
        return self.sections

    def parse(self, text: str) -> dict[str, str]:
        """Parse ``text`` with the session grammar; render the instance view.

        :returns: The updated sections (``instance`` + ``status``), or
            ``{"error": …}`` — an ambiguity refusal is diagnosed as such.
        """
        self.input = text
        if self.compiled is None:
            return {"error": "PraxisError\ncompile a grammar first"}
        try:
            model = self.compiled.parse(text)
        except LexicError as exc:
            note = ambiguity_note(self.compiled.grammar, text)
            detail = f"{type(exc).__name__}\n{exc}"
            return {"error": f"{note}\n\n{detail}" if note else detail}
        update = {
            "instance": instance_html(model, text),
            "engine": engine_html(self.compiled, text),
            "status": f"parsed · {len(text)} chars · {type(model).__name__}",
        }
        self.sections.update(update)
        return update
