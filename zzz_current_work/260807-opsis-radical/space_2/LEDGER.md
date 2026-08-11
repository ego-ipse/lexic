# space_2 — what is built, and what is not

Kept here rather than in the README: the README says what space_2 IS, this
says how far along it is. Nothing below is rounded up.

## Built and driven

| | |
|---|---|
| the frame protocol | `box · line · curve · bez · arc · text` + `hit`, and the tone register |
| the tone register | on the server: fills, edges, faces, glyph widths — the leaf holds no style |
| surfaces as nodes | `opsis/surfaces/` — one class each, an open table, no branch on which |
| the arrangement | `space.arrange` measured AND applied server-side (`opsis/frame/panels.py`) |
| rooms | panel, header, tab strip, dock chips, per-room scroll |
| tabs | reader · relations · railroad · machine share the reader's column |
| the derivation | band + model/pda/earley clocks + lanes under a scrubbing cursor |
| the spine | the open stack at the cursor, indented by depth |
| the ring graph | three-space rings with the camera ON THE SERVER, size fixed by the cloud's radius |
| pop-out / clone | `⧉ ⊞` open `/?only=<room>`; a popped window is one room, same session |
| responsiveness | 3–5 ms a gesture (was 230); the reader compiles once per spelling, each engine runs once per reading |
| the leaf | 172 lines: paint marks, post gestures, coalesce what arrives mid-flight |

## Not built yet

- **editing** — space_1 could type into the document, `Ctrl+Enter` to re-read,
  `Ctrl+S` to save. space_2 cannot. This is the biggest gap and the next thing.
- **forms** — source · canonical · codegen · lifted as a property of the
  reader. `kairos/pipeline.py` is here and unused.
- **strata** — `praxis/strata.py` is here and unused; no rung, no travel.
- **places** — `opsis/rooms.py` (the rules/machine/artefacts/IR-value browser)
  is here and unused.
- **pins**, **selection**, **drag-to-resize seams** (`arrange` already takes
  `dragged`; nothing sends it).
- **the gate** — space_1's `gate.py` (44 facts) has no counterpart here.

## Known, and not silently

- **The railroad's geometry is space_1's, byte for byte** (`opsis/paint.py`
  and `opsis/measure.py` are unchanged copies). space_2 renders its curves
  properly now, where space_1's leaf drew some of them straight — but if the
  shape itself is still wrong, it is wrong in both, and fixing it is a change
  to the measurement, not to the frame.
- The first `earley` clock costs ~1.5 s (the engine runs over the whole
  document). It is kept after that; every later frame is ~25 ms.
