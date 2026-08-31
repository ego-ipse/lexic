# Target-shaped parsing

## One-line summary

Compile grammar semantics and the requested codomain into one parser product that builds the final value directly, without constructing and folding unwanted intermediate models.

## Ten-line summary

- Grammar remains the ground truth; a target changes representation, never language.
- One typed `reduce` surface can return IR, Python values, extents, tokenizers, or custom values.
- Semantic signatures describe lower meaning; schemas refine it for stricter targets.
- A flat product program carries construction, demand, validation, and finalization.
- PDA and Earley execute the same product operations while retaining their recognition strengths.
- Recognition uses the armed grammar; generated binding uses the relaxed grammar.
- Ambiguity compares complete requested-root meanings across choices, cycles, and islands.
- Direct construction retains only demanded data and validates in deterministic semantic order.
- Parallel parsing produces target fragments through grammar-derived splits and the same algebra.
- The finished tree removes fold, variant, templating, and model-shaped stitching duplication.

## Full summary

### The change

- The current path builds a model, folds it into IR, then often converts it again; the new path compiles the requested result into the parse.
- Text is recognized once and retained data is constructed once.
- Grammar remains the sole definition of accepted text.
- Reducer semantics define meaning independently of its final representation.
- Targets are generic codomains, not grammar-specific parser forks.

### Interface, signatures, and schemas

- `reduce` remains the single typed entry point.
- Its default result is the reducer's ordinary IR meaning.
- `into=` selects another declared codomain without introducing another parse API.
- `resolve=` and `cores=` preserve one ambiguity and sequential/parallel contract.
- A reducer-free selection still uses this surface rather than a second templating API.
- A semantic signature describes the lower meaning exposed by a reducer.
- A target schema refines that signature with demanded paths and stronger constraints.
- Tokenizer structure therefore layers over JSON meaning instead of replacing it.
- Schema compilation proves compatibility before parsing begins.
- Unsupported compositions refuse explicitly and early.

### Compiled execution

- Compilation lowers the grammar, reduction, and target to flat integer tables.
- Tables identify operations, slots, constants, routes, and completion ranges.
- Validation and root finalization are part of the product, not a later traversal.
- Bound programs and caches are owned by the compiled grammar artefact.
- Mutable state belongs to one parse occurrence.
- Transaction marks isolate failed arms, probes, islands, and fragments.
- Rollback work is proportional to mutation, not document size.
- PDA and Earley execute the same product vocabulary.
- Recognition uses the armed grammar before non-semantic relaxation.
- Generated class binding uses the relaxed grammar for constructor ergonomics.
- This removes the current relax-then-lift recognition route.
- Unused product state, target callbacks, and reflection stay out of paid loops.

### Ambiguity

- Ambiguity is defined over complete requested-root meanings.
- Different local trees are harmless when their requested root values are equal.
- Ordinary split allocation retains its defined leftmost answer.
- Nullable quantifiers preserve differing semantic occurrence counts.
- Interacting and shared-occurrence choices are evaluated together, never one flip at a time.
- Leo links are expanded as part of ambiguity readout.
- Finite zero-width cycles reach an exact structural fixpoint.
- Infinite growing cycles can produce an occurrence-addressed second derivation.

### PDA islands

- Islands remain local Earley recognition regions inside a predictive PDA parse.
- Their meanings compose through cached continuations to the requested root.
- A local alternative is discarded only when that continuation proves root equivalence.
- Non-injective continuations execute against the actual competing meanings.
- Interacting island and outer choices remain part of one exact ambiguity question.
- Both engines construct complete-document pairs only when a resolver requires them.

### Direct codomains and tokenizer

- Generated models use the common product ABI without acquiring unused target work.
- Default reduction builds its IR meaning directly rather than model-plus-fold.
- Python reduction constructs native scalars, lists, and dictionaries.
- Selection constructs only occurrences demanded by compiled routes.
- Extent products return bounds certified by the parser.
- Custom codomains use declared carriers and operations without reflection.
- The tokenizer schema consumes the lower JSON signature.
- Vocabulary, inverse vocabulary, merge ranks, and pipeline data become final indexes.
- Missing fields, duplicate ids, invalid merges, and pipeline errors have fixed ordering.
- Every relevant format field is consumed or refused explicitly.
- No generated JSON model, complete `IrMap`, or duplicate tokenizer is constructed.

### Parallel products and performance

- Parallelization begins from grammar-derived split shapes.
- Target demand can derive route anchors and certified regular regions.
- Workers own their parse state and returned fragments.
- Fragments join through the same product algebra used sequentially.
- Root validation and finalization occur once after joining.
- Sequential and parallel values, refusals, and ambiguity decisions are identical.
- The measured 2 KiB-per-worker floor remains unchanged.
- Every engaged split shape must yield a material win.
- Base generated-model parsing must remain equally fast or improve.
- Token parsing must remain equally fast or improve.
- A downstream reduction or tokenizer gain cannot offset either regression.
- Even a correctness-driven regression requires explicit approval after measurement.
- Qwen recursive Python pursues less than 0.100 seconds wall.
- Qwen resident-text tokenizer must complete below 1.000 second wall.
- The like-for-like tokenizer route continues toward roughly 105×.
- The 105× objective is target-specific rather than universal to every reduction.
- Measurements separate wall, CPU, resident, cold, and warm paths; instrumentation stays external.

### Final source shape

- Semantic declarations, product compilation, and engine execution have one owner each.
- Parser code contains generic target machinery and no JSON or tokenizer special cases.
- `ReduceFold` and reducer-derived parsing variants are removed.
- Old templating execution is replaced by product demand and selection.
- Model-shaped parallel stitching is replaced by target-fragment joins.
- Compatibility aliases and fallback implementations are not retained pre-alpha.
- README, wiki, examples, and package documentation describe the one resulting path.
