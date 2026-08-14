"""The rooms — a subject seen as what it IS, never as the parser's view of it.

Each room is a function of the reading it is about: the rules by what they
account for, one rule with everything it is, the machine, the artefacts, the
value surface, and the pipeline as steps with claims that are checked.
"""

from __future__ import annotations

from collections.abc import Sequence

from eidolon.topology import reachable
from eidolon.value import graph as ir_graph
from eidolon.value import refused as ir_refused
from kairos.artefacts import Artefact
from kairos.generation import make as generate_document
from kairos.machine import of
from kairos.pipeline import FORMS, form_of, spelled
from opsis.scene import ruledefs
from praxis.reading import Reading, as_written

from lexic.compile import CompiledGrammar
from lexic.grammars import get_flavour
from lexic.ir import IrAst
from lexic.ir.spine.spine import IrSelf

__all__ = ["room", "subject"]


def subject(
    reading: Reading,
    pid: str,
    machine: CompiledGrammar,
    praxis: IrSelf | None = None,
) -> IrSelf | None:
    """What a place id NAMES, as a live value — never a description of one."""
    if pid == "grammar":
        return machine.grammar
    if pid == "reducer":
        return get_flavour(reading.flavour or "gbnf").reducer
    if pid == "codegen":
        return machine.codegen_grammar
    if pid == "instrument":
        return praxis
    if pid.startswith("rule:"):
        wanted = pid[5:].casefold()
        for rule in machine.grammar.rules:
            if str(rule.name).casefold() == wanted:
                return rule
    return None


def room(
    which: str,
    machine: CompiledGrammar,
    reading: Reading,
    state: dict[str, str],
    generation: int = 0,
    artefacts: Sequence[Artefact] | None = None,
    praxis: IrSelf | None = None,
) -> str:
    """One room, spelled. A room nobody authored says so, in place."""
    if which in ("index", ""):
        rows = [
            "the pipeline — the same language, four moments\tplace:pipeline",
            "the rules — each one, by what it accounts for\tplace:rules",
            "the machine — clones, not rules\tplace:machine",
            "the artefacts — each one loaded back\tplace:artefacts",
            "the grammar as a VALUE — the IR it loaded to\tplace:ir:grammar",
            "what codegen made of it — the grammar the parser runs\tplace:ir:codegen",
            "the reducer as a VALUE — where meaning attaches\tplace:ir:reducer",
            "the instrument as a VALUE — Praxis on the same spine\tplace:ir:instrument",
            "a document this reader accepts — generated and read back\tplace:generate:0",
        ]
        return "\n".join(
            [
                "#PLACE index rooms the rooms this reading holds",
                "#SEC title 1",
                "ROOMS",
                f"#SEC list {len(rows)}",
                *rows,
                "",
            ]
        )
    if which == "machine":
        built = of(machine)
        return "\n".join(
            [
                "#PLACE machine compiler the machine this grammar compiles to",
                "#SEC title 1",
                built.line(),
                "#SEC kv 3",
                f"clones built\t{built.clones}",
                f"rules\t{built.rules}",
                f"deep\t{built.deepest}",
                "",
            ]
        )
    if which == "pipeline":
        # the pipeline as STEPS with checked claims, not a list of names.
        # What each moment did to the one before is a fact about two
        # grammars, so it is computed from them rather than described.
        here = state.get("form", "source")
        rows: list[str] = []
        facts: list[str] = []
        before: IrAst | None = None
        for which_form in FORMS:
            now = form_of(machine, reading, which_form)
            names = [str(rule.name) for rule in now.rules]
            spelled_now = spelled(reading, now, which_form)
            if before is None:
                said = f"{len(names)} rules · {len(spelled_now):,} chars"
            else:
                was = {str(rule.name) for rule in before.rules}
                cut = sorted(set(names) - was)
                gone = sorted(was - set(names))
                said = (
                    f"{len(names)} rules"
                    + (f" · +{len(cut)}: {', '.join(cut[:3])}" if cut else "")
                    + (f" · −{len(gone)}: {', '.join(gone[:3])}" if gone else "")
                    + ("" if cut or gone else " · same rules, respelled")
                )
            facts.append(f"{which_form}\t{said}")
            rows.append(
                f"{'▸ ' if which_form == here else ''}{which_form} — {said}"
                f"\tform:{which_form}"
            )
            before = now
        reads = reading.faithful
        return "\n".join(
            [
                "#PLACE pipeline pipeline the same language, four moments",
                "#SEC title 1",
                f"{reading.reader_name} — showing the {here} form",
                f"#SEC kv {len(facts) + 1}",
                *facts,
                "the parse of this document\t"
                + ("re-emits its own text" if reads else "IS NOT FAITHFUL"),
                f"#SEC list {len(rows)}",
                *rows,
                "",
            ]
        )
    if which.startswith("generate"):
        _, _, seed_text = which.partition(":")
        seed = int(seed_text) if seed_text.isdigit() else 0
        made = generate_document(machine, seed)
        if not made.faithful:
            return "\n".join(
                [
                    f"#PLACE {which} generation a document this reader accepts",
                    "#SEC title 1",
                    f"GENERATE · {made.root} · seed {made.seed}",
                    "#SEC refusal 1",
                    made.words,
                    "#SEC list 1",
                    f"try the next seed\tplace:generate:{seed + 1}",
                    "",
                ]
            )
        spelling = made.text.encode("unicode_escape").decode("ascii")
        return "\n".join(
            [
                f"#PLACE {which} generation a document this reader accepts",
                "#SEC title 1",
                f"GENERATED DOCUMENT · {len(made.text):,} chars",
                "#SEC kv 4",
                f"root rule\t{made.root}",
                f"seed\t{made.seed}",
                f"read-back\t{made.words}",
                f"document\t{spelling or '«empty document»'}",
                "#SEC list 1",
                f"generate another\tplace:generate:{seed + 1}",
                "",
            ]
        )
    if which == "rules":
        # ordered by how much of the document each rule ACCOUNTS FOR, not
        # alphabetically: the ordering is a reading of this document, and
        # a name-sorted list says nothing about what was parsed
        counts: dict[str, int] = {}
        for span in reading.spans:
            counts[span.rule] = counts.get(span.rule, 0) + 1
        ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
        rules = ruledefs(reading.reader_text)
        return "\n".join(
            [
                f"#PLACE rules rules the {len(ranked)} rules this document used",
                "#SEC title 1",
                f"{len(ranked)} rules used · {len(reading.spans):,} occurrences",
                f"#SEC list {len(ranked)}",
                *(
                    f"{as_written(rules, name)} — {n:,} occurrences"
                    f"\tplace:rule:{as_written(rules, name)}"
                    for name, n in ranked
                ),
                "",
            ]
        )
    if which.startswith("rule:"):
        rule = subject(reading, which, machine)
        if rule is None:
            return nothing(which, "this reader defines no rule called")
        name = which[5:]
        here = [s for s in reading.spans if s.rule.casefold() == name.casefold()]
        _, depth = reachable(machine.grammar, name)
        clones = sum(
            1
            for key in machine.pda_tables().clones
            if getattr(key, "name", "").casefold() == name.casefold()
        )
        walk = ir_graph(rule)
        return "\n".join(
            [
                f"#PLACE {which} rule one rule — everything it is",
                "#SEC title 1",
                f"{name} — {len(here)} occurrences in this document",
                "#SEC kv 5",
                f"occurrences\t{len(here):,}",
                f"deepest occurrence\t{max((s.depth for s in here), default=0)}",
                f"rules it can reach\t{len(depth) - 1}",
                f"clones compiled for it\t{clones}",
                f"its own IR\t{len(walk.nodes)} nodes, {len(walk.edges)} edges",
                "#SEC graphview 1",
                which,
                "#SEC irvalue 1",
                which,
                "#SEC list 2",
                "the whole grammar's graph\tplace:ir:grammar",
                "the machine\tplace:machine",
                "",
            ]
        )
    if which.startswith("ir:"):
        pid = which[3:]
        value = subject(reading, pid, machine, praxis)
        if value is None:
            return nothing(which, "no value here is addressed")
        walk = ir_graph(value)
        shared = [at for at, n in walk.refs.items() if n > 1]
        return "\n".join(
            [
                f"#PLACE {which} value the {pid} as the value it IS",
                "#SEC title 1",
                f"{type(value).__name__} — {len(walk.nodes)} unique nodes, "
                f"{len(walk.edges)} edges",
                "#SEC kv 4",
                f"unique nodes\t{len(walk.nodes)}",
                f"edges\t{len(walk.edges)}",
                f"shared objects\t{len(shared)} reached "
                f"{sum(walk.refs[at] for at in shared)} times",
                f"the notation refuses\t"
                f"{sum(1 for n in walk.nodes if ir_refused(n))} nodes",
                "#SEC irvalue 1",
                pid,
                "#SEC list 3",
                "the grammar as a value\tplace:ir:grammar",
                "the reducer as a value\tplace:ir:reducer",
                "the instrument as a value\tplace:ir:instrument",
                "",
            ]
        )
    if which == "artefacts":
        if artefacts is None:
            return "\n".join(
                [
                    "#PLACE artefacts artefacts what this reader can be written as",
                    "#SEC title 1",
                    "ARTEFACTS — witnesses are running…",
                    "#SEC kv 1",
                    "family\tPENDING · exporting and loading every form back",
                    "",
                ]
            )
        made = artefacts
        return "\n".join(
            [
                "#PLACE artefacts artefacts what this reader can be written as",
                "#SEC title 1",
                "ARTEFACTS — none counts until it loads back",
                f"#SEC kv {len(made)}",
                *(
                    f"{a.name}\t{a.chars:,} chars · {a.witness} — {a.words}"
                    + (f" · runtime {a.module}" if a.module else "")
                    for a in made
                ),
                "",
            ]
        )
    return nothing(which, "no room here is addressed")


def nothing(which: str, why: str) -> str:
    """A refusal, in place — with what this reading DOES hold."""
    return "\n".join(
        [
            f"#PLACE {which} missing no such room",
            "#SEC title 1",
            "NO SUCH ROOM",
            "#SEC refusal 1",
            f"{why} {which!r}",
            "#SEC list 4",
            "the machine\tplace:machine",
            "the artefacts\tplace:artefacts",
            "the grammar as a value\tplace:ir:grammar",
            "the reducer as a value\tplace:ir:reducer",
            "",
        ]
    )
