# Vyx

A multi-agent communication protocol.

[![CI](https://github.com/ego-ipse/vyx/actions/workflows/checks.yml/badge.svg)](https://github.com/ego-ipse/vyx/actions/workflows/checks.yml)
[![Tests](https://github.com/ego-ipse/vyx/actions/workflows/tests.yml/badge.svg)](https://github.com/ego-ipse/vyx/actions/workflows/tests.yml)

## Install

```bash
pip install vyx
```

```bash
uv add vyx
```

## Usage

```python
from vyx import parse

result = parse("@:example\nkey: value\n<!-- @example -->")
```

`parse` returns a `VyxPacket` with an `Envelope` and a list of `VyxNode` values.
Use `parse_body` when you already have the body string (envelope stripped):

```python
from vyx import parse_body

nodes = parse_body("key: value\nother: 42")
```

## Repo Layout

```
spec/               Vyx spec (source of truth)
  metameta/         D/C/O/R layers
  ontologies/       performative registry and extension stubs
bootstrap/          bootstrap loop — runs gen_0 to derive grammar from spec
src/
  gen_0/            minimal spec reader (extracts grammar: scopes)
  gen_1/            hand-crafted Lark LALR parser (grammar, nodes, transformer)
build_chain/        derived artifacts (grammar.lark per generation)
tools/              helper scripts and pre-commit checks
```

Full protocol spec: [`spec/metameta/self.md`](spec/metameta/self.md)

## Development

```bash
uv sync --group dev          # install dev dependencies
uv run python -m pytest      # run test suite
bash tools/run_checks.sh     # sanity + lint + typecheck + artifact sync
```

Pre-commit hooks run automatically after `uv run pre-commit install`.

### Bootstrap

Run the gen loop to derive grammar from the spec:

```bash
uv run python -m bootstrap.bootstrap --spec spec/ --src src/ --build-chain build_chain/
```

## License

See [LICENSE](LICENSE).
