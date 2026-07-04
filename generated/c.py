"""Generated module: c. Do not edit; regenerated from grammar."""

from __future__ import annotations

from typing import Annotated, ClassVar, List, Optional

from pydantic import StringConstraints

from lexic.base import GrammarModel
from lexic.ir import (
    IrAlternation,
    IrAst,
    IrBind,
    IrCharClass,
    IrChr,
    IrItem,
    IrLiteral,
    IrNone,
    IrQuantifier,
    IrRange,
    IrRule,
    IrRuleRef,
    IrSeq,
    IrSequence,
)

Pattern = Annotated[str, StringConstraints(pattern=r"^[A-Z_a-z]$")]

Alnum = Annotated[str, StringConstraints(pattern=r"^[0-9A-Z_a-z]*$")]

Pattern2 = Annotated[str, StringConstraints(pattern=r"^[\x09-\x0a ]+$")]

Pattern3 = Annotated[str, StringConstraints(pattern=r"^[\x00-\x09\x0b-\U0010ffff]*$")]

Pattern4 = Annotated[str, StringConstraints(pattern=r"^[\x00-)+-\U0010ffff]$")]

Pattern5 = Annotated[str, StringConstraints(pattern=r"^[\x00-.0-\U0010ffff]$")]

Pattern6 = Annotated[
    str, StringConstraints(pattern=r"^([\x00-)+-\U0010ffff]|\*[\x00-.0-\U0010ffff])*$")
]

Pattern7 = Annotated[str, StringConstraints(pattern=r"^(<=|<|==|!=|>=|>)$")]

Digit = Annotated[str, StringConstraints(pattern=r"^[0-9]+$")]

Pattern8 = Annotated[str, StringConstraints(pattern=r"^[+-]$")]

Pattern9 = Annotated[str, StringConstraints(pattern=r"^[*/]$")]


class Root(GrammarModel):
    declaration: Annotated[List[Declaration], IrBind(0, "models")]
    __grammar__: ClassVar[IrRule] = IrRule(
        "root",
        IrAlternation(
            IrSequence(IrItem(IrRuleRef("declaration"), IrQuantifier(0, IrNone)))
        ),
    )


class Declaration(GrammarModel):
    datatype: Annotated[Datatype, IrBind(0, "model")]
    identifier: Annotated[Identifier, IrBind(1, "model")]
    parameter: Annotated[Optional[Parameter], IrBind(3, "model")] = None
    statement: Annotated[List[Statement], IrBind(5, "models")]
    __grammar__: ClassVar[IrRule] = IrRule(
        "declaration",
        IrAlternation(
            IrSequence(
                IrItem(IrRuleRef("datatype")),
                IrItem(IrRuleRef("identifier")),
                IrItem(IrLiteral("(")),
                IrItem(IrRuleRef("parameter"), IrQuantifier(0)),
                IrItem(IrLiteral("){")),
                IrItem(IrRuleRef("statement"), IrQuantifier(0, IrNone)),
                IrItem(IrLiteral("}")),
            )
        ),
    )


class Datatype(GrammarModel):
    __grammar__: ClassVar[IrRule] = IrRule(
        "datatype",
        IrAlternation(
            IrSequence(IrItem(IrRuleRef("datatype-arm1"))),
            IrSequence(IrItem(IrRuleRef("datatype-arm2"))),
            IrSequence(IrItem(IrRuleRef("datatype-arm3"))),
        ),
    )


class DatatypeArm1(Datatype):
    ws: Annotated[Optional[Ws], IrBind(1, "model", False)] = None
    __grammar__: ClassVar[IrRule] = IrRule(
        "datatype-arm1",
        IrAlternation(
            IrSequence(
                IrItem(IrLiteral("int")), IrItem(IrRuleRef("ws"), IrQuantifier(0))
            )
        ),
    )


class DatatypeArm2(Datatype):
    ws: Annotated[Optional[Ws], IrBind(1, "model", False)] = None
    __grammar__: ClassVar[IrRule] = IrRule(
        "datatype-arm2",
        IrAlternation(
            IrSequence(
                IrItem(IrLiteral("float")), IrItem(IrRuleRef("ws"), IrQuantifier(0))
            )
        ),
    )


class DatatypeArm3(Datatype):
    ws: Annotated[Optional[Ws], IrBind(1, "model", False)] = None
    __grammar__: ClassVar[IrRule] = IrRule(
        "datatype-arm3",
        IrAlternation(
            IrSequence(
                IrItem(IrLiteral("char")), IrItem(IrRuleRef("ws"), IrQuantifier(0))
            )
        ),
    )


class Factor(GrammarModel):
    __grammar__: ClassVar[IrRule] = IrRule(
        "factor",
        IrAlternation(
            IrSequence(IrItem(IrRuleRef("identifier"))),
            IrSequence(IrItem(IrRuleRef("number"))),
            IrSequence(IrItem(IrRuleRef("unaryterm"))),
            IrSequence(IrItem(IrRuleRef("funccall"))),
            IrSequence(IrItem(IrRuleRef("parenexpression"))),
        ),
    )


class Identifier(Factor):
    value: str
    __grammar__: ClassVar[IrRule] = IrRule(
        "identifier",
        IrAlternation(
            IrSequence(
                IrItem(
                    IrCharClass(
                        IrRange(IrChr(65), IrChr(90)),
                        IrChr(95),
                        IrRange(IrChr(97), IrChr(122)),
                    )
                ),
                IrItem(
                    IrCharClass(
                        IrRange(IrChr(48), IrChr(57)),
                        IrRange(IrChr(65), IrChr(90)),
                        IrChr(95),
                        IrRange(IrChr(97), IrChr(122)),
                    ),
                    IrQuantifier(0, IrNone),
                ),
            )
        ),
    )


class Parameter(GrammarModel):
    datatype: Annotated[Datatype, IrBind(0, "model")]
    identifier: Annotated[Identifier, IrBind(1, "model")]
    __grammar__: ClassVar[IrRule] = IrRule(
        "parameter",
        IrAlternation(
            IrSequence(IrItem(IrRuleRef("datatype")), IrItem(IrRuleRef("identifier")))
        ),
    )


class Statement(GrammarModel):
    __grammar__: ClassVar[IrRule] = IrRule(
        "statement",
        IrAlternation(
            IrSequence(IrItem(IrRuleRef("statement-arm1"))),
            IrSequence(IrItem(IrRuleRef("statement-arm2"))),
            IrSequence(IrItem(IrRuleRef("statement-arm3"))),
            IrSequence(IrItem(IrRuleRef("statement-arm4"))),
            IrSequence(IrItem(IrRuleRef("statement-arm5"))),
            IrSequence(IrItem(IrRuleRef("statement-arm6"))),
            IrSequence(IrItem(IrRuleRef("statement-arm7"))),
            IrSequence(IrItem(IrRuleRef("singlelinecomment"))),
            IrSequence(IrItem(IrRuleRef("multilinecomment"))),
        ),
    )


class StatementArm1(Statement):
    datatype: Annotated[Datatype, IrBind(0, "model")]
    identifier: Annotated[Identifier, IrBind(1, "model")]
    ws: Annotated[Optional[Ws], IrBind(2, "model", False)] = None
    ws2: Annotated[Optional[Ws], IrBind(4, "model", False)] = None
    expression: Annotated[Expression, IrBind(5, "model")]
    __grammar__: ClassVar[IrRule] = IrRule(
        "statement-arm1",
        IrAlternation(
            IrSequence(
                IrItem(IrRuleRef("datatype")),
                IrItem(IrRuleRef("identifier")),
                IrItem(IrRuleRef("ws"), IrQuantifier(0)),
                IrItem(IrLiteral("=")),
                IrItem(IrRuleRef("ws"), IrQuantifier(0)),
                IrItem(IrRuleRef("expression")),
                IrItem(IrLiteral(";")),
            )
        ),
    )


class StatementArm2(Statement):
    identifier: Annotated[Identifier, IrBind(0, "model")]
    ws: Annotated[Optional[Ws], IrBind(1, "model", False)] = None
    ws2: Annotated[Optional[Ws], IrBind(3, "model", False)] = None
    expression: Annotated[Expression, IrBind(4, "model")]
    __grammar__: ClassVar[IrRule] = IrRule(
        "statement-arm2",
        IrAlternation(
            IrSequence(
                IrItem(IrRuleRef("identifier")),
                IrItem(IrRuleRef("ws"), IrQuantifier(0)),
                IrItem(IrLiteral("=")),
                IrItem(IrRuleRef("ws"), IrQuantifier(0)),
                IrItem(IrRuleRef("expression")),
                IrItem(IrLiteral(";")),
            )
        ),
    )


class StatementArm3(Statement):
    identifier: Annotated[Identifier, IrBind(0, "model")]
    ws: Annotated[Optional[Ws], IrBind(1, "model", False)] = None
    arglist: Annotated[Optional[Arglist], IrBind(3, "model")] = None
    __grammar__: ClassVar[IrRule] = IrRule(
        "statement-arm3",
        IrAlternation(
            IrSequence(
                IrItem(IrRuleRef("identifier")),
                IrItem(IrRuleRef("ws"), IrQuantifier(0)),
                IrItem(IrLiteral("(")),
                IrItem(IrRuleRef("arglist"), IrQuantifier(0)),
                IrItem(IrLiteral(");")),
            )
        ),
    )


class StatementArm4(Statement):
    ws: Annotated[Optional[Ws], IrBind(1, "model", False)] = None
    expression: Annotated[Expression, IrBind(2, "model")]
    __grammar__: ClassVar[IrRule] = IrRule(
        "statement-arm4",
        IrAlternation(
            IrSequence(
                IrItem(IrLiteral("return")),
                IrItem(IrRuleRef("ws"), IrQuantifier(0)),
                IrItem(IrRuleRef("expression")),
                IrItem(IrLiteral(";")),
            )
        ),
    )


class StatementArm5(Statement):
    condition: Annotated[Condition, IrBind(1, "model")]
    statement: Annotated[List[Statement], IrBind(3, "models")]
    __grammar__: ClassVar[IrRule] = IrRule(
        "statement-arm5",
        IrAlternation(
            IrSequence(
                IrItem(IrLiteral("while(")),
                IrItem(IrRuleRef("condition")),
                IrItem(IrLiteral("){")),
                IrItem(IrRuleRef("statement"), IrQuantifier(0, IrNone)),
                IrItem(IrLiteral("}")),
            )
        ),
    )


class StatementArm6(Statement):
    forinit: Annotated[Forinit, IrBind(1, "model")]
    ws: Annotated[Optional[Ws], IrBind(3, "model", False)] = None
    condition: Annotated[Condition, IrBind(4, "model")]
    ws2: Annotated[Optional[Ws], IrBind(6, "model", False)] = None
    forupdate: Annotated[Forupdate, IrBind(7, "model")]
    statement: Annotated[List[Statement], IrBind(9, "models")]
    __grammar__: ClassVar[IrRule] = IrRule(
        "statement-arm6",
        IrAlternation(
            IrSequence(
                IrItem(IrLiteral("for(")),
                IrItem(IrRuleRef("forinit")),
                IrItem(IrLiteral(";")),
                IrItem(IrRuleRef("ws"), IrQuantifier(0)),
                IrItem(IrRuleRef("condition")),
                IrItem(IrLiteral(";")),
                IrItem(IrRuleRef("ws"), IrQuantifier(0)),
                IrItem(IrRuleRef("forupdate")),
                IrItem(IrLiteral("){")),
                IrItem(IrRuleRef("statement"), IrQuantifier(0, IrNone)),
                IrItem(IrLiteral("}")),
            )
        ),
    )


class StatementArm7(Statement):
    condition: Annotated[Condition, IrBind(1, "model")]
    statement: Annotated[List[Statement], IrBind(3, "models")]
    statement_item: Annotated[Optional[StatementItem], IrBind(5, "model")] = None
    __grammar__: ClassVar[IrRule] = IrRule(
        "statement-arm7",
        IrAlternation(
            IrSequence(
                IrItem(IrLiteral("if(")),
                IrItem(IrRuleRef("condition")),
                IrItem(IrLiteral("){")),
                IrItem(IrRuleRef("statement"), IrQuantifier(0, IrNone)),
                IrItem(IrLiteral("}")),
                IrItem(IrRuleRef("statement-item"), IrQuantifier(0)),
            )
        ),
    )


class Ws(GrammarModel):
    value: Pattern2
    __grammar__: ClassVar[IrRule] = IrRule(
        "ws",
        IrAlternation(
            IrSequence(
                IrItem(
                    IrCharClass(IrRange(IrChr(9), IrChr(10)), IrChr(32)),
                    IrQuantifier(1, IrNone),
                )
            )
        ),
        False,
    )


class Expression(GrammarModel):
    term: Annotated[Term, IrBind(0, "model")]
    expression_item: Annotated[List[ExpressionItem], IrBind(1, "models")]
    __grammar__: ClassVar[IrRule] = IrRule(
        "expression",
        IrAlternation(
            IrSequence(
                IrItem(IrRuleRef("term")),
                IrItem(IrRuleRef("expression-item"), IrQuantifier(0, IrNone)),
            )
        ),
    )


class Arglist(GrammarModel):
    expression: Annotated[Expression, IrBind(0, "model")]
    arglist_item: Annotated[List[ArglistItem], IrBind(1, "models")]
    __grammar__: ClassVar[IrRule] = IrRule(
        "arglist",
        IrAlternation(
            IrSequence(
                IrItem(IrRuleRef("expression")),
                IrItem(IrRuleRef("arglist-item"), IrQuantifier(0, IrNone)),
            )
        ),
    )


class Condition(GrammarModel):
    expression: Annotated[Expression, IrBind(0, "model")]
    relationoperator: Annotated[Relationoperator, IrBind(1, "model")]
    expression2: Annotated[Expression, IrBind(2, "model")]
    __grammar__: ClassVar[IrRule] = IrRule(
        "condition",
        IrAlternation(
            IrSequence(
                IrItem(IrRuleRef("expression")),
                IrItem(IrRuleRef("relationoperator")),
                IrItem(IrRuleRef("expression")),
            )
        ),
    )


class Forinit(GrammarModel):
    __grammar__: ClassVar[IrRule] = IrRule(
        "forinit",
        IrAlternation(
            IrSequence(IrItem(IrRuleRef("forinit-arm1"))),
            IrSequence(IrItem(IrRuleRef("forinit-arm2"))),
        ),
    )


class ForinitArm1(Forinit):
    datatype: Annotated[Datatype, IrBind(0, "model")]
    identifier: Annotated[Identifier, IrBind(1, "model")]
    ws: Annotated[Optional[Ws], IrBind(2, "model", False)] = None
    ws2: Annotated[Optional[Ws], IrBind(4, "model", False)] = None
    expression: Annotated[Expression, IrBind(5, "model")]
    __grammar__: ClassVar[IrRule] = IrRule(
        "forinit-arm1",
        IrAlternation(
            IrSequence(
                IrItem(IrRuleRef("datatype")),
                IrItem(IrRuleRef("identifier")),
                IrItem(IrRuleRef("ws"), IrQuantifier(0)),
                IrItem(IrLiteral("=")),
                IrItem(IrRuleRef("ws"), IrQuantifier(0)),
                IrItem(IrRuleRef("expression")),
            )
        ),
    )


class ForinitArm2(Forinit):
    identifier: Annotated[Identifier, IrBind(0, "model")]
    ws: Annotated[Optional[Ws], IrBind(1, "model", False)] = None
    ws2: Annotated[Optional[Ws], IrBind(3, "model", False)] = None
    expression: Annotated[Expression, IrBind(4, "model")]
    __grammar__: ClassVar[IrRule] = IrRule(
        "forinit-arm2",
        IrAlternation(
            IrSequence(
                IrItem(IrRuleRef("identifier")),
                IrItem(IrRuleRef("ws"), IrQuantifier(0)),
                IrItem(IrLiteral("=")),
                IrItem(IrRuleRef("ws"), IrQuantifier(0)),
                IrItem(IrRuleRef("expression")),
            )
        ),
    )


class Forupdate(GrammarModel):
    identifier: Annotated[Identifier, IrBind(0, "model")]
    ws: Annotated[Optional[Ws], IrBind(1, "model", False)] = None
    ws2: Annotated[Optional[Ws], IrBind(3, "model", False)] = None
    expression: Annotated[Expression, IrBind(4, "model")]
    __grammar__: ClassVar[IrRule] = IrRule(
        "forupdate",
        IrAlternation(
            IrSequence(
                IrItem(IrRuleRef("identifier")),
                IrItem(IrRuleRef("ws"), IrQuantifier(0)),
                IrItem(IrLiteral("=")),
                IrItem(IrRuleRef("ws"), IrQuantifier(0)),
                IrItem(IrRuleRef("expression")),
            )
        ),
    )


class Singlelinecomment(Statement):
    value: str
    __grammar__: ClassVar[IrRule] = IrRule(
        "singlelinecomment",
        IrAlternation(
            IrSequence(
                IrItem(IrLiteral("//")),
                IrItem(
                    IrCharClass(
                        IrRange(IrChr(0), IrChr(9)), IrRange(IrChr(11), IrChr(1114111))
                    ),
                    IrQuantifier(0, IrNone),
                ),
                IrItem(IrLiteral("\n")),
            )
        ),
    )


class Multilinecomment(Statement):
    value: str
    __grammar__: ClassVar[IrRule] = IrRule(
        "multilinecomment",
        IrAlternation(
            IrSequence(
                IrItem(IrLiteral("/*")),
                IrItem(
                    IrAlternation(
                        IrSequence(
                            IrItem(
                                IrCharClass(
                                    IrRange(IrChr(0), IrChr(41)),
                                    IrRange(IrChr(43), IrChr(1114111)),
                                )
                            )
                        ),
                        IrSequence(
                            IrItem(IrLiteral("*")),
                            IrItem(
                                IrCharClass(
                                    IrRange(IrChr(0), IrChr(46)),
                                    IrRange(IrChr(48), IrChr(1114111)),
                                )
                            ),
                        ),
                    ),
                    IrQuantifier(0, IrNone),
                ),
                IrItem(IrLiteral("*/")),
            )
        ),
    )


class Term(GrammarModel):
    factor: Annotated[Factor, IrBind(0, "model")]
    term_item: Annotated[List[TermItem], IrBind(1, "models")]
    __grammar__: ClassVar[IrRule] = IrRule(
        "term",
        IrAlternation(
            IrSequence(
                IrItem(IrRuleRef("factor")),
                IrItem(IrRuleRef("term-item"), IrQuantifier(0, IrNone)),
            )
        ),
    )


class Relationoperator(GrammarModel):
    value: Pattern7
    __grammar__: ClassVar[IrRule] = IrRule(
        "relationoperator",
        IrAlternation(
            IrSequence(
                IrItem(
                    IrAlternation(
                        IrSequence(IrItem(IrLiteral("<="))),
                        IrSequence(IrItem(IrLiteral("<"))),
                        IrSequence(IrItem(IrLiteral("=="))),
                        IrSequence(IrItem(IrLiteral("!="))),
                        IrSequence(IrItem(IrLiteral(">="))),
                        IrSequence(IrItem(IrLiteral(">"))),
                    )
                )
            )
        ),
    )


class Number(Factor):
    value: Digit
    __grammar__: ClassVar[IrRule] = IrRule(
        "number",
        IrAlternation(
            IrSequence(
                IrItem(
                    IrCharClass(IrRange(IrChr(48), IrChr(57))), IrQuantifier(1, IrNone)
                )
            )
        ),
    )


class Unaryterm(Factor):
    factor: Annotated[Factor, IrBind(1, "model")]
    __grammar__: ClassVar[IrRule] = IrRule(
        "unaryterm",
        IrAlternation(IrSequence(IrItem(IrLiteral("-")), IrItem(IrRuleRef("factor")))),
    )


class Funccall(Factor):
    identifier: Annotated[Identifier, IrBind(0, "model")]
    arglist: Annotated[Optional[Arglist], IrBind(2, "model")] = None
    __grammar__: ClassVar[IrRule] = IrRule(
        "funccall",
        IrAlternation(
            IrSequence(
                IrItem(IrRuleRef("identifier")),
                IrItem(IrLiteral("(")),
                IrItem(IrRuleRef("arglist"), IrQuantifier(0)),
                IrItem(IrLiteral(")")),
            )
        ),
    )


class Parenexpression(Factor):
    ws: Annotated[Optional[Ws], IrBind(1, "model", False)] = None
    expression: Annotated[Expression, IrBind(2, "model")]
    ws2: Annotated[Optional[Ws], IrBind(3, "model", False)] = None
    __grammar__: ClassVar[IrRule] = IrRule(
        "parenexpression",
        IrAlternation(
            IrSequence(
                IrItem(IrLiteral("(")),
                IrItem(IrRuleRef("ws"), IrQuantifier(0)),
                IrItem(IrRuleRef("expression")),
                IrItem(IrRuleRef("ws"), IrQuantifier(0)),
                IrItem(IrLiteral(")")),
            )
        ),
    )


class StatementItem(GrammarModel):
    statement: Annotated[List[Statement], IrBind(1, "models")]
    __grammar__: ClassVar[IrRule] = IrRule(
        "statement-item",
        IrAlternation(
            IrSequence(
                IrItem(IrLiteral("else{")),
                IrItem(IrRuleRef("statement"), IrQuantifier(0, IrNone)),
                IrItem(IrLiteral("}")),
            )
        ),
    )


class ExpressionItem(GrammarModel):
    head: Annotated[Pattern8, IrBind(0, "text")]
    term: Annotated[Term, IrBind(1, "model")]
    __grammar__: ClassVar[IrRule] = IrRule(
        "expression-item",
        IrAlternation(
            IrSequence(
                IrItem(IrCharClass(IrChr(43), IrChr(45))), IrItem(IrRuleRef("term"))
            )
        ),
    )


class ArglistItem(GrammarModel):
    ws: Annotated[Optional[Ws], IrBind(1, "model", False)] = None
    expression: Annotated[Expression, IrBind(2, "model")]
    __grammar__: ClassVar[IrRule] = IrRule(
        "arglist-item",
        IrAlternation(
            IrSequence(
                IrItem(IrLiteral(",")),
                IrItem(IrRuleRef("ws"), IrQuantifier(0)),
                IrItem(IrRuleRef("expression")),
            )
        ),
    )


class TermItem(GrammarModel):
    head: Annotated[Pattern9, IrBind(0, "text")]
    factor: Annotated[Factor, IrBind(1, "model")]
    __grammar__: ClassVar[IrRule] = IrRule(
        "term-item",
        IrAlternation(
            IrSequence(
                IrItem(IrCharClass(IrChr(42), IrChr(47))), IrItem(IrRuleRef("factor"))
            )
        ),
    )


GRAMMAR: IrAst = IrAst(
    IrSeq(
        IrRule(
            "root",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("declaration"), IrQuantifier(0, IrNone)))
            ),
        ),
        IrRule(
            "declaration",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("datatype")),
                    IrItem(IrRuleRef("identifier")),
                    IrItem(IrLiteral("(")),
                    IrItem(IrRuleRef("parameter"), IrQuantifier(0)),
                    IrItem(IrLiteral("){")),
                    IrItem(IrRuleRef("statement"), IrQuantifier(0, IrNone)),
                    IrItem(IrLiteral("}")),
                )
            ),
        ),
        IrRule(
            "datatype",
            IrAlternation(
                IrSequence(IrItem(IrLiteral("int")), IrItem(IrRuleRef("ws"))),
                IrSequence(IrItem(IrLiteral("float")), IrItem(IrRuleRef("ws"))),
                IrSequence(IrItem(IrLiteral("char")), IrItem(IrRuleRef("ws"))),
            ),
        ),
        IrRule(
            "identifier",
            IrAlternation(
                IrSequence(
                    IrItem(
                        IrCharClass(
                            IrRange(IrChr(65), IrChr(90)),
                            IrChr(95),
                            IrRange(IrChr(97), IrChr(122)),
                        )
                    ),
                    IrItem(
                        IrCharClass(
                            IrRange(IrChr(48), IrChr(57)),
                            IrRange(IrChr(65), IrChr(90)),
                            IrChr(95),
                            IrRange(IrChr(97), IrChr(122)),
                        ),
                        IrQuantifier(0, IrNone),
                    ),
                )
            ),
        ),
        IrRule(
            "parameter",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("datatype")), IrItem(IrRuleRef("identifier"))
                )
            ),
        ),
        IrRule(
            "statement",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("datatype")),
                    IrItem(IrRuleRef("identifier")),
                    IrItem(IrRuleRef("ws")),
                    IrItem(IrLiteral("=")),
                    IrItem(IrRuleRef("ws")),
                    IrItem(IrRuleRef("expression")),
                    IrItem(IrLiteral(";")),
                ),
                IrSequence(
                    IrItem(IrRuleRef("identifier")),
                    IrItem(IrRuleRef("ws")),
                    IrItem(IrLiteral("=")),
                    IrItem(IrRuleRef("ws")),
                    IrItem(IrRuleRef("expression")),
                    IrItem(IrLiteral(";")),
                ),
                IrSequence(
                    IrItem(IrRuleRef("identifier")),
                    IrItem(IrRuleRef("ws")),
                    IrItem(IrLiteral("(")),
                    IrItem(IrRuleRef("arglist"), IrQuantifier(0)),
                    IrItem(IrLiteral(");")),
                ),
                IrSequence(
                    IrItem(IrLiteral("return")),
                    IrItem(IrRuleRef("ws")),
                    IrItem(IrRuleRef("expression")),
                    IrItem(IrLiteral(";")),
                ),
                IrSequence(
                    IrItem(IrLiteral("while(")),
                    IrItem(IrRuleRef("condition")),
                    IrItem(IrLiteral("){")),
                    IrItem(IrRuleRef("statement"), IrQuantifier(0, IrNone)),
                    IrItem(IrLiteral("}")),
                ),
                IrSequence(
                    IrItem(IrLiteral("for(")),
                    IrItem(IrRuleRef("forinit")),
                    IrItem(IrLiteral(";")),
                    IrItem(IrRuleRef("ws")),
                    IrItem(IrRuleRef("condition")),
                    IrItem(IrLiteral(";")),
                    IrItem(IrRuleRef("ws")),
                    IrItem(IrRuleRef("forupdate")),
                    IrItem(IrLiteral("){")),
                    IrItem(IrRuleRef("statement"), IrQuantifier(0, IrNone)),
                    IrItem(IrLiteral("}")),
                ),
                IrSequence(
                    IrItem(IrLiteral("if(")),
                    IrItem(IrRuleRef("condition")),
                    IrItem(IrLiteral("){")),
                    IrItem(IrRuleRef("statement"), IrQuantifier(0, IrNone)),
                    IrItem(IrLiteral("}")),
                    IrItem(
                        IrAlternation(
                            IrSequence(
                                IrItem(IrLiteral("else{")),
                                IrItem(IrRuleRef("statement"), IrQuantifier(0, IrNone)),
                                IrItem(IrLiteral("}")),
                            )
                        ),
                        IrQuantifier(0),
                    ),
                ),
                IrSequence(IrItem(IrRuleRef("singlelinecomment"))),
                IrSequence(IrItem(IrRuleRef("multilinecomment"))),
            ),
        ),
        IrRule(
            "ws",
            IrAlternation(
                IrSequence(
                    IrItem(
                        IrCharClass(IrRange(IrChr(9), IrChr(10)), IrChr(32)),
                        IrQuantifier(1, IrNone),
                    )
                )
            ),
            False,
        ),
        IrRule(
            "expression",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("term")),
                    IrItem(
                        IrAlternation(
                            IrSequence(
                                IrItem(IrCharClass(IrChr(43), IrChr(45))),
                                IrItem(IrRuleRef("term")),
                            )
                        ),
                        IrQuantifier(0, IrNone),
                    ),
                )
            ),
        ),
        IrRule(
            "arglist",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("expression")),
                    IrItem(
                        IrAlternation(
                            IrSequence(
                                IrItem(IrLiteral(",")),
                                IrItem(IrRuleRef("ws")),
                                IrItem(IrRuleRef("expression")),
                            )
                        ),
                        IrQuantifier(0, IrNone),
                    ),
                )
            ),
        ),
        IrRule(
            "condition",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("expression")),
                    IrItem(IrRuleRef("relationoperator")),
                    IrItem(IrRuleRef("expression")),
                )
            ),
        ),
        IrRule(
            "forinit",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("datatype")),
                    IrItem(IrRuleRef("identifier")),
                    IrItem(IrRuleRef("ws")),
                    IrItem(IrLiteral("=")),
                    IrItem(IrRuleRef("ws")),
                    IrItem(IrRuleRef("expression")),
                ),
                IrSequence(
                    IrItem(IrRuleRef("identifier")),
                    IrItem(IrRuleRef("ws")),
                    IrItem(IrLiteral("=")),
                    IrItem(IrRuleRef("ws")),
                    IrItem(IrRuleRef("expression")),
                ),
            ),
        ),
        IrRule(
            "forupdate",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("identifier")),
                    IrItem(IrRuleRef("ws")),
                    IrItem(IrLiteral("=")),
                    IrItem(IrRuleRef("ws")),
                    IrItem(IrRuleRef("expression")),
                )
            ),
        ),
        IrRule(
            "singlelinecomment",
            IrAlternation(
                IrSequence(
                    IrItem(IrLiteral("//")),
                    IrItem(
                        IrCharClass(
                            IrRange(IrChr(0), IrChr(9)),
                            IrRange(IrChr(11), IrChr(1114111)),
                        ),
                        IrQuantifier(0, IrNone),
                    ),
                    IrItem(IrLiteral("\n")),
                )
            ),
        ),
        IrRule(
            "multilinecomment",
            IrAlternation(
                IrSequence(
                    IrItem(IrLiteral("/*")),
                    IrItem(
                        IrAlternation(
                            IrSequence(
                                IrItem(
                                    IrCharClass(
                                        IrRange(IrChr(0), IrChr(41)),
                                        IrRange(IrChr(43), IrChr(1114111)),
                                    )
                                )
                            ),
                            IrSequence(
                                IrItem(IrLiteral("*")),
                                IrItem(
                                    IrCharClass(
                                        IrRange(IrChr(0), IrChr(46)),
                                        IrRange(IrChr(48), IrChr(1114111)),
                                    )
                                ),
                            ),
                        ),
                        IrQuantifier(0, IrNone),
                    ),
                    IrItem(IrLiteral("*/")),
                )
            ),
        ),
        IrRule(
            "term",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("factor")),
                    IrItem(
                        IrAlternation(
                            IrSequence(
                                IrItem(IrCharClass(IrChr(42), IrChr(47))),
                                IrItem(IrRuleRef("factor")),
                            )
                        ),
                        IrQuantifier(0, IrNone),
                    ),
                )
            ),
        ),
        IrRule(
            "relationoperator",
            IrAlternation(
                IrSequence(
                    IrItem(
                        IrAlternation(
                            IrSequence(IrItem(IrLiteral("<="))),
                            IrSequence(IrItem(IrLiteral("<"))),
                            IrSequence(IrItem(IrLiteral("=="))),
                            IrSequence(IrItem(IrLiteral("!="))),
                            IrSequence(IrItem(IrLiteral(">="))),
                            IrSequence(IrItem(IrLiteral(">"))),
                        )
                    )
                )
            ),
        ),
        IrRule(
            "factor",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("identifier"))),
                IrSequence(IrItem(IrRuleRef("number"))),
                IrSequence(IrItem(IrRuleRef("unaryterm"))),
                IrSequence(IrItem(IrRuleRef("funccall"))),
                IrSequence(IrItem(IrRuleRef("parenexpression"))),
            ),
        ),
        IrRule(
            "number",
            IrAlternation(
                IrSequence(
                    IrItem(
                        IrCharClass(IrRange(IrChr(48), IrChr(57))),
                        IrQuantifier(1, IrNone),
                    )
                )
            ),
        ),
        IrRule(
            "unaryterm",
            IrAlternation(
                IrSequence(IrItem(IrLiteral("-")), IrItem(IrRuleRef("factor")))
            ),
        ),
        IrRule(
            "funccall",
            IrAlternation(
                IrSequence(
                    IrItem(IrRuleRef("identifier")),
                    IrItem(IrLiteral("(")),
                    IrItem(IrRuleRef("arglist"), IrQuantifier(0)),
                    IrItem(IrLiteral(")")),
                )
            ),
        ),
        IrRule(
            "parenexpression",
            IrAlternation(
                IrSequence(
                    IrItem(IrLiteral("(")),
                    IrItem(IrRuleRef("ws")),
                    IrItem(IrRuleRef("expression")),
                    IrItem(IrRuleRef("ws")),
                    IrItem(IrLiteral(")")),
                )
            ),
        ),
    ),
    "root",
)

START: str = "root"
