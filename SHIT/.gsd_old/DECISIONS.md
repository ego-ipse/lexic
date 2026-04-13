# Decisions Register

<!-- Append-only. Never edit or remove existing rows.
     To reverse a decision, add a new row that supersedes it.
     Read this file at the start of any planning or research phase. -->

| # | When | Scope | Decision | Choice | Rationale | Revisable? | Made By |
|---|------|-------|----------|--------|-----------|------------|---------|
| D001 | M001 | arch | Parser implementation strategy | Lark Earley at runtime — no generated parser.py | Lark Earley handles left-recursion and ambiguity correctly for arbitrary GBNF. The generated recursive descent approach in FAILED_ATTEMPT/builder.py is proven broken. `_gbnf_to_earley_lark()` from with_guidance.py already works for json_ws. | No | collaborative |
| D002 | M001 | pattern | Model generation for alternation rules | Abstract base class + concrete subclasses (SOLID inheritance) | User explicitly required SOLID. For `X ::= A \| B \| C`, generates abstract `X(BaseModel)` + `AX(X)`, `BX(X)`, `CX(X)`. Union fields collapse type information and prevent isinstance checks. | No | human |
| D003 | M001 | arch | Constrained generation approach | Approach A — guidance.models.LlamaCpp + guidance.lark() | Approach A works. Approach B (raw LLMatcher LogitsProcessor) produces nonsense due to double-consuming tokens in the logits processor. LlamaGrammar (tst.py) is correct but slower. | Yes — if Approach A proves unreliable | collaborative |
| D004 | M001 | convention | Code output location | All new code to src/ | User requirement. The built/ pattern from the failed attempt added unnecessary indirection. | No | human |
| D005 | M001 | arch | GSD isolation mode | none (no worktrees, work directly on current branch) | User requirement: "Do NOT use worktrees." | No | human |
