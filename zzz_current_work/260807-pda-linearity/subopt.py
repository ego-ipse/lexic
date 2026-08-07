"""Full two-part prototype: compile-side sub-clone optimization + the _enter fix."""
import time
from collections import Counter
from pathlib import Path
import lexic.parsing.pda.compiler.flatten as F
import lexic.parsing.pda.compiler.lower as L
from lexic.parsing.pda.core.errors import PdaFail
from lexic.parsing.pda.core.scanner import scan_gate_take
from lexic.parsing.pda.runtime.admission import sole_admitted
from lexic.parsing.pda.runtime.kernel.kernel import PdaKernel

# ── part 1: compile — optimize the attempt sub-clones where they are born ──
def widened(arm):
    if arm.n == 1 and arm.los[0] == 1 and arm.his[0] == 1 and arm.kinds[0] in (F.OP_REF, F.OP_REF1):
        return arm.payloads[0]
    return None

STATS = Counter()
_orig_entries = L._attempt_entries
def patched_entries(clone, is_reduce):
    entries = _orig_entries(clone, is_reduce)
    if is_reduce:
        # R1: the reduce path is EXCLUDED by licence, not by luck. A dispatch
        # chase is frame-less, so it skips the completion callback a reduce
        # clone needs to eval its reduction body — silent wrong values. Today
        # `reduce_rewrite` bakes every reachable clone to BUILD_REDUCE, so
        # `_convert_dispatch`'s `mode != BUILD_ALT` test happens to refuse them;
        # that is a mode-value coincidence, and `reduce_rewrite` says the model
        # specialisations are "deliberately skipped" here. Say so, once.
        return entries
    saved, F._unit_ref_target = F._unit_ref_target, widened
    try:
        for entry in entries:
            sub = entry[-1]
            was = sub.mode
            F._convert_dispatch(sub)
            STATS["subs"] += 1
            STATS["converted"] += sub.mode != was
    finally:
        F._unit_ref_target = saved
    return entries

# ── part 2: runtime — re-check the specialisations after a substitution ──
def patched_enter(self, clone, out):
    """``_enter`` with its head as a LOOP: chase, substitute, re-check."""
    char = self.text[self.pos : self.pos + 1]
    while True:
        if clone.mode == F.BUILD_DISPATCH:
            chased = self._chase_dispatch(clone, char)
            if chased is None:
                return False
            clone = chased
            continue
        if clone.attempt is not None:
            sole = sole_admitted(clone.attempt[1], self.text, self.pos)
            if sole is None:
                self.attempt(clone, out)
                return False
            clone = sole
            continue
        break
    if clone.kwin_selectors is not None or clone.pn_selectors is not None:
        gated = F.select_gated(self.text, self.pos, clone)
        self.stack.append([gated, 0, 0, out, clone.mode, clone, self.pos, [0] * gated.n, None])
        return True
    gate = clone.struct_arm
    if gate is not None and not scan_gate_take(self.text, self.pos, gate):
        arm = clone.default
        if arm is None:
            raise PdaFail(f"no arm at {self.pos}", self.pos)
        self.stack.append([arm, 0, 0, out, clone.mode, clone, self.pos, [0] * arm.n, None])
        return True
    if clone.leaf:
        self.pos = self._run_leaf(clone, out, self.pos)
        return False
    arm = None
    for chars, negated, candidate in clone.selectors:
        if (char != "" and char not in chars) if negated else char in chars:
            arm = candidate
            break
    if arm is None:
        arm = clone.default
        if arm is None:
            raise PdaFail(f"no arm at {self.pos}", self.pos)
    self.stack.append([arm, 0, 0, out, clone.mode, clone, self.pos, [0] * arm.n, None])
    return True


# installed as a pytest plugin: the two-part change, live for the whole suite
L._attempt_entries = patched_entries
PdaKernel._enter = patched_enter
