# The build bake

Two modules composing one thing: the build state a clone carries, filled once
at bake and read by every completion afterwards.

**`lowering.py` — the per-shape build tail.** One callable composed once for a
clone's shape, so the runtime's completion does not re-decide per occurrence
what that shape builds. The memo tables it keeps are closed vocabularies keyed
by shape, not identity caches.

**`product.py` — the product-side fill.** A clone's capture layout and
construction plan from its rule's verified routine, so the flat runtime holds
the product's own statement of what the rule captures and completes with.

They sit together because a build read from a plan and the plan it was
composed from are one coupling, and the gate that checks they agree
(`tests/integration/lexic/invariants/test_build_matches_plan.py`) scans both
as writers of the same state.
