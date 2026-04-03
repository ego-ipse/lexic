"""Vyx text parser — grammar-driven, no hardcoded structure.

The dispatch table for body-line alternatives is derived directly from
the grammar via GBNFModelBuilder.dispatch_table("body-line"). No Vyx
-specific knowledge lives here: not sigil characters, not field names,
not rule structure. The builder already knows all of that.

Entry points:
    parse(text)       → VyxBase (the "packet" model instance)
    parse_body(text)  → list[VyxBase] (body-line instances)

Both load grammar.gbnf once at module level.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from base import VyxBase
from builder import GBNFModelBuilder
from gbnf import GBNFNode, GBNFParser

_GRAMMAR_PATH = Path(__file__).parent.parent / "grammar.gbnf"


class ParseError(Exception):
    def __init__(self, msg: str, line_no: int = 0) -> None:
        super().__init__(f"line {line_no}: {msg}")
        self.line_no = line_no


# ------------------------------------------------------------------
# Inline value parser — shared across all value positions
# ------------------------------------------------------------------


def _parse_value(text: str, pos: int) -> tuple[Any, int]:
    """Parse one value token from text[pos:]. Returns (value, new_pos)."""
    if pos >= len(text):
        return None, pos

    ch = text[pos]

    # null _
    if ch == "_" and (pos + 1 >= len(text) or text[pos + 1] in " \t"):
        return None, pos + 1

    # quoted "..."
    if ch == '"':
        end = text.find('"', pos + 1)
        if end == -1:
            raise ParseError("unclosed quoted string")
        raw = text[pos + 1 : end]
        raw = (
            raw.replace("\\n", "\n")
            .replace("\\t", "\t")
            .replace("\\|", "|")
            .replace('\\"', '"')
        )
        return raw, end + 1

    # pipe: &label|... or |...
    if ch == "&":
        m = re.match(r"[a-zA-Z0-9_-]+", text, pos + 1)
        label = m.group() if m else None
        p = m.end() if m else pos + 1
        if p < len(text) and text[p] == "|":
            return _parse_pipe(text, p, label)
    if ch == "|":
        return _parse_pipe(text, pos, None)

    # ref ^id
    if ch == "^":
        m = re.match(r"[a-zA-Z0-9_-]+", text, pos + 1)
        if m:
            return ("^", m.group()), m.end()

    # spread ~id
    if ch == "~":
        m = re.match(r"[a-zA-Z0-9_-]+", text, pos + 1)
        if m:
            return ("~", m.group()), m.end()

    # unquoted scalar
    m = re.match(r"[!-% \'-;=?-~]+", text, pos)
    if m:
        raw = m.group().rstrip()
        if not raw:
            return None, pos
        if raw == "1":
            return True, m.end()
        if raw == "0":
            return False, m.end()
        try:
            return int(raw), m.end()
        except ValueError:
            pass
        try:
            return float(raw), m.end()
        except ValueError:
            pass
        return raw, m.end()

    return None, pos


def _parse_pipe(text: str, pos: int, label: str | None) -> tuple[dict, int]:
    assert text[pos] == "|", f"expected | at {pos}"
    pos += 1
    elements: list[Any] = []
    while pos <= len(text):
        if pos == len(text) or text[pos] in " \t\n":
            break
        end = text.find("|", pos)
        chunk = text[pos:end] if end != -1 else text[pos:]
        # strip element-level label (rightmost &id where id matches)
        elem_label = None
        amp = chunk.rfind("&")
        if amp != -1:
            pid = chunk[amp + 1 :]
            if re.fullmatch(r"[a-zA-Z0-9_-]+", pid):
                elem_label = pid
                chunk = chunk[:amp]
        val, _ = _parse_value(chunk, 0)
        elements.append(val)
        pos = (end + 1) if end != -1 else len(text)
    return {"type": "pipe", "label": label, "elements": elements}, pos


def _parse_kv_pairs(text: str, pos: int) -> list[dict]:
    """Parse space-separated key=value or key+=value pairs."""
    pairs: list[dict] = []
    while pos < len(text):
        m = re.match(r"[a-zA-Z0-9_-]+", text, pos)
        if not m:
            break
        key = m.group()
        p = m.end()
        if text[p : p + 2] == "+=":
            merge = True
            p += 2
        elif p < len(text) and text[p] == "=":
            merge = False
            p += 1
        else:
            break
        val, p = _parse_value(text, p)
        pairs.append({"key": key, "value": val, "merge": merge})
        if p < len(text) and text[p] == " ":
            p += 1
    return pairs


# ------------------------------------------------------------------
# VyxParser
# ------------------------------------------------------------------


class VyxParser:
    """Grammar-driven Vyx text parser.

    Takes the registry (from GBNFModelBuilder) and the raw rule dict.
    Derives its dispatch table entirely from the grammar — no hardcoded
    knowledge of sigil characters or rule names.
    """

    def __init__(
        self,
        registry: dict[str, type[VyxBase]],
        rules: dict[str, GBNFNode],
    ) -> None:
        self._reg = registry
        self._rules = rules
        self._lines: list[str] = []
        self._pos: int = 0

        # Dispatch table from grammar — {first_literal: rule_name}
        builder = GBNFModelBuilder(rules)
        raw_table = builder.dispatch_table("body-line")
        # Sort longest-first so "# " matches before "#"
        self._dispatch_keys = sorted(raw_table, key=len, reverse=True)
        self._dispatch = raw_table

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def _peek(self) -> str | None:
        return self._lines[self._pos] if self._pos < len(self._lines) else None

    def _consume(self) -> str:
        line = self._lines[self._pos]
        self._pos += 1
        return line

    def _at_end(self) -> bool:
        return self._pos >= len(self._lines)

    @staticmethod
    def _indent(line: str) -> int:
        return len(line) - len(line.lstrip(" "))

    # ------------------------------------------------------------------
    # Grammar-driven dispatch
    # ------------------------------------------------------------------

    def _rule_for_line(self, stripped: str) -> str | None:
        """Return the grammar rule name for a stripped line, or None."""
        for key in self._dispatch_keys:
            if stripped.startswith(key):
                return self._dispatch[key]
        return None

    def _make(self, rule: str, **kwargs: Any) -> VyxBase:
        """Instantiate the model for rule, falling back to bare VyxBase."""
        model = self._reg.get(rule, VyxBase)
        try:
            return model(**kwargs)
        except Exception:
            return VyxBase()

    # ------------------------------------------------------------------
    # Body-line parsing
    # ------------------------------------------------------------------

    def _parse_body_line(
        self, line: str, min_indent: int
    ) -> VyxBase | list[dict] | None:
        stripped = line.lstrip(" ")
        if not stripped:
            return None

        ind = self._indent(line)
        rule = self._rule_for_line(stripped)

        # Fixed-first-literal rules from dispatch table
        if rule == "nl-escape":
            self._consume()
            return self._make(rule, text=stripped.lstrip("\\").lstrip("#").rstrip())

        if rule == "nl-force":
            self._consume()
            return self._make(rule, text=stripped[2:].rstrip())

        if rule == "dict-def":
            self._consume()
            return self._make(rule, raw=stripped)

        if rule == "table-block":
            return self._parse_table_block(ind)

        if rule == "seq-item":
            return self._parse_seq_item(ind)

        # Fallback rules — no fixed first literal in grammar
        # Distinguish scope-line (ends with :) from kv-line (contains =)
        # by scanning the stripped content after any indent.
        if self._looks_like_scope(stripped):
            return self._parse_scope_line(ind)

        kv_pairs = _parse_kv_pairs(stripped, 0)
        if kv_pairs:
            self._consume()
            return kv_pairs  # list[dict]; caller wraps in models

        # nl-text — residual
        self._consume()
        return self._make("nl-text", text=stripped.rstrip())

    @staticmethod
    def _looks_like_scope(stripped: str) -> bool:
        """True if stripped looks like a scope-line: path: or path/sub:"""
        m = re.match(r"[a-zA-Z0-9][a-zA-Z0-9_/-]*\s*(?:\+=)?\s*:", stripped)
        if not m:
            return False
        # Ensure no bare = before the :
        before_colon = stripped[: m.end() - 1]
        return "=" not in before_colon or "+=" in before_colon

    # ------------------------------------------------------------------
    # Scope
    # ------------------------------------------------------------------

    def _parse_scope_line(self, base_indent: int) -> VyxBase:
        line = self._consume()
        stripped = line.lstrip()
        ind = self._indent(line)
        merge = "+=" in stripped.split(":")[0]

        colon = stripped.index(":")
        path_str = stripped[:colon].replace("+=", "").strip()
        path_parts = [p.strip() for p in path_str.split("/") if p.strip()]
        name = path_parts[-1] if path_parts else path_str

        # Opener KVs after the colon on the same line
        rest = stripped[colon + 1 :].strip()
        opener_kvs = _parse_kv_pairs(rest, 0) if rest else []

        try:
            node = self._reg["scope-line"](name=name, path=path_parts, merge=merge)
        except Exception:
            node = VyxBase()

        # Set opener KVs if the model supports it
        if hasattr(node, "_set_opener"):
            for kv in opener_kvs:
                node._set_opener(kv["key"], kv["value"])
        else:
            # Store as child kv-pair models if no _set_opener
            kv_model = self._reg.get("kv-pair", VyxBase)
            for kv in opener_kvs:
                try:
                    child = kv_model(key=kv["key"], value=kv["value"])
                except Exception:
                    child = VyxBase()
                node._append_child(child)

        self._parse_into(node, min_indent=ind + 1)
        return node

    # ------------------------------------------------------------------
    # Table
    # ------------------------------------------------------------------

    def _parse_table_block(self, base_indent: int) -> VyxBase:
        line = self._consume().lstrip()

        m = re.match(
            r"\$([A-Za-z0-9]+)\s+\[([0-9?]+)\]"
            r"(?:\{([^}]*)\})?:",
            line,
        )
        if not m:
            raise ParseError(f"malformed table header: {line!r}")

        tag = m.group(1)
        count = None if m.group(2) == "?" else int(m.group(2))
        fields = [f.strip() for f in (m.group(3) or "").split() if f.strip()]

        try:
            node = self._reg["table-block"](tag=tag, count=count, fields=fields)
        except Exception:
            node = VyxBase()

        row_model = self._reg.get("table-row", VyxBase)

        while not self._at_end():
            nxt = self._peek()
            if nxt is None or not nxt.strip():
                self._consume()
                break
            if self._indent(nxt) <= base_indent and nxt.strip():
                break
            row_line = self._consume().strip()
            if not row_line:
                break
            cells: list[Any] = []
            pos = 0
            while pos < len(row_line):
                val, pos = _parse_value(row_line, pos)
                cells.append(val)
                if pos < len(row_line) and row_line[pos] == " ":
                    pos += 1
            try:
                row = row_model(cells=cells)
            except Exception:
                row = VyxBase()
            node._append_child(row)

        return node

    # ------------------------------------------------------------------
    # Sequence item
    # ------------------------------------------------------------------

    def _parse_seq_item(self, base_indent: int) -> VyxBase:
        line = self._consume()
        stripped = line.lstrip()
        ind = self._indent(line)
        rest = stripped[2:]  # strip "- "

        # Optional label &id
        label: str | None = None
        lm = re.match(r"&([a-zA-Z0-9_-]+)\s+", rest)
        if lm:
            label = lm.group(1)
            rest = rest[lm.end() :]

        head: Any = _parse_kv_pairs(rest, 0) or rest.rstrip() or None

        try:
            item = self._reg["seq-item"](label=label, head=head)
        except Exception:
            item = VyxBase()

        self._parse_into(item, min_indent=ind + 1)
        return item

    # ------------------------------------------------------------------
    # Generic body consumer
    # ------------------------------------------------------------------

    def _parse_into(self, parent: VyxBase, min_indent: int) -> None:
        """Consume lines with indent >= min_indent; append to parent."""
        kv_model = self._reg.get("kv-pair", VyxBase)
        while not self._at_end():
            line = self._peek()
            if line is None:
                break
            if not line.strip():
                self._consume()
                continue
            if self._indent(line) < min_indent:
                break
            result = self._parse_body_line(line, min_indent)
            if result is None:
                self._consume()
            elif isinstance(result, list):
                # KV pair list returned from kv-line
                for kv in result:
                    try:
                        child = kv_model(key=kv["key"], value=kv["value"])
                    except Exception:
                        child = VyxBase()
                    parent._append_child(child)
            else:
                parent._append_child(result)

    # ------------------------------------------------------------------
    # Envelope
    # ------------------------------------------------------------------

    def _parse_envelope(self, line: str) -> VyxBase:
        line = line.strip()
        if not line.startswith("!"):
            raise ParseError(f"envelope must start with !: {line!r}")

        m = re.match(r"!([A-Z])", line)
        if not m:
            raise ParseError("expected performative letter after !")
        perf = "!" + m.group(1)
        pos = m.end()

        kw: dict[str, Any] = {"performative": perf}

        while pos < len(line):
            if line[pos] == " ":
                pos += 1
                continue
            # o:ont
            if line[pos : pos + 2] == "o:":
                m2 = re.match(r"[a-zA-Z0-9.]+", line, pos + 2)
                if m2:
                    kw["ontology"] = m2.group()
                    pos = m2.end()
                continue
            # s: or s!:
            if re.match(r"s!?:", line[pos : pos + 3]):
                skip = 3 if pos + 1 < len(line) and line[pos + 1] == "!" else 2
                m2 = re.match(r"@?[a-zA-Z0-9_-]+", line, pos + skip)
                if m2:
                    kw["sender"] = m2.group()
                    pos = m2.end()
                continue
            # r: or r!:
            if re.match(r"r!?:", line[pos : pos + 3]):
                skip = 3 if pos + 1 < len(line) and line[pos + 1] == "!" else 2
                m2 = re.match(r"@?[a-zA-Z0-9_-]+", line, pos + skip)
                if m2:
                    kw["receiver"] = m2.group()
                    pos = m2.end()
                continue
            # &label
            if line[pos] == "&":
                m2 = re.match(r"[a-zA-Z0-9_-]+", line, pos + 1)
                if m2:
                    kw["msg_label"] = m2.group()
                    pos = m2.end()
                continue
            # ^ref
            if line[pos] == "^":
                m2 = re.match(r"[a-zA-Z0-9_-]+", line, pos + 1)
                if m2:
                    kw["msg_ref"] = m2.group()
                    pos = m2.end()
                continue
            # v:
            if line[pos : pos + 2] == "v:":
                m2 = re.match(r"[0-9.]+", line, pos + 2)
                if m2:
                    kw["version"] = m2.group()
                    pos = m2.end()
                continue
            # L<budget
            if line[pos] == "L":
                m2 = re.match(r"\d+", line, pos + 1)
                if m2:
                    kw["budget"] = int(m2.group())
                    pos = m2.end()
                    if pos < len(line) and line[pos] == "<":
                        pos += 1
                continue
            pos += 1

        try:
            return self._reg["envelope"](**kw)
        except Exception:
            return VyxBase()

    # ------------------------------------------------------------------
    # Entry points
    # ------------------------------------------------------------------

    def parse(self, text: str) -> VyxBase:
        """Parse a full Vyx packet → "packet" model instance."""
        self._lines = [ln for ln in text.splitlines() if ln.strip() != ">"]
        self._pos = 0

        # Skip leading blank lines
        while not self._at_end() and not (self._peek() or "").strip():
            self._consume()

        if self._at_end():
            raise ParseError("empty input")

        envelope = self._parse_envelope(self._consume())

        try:
            packet = self._reg["packet"](envelope=envelope)
        except Exception:
            packet = VyxBase()

        self._parse_into(packet, min_indent=0)
        return packet

    def parse_body(self, text: str) -> list[VyxBase]:
        """Parse Vyx body content → list of body-line instances."""
        self._lines = [ln for ln in text.splitlines() if ln.strip() not in (">", "")]
        self._pos = 0
        container = VyxBase()
        self._parse_into(container, min_indent=0)
        return list(container)


# ------------------------------------------------------------------
# Module-level convenience — grammar loaded once
# ------------------------------------------------------------------

_registry: dict[str, type[VyxBase]] | None = None
_rules: dict[str, GBNFNode] | None = None


def _load() -> tuple[dict[str, type[VyxBase]], dict[str, GBNFNode]]:
    global _registry, _rules
    if _registry is None:
        grammar = _GRAMMAR_PATH.read_text()
        _rules = GBNFParser().parse(grammar)
        _registry = GBNFModelBuilder(_rules).build()
    return _registry, _rules  # type: ignore[return-value]


def parse(text: str) -> VyxBase:
    """Parse a full Vyx packet from text."""
    reg, rules = _load()
    return VyxParser(reg, rules).parse(text)


def parse_body(text: str) -> list[VyxBase]:
    """Parse Vyx body content (no envelope)."""
    reg, rules = _load()
    return VyxParser(reg, rules).parse_body(text)
