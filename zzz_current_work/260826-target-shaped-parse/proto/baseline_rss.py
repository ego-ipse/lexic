"""Measure the unchanged tokenizer reader's baseline peak RSS by scenario."""

from __future__ import annotations

import argparse
import gc
import hashlib
import resource
import time
from collections.abc import Sequence
from pathlib import Path

from lexic.api.json_tokenizer import read, read_from_path
from lexic.exceptions import UnsupportedConstructError
from lexic.grammars.json import JSON_GRAMMAR, JSON_REDUCER
from lexic.ir import IrTokenizer


class Options(argparse.Namespace):
    """Validated baseline scenario."""

    mode: str

    def validate(self) -> None:
        """Refuse scenarios outside the pinned matrix."""
        if self.mode not in ("resident", "path-cold", "path-warm"):
            raise UnsupportedConstructError(
                f"baseline RSS prototype: unsupported mode {self.mode!r}"
            )


def _options(arguments: Sequence[str] | None = None) -> Options:
    """Parse one isolated scenario."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", required=True)
    options = Options()
    parser.parse_args(arguments, namespace=options)
    options.validate()
    return options


def _source() -> Path:
    """Return the fetched Qwen witness path."""
    return (
        Path(__file__).resolve().parents[3]
        / "resources"
        / "tokenizers"
        / "qwen3.tokenizer.json"
    )


def _rss_kib() -> int:
    """Return this process's high-water RSS in KiB on Linux."""
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss


def _digest(tokenizer: IrTokenizer) -> str:
    """Hash the final tokenizer tables without rendering a second document."""
    digest = hashlib.blake2b()
    for spelling, ordinal in tokenizer.encode.items():
        encoded = str(spelling).encode()
        digest.update(len(encoded).to_bytes(8, "little"))
        digest.update(encoded)
        digest.update(int(ordinal).to_bytes(8, "little", signed=True))
    for dyad, rank in tokenizer.ranks.items():
        for spelling in dyad:
            encoded = str(spelling).encode()
            digest.update(len(encoded).to_bytes(8, "little"))
            digest.update(encoded)
        digest.update(int(rank).to_bytes(8, "little", signed=True))
    return digest.hexdigest()


def _resident(source: Path) -> IrTokenizer:
    """Run the reader with source text already resident."""
    text = source.read_text(encoding="utf-8")
    gc.collect()
    print("resident_chars", len(text), sep="\t")
    print("rss_before_product_kib", _rss_kib(), sep="\t")
    return read(text, JSON_GRAMMAR, JSON_REDUCER, name="qwen3")


def _path(source: Path) -> IrTokenizer:
    """Run the public path-taking reader."""
    print("rss_before_product_kib", _rss_kib(), sep="\t")
    return read_from_path(source, JSON_GRAMMAR, JSON_REDUCER, name="qwen3")


def main(arguments: Sequence[str] | None = None) -> None:
    """Print one isolated baseline row with an exact final-table digest."""
    options = _options(arguments)
    source = _source()
    if options.mode == "path-warm":
        warmup = _path(source)
        warmup_digest = _digest(warmup)
        del warmup
        gc.collect()
        print("rss_after_warmup_kib", _rss_kib(), sep="\t")
    else:
        warmup_digest = ""
    process_started = time.process_time()
    wall_started = time.perf_counter()
    if options.mode == "resident":
        tokenizer = _resident(source)
    else:
        tokenizer = _path(source)
    process_seconds = time.process_time() - process_started
    wall_seconds = time.perf_counter() - wall_started
    observed_digest = _digest(tokenizer)
    if warmup_digest and observed_digest != warmup_digest:
        raise AssertionError("baseline RSS prototype: warm result changed")
    print("mode", options.mode, sep="\t")
    print("process_seconds", f"{process_seconds:.6f}", sep="\t")
    print("wall_seconds", f"{wall_seconds:.6f}", sep="\t")
    print("peak_rss_kib", _rss_kib(), sep="\t")
    print("vocab", len(tokenizer.encode), sep="\t")
    print("merges", len(tokenizer.ranks), sep="\t")
    print("result_digest", observed_digest, sep="\t")


if __name__ == "__main__":
    main()
