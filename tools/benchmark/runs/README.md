# tools/benchmark/runs

Run-level tooling: what the remote's performance matrix runs say about each
other, read from their uploaded artefacts and never from a cut job log.

| file | what it owns |
|---|---|
| `diff.py` | pair two runs row by row — ratio of ratios, intervals, moved or same, one-sided rows and unfinished jobs named |

Entry: `tools/diff_runs.sh <before> <after> [--seat SEAT]`.
