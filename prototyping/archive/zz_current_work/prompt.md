# AGENTS SHOULD NOT READ THIS FILE.

They should aim to keep the IrSelf derived objects. No free methods. Use eval and dunders preferably. Prefer IrSelf objects. Prefer making the class itself an IrMultiMap if mutability improves performance instead of making a dict attr.If any of these rules is broken, it should be clearly justified.



Neither. And I agree with some of your reservations. I want to do a new round of exploratory work. Send out four parallel sonnet agents. These have a special exemption to use git worktrees.

1- One to review if we should implement F1, F2, both or neither or some third option (full Marpa?).
2- A second one to review the remaining optimizations proposed across the documents.
3 and 4 - Let the third and fourth one investigate new optimizations strategies.
Subagent 4 should be a radical one, not afraid to do anything while keeping the IrSelf derived objects,
but should not be afraid to delete or create new ones. Carte blanche.

The regular agent rules are thoroughly waved for the exploratory work but should be kept in mind:
"Agents should aim to keep the IrSelf derived objects. No free methods. Use eval and dunders preferably. Prefer IrSelf objects. Prefer making the class itself an IrMultiMap if mutability improves performance instead of making a dict attr.If any of these rules is broken, it should be clearly justified."

Agents shouldn't bother writing docstrings on code that will not be merged.

All agents MUST produce an md file with the results. Results should be backed by data.
Results should be placed in zz_current_work/ (new folder)

After all agents have finished, review the results and create a new HANDOVER document in the same folder.

Commited the postmortem. Send now three sonnet agents. Special exemption to use git worktrees.

Before sending out the agents, run the benchmarks before and after the commit.
Return to the present commit before creating the agents and worktrees.

1- The first should drop the leoparse commit and re-measure a better implementation.
2- The second should seek to improve the current implementation.
3- The third should go more radical.

One transversal question: Why is parsing super-linear?
One transversal goal: Make our implementation faster than Lark.

All of them should produce an md file with the results. Results should be backed by data.
Results should be placed in zzz_current_work/postleo/ (new folder)
The agents should not bother writing docstrings on code that will not be merged.

The regular agent rules are thoroughly waved for the exploratory work but should be kept in mind:
"Agents should aim to keep the IrSelf derived objects. No free methods. Use eval and dunders preferably. Prefer IrSelf objects. Prefer making the class itself an IrMultiMap if mutability improves performance instead of making a dict attr.If any of these rules is broken, it should be clearly justified."

After all agents have finished, review the results and create a new HANDOVER document in the same folder.