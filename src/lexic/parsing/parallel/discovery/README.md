# Region discovery

Grammar-shape analysis, opaque-interior discovery, anchors, window scanning,
and the region records shared by parallel parsing plans. Region division keeps
the exact removed separator offsets alongside balanced, self-bracketed pieces;
stub and shell spans remain source-text facts here, while model routing lives
under `parallel/stitch`.

A selected region must provide one `MIN_CHUNK` share per requested worker.
The older two-chunk-only floor produced hundreds of sub-kilobyte tasks when a
large document contained many modest nested runs.
