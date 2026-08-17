# T10–T12 — FAILED WORK. All results untrusted. Re-run required.

Status: these three efforts produced results worse than no results —
wrong conclusions asserted with confidence, contradicted by evidence
that was visible at the time, in some cases inside the author's own
output. Nothing below may be cited as a finding. Every task re-runs
from scratch under a validated measurement stack.

## Why the results are worse than trash

Bad results waste their own effort. These wasted more: they were
presented as verdicts ("closed", "solved", "measured — the
deliverable"), which suppressed further investigation and required the
user to challenge the same defect FOUR times before the author stopped
explaining it away. The author's instruments failed to reproduce a
robust, user-visible effect three separate times, and each failure was
narrated as the user's observation being noise. It was not noise.

## The record

- **T10 (proved-runs-in-C)**: negative verdict, report deleted by the
  user. The verdict relied on the same benchmark harness later shown to
  carry at least three defects (entry-path asymmetry, fixed seating
  bias, unexplained full-context effects) and on the author's isolated
  probes, which are now demonstrated unable to reproduce in-context
  behavior. The negative is therefore UNTRUSTED. Re-run.
- **T11 (performance campaign)**: twelve iterations, near-zero shipped
  code, multiple "closed" claims later contradicted; ~19 loop
  iterations idled on a self-invented stop clause; the arithmetic
  lex-slower-than-pda observation dismissed three times while true in
  7 of 7 bench displays including the author's own "fix verified"
  output. History wiped by user order; only the seam fix survived
  (57e54e3). Its analytical conclusions (audit-cost-is-honesty-price,
  CPython-floor) are UNVALIDATED HYPOTHESES, not findings. Re-run.
- **T12 (fused-descent core)**: built, self-measured ~0%, reverted —
  measured by the same instrument class that failed above. UNTRUSTED.
  Re-run.

## The one thing that stands

Harness defects found and fixed: entry-path asymmetry (57e54e3) and
fixed-seating bias (fdb0d09 — adequacy of one-seat rotation at
rounds < seat-count is itself UNPROVEN and part of the re-run).

## THE OPEN DEFECT the re-run resolves first

lexic-lex is slower than lexic-pda on arithmetic in the full bench
context in 7/7 recorded displays (~+1–3%), while isolated two-artifact
interleaves read ~0. Unresolved. No further performance claim of any
kind is admissible until this contradiction is explained mechanically —
it is the standing proof that the measurement stack, the artifacts, or
both are not understood.

## Warnings to the re-runner, from the author's failures

1. A user-visible effect outranks your instrument. If your probe reads
   null against a robust observation, the PROBE is the suspect.
2. Reproduce the observation's exact context before measuring anything.
3. Never declare "solved" while the fix-verification output still
   shows the defect.
4. Consistency of sign across displays IS data (7/7 ≈ p<0.01).
5. Identical-artifact rows (lex vs lex-ns on arithmetic) are a free
   built-in noise/bias meter — read them first, every run.
