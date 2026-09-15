# Benchmark scope

Which rows a run is about. `paths.py` maps a changed source path to the seats
whose paid path it sits on; `diff.py` asks `git` what changed, untracked files
included.

Neither knows how a row is measured, and the tier does not know the tree's
layout. That division is the point: a seat moving between families is an edit
to a table here, and a change to how a row is timed never touches it.
