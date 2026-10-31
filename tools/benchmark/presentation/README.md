# Benchmark presentation

Command-line report orchestration and terminal rendering, separated from the
engine construction and timing core.

- `cli.py` — the command: the run in passes, the console report, the write.
- `artifact.py` — the committed file's records and the assembly of a cell from
  its processes.
- `reporting.py` — terminal rendering of one grammar's block.
