"""Transpile python to c++ — the same model-plane mechanism as ex16.

A transpiler between programming languages has three stages: parse to a
typed AST, transform, pretty-print. Lexic supplies the first and last from
the two grammars alone — the parsed model IS the typed AST, and the target
grammar's ``to_text()`` IS the pretty-printer — so what remains is the
transform: a table of per-rule bodies, keyed by python's rule names,
building c++'s models by name.

Almost every row is ``Make`` splatting its already-transformed children —
the two ASTs are near-parallel, and the table says so by being nearly
empty. The ONE function in this file is the one thing a transpiler
genuinely is: c++ declares variables and python does not, so the
``funcdef`` row pipes the built function through a declaration pass that
turns a name's FIRST assignment into ``int y = ...`` and every later one
into plain assignment — semantic knowledge neither grammar carries.

Run::

    uv run python -m getting_started.ex17_transpile_python_cpp
"""

from __future__ import annotations

from functools import partial

from lexic import compile_text
from lexic.compile import Flat, Make, Spelled, transpile
from lexic.ir import (
    IrArg,
    IrEach,
    IrLambda,
    IrMap,
    IrPipe,
    IrRuleRef,
    IrThis,
    IrTuple,
)
from lexic.model import GrammarModel

# The SOURCE language: a python subset. One-level function bodies, the
# indent is a literal token, so the notorious non-context-free part of
# python's surface stays out of the subset.
PY_GRAMMAR = r"""module ::= funcdef+
funcdef ::= "def " fname "(" params? "):" "\n" body
params ::= pname (", " pname)*
body ::= stmt+
stmt ::= "    " inner "\n"
inner ::= "return " expr | target " = " expr
expr ::= term (op term)*
op ::= " + " | " - " | " * "
term ::= [a-z_]+ | [0-9]+
fname ::= [a-z_]+
pname ::= [a-z_]+
target ::= [a-z_]+
"""

# The TARGET language, written before the transform: the c++ this subset
# lands in. Every value is ``int`` — a stated domain, not an inference.
CPP_GRAMMAR = r"""unit ::= func+
func ::= "int " fname "(" cparams? ") {" "\n" cbody "}" "\n"
cparams ::= cparam (", " cparam)*
cparam ::= "int " pname
cbody ::= cstmt+
cstmt ::= "    " cinner ";" "\n"
cinner ::= "return " cexpr | "int " target " = " cexpr | target " = " cexpr
cexpr ::= cterm (cop cterm)*
cop ::= " + " | " - " | " * "
cterm ::= [a-z_]+ | [0-9]+
fname ::= [a-z_]+
pname ::= [a-z_]+
target ::= [a-z_]+
"""

PROGRAM = """\
def add(a, b):
    return a + b
def scale(x):
    y = x * 3
    y = y + 1
    return y
"""

PY = compile_text(PY_GRAMMAR, cache_key="ex17-py")
CPP = compile_text(CPP_GRAMMAR, cache_key="ex17-cpp")


def _declared(b: dict[str, type], _d, func: GrammarModel, _nc) -> GrammarModel:
    """THE transpiler: a name's first assignment becomes a declaration.

    The focus is the already-built c++ function; parameters arrive bound,
    and each plain assignment (``cinner-arm3``) to a new name is rewritten
    to a declaration (``cinner-arm2``). Function-scoped state, held on the
    function node — where it belongs.
    """
    cparams = getattr(func, "cparams")
    bound = set()
    if cparams is not None:
        bound.add(str(getattr(getattr(cparams, "cparam"), "pname")))
        for item in getattr(cparams, "cparams_item"):
            bound.add(str(getattr(getattr(item, "cparam"), "pname")))
    rows = []
    for stmt in getattr(getattr(func, "cbody"), "cstmt"):
        arm = getattr(stmt, "cinner")
        if type(arm).__name__ == "CinnerArm3":
            name = str(getattr(arm, "target"))
            if name not in bound:
                bound.add(name)
                declared = b["CinnerArm2"](
                    target=getattr(arm, "target"), cexpr=getattr(arm, "cexpr")
                )
                stmt = b["Cstmt"](cinner=declared)
        rows.append(stmt)
    return b["Func"](
        fname=getattr(func, "fname"), cparams=cparams, cbody=b["Cbody"](cstmt=rows)
    )


RULES = IrMap(
    IrTuple(IrRuleRef("term"), Make("cterm", IrTuple(Spelled()))),
    IrTuple(IrRuleRef("op"), Make("cop", IrTuple(Spelled()))),
    IrTuple(IrRuleRef("fname"), Make("fname", IrTuple(Spelled()))),
    IrTuple(IrRuleRef("pname"), Make("pname", IrTuple(Spelled()))),
    IrTuple(IrRuleRef("target"), Make("target", IrTuple(Spelled()))),
    IrTuple(IrRuleRef("expr-item"), Make("cexpr-item")),
    IrTuple(IrRuleRef("expr"), Make("cexpr")),
    IrTuple(IrRuleRef("params-item"), IrArg(-1)),
    IrTuple(
        IrRuleRef("params"),
        Make("cparams", IrPipe(Flat(), IrEach(Make("cparam", IrTuple(IrThis()))))),
    ),
    IrTuple(IrRuleRef("inner-arm1"), Make("cinner-arm1")),
    IrTuple(IrRuleRef("inner-arm2"), Make("cinner-arm3")),
    IrTuple(IrRuleRef("stmt"), Make("cstmt")),
    IrTuple(IrRuleRef("body"), Make("cbody")),
    IrTuple(
        IrRuleRef("funcdef"),
        IrPipe(Make("func"), IrLambda(partial(_declared, CPP.classes))),
    ),
    IrTuple(IrRuleRef("module"), Make("unit")),
)
"""T, whole: nearly-parallel ASTs make a nearly-empty table — a bare
``Make("x")`` splats the transformed children straight into the target's
constructor. One row carries the one function a transpiler genuinely is."""


def main() -> None:
    """Run the table — lexic bakes it and gates the rest."""
    out = transpile(PY, CPP, RULES).run(PROGRAM)
    print("=== python in ===")
    print(PROGRAM)
    print("=== c++ out ===")
    print(out)

    # `run` gated completeness, membership and fidelity; what remains is
    # T's own claim — the declaration inference did its job.
    assert "int y = x * 3;" in out and "    y = y + 1;" in out
    print("witness: run() gated · first assignment declares, later ones do not")


if __name__ == "__main__":
    main()
