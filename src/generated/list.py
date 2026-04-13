# Generated from list.gbnf — DO NOT EDIT

from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Any, Optional, Union
from src.base import GrammarNode

class Root(GrammarNode):
    items: list[str] = Field(default_factory=list)


Root.model_rebuild()
