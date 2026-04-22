"""Build a Lark Transformer from RuleSpec IR + Pydantic classes.

Public surface: build_transformer(specs, classes). Internals:
- context.py    BuildContext, FieldResult, SkipField, SKIP_FIELD, BuildResult
- registry.py   BUILDER_BY_ATOM dispatch table + builder_for()
- builders.py   FieldBuilder implementations per atom type
"""

from lexic.codegen.transformer.build_transformer import build_transformer

__all__ = ["build_transformer"]
