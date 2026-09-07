"""Frame-less execution for attempt-gated value-string references.

The compiler keeps attempt ownership explicit with ``OP_AVSTR`` and
``OP_AVDISP``.  These items cannot descend, so their quantified loop can run
here without paying the generic driver round trip for every character.  Only
the soft-continuation overlap population returns to ``Attempting`` for the
ordinary continuation classification and fork audit.
"""

from __future__ import annotations

from lexic.exceptions import LexicError
from lexic.parsing.pda.compiler.program.flatten import FlatArm
from lexic.parsing.pda.compiler.program.opcodes import OP_AVDISP, OP_AVSTR
from lexic.parsing.pda.core.errors import PdaFail
from lexic.parsing.pda.runtime.admission import KernelCaches, admits
from lexic.parsing.pda.runtime.build import Frame
from lexic.parsing.pda.runtime.matchers import vdisp_once, vstr_once

__all__ = ["AttemptInlineMixin"]


class AttemptInlineMixin[Carry]:
    """Attempt-aware inline loops inherited by the PDA kernel."""

    __slots__ = ()

    text: str
    pos: int
    _caches: KernelCaches

    def _sink_for(self, frame: Frame[Carry], arm: FlatArm, i: int) -> list[Carry]:
        """Provided by the kernel — item ``i``'s lazily allocated sink."""
        raise NotImplementedError

    def _attempt_choice(
        self,
        arm: FlatArm,
        i: int,
        pos: int,
        got: tuple[int, list[Carry]],
    ) -> bool:
        """Provided by ``Attempting`` — audit one tentative iteration."""
        raise NotImplementedError

    def attempt_inline_loop(
        self, frame: Frame[Carry], arm: FlatArm, i: int, pos: int
    ) -> int:
        """Run one attempt-aware value-string item's entire quantified loop."""
        target = arm.payloads[i]
        if (
            arm.kinds[i] == OP_AVSTR
            and target.chartable is not None
            and target.runarm is None
        ):
            return self._attempt_tabled_loop(frame, arm, i, pos)
        if arm.kinds[i] == OP_AVDISP:
            return self._attempt_vdisp_loop(frame, arm, i, pos)
        lo, hi = arm.los[i], arm.his[i]
        first = arm.gate_data[i][0]
        count = frame.count
        sink: list[Carry] | None = None
        frame.i = i
        while count < lo:
            end, values = self._inline_once(arm, i, pos)
            if sink is None:
                sink = self._sink_for(frame, arm, i)
            sink.extend(values)
            pos = end
            count += 1
        while hi < 0 or count < hi:
            char = self.text[pos : pos + 1]
            if not admits(char, *first):
                break
            got = self.attempt_inline(arm, i, pos)
            if got is None or got[0] == pos:
                break
            frame.count = count
            self.pos = pos
            if not self._attempt_choice(arm, i, pos, got):
                break
            if sink is None:
                sink = self._sink_for(frame, arm, i)
            sink.extend(got[1])
            pos = got[0]
            count += 1
        frame.count = 0
        self.pos = pos
        return pos

    def _attempt_vdisp_loop(
        self, frame: Frame[Carry], arm: FlatArm, i: int, pos: int
    ) -> int:
        """Attempt-aware loop over an inlinable dispatch chase."""
        sink = self._sink_for(frame, arm, i)
        lo, hi = arm.los[i], arm.his[i]
        first, soft = arm.gate_data[i]
        count = frame.count
        frame.i = i
        while count < lo:
            pos = vdisp_once(self.text, self._caches.intern, arm.payloads[i], sink, pos)
            count += 1
        while hi < 0 or count < hi:
            char = self.text[pos : pos + 1]
            if not admits(char, *first):
                break
            if not admits(char, *soft):
                try:
                    pos = vdisp_once(
                        self.text,
                        self._caches.intern,
                        arm.payloads[i],
                        sink,
                        pos,
                    )
                except PdaFail, LexicError:
                    break
                count += 1
                continue
            got = self.attempt_inline(arm, i, pos)
            if got is None or got[0] == pos:
                break
            frame.count = count
            self.pos = pos
            if not self._attempt_choice(arm, i, pos, got):
                break
            sink.extend(got[1])
            pos = got[0]
            count += 1
        frame.count = 0
        self.pos = pos
        return pos

    def _attempt_tabled_loop(
        self, frame: Frame[Carry], arm: FlatArm, i: int, pos: int
    ) -> int:
        """Attempt-aware loop over a one-character model table.

        Vyx's hot population is a table hit per character. The forced run
        avoids a scratch list and matcher call per character; only a soft
        overlap materialises a tentative pair for the ordinary fork audit.
        """
        get = arm.payloads[i].chartable.get
        sink = self._sink_for(frame, arm, i)
        append = sink.append
        bounds = arm.los[i], arm.his[i]
        gates = arm.gate_data[i]
        count = frame.count
        frame.i = i
        while count < bounds[0]:
            char = self.text[pos : pos + 1]
            model = get(char)
            if model is None:
                got = self._inline_once(arm, i, pos)
                sink.extend(got[1])
                pos = got[0]
            else:
                append(model)
                pos += 1
            count += 1
        while bounds[1] < 0 or count < bounds[1]:
            char = self.text[pos : pos + 1]
            if not admits(char, *gates[0]):
                break
            if not admits(char, *gates[1]):
                model = get(char)
                if model is None:
                    got = self.attempt_inline(arm, i, pos)
                    if got is None or got[0] == pos:
                        break
                    sink.extend(got[1])
                    pos = got[0]
                else:
                    append(model)
                    pos += 1
                count += 1
                continue
            got = self.attempt_inline(arm, i, pos)
            if got is None or got[0] == pos:
                break
            frame.count = count
            self.pos = pos
            if not self._attempt_choice(arm, i, pos, got):
                break
            sink.extend(got[1])
            pos = got[0]
            count += 1
        frame.count = 0
        self.pos = pos
        return pos

    def attempt_inline(
        self, arm: FlatArm, i: int, pos: int
    ) -> tuple[int, list[Carry]] | None:
        """Try one frame-less value-string iteration, fail-soft."""
        try:
            return self._inline_once(arm, i, pos)
        except PdaFail, LexicError:
            return None

    def _inline_once(self, arm: FlatArm, i: int, pos: int) -> tuple[int, list[Carry]]:
        """One attempt-aware match, raising on a mandatory mismatch."""
        holder: list[Carry] = []
        end = (
            vstr_once(
                self.text,
                self._caches.intern,
                arm.payloads[i],
                holder,
                pos,
            )
            if arm.kinds[i] == OP_AVSTR
            else vdisp_once(
                self.text,
                self._caches.intern,
                arm.payloads[i],
                holder,
                pos,
            )
        )
        return end, holder
