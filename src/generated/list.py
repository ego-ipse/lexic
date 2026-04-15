# Generated from list.gbnf — DO NOT EDIT

from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Any, Optional, Union

class Root(BaseModel):
    items: list[str] = Field(default_factory=list)


Root.model_rebuild()
