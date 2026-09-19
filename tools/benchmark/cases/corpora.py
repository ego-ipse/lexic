"""The documents every engine parses — one generator per benchmark language.

Kept apart from the grammars so a file that answers "what language is this?"
is not also answering "what text is timed?". A generator's only contract is
that its output derives from its grammar at both scales; the grammar module
pairs the two.

The corpora are synthetic by design. A sampled document is one author's habits,
and a row would then measure those as much as the language — so each generator
walks its grammar's constructs deliberately, and a shape that appears in the
grammar appears in the document.
"""

from __future__ import annotations

import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]


def split_nullable_corpus(paras: int) -> str:
    """Paragraphs of three lines, including empty ones, each closed by a blank."""
    letters = "abcdefghijklmnopqrstuvwxyz"
    out: list[str] = []
    for n in range(paras):
        for k in range(3):
            tag = letters[(n + k) % 26]
            body = f"line {tag} of para {letters[n % 26] * 3} here"
            out.append("\n" if k == 1 and n % 4 == 0 else f"{body}\n")
        out.append("\n")
    return "".join(out)


def wrapped_unit_corpus(paras: int) -> str:
    """The split-nullable document behind an opener and before a closer."""
    return f"<<<\n{split_nullable_corpus(paras)}>>>\n"


def island_corpus(terms: int) -> str:
    """A left-associative chain of calls, each over a LONG argument run.

    The chain is the left recursion the row exists for, and its length is the
    model's nesting depth — so the size comes from the interiors rather than
    from more terms. A chain of a thousand would be a recursion-limit fixture
    instead of an Earley one.
    """
    letters = "abcdefghijklmnopqrstuvwxyz"
    parts: list[str] = []
    for n in range(terms):
        tag = letters[n % 26]
        run = f"{tag * 5}deterministic.interior_{n % 97},12.5,path/to/{tag}/x,"
        parts.append(f"{tag}fn{n}({run * 4}end)" if n % 2 else f"{tag}var{n}")
    return " + ".join(parts) + "\n"


def dense_earley_corpus(terms: int, per_line: int = 24) -> str:
    """A left-recursive chain of SINGLE-CHARACTER terms, bounded per line.

    Every character is a term or the operator between two, so essentially every
    chart column holds items — the opposite of a run-collapsed grammar, where a
    terminal steps many characters at once and leaves most columns empty. That
    is what makes this the dense control: a per-column change reads a saving on
    a sparse chart whether or not it taxes the columns that are occupied.

    The chain is per LINE rather than over the whole document, so its depth is
    ``per_line`` and does not grow with the document. Depth is a property of
    this generator, not of what is being measured, and a chain of thousands
    would price the recursion limit instead.
    """
    letters = "abcdefghijklmnopqrstuvwxyz"
    lines: list[str] = []
    for start in range(0, terms, per_line):
        width = min(per_line, terms - start)
        lines.append("+".join(letters[(start + n) % 26] for n in range(width)))
    return "\n".join(lines) + "\n"


def start_fallback_corpus(units: int) -> str:
    """A run of units for a left-recursive START rule the fold refuses.

    The rule's recursive arm captures nothing, so the fold declines it
    (``fold_build`` returns ``None``) and the predictive path raises — the
    product's own fallback then parses the whole document on Earley. The
    document is one flat run because the shape, not its content, is what
    reaches the engine.
    """
    return "a" * units


def interior_exact_corpus(units: int) -> str:
    """The same refused recursion as an INTERIOR rule, with a disjoint tail.

    The island's alphabet cannot contain the tail's first character, so the
    continuation analysis proves an exact width and the sub-parse runs ONCE at
    it. This is the bounded half of the island window.
    """
    return "a" * units + "\n"


def interior_climb_corpus(units: int) -> str:
    """The same shape with an OVERLAPPING tail — so the window must climb.

    The island's alphabet contains the continuation's first character, so no
    exact width is provable and the sub-parse re-runs at 256, 512, 1024 …
    until the chart stops extending. Every proper prefix is followed by an
    ``a``, which the tail refuses, so exactly one end composes and the island
    still ANSWERS rather than falling back.
    """
    return "z" + "a" * units + "zz\n"


def announced_corpus(sections: int) -> str:
    """Sections of a header and four body lines, with no readable boundary."""
    letters = "abcdefghijklmnopqrstuvwxyz"
    out: list[str] = []
    for n in range(sections):
        out.append(f"#section {letters[n % 26] * 3} heading\n")
        for k in range(4):
            out.append(
                f"body line {letters[k]} of section {letters[(n + k) % 26] * 2} here\n"
            )
    return "".join(out)


def mixedends_corpus(rows: int) -> str:
    """A stream interleaving all three record kinds, none of them separated."""
    out: list[str] = []
    for n in range(rows):
        out.append(f"%key{n % 40}_a=value/{n}.{n % 7};")
        out.append(f"<span{n % 30}:{n * 3}>")
        out.append(f"note{n} carries {n % 11} words here\n")
    return "".join(out)


def markdown_corpus(sections: int) -> str:
    """A document exercising every block and inline kind this subset defines."""
    out: list[str] = ["# Release notes\n", "\n"]
    for n in range(sections):
        out.append(f"## Section {n}\n")
        out.append(f"Prose for section {n} with *stress*, **weight** and `code`.\n")
        out.append(
            f"See [the docs](http://example.test/{n}) or ![figure](img/{n}.png).\n"
        )
        out.append(f"- bullet {n} carrying `inline` and *accent*\n")
        out.append(f"{n % 9 + 1}. numbered {n} with **weight**\n")
        out.append(f"> quoted remark {n}\n")
        if n % 4 == 0:
            out.append("```python\n")
            out.append(f"value = compute({n})\n")
            out.append("return value\n")
            out.append("```\n")
        if n % 5 == 0:
            out.append("---\n")
        out.append("\n")
    return "".join(out)


def nested_corpus(depth: int, rows: int) -> str:
    """Nesting to ``depth`` at the spine, with breadth at each level."""
    out: list[str] = []
    for r in range(rows):
        inner = f"leaf{'' if r % 2 else 'x'}".replace("0", "o")
        text = "".join(ch for ch in inner if ch.isalpha())
        for d in range(depth):
            text = f"({text},{'ab'[d % 2]})" if d % 3 == 0 else f"({text})"
        out.append(text)
    return ",".join(out).join("()")


def lexrun_corpus(rows: int) -> str:
    """Entries whose terminals are long — the inverse of the arithmetic row."""
    out: list[str] = []
    for n in range(rows):
        name = "field_" + "n" * (n % 40 + 8) + f"_{n}"
        if n % 3 == 0:
            value = '"' + ("text value " * (n % 6 + 3)).strip() + '"'
        elif n % 3 == 1:
            value = "path/to/some." + "segment" * (n % 5 + 2)
        else:
            value = str(n) * (n % 12 + 4)
        out.append(f"{name}={value}")
    return "\n".join(out)


def backtrack_corpus(rows: int) -> str:
    """Statements whose arm is decided only after an unbounded shared prefix."""
    out: list[str] = []
    for n in range(rows):
        name = "n" + "a" * (n % 30 + 2) + str(n)
        if n % 2:
            out.append(f"def {name}() {{body{n}}}\n")
        else:
            out.append(f"def {name}() = value{n};\n")
    return "".join(out)


def arith_corpus(target: int) -> str:
    """A left-nested arithmetic expression of roughly ``target`` characters."""
    parts: list[str] = ["1"]
    size = 1
    ops = ("+", "*", "-", "/")
    while size < target:
        step = len(parts)
        term = f"({step % 97 + 1}+{step % 89 + 2})"
        parts.append(ops[step % 4])
        parts.append(term)
        size += 1 + len(term)
    return "".join(parts)


def csv_corpus(rows: int) -> str:
    """A rectangular CSV body — no quoting, so the grammar stays unambiguous."""
    return "\n".join(",".join(f"cell {r}{c}" for c in range(6)) for r in range(rows))


def json_corpus(items: int) -> str:
    """A nested json document of ``items`` records."""
    body = ", ".join(
        f'{{"id{n}": "row {n}", "tags": ["a", "b"]}}' for n in range(items)
    )
    return f'{{"rows": [{body}], "ok": "yes"}}'


def vyx_corpus(rows: int) -> str:
    """A template-carrying vyx packet whose block body mixes the line types.

    Each row contributes one kv-line, one indented scope-line, one seq-item and
    one nl-text prose line — the D.17 body shapes a real packet interleaves.
    """
    lines: list[str] = []
    for n in range(rows):
        lines.append(f"id=ORD-{n:04d} qty={n % 9 + 1} note=_")
        lines.append(f" ship: meth=express carr=DHL leg={n % 5}")
        lines.append(f'- type=feature idx={n} title="Widget {n}"')
        lines.append("free prose line about the widget catalogue")
    body = "\n".join(lines) + "\n"
    return f"T:w=o:inv s:@buyer r:@supplier\n!I %w n:7 L{len(body.encode())}<\n{body}>"


def ground_truth(stem: str) -> str:
    """A ground-truth grammar file — the meta row's input."""
    return (_ROOT / "resources" / "ground_truth" / stem).read_text(encoding="utf-8")


def meta_corpus(stem: str, copies: int) -> str:
    """A large grammar file: the ground-truth grammar, concatenated.

    Each copy's rule names get a ``c<k>-`` prefix — references included, so
    every copy stays a well-formed grammar fragment and the whole keeps a
    real file's shape rather than inventing rules. Quoted literals are left
    alone: ``true`` is a rule name AND a spelled keyword, and renaming the
    keyword would change the described language mid-corpus.
    """
    source = ground_truth(stem)
    quoted = re.compile(r'"(?:\\.|[^"\\])*"')
    names = re.findall(r"^([A-Za-z][A-Za-z0-9-]*)\s*(?:::=|=)", source, re.MULTILINE)
    rename = re.compile(
        r"\b(" + "|".join(sorted(set(names), key=len, reverse=True)) + r")\b"
    )
    out: list[str] = []
    for copy in range(copies):
        at = 0
        pieces: list[str] = []
        for match in quoted.finditer(source):
            pieces.append(rename.sub(rf"c{copy}-\1", source[at : match.start()]))
            pieces.append(match.group())
            at = match.end()
        pieces.append(rename.sub(rf"c{copy}-\1", source[at:]))
        out.append("".join(pieces))
    return "".join(out)
