"""Unit tests for src/lexic/utils/names.py"""

import pytest

from lexic.utils.names import to_lark_name, to_pascal, to_snake


@pytest.mark.parametrize(
    "inp, expected",
    [
        ("root", "root"),
        ("json-ws", "json_ws"),
        ("JP-char", "jp_char"),
        ("arm1", "arm1"),
    ],
)
def test_to_lark_name(inp, expected):
    """to_lark_name converts hyphens and case correctly."""
    assert to_lark_name(inp) == expected


@pytest.mark.parametrize(
    "inp, expected",
    [
        ("root", "Root"),
        ("json-ws", "JsonWs"),
        ("jp-char", "JpChar"),
        ("arm_item_1", "ArmItem1"),
        ("", ""),
    ],
)
def test_to_pascal(inp, expected):
    """to_pascal converts snake/hyphen to PascalCase."""
    assert to_pascal(inp) == expected


@pytest.mark.parametrize(
    "inp, expected",
    [
        ("JsonWs", "json_ws"),
        ("JPChar", "jp_char"),
        ("Root", "root"),
        ("AB", "ab"),
    ],
)
def test_to_snake(inp, expected):
    """to_snake converts PascalCase to snake_case."""
    assert to_snake(inp) == expected
