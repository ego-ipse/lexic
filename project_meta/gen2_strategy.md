## gen-2 — Replace Lark with Pydantic

```@:gen-2
full="gen-2 Pydantic Implementation Strategy"
header:
```
Replace the gen-1 Lark/dataclass implementation with a Pydantic-based
system where the GBNF grammar is the single source of truth. Gen-1 uses
Lark LALR parsing (`grammar.lark`) and a `VyxTransformer` that walks the
Lark tree to produce typed dataclass nodes (`nodes.py`). The replacement
keeps the same node semantics but derives node types, sigils, and the
parser dispatch table directly from the grammar at runtime.

Gen-1 files for reference only — do not modify:
```
src=gen_1/
files=|grammar.lark|nodes.py|parser.py|transform.py
parser: lark LALR start=packet
transformer: VyxTransformer maps lark.Tree → dataclass nodes
nodes: dataclasses not pydantic — no schema export
constraint: table transformer not fully implemented
```
<!-- @gen-2 -->

### Architecture

```@:gen-2.arch
full="Target Architecture"
header:
```
Four files. No nodes.py. Grammar drives everything.
```
src=gen_2/
grammar=grammar.gbnf
files=|gbnf.py|base.py|builder.py|parser.py

grammar.gbnf:
 role: single source of truth
 replaces: grammar.lark
 format: GBNF not Lark
 note: "same rules, different notation"

gbnf.py:
 role: pure Python IR + parser
 deps: none
 exports=|GBNFParser|GBNFNode subtypes|_unescape|first_terminal|dispatch_table
 note: "no pydantic — importable anywhere"

base.py:
 role: single parent class + Self sentinel
 deps: pydantic only
 exports=|VyxBase|Self
 note: "indexing machinery only — no Vyx field declarations"

builder.py:
 role: grammar → Pydantic models
 deps=|pydantic|gbnf.py|base.py
 exports=|GBNFModelBuilder
 mechanism: "create_model() per grammar rule. sigils from first_terminal(). no hardcoded maps."

parser.py:
 role: Vyx text → VyxBase node trees
 deps=|gbnf.py|builder.py|base.py
 exports=|VyxParser|parse|parse_body|ParseError
 mechanism: "dispatch table from dispatch_table('body-line'). no hardcoded sigil chars."
```
<!-- @gen-2.arch -->

### What replaces what

```@:gen-2.map
full="Gen-1 to Gen-2 Mapping"
header:
```
Direct replacements. Semantics preserved, mechanism changed.
```
$MAP [5]{gen1 gen2 note}:
grammar.lark grammar.gbnf "same rules GBNF notation"
nodes.py _ "eliminated — create_model() at runtime from grammar"
VyxTransformer VyxParser "grammar-driven dispatch not Lark callback"
dataclass VyxBase "pydantic frozen model — adds schema export"
Span _ "dropped for now — add back in P5 if needed"
```
<!-- @gen-2.map -->

### VyxBase indexing

```@:gen-2.indexing
full="VyxBase Indexing Design"
header:
```
Two namespaces per node. One class.
```
opener: "node's own pydantic fields"
 access=|dot|Self-sentinel
body: "ordered children appended by parser"
 access=|type+key|type+index|abs-index|sigil-prefix

access-forms:
 node.name                 "opener field — dot"
 node[Self,"name"]         "opener field — explicit"
 node[SomeModel,"key"]     "body child by type + key"
 node[SomeModel,0]         "body child by type + index"
 node[0]                   "body child absolute position"
 node["$C"]                "sigil-prefixed shorthand"

Self:
 role: sentinel class — never instantiated
 match: "t is Self — identity check not isinstance"

_children:
 type: PrivateAttr list
 mutable: 1
 note: "PrivateAttr mutable despite frozen=True"
 populated-by: _append_child called from parser

_sigil_registry:
 type: ClassVar dict
 key: first_terminal of rule
 value: model class
 populated-by: __init_subclass__ automatic
 source: grammar only — no hardcoded map
```
<!-- @gen-2.indexing -->

### Key derivations from grammar

```@:gen-2.derivations
full="What Gets Derived from Grammar"
header:
```
Nothing about Vyx structure is hardcoded in Python.
```
sigils:
 mechanism: first_terminal(rules, rules[rule_name])
 examples:
  nl-escape → "\\"
  nl-force  → "# "
  dict-def  → "D:"
  table-block → "$"
  seq-item  → "- "
  ref       → "^"
  spread    → "~"
 fallbacks: "scope-line and kv-line have no fixed first terminal"
  reason: "start with variable indent + alphanumeric"
  handling: "parser detects by structure not sigil"

dispatch-table:
 source: dispatch_table("body-line") in gbnf.py
 mechanism: "walk body-line alternation arms, call first_terminal per arm"
 output: dict mapping literal → rule name
 note: "sorted longest-first so '# ' matches before '#'"

models:
 mechanism: GBNFModelBuilder.build()
 one-model-per-rule: 1
 fields: derived from rule structure
  GBNFLiteral all-terminal → Literal[values]
  GBNFAlternation mixed → Union of types
  GBNFSequence → model with typed fields
  GBNFRepetition min=1 → list with Field(min_length=1)
  GBNFOptional → type | None
  GBNFReference → the model for that rule
  GBNFCharClass → str

first_terminal-alternation:
 rule: "if every arm of an alternation shares the same first terminal return it"
 example: "performative ::= '!' std-perf | '!' custom-perf → '!'"
```
<!-- @gen-2.derivations -->

### Bidirectional converter (gen-2 extension)

```@:gen-2.converter
full="Spec-Driven Bidirectional Converter"
header:
```
Given a GBNF grammar and a grammatically valid spec block, convert
data to and from Vyx without semantic understanding of what it means.
```
inputs=|grammar.gbnf|spec block in Vyx

spec-block:
 source: metameta.md D.1–D.17 sections
 format: markdown with Vyx fences @:D.N
 content: KV pairs + grammar: scope + errors: scope

pipeline:
 SpecExtractor: "markdown → (section_id, vyx_body_text) pairs"
 gen-2 parse_body: "vyx_body_text → VyxBase node trees"
 SpecCompiler: "VyxBase trees → DSection pydantic models"
 VyxEmitter: "pydantic model → Vyx text"

DSection:
 id: str
 full: str
 fields: dict
 grammar: GrammarBlock | None
 errors: dict[str, ErrorCode]

GrammarBlock:
 rules: dict[str, str]
 terminals: dict[str, str]
 deps: list[str]

VyxEmitter:
 driven-by: GrammarBlock from spec
 quoting: "derived from unquoted rule char range — not hardcoded"
 guarantee: "parse(emit(model)) == model — structural identity"

round-trip:
 forward: "Vyx text → parse_body() → VyxBase → validated model"
 backward: "model → VyxEmitter.emit() → Vyx text"
 correctness: "DSectionRegistry.merged_grammar() must agree with grammar.gbnf"
```
<!-- @gen-2.converter -->

### Implementation phases

```@:gen-2.phases
full="Implementation Order"
header:
```
```
$PH [7]{phase file what test}:
P0 gbnf.py "GBNFParser + _unescape + first_terminal + dispatch_table" "63 rules. body-line 8 arms. _unescape round-trips all literals."
P1 base.py "VyxBase + Self + PrivateAttr _children + __getitem__ dispatch" "All 4 access forms. Self sentinel by identity. sigil shorthand."
P2 builder.py "GBNFModelBuilder.build() + first_terminal sigil derivation" "Every model has SIGIL == first_terminal. dispatch_table returns 5 entries."
P3 parser.py "VyxParser + grammar-driven dispatch + parse + parse_body" "parse() round-trips D.13 packet. parse_body() handles all body-line types."
P4 spec/extractor.py "SpecExtractor — markdown → (id, body_text)" "Extract D.1–D.17. None empty. D.3 body contains grammar: scope."
P5 spec/compiler.py "SpecCompiler — VyxBase trees → DSection" "D.3 grammar.rules[kv_pair] correct. deps list correct. errors compiled."
P6 emitter.py "VyxEmitter — model → Vyx text" "parse(emit(parse(text))) == parse(text) for all D sections."
```
<!-- @gen-2.phases -->

### Invariants

```@:gen-2.invariants
full="Non-Negotiable Invariants"
header:
```
```
inv:
 1: "grammar.gbnf is the only place Vyx structure is defined"
 2: "no nodes.py — create_model() at runtime from grammar rules"
 3: "no _SIGIL_MAP or equivalent — sigils from first_terminal() only"
 4: "parser dispatch table from dispatch_table('body-line') only"
 5: "VyxBase carries indexing machinery only — no field declarations"
 6: "spec/models.py field names are justified — they name semantic concepts from the spec, not grammar structure"
 7: "VyxEmitter quoting from unquoted rule char range — not hardcoded"
 8: "parse(emit(model)) == model — structural not string identity"
```
<!-- @gen-2.invariants -->
