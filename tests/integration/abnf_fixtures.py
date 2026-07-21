"""Shared ABNF source fixtures for the integration suite."""

from __future__ import annotations

NON_SEMANTIC_DIRECTIVE_ABNF = (
    "; @non-semantic WSP\n"
    "root = num WSP\n"
    "num  = 1*DIGIT\n"
    "DIGIT = %x30-39\n"
    "WSP  = %x20 / %x09\n"
)
