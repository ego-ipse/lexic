"""The scene — one reading spelled for the leaf, and nothing decided by it.

Every name the leaf receives is read off the reader text of the form being
shown, so the graph's nodes, the spans' rules and the spine all agree. The
arrangement rides in the same frame: the leaf applies it.
"""

from __future__ import annotations

import re

from lexic.compile import CompiledGrammar, compile_text
from lexic.exceptions import LexicError
from praxis.state import chain
from praxis.reading import Facet, Reading, as_written
from eidolon.topology import edges, graph_facet, levels
from opsis.space import arrange, held, shares
from kairos.machine import machine_facet
from kairos.pipeline import FORMS, form_of, spelled

__all__ = ["GENERATION", "drawn", "moved", "reader_of", "ruledefs", "scene"]

HEAD = re.compile(r"^([A-Za-z0-9_-]+)\s*(?:::=|=/|=)")


def ruledefs(text: str) -> list[tuple[str, int, int]]:
    """Where each rule lives in the reader text — line ranges, addressable."""
    heads = [
        (m.group(1), i)
        for i, line in enumerate(text.split("\n"))
        if (m := HEAD.match(line))
    ]
    out = []
    for place, (name, start) in enumerate(heads):
        stop = heads[place + 1][1] - 1 if place + 1 < len(heads) else text.count("\n")
        out.append((name, start, stop))
    return out


# The same language, at three moments of the pipeline. None of them is more
# true than the others: a grammar as WRITTEN, in its canonical normal form,
# and as codegen cut it for the parser. The views disagreed because each was
# drawing a different one — the automaton is built from the codegen form, so
# a choice it makes has no node in the source form at all.


def reader_of(reading: Reading) -> CompiledGrammar | None:
    """This reading's reader, compiled — or nothing, if nothing reads it."""
    try:
        return compile_text(reading.reader_text, flavour=reading.flavour or "gbnf")
    except LexicError, RecursionError, ValueError:
        return None


def offered(machine: CompiledGrammar | None, placed: bool = False) -> list[Facet]:
    """The surfaces this reading COULD show, each already sized.

    They are not placed — they are offered, with the room each needs, so the
    arrangement can answer "here" or "in a window" instead of drawing a
    picture nobody can read.
    """
    if machine is None:
        return []  # an unreadable reader offers nothing to look at
    rest = [machine_facet(machine)]
    return rest if placed else [graph_facet(machine.grammar), *rest]


# Which reading this is. Every derived surface — the clocks, the automaton,
# the verdicts, the value — is a function of the text, so the leaf must be
# able to tell that the text moved. It was a literal 1, so after a re-read
# only the model came back new and every other surface stayed stale.

GENERATION = [1]


def moved() -> None:
    """The text (or the rung) changed: everything derived from it is old."""
    GENERATION[0] += 1
    _DRAWN.clear()


def scene(reading: Reading, state: dict[str, str] | None = None) -> str:
    """The reading, spelled — with the arrangement its surfaces asked for."""
    machine = reader_of(reading)
    # the relations are a PLACED surface, between the reader they are a
    # picture of and the document. Offered-but-never-placed is how the graph
    # spent four rounds being drawn into a column measured for text.
    facets = reading.facets()
    if machine is not None:
        facets = [*facets[:1], graph_facet(machine.grammar), *facets[1:]]
    # THE FORM IS A PROPERTY OF THE READER: it decides what the reader
    # displays. The grammar as written, its canonical normal form, or the
    # form codegen cut for the parser — each spelled by the flavour, so the
    # reader shows real grammar text in every one of them, and every name
    # downstream (the graph's nodes, the spans' rules, the spine) is read off
    # THAT text. One spelling, one picture, whichever form you are in.
    form = (state or {}).get("form", "source")
    shown = form_of(machine, reading, form) if machine else None
    reader_text = spelled(reading, shown, form)
    rules = ruledefs(reader_text)
    said = [as_written(rules, span.rule) for span in reading.spans]
    names = sorted(set(said))
    fields = sorted({s.field for s in reading.spans})
    at = {name: i for i, name in enumerate(names)}
    fat = {name: i for i, name in enumerate(fields)}
    # two populations, judged separately: what is PLACED is judged against
    # the split it actually got, and what is merely OFFERED is judged against
    # the widest column that split leaves. Mixing them made every surface
    # read as not fitting.
    given = shares(facets, 200)
    elsewhere = offered(machine, placed=True)
    # WHICH RULE REFERS TO WHICH — the relationships. The leaf's wire reader
    # has always had a place for these two blocks; nothing ever filled it, so
    # every graph drew rules as unrelated dots and read as broken.
    relations = (
        [(as_written(rules, a), as_written(rules, b)) for a, b in edges(shown)]
        if shown
        else []
    )
    deep = (
        {as_written(rules, name): at for name, at in levels(shown).items()}
        if shown
        else {}
    )
    policy = {
        "needs": " ".join(f"{f.name}:{f.wide}x{f.tall}" for f in [*facets, *elsewhere]),
        "offered": " ".join(f"{name}:{cols}" for name, cols in given.items()),
        # a shape the hand made outlives a re-read: the arrangement is
        # recomputed only when nobody has said otherwise
        "arrange.tree": held((state or {}).get("arrange.shape", ""), facets)
        or arrange(
            facets,
            dragged=[
                float(word)
                for word in (state or {}).get("arrange.shares", "").split()
                if word.replace(".", "", 1).isdigit()
            ],
            showing={
                key[len("tab.") :]: int(value)
                for key, value in (state or {}).items()
                if key.startswith("tab.") and value.isdigit()
            },
        ),
        "chain": " | ".join(rung.line() for rung in chain(reading)),
        # which moment of the pipeline every view is drawing
        "form": form,
        "forms": " ".join(FORMS),
    }
    # what the leaf remembers about how it is looking at this reading — modes,
    # views, pins — belongs in the frame it boots from, or a reload silently
    # drops back to the primary view
    policy.update(state or {})
    return "\n".join(
        [
            "#META",
            f"fixture {reading.document.name} ⊳ {reading.reader_name}",
            f"reader {reading.reader_name}",
            f"seconds {reading.seconds:.2f}",
            "resolver 0",
            f"faithful {1 if reading.faithful else 0}",
            f"generation {GENERATION[0]}",
            "t 0.0",
            f"#POLICY {len(policy)}",
            *(f"{k} {v}" for k, v in policy.items()),
            f"#RULEDEFS {len(rules)}",
            *(f"{n} {a} {b}" for n, a, b in rules),
            f"#RULENAMES {len(names)}",
            *names,
            f"#FIELDNAMES {len(fields)}",
            *fields,
            # what each surface is CALLED and where it lives. The leaf used
            # to carry "THE READER" in its own markup and a facet list in its
            # own source, so adding a surface meant editing the leaf.
            f"#FACETS {len(facets)}",
            *(f.wire()[len("#FACET ") :] for f in facets),
            f"#EDGES {len(relations)}",
            *(f"{a} {b}" for a, b in relations),
            f"#DEPTHS {len(deep)}",
            *(f"{name} {at_}" for name, at_ in deep.items()),
            f"#SPANS {len(reading.spans)}",
            *(
                f"{s.start} {s.end} {s.depth} {at[r]} {fat[s.field]}"
                for s, r in zip(reading.spans, said, strict=True)
            ),
            f"#READER {len(reader_text)}",
            reader_text,
            f"#DOC {len(reading.text)}",
            reading.text,
            "",
        ]
    )


_DRAWN: dict[int, str] = {}


def drawn(reading: Reading, state: dict[str, str] | None = None) -> str:
    """The scene, built once per state of the text.

    A quarter of a megabyte was being rebuilt — spans, both text blocks, every
    measurement — on every poll the leaf makes. It changes when the text
    changes, so that is when it is rebuilt.
    """
    key = hash(
        (
            GENERATION[0],
            reading.text,
            reading.reader_text,
            tuple(sorted((state or {}).items())),
        )
    )
    if key not in _DRAWN:
        _DRAWN.clear()
        _DRAWN[key] = scene(reading, state)
    return _DRAWN[key]
