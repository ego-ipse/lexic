from pydantic import BaseModel
from builder import GBNFModelBuilder
from ogbnf import GBNFParser

SIMPLE = """
greeting ::= "hello" " " name
name ::= [a-zA-Z]+
"""

KV = """
kv-pair ::= key "=" val
key ::= [a-zA-Z]+
val ::= [0-9]+
"""


def test_models_are_basemodel_subclasses():
    rules = GBNFParser().parse(SIMPLE)
    models = GBNFModelBuilder(rules).build()
    for model in models.values():
        assert issubclass(model, BaseModel)


def test_no_sigil_attr():
    rules = GBNFParser().parse(SIMPLE)
    models = GBNFModelBuilder(rules).build()
    for model in models.values():
        assert not hasattr(model, "SIGIL")


def test_no_children_attr():
    rules = GBNFParser().parse(SIMPLE)
    models = GBNFModelBuilder(rules).build()
    for model in models.values():
        assert not hasattr(model, "_children")


def test_charclass_repetition_is_str_not_list():
    """[a-z]+ should produce a str field, not list[str]."""
    rules = GBNFParser().parse(KV)
    models = GBNFModelBuilder(rules).build()
    key_model = models["key"]
    fields = key_model.model_fields
    # key rule is [a-zA-Z]+ — should have one str field
    assert len(fields) == 1
    field = next(iter(fields.values()))
    assert field.annotation is str


def test_vyx_grammar_builds(vyx_rules):
    """Full Vyx grammar should produce BaseModel subclasses for all rules."""
    models = GBNFModelBuilder(vyx_rules).build()
    assert len(models) > 30
    for model in models.values():
        assert issubclass(model, BaseModel)
