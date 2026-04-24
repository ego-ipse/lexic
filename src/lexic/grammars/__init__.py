"""Grammar-flavour layer — public endpoint.

Re-exports the registry API and eagerly registers the built-in GBNF adapter
so callers get a fully populated ADAPTERS dict on first import.
"""

from __future__ import annotations

from lexic.grammars.flavours import (
    ADAPTERS,
    FlavourAdapter,
    FlavourEmitter,
    FlavourParser,
    adapter_for_extension,
    get_adapter,
    register_adapter,
)
from lexic.grammars.gbnf.adapter import GbnfAdapter

register_adapter(GbnfAdapter())

__all__ = [
    "ADAPTERS",
    "FlavourAdapter",
    "FlavourEmitter",
    "FlavourParser",
    "adapter_for_extension",
    "get_adapter",
    "register_adapter",
]
