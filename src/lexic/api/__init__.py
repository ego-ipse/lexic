"""Readers for third-party formats — applications of lexic, shipped with it.

Each module here turns some external artefact into a lexic object using the
ordinary pipeline: lexic parses the document, and the reader only names which
field means what. They are the answer to "how do I load *my* file", and they
carry no privileged formulation — the grammar and reducer that read a
document are always parameters.

What is NOT here: *getting* the artefact. Fetching lives in ``ext/API/``,
outside the shipped package, because a network client is not part of a
grammar engine.

Layering: these are runtime modules, so they reach the engine only through
the ``lexic.compile`` seam, never ``lexic.parsing`` directly.
"""

from __future__ import annotations

from lexic.api.json_tokenizer import PRETOKENS, read, read_from_path, tokenizer_of
from lexic.api.pretokens import (
    BYTE_FALLBACK,
    BYTE_LEVEL_REMAP,
    QWEN_PATTERN,
    IrByteLevel,
    IrDigits,
    IrQwenSplit,
    IrSplitMerged,
)

__all__ = [
    "BYTE_FALLBACK",
    "BYTE_LEVEL_REMAP",
    "IrByteLevel",
    "IrDigits",
    "IrQwenSplit",
    "IrSplitMerged",
    "QWEN_PATTERN",
    "PRETOKENS",
    "read",
    "read_from_path",
    "tokenizer_of",
]
