"""Unit tests for src/lexic/codegen/transformer/build_transformer.py"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path

from lark import Lark, Transformer

from lexic.codegen.ir_builder import IRBuilder
from lexic.codegen.lark_builder import LarkBuilder
from lexic.codegen.model_emitter import ModelEmitter
from lexic.codegen.transformer.build_transformer import build_transformer
from lexic.grammars.gbnf.parser import parse_gbnf


def _compile_grammar(gbnf_text: str, stem: str):
    rules = parse_gbnf(gbnf_text)
    specs = IRBuilder(rules).build()
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / f"{stem}.py"
        out.write_text(ModelEmitter(specs, f"<test:{stem}>").render())
        mod_name = f"_test_btr_{stem}"
        spec = importlib.util.spec_from_file_location(mod_name, out)
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = mod
        spec.loader.exec_module(mod)
        classes = {
            s.class_name: getattr(mod, s.class_name)
            for s in specs
            if hasattr(mod, s.class_name)
        }
    return specs, classes


def test_build_transformer_returns_transformer_instance():
    specs, classes = _compile_grammar("root ::= [a-z]+", "simple")
    transformer = build_transformer(specs, classes)
    assert isinstance(transformer, Transformer)


def test_build_transformer_produces_callable_transformer():
    gbnf = "root ::= digit+\ndigit ::= [0-9]"
    specs, classes = _compile_grammar(gbnf, "digits")
    builder = LarkBuilder(specs)
    grammar_str, start = builder.build_grammar()
    parser = Lark(grammar_str, parser="earley", ambiguity="resolve", start=start)
    transformer = build_transformer(specs, classes)
    tree = parser.parse("42")
    result = transformer.transform(tree)
    assert result is not None


def test_build_transformer_unknown_class_skipped():
    specs, classes = _compile_grammar("root ::= [a-z]+", "skip_test")
    empty_classes: dict[str, type] = {}
    transformer = build_transformer(specs, empty_classes)
    assert isinstance(transformer, Transformer)
