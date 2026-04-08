from pathlib import Path
import pytest
from ogbnf import GBNFParser, GBNFNode

GRAMMAR_PATH = Path(__file__).parent.parent / "spec_built" / "grammar.gbnf"


@pytest.fixture(scope="session")
def vyx_grammar_text() -> str:
    return GRAMMAR_PATH.read_text()


@pytest.fixture(scope="session")
def vyx_rules(vyx_grammar_text: str) -> dict[str, GBNFNode]:
    return GBNFParser().parse(vyx_grammar_text)
