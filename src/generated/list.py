# Generated from list.gbnf by src/codegen.py — DO NOT EDIT

from __future__ import annotations
from typing import Any, Optional, Union
from pydantic import BaseModel, Field

class Root(BaseModel):
    items: list[str] = Field(default_factory=list)


Root.model_rebuild()
