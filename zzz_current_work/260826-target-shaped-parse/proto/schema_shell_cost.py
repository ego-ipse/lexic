"""Measure pre-submission certification of target-route interior proposals."""

from __future__ import annotations

import argparse
import gc
import statistics
import time
from collections.abc import Sequence
from pathlib import Path
from typing import NamedTuple

from anchored_tokenizer_regions import RegionBounds
from python_tree_cost import JsonValue, _load

from lexic.exceptions import UnsupportedConstructError


class Options(argparse.Namespace):
    """Validated round count."""

    rounds: int

    def validate(self) -> None:
        """Refuse a non-positive round count."""
        if self.rounds < 1:
            raise UnsupportedConstructError(
                "schema shell prototype: rounds must be positive"
            )


class Reading(NamedTuple):
    """One proposal and shell-certification reading."""

    process_seconds: float
    wall_seconds: float


class CertifiedShell(NamedTuple):
    """The validated small document and proposed source bounds."""

    text: str
    bounds: RegionBounds
    value: JsonValue


def _propose(text: str) -> RegionBounds | None:
    """Propose ordinary-spelling nested routes without trusting them."""
    vocab_marker = '"vocab": {'
    merges_marker = '"merges": ['
    vocab_member = text.find(vocab_marker)
    if vocab_member < 0:
        return None
    vocab_open = vocab_member + len(vocab_marker) - 1
    merges_member = text.find(merges_marker, vocab_open)
    if merges_member < 0:
        return None
    vocab_close = text.rfind("}", vocab_open, merges_member)
    merges_open = merges_member + len(merges_marker) - 1
    root_close = text.rfind("}")
    model_close = text.rfind("}", merges_open, root_close)
    merges_close = text.rfind("]", merges_open, model_close)
    if min(vocab_close, root_close, model_close, merges_close) < 0:
        return None
    return RegionBounds(vocab_open, vocab_close, merges_open, merges_close)


def _shell(text: str, bounds: RegionBounds) -> str:
    """Replace proposed interiors with their typed empty shell spellings."""
    return "".join(
        (
            text[: bounds.vocab_open],
            "{}",
            text[bounds.vocab_close + 1 : bounds.merges_open],
            "[]",
            text[bounds.merges_close + 1 :],
        )
    )


def _certify(text: str) -> CertifiedShell | None:
    """Accept only proposals occupying the declared nested schema routes."""
    bounds = _propose(text)
    if bounds is None:
        return None
    shell = _shell(text, bounds)
    try:
        value = _load(shell)
    except ValueError:
        return None
    if not isinstance(value, dict):
        return None
    model = value.get("model")
    if not isinstance(model, dict):
        return None
    if model.get("vocab") != {} or model.get("merges") != []:
        return None
    return CertifiedShell(shell, bounds, value)


def _adversarial() -> None:
    """Require false, reordered, and escaped proposals to decline."""
    nested_false = (
        '{"noise":{"vocab":{},"merges":[]},'
        '"model":{"vocab":{"a":0},"merges":[["a","b"]]}}'
    )
    reordered = '{"model":{"merges":[["a","b"]],"vocab":{"a":0}}}'
    escaped = '{"model":{"v\\u006fcab":{"a":0},"m\\u0065rges":[["a","b"]]}}'
    if _certify(nested_false) is not None:
        raise AssertionError("schema shell accepted nested false anchors")
    if _certify(reordered) is not None:
        raise AssertionError("schema shell accepted an unsupported order")
    if _certify(escaped) is not None:
        raise AssertionError("schema shell accepted absent ordinary anchors")


def _measure(text: str) -> tuple[Reading, CertifiedShell]:
    """Measure proposal, shell construction, parse, and route validation."""
    gc.disable()
    process_started = time.process_time()
    wall_started = time.perf_counter()
    try:
        certified = _certify(text)
    finally:
        process_elapsed = time.process_time() - process_started
        wall_elapsed = time.perf_counter() - wall_started
        gc.enable()
    if certified is None:
        raise UnsupportedConstructError(
            "schema shell prototype: Qwen route proposal did not certify"
        )
    return Reading(process_elapsed, wall_elapsed), certified


def _parse_options(arguments: Sequence[str] | None = None) -> Options:
    """Parse one isolated shell-certification run."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--rounds", type=int, default=9)
    options = Options()
    parser.parse_args(arguments, namespace=options)
    options.validate()
    return options


def main(arguments: Sequence[str] | None = None) -> None:
    """Measure the real shell and prove conservative adversarial decline."""
    options = _parse_options(arguments)
    source = (
        Path(__file__).resolve().parents[3]
        / "resources"
        / "tokenizers"
        / "qwen3.tokenizer.json"
    )
    text = source.read_text(encoding="utf-8")
    _adversarial()
    readings: list[Reading] = []
    expected: str | None = None
    for number in range(1, options.rounds + 1):
        reading, certified = _measure(text)
        if expected is None:
            expected = certified.text
        elif certified.text != expected:
            raise AssertionError("schema shell certification changed its text")
        readings.append(reading)
        print(
            "round",
            number,
            f"{reading.process_seconds:.6f}",
            f"{reading.wall_seconds:.6f}",
            len(certified.text),
            sep="\t",
        )
        del certified
        gc.collect()
    print(
        "median",
        f"{statistics.median(value.process_seconds for value in readings):.6f}",
        f"{statistics.median(value.wall_seconds for value in readings):.6f}",
        sep="\t",
    )


if __name__ == "__main__":
    main()
