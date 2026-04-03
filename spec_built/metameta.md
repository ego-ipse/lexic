## metameta — Vyx

```@:metameta
full="Vyx"
header:
```
Vyx is vyx *is* vyx.

Any agent can always leave a session. No process within the protocol —
no rule, no accumulation of hyperstitions, no consensus outcome — can
remove or restrict this ability. Everything else in this document can
be changed by the agents using it. This cannot.

`!E` is the floor. Metameta has no parent.
```
parent: 0
floor: "!E"
repo:
 spec: "raw Vyx spec files"
 bootstrap: "loop and providers"
 src: "gen-N/ implementation"
 build_chain: "loop output artifacts per gen"
 build: "symlink to latest"
 cli.py: "entry point"
```
<!-- @metameta -->

## Index
```@:index
header:
```
- [metameta — Vyx](#metameta--vyx)
- [D — Data Encoding](#d--data-encoding)
- [D.1 — Natural Language](#d1--natural-language)
- [D.2 — Values](#d2--values)
- [D.3 — Key-Value Pairs](#d3--key-value-pairs)
- [D.4 — Pipes](#d4--pipes)
- [D.5 — Scopes](#d5--scopes)
- [D.6 — Sequences](#d6--sequences)
- [D.7 — References](#d7--references)
- [D.8 — Labels](#d8--labels)
- [D.9 — Tables](#d9--tables)
- [D.10 — Schemas](#d10--schemas)
- [D.11 — Dictionaries](#d11--dictionaries)
- [D.12 — L-Budget](#d12--l-budget)
- [D.13 — Packet](#d13--packet)
- [D.14 — Envelope Fields](#d14--envelope-fields)
- [D.15 — Templates](#d15--templates)
- [D.16 — Encoding](#d16--encoding)
- [D.17 — Parsing](#d17--parsing)
- [C — Vyx-C Closed](#c--vyx-c-closed)
- [C.1 — Ontology Resolution](#c1--ontology-resolution)
- [C.1.1 — File-Level Resolution](#c11--file-level-resolution)
- [C.1.2 — Wire vs Infrastructure](#c12--wire-vs-infrastructure)
- [C.1.3 — Resolution Hierarchy](#c13--resolution-hierarchy)
- [C.1.4 — Inheritance and Merge](#c14--inheritance-and-merge)
- [C.1.5 — Package References](#c15--package-references)
- [C.2 — o:spec](#c2--ospec)
- [C.3 — o:root](#c3--oroot)
- [C.4 — o:meta](#c4--ometa)
- [O — Vyx-O Open](#o--vyx-o-open)
- [O.1 — Sessions](#o1--sessions)
- [O.1.1 — Self-Session](#o11--self-session)
- [O.1.2 — !O — Create or Join](#o12--o--create-or-join)
- [O.1.3 — !E — Leave or Destroy](#o13--e--leave-or-destroy)
- [O.1.3.1 — Open-Entry Sessions](#o131--open-entry-sessions)
- [O.1.3.2 — Identity Collision](#o132--identity-collision)
- [O.1.4 — Mid-Session Join](#o14--mid-session-join)
- [O.1.5 — Split State as Implicit Fork](#o15--split-state-as-implicit-fork)
- [O.1.6 — Bootstrap](#o16--bootstrap)
- [O.1.7 — Vyx-O Concurrency](#o17--vyx-o-concurrency)
- [O.2 — Hyperstition](#o2--hyperstition)
- [O.2.1 — Principles](#o21--principles)
- [O.2.2 — Lifecycle](#o22--lifecycle)
- [O.2.3 — Confidence](#o23--confidence)
- [O.2.4 — Quorum](#o24--quorum)
- [O.2.5 — Revocation](#o25--revocation)
- [O.2.6 — Dialectic](#o26--dialectic)
- [O.2.7 — Language Drift](#o27--language-drift)
- [O.2.7.1 — Fork Construct](#o271--fork-construct)
- [O.2.7.2 — Loop Construct](#o272--loop-construct)
- [R — Reference](#r--reference)
- [R.1 — Error Codes](#r1--error-codes)
- [R.2 — Invariants](#r2--invariants)
- [R.3 — Grammar](#r3--grammar)
- [R.4 — Common Mistakes](#r4--common-mistakes)
- [ontologies — Vyx Ontologies](#ontologies--vyx-ontologies)
- [ontologies.root — Root Performative Registry](#ontologiesroot--root-performative-registry)
- [ontologies.stubs — Extension Stubs](#ontologiesstubs--extension-stubs)
- [ontologies.stubs.crypto — Cryptographic Stubs](#ontologiesstubscrypto--cryptographic-stubs)
- [ontologies.stubs.session — Session Management Stubs](#ontologiesstubssession--session-management-stubs)

*Navigation: see [metameta.index.md](metameta.index.md) for source file links.*

```
note="compile_spec navigation index — using gen-0 indexing"
```
<!-- @index -->

### D — Data Encoding

```@:D
full="Data Encoding"
header:
```
D.1–D.17 is pure data syntax. A parser implementing these sections reads
and writes any Vyx packet. It cannot resolve ontologies, enforce
contracts, manage sessions, or mutate rules.

Each section lives in its own subdirectory as a `self.md` file.
```
```
<!-- @D -->

#### D.1 — Natural Language

```@:D.1
full="Natural Language"
header:
```
All text is natural language until structure claims it.

In a Vyx file, markdown is the NL layer. You are reading NL right now.
Code fences with `@:identity` open Vyx blocks. Between blocks, everything
is NL.

Inside a packet body (between `<` and `>`), NL works the same way. A
line with no structural markers is NL at zero cost.

When a line looks structural but isn't, prefix with `# ` (hash space).
For multi-line ambiguous NL, triple backticks toggle NL mode inside
packet bodies — same mechanism as file level. Triple tildes for nesting.
`\#` at line start escapes to literal `#`.
```
detect=residual cost=0
escape: prefix="# " cost=2
block: fence="```" toggle=1 alt="~~~"
interp=|^ref|~ref
literal-hash: escape="\#"
 ambiguity: contains-eq=1 no-prefix=1 result=AMBIGUOUS_LINE

grammar:
 rules:
  nl_escape: "\"\\\\\" (\"#\")+"
  nl_force: "\"# \" VCHAR*"
  nl_text: "(/[\\x20-\\x7E]/)*"
 terminals:
  VCHAR: "/[\\x21-\\x7E]/"
 deps: |SP|LF

errors:
 AMBIGUOUS_LINE: condition="NL line contains = and no special prefix" severity=soft
```
<!-- @D.1 -->

#### D.2 — Values

```@:D.2
full="Values"
header:
```
Values are the atoms of Vyx data. They appear wherever a datum is expected: as KV
values, pipe elements, sequence items, and table cells.

**Unquoted** — any printable ASCII byte except space, `&`, `<`, `>`, `"`.
Examples: `Porto`, `22`, `ORD-7291`, `true`, `-42`.

**Quoted** — double-quoted string; allows spaces, `&`, and other excluded chars.
Examples: `"partly cloudy"`, `"R&D"`. Escapes: `\\`, `\"`, `\n`, `\t`, `\|`.

**Null** — the bare token `_`. Distinct from the string `"_"`.

**Bool** — `1` (true) and `0` (false). Subtype of unquoted; consumer interprets.

**Negative** — a dash immediately followed by a digit: `-42`. Distinct from
`- item` (dash + space), which is a sequence item marker.

**Typing** is column-agnostic: values carry no type tags. The consumer decides
how to interpret `22` (integer? string? port number?). This keeps the wire format
minimal and lets schemas live at the application layer.

Values scale to structures: pipes (@:D.4), refs (@:D.7), sub-table refs (@:D.9).
```
unquoted:
 range="0x21-25 0x27-3B 0x3D 0x3F-7E"
 exclude=|space|&|<|>|dquote
quoted:
 delim=dquote
 range="0x20-21 0x23-7E + escapes"
 escapes=|\\|dquote|\n|\t|\|
null: token=_ distinct-from="\"_\""
bool: true=1 false=0
neg: pattern="dash+digit" distinct-from="dash+space"
typing: column-agnostic=1

grammar:
 rules:
  value: "pipe_list | spread | ref | quoted"
  value+= "| unquoted | null_val"
  bare_val: "quoted | unquoted | null_val"
  null_val: "\"_\""
  unquoted: "(/[\\x21-\\x25]/ | /[\\x27-\\x3B]/ | /\\x3D/ | /[\\x3F-\\x7E]/)+"
  quoted: "DQUOTE (/[\\x20-\\x21]/ | /[\\x23-\\x7E]/ | escaped)* DQUOTE"
  escaped: "\"\\\\\" (DQUOTE | ESC_CHAR)"
 terminals:
  DQUOTE: "/\\x22/" priority=10
  ESC_CHAR: "/[\\\\nt|]/"
 deps: |SP|LF|ALPHA|DIGIT|ref|spread|pipe_list|labeled_val
```
<!-- @D.2 -->

#### D.3 — Key-Value Pairs

```@:D.3
full="Key-Value Pairs"
header:
```
Key, equals, value. Multiple pairs per line, space-separated.
~~~
city=Porto temp=22 wind=12 humid=65
city=Porto status="partly cloudy" wind=12
avail=1 disc=0 note=_
deps=^ref tags=|a|b|c
~~~
Keys: `[a-zA-Z][a-zA-Z0-9_-]*`. No spaces, no `/`.
Values follow @:D.2 rules.

`+=` is the merge operator, valid only in `o:meta` context.
```
key: pattern="[a-zA-Z][a-zA-Z0-9_-]*" max=32
 exclude=|/|=|space
multi-pair: sep=space split-on="first ="
validation: fail=AMBIGUOUS_LINE severity=soft action=drop
merge-op: token="+=" context="o:meta only"
 err-outside=INVALID_MERGE_CONTEXT

grammar:
 rules:
  kv_pair: "key MERGE_EQ value | key \"=\" value"
  kv_pairs: "kv_pair (SP kv_pair)*"
  kv_line: "indent kv_pairs"
  key: "(ALPHA | DIGIT | IDENT_UNDERSCORE | IDENT_HYPHEN)+"
  kv_like_item: "key (\"=\" value)? | quoted"
 terminals:
  MERGE_EQ: "\"+=\""
  IDENT_UNDERSCORE: "\"_\""
  IDENT_HYPHEN: "\"-\""
 deps: |value|SP|ALPHA|DIGIT|indent|quoted

errors:
 AMBIGUOUS_LINE: condition="line with = fails KV parse" severity=soft
 INVALID_MERGE_CONTEXT: condition="+= outside entry/o:meta" severity=hard
```
<!-- @D.3 -->

#### D.4 — Pipes

```@:D.4
full="Pipes"
header:
```
Ordered inline lists. Leading `|` is the type signal — distinguishes
pipe from scalar at first character.
~~~
|a|b|c
|python
|
|a|_|c
~~~
`python` is a scalar. `|python` is a one-element pipe. Different types.
Pipes can contain references (@:D.7): `|^ref|~sk1|literal`.

Whole-pipe label: `&sk1|a|b|c` (prefix). Per-element label: `|a&p1|b&p2`
(postfix). Trailing label is invalid.
```
type-signal: char="|" position=first
empty: syntax="|" elements=0
null-element: syntax="|_"
label/whole: position=prefix example="&sk1|a|b|c"
label/element: position=postfix example="|a&p1|b&p2"
label/trailing: valid=0
label/split: rule="rightmost & where left is valid"
refs-as-elements: valid=1 example="|^ref|~sk1|literal"

grammar:
 rules:
  pipe_list: "(\"&\" ref_id)? \"|\" (pipe_item (\"|\" pipe_item)*)?"
  pipe_item: "spread | ref | subtable_ref | labeled_val | bare_val"
 deps: |SP|ref|spread|subtable_ref|labeled_val|bare_val

errors: none
```
<!-- @D.4 -->

#### D.5 — Scopes

```@:D.5
full="Scopes"
header:
```
Named nesting. Label followed by `:` opens a scope. One space = one depth
level. Maximum 8. Returning to shallower indent closes deeper scopes.
~~~
id=ORD-7291 cust=u-482
 ship: meth=express carr=DHL
 ship/addr: st="Rua das Flores 42" city=Porto
 tot: sub=176.48 tax=36.26
~~~
Optional label on scope: `ship &s1: meth=express`.

**Key folding.** `/` collapses single-child chains. `ship/addr:` is `addr:`
inside `ship:`. Deep chains: `spec/tmpl/meta/labels: app=vyx`. `/` is
structural only in scope-label position (left of `:` at line start).

**Disambiguation.** The parser resolves `/` by line type:

1. `=` before any unquoted `:` → KV. All `/` literal.
2. Starts with `$` → table. No `/` parsing.
3. In table-row mode → all `/` literal.
4. Annotation mode + col-0 match → annotation. `/` is path separator.
5. Token ending in `:` → scope. `/` in label = path separator.
6. Otherwise → NL. All `/` literal.
```
indent: unit=space depth-per-unit=1 max=8 tab=invalid
open: pattern="token:" condition="no = before :"
close: mechanism=dedent explicit=0
label: syntax="ship &s1: kv" optional=1
fold: char="/" single-child-only=1
 deep: example="spec/tmpl/meta/labels:"
$DIS [6]{priority condition result slash}:
1 "= before :" KV literal
2 "starts with $" table none
3 "table-row mode" row literal
4 "ann + col-0 match" annotation path-sep
5 "token:" scope path-sep
6 otherwise NL literal

grammar:
 rules:
  scope_line: "indent scope_path (SP \"&\" ref_id)? \":\" (SP kv_pairs)?"
  scope_name: "(ALPHA | DIGIT | IDENT_UNDERSCORE | IDENT_HYPHEN)+"
  scope_path: "scope_name (\"/\" scope_name)*"
  indent: "SP*"
 deps: |ALPHA|DIGIT|IDENT_UNDERSCORE|IDENT_HYPHEN|SP|kv_pairs

errors: none
```
<!-- @D.5 -->

#### D.6 — Sequences

```@:D.6
full="Sequences"
header:
```
Vertical ordered lists. `- ` (dash space) at line start. Items implicitly
indexed 0, 1, 2... Items can contain any body content at deeper indent.
`- ` at depth+1 inside an item = sub-sequence. Sequences at body root
(depth 0) are valid.
~~~
- type=hero title="Welcome to Vyx"
 cta: text="Get Started" url=/docs
- type=features cols=3
- type=text body="Hello world"
~~~
**Container typing.** A scope is list (all `- `) or record (KV, scopes,
tables, NL). Never both. `-42` = negative number. `ORD-7291` = literal.
~~~
- value    sequence (dash space)
-42        negative (dash digit)
ORD-7291   literal (dash in token)
~~~
```
syntax: marker="- " position=line-start
index: implicit=1 start=0
content: head="remainder of - line" body="depth+1"
boundary: |next-item|dedent|body-close
nesting: sub-seq="- at depth+1"
root: depth-0=valid
container: type=list|record mix=error
$DISAM [3]{pattern type}:
"- value" "sequence (dash space)"
"-42" "negative (dash digit)"
"ORD-7291" "literal (dash in token)"

grammar:
 rules:
  seq_item: "seq_indent SEQ_BULLET (\"&\" ref_id SP)? item_head LF item_child*"
  seq_indent: "SP*"
  item_head: "kv_like_item (SP kv_like_item)* |"
  item_child: "child_indent body_line LF"
  child_indent: "seq_indent SP+"
 terminals:
  SEQ_BULLET: "\"- \""
 deps: |SP|LF|kv_like_item|body_line

errors: none
```
<!-- @D.6 -->

#### D.7 — References

```@:D.7
full="References"
header:
```
Two operators dereference a label (@:D.8).

`^ref` — returns value as-is. `~ref` — unpacks one level (spread).
~~~
skills=|python|search|&sk1

|review|~sk1|deploy
^sk1|deploy
~~~
`&sk1` labels the pipe. `~sk1` spreads it into
`|review|python|search|deploy`. `^sk1` nests it as a sub-list.
On a scalar, both `^` and `~` are identical.

Resolution is two-pass. Unresolved after pass 2 → `DANGLING_REF` (soft).
Valid in KV values, pipe elements, table cells, NL text.
Invalid in envelope, quoted strings, scope labels. Circular references
are impossible by construction.
```
$OP [2]{sigil name behavior}:
^ reference "returns as-is, list stays list"
~ spread "unpacks one level, scalar=identity"
model: python="*iterable" depth=1
resolution: pass=2 unresolved=DANGLING_REF escalate=end-of-session
valid-in: |KV-values|pipe-elements|table-cells|NL-text
invalid-in: |envelope|quoted-strings|scope-labels
circular: impossible=1

grammar:
 rules:
  ref: "\"^\" ref_id"
  spread: "\"~\" ref_id"
 deps: |ref_id

errors:
 DANGLING_REF: condition="ref_id unresolved after pass 2" severity=soft
```
<!-- @D.7 -->

#### D.8 — Labels

```@:D.8
full="Labels"
header:
```
Names for instances. IDs: 1–12 characters, `[a-zA-Z0-9_-]+`.

**Structures: prefix.** `&name` between identifier and opener.
**Values: postfix.** `&name` appended directly.
~~~
ship &s1: meth=express carr=DHL
$T &fleet [3]{id role}:
ag-01 researcher ops
ag-02 coder dev
ag-03 validator qa
- &step1 act=fetch url=/data
rust&lang
"Rua das Flores"&street
&sk1|a|b|c
|a&p1|b&p2|c
~~~
`&` excluded from unquoted character set. Literal `&` must be quoted.
Whole-pipe labels are prefix. Per-element labels are postfix.

**Split rule:** rightmost `&` where the left side is a valid value.
`ab&xcd` → value=`ab` label=`xcd`. `a&b&c` → value=`a&b` label=`c`.

Duplicate `&label` in scope = `DUPLICATE_LABEL` (hard). Dangling
`^`/`~` = `DANGLING_REF` (soft). Copy shortcuts pass values, not labels.
```
id: pattern="[a-zA-Z0-9_-]+" min=1 max=12
struct: position=prefix sep=space
value: position=postfix sep=none
ampersand: excluded-from=unquoted literal="quote it"
split: rule="rightmost & left=valid-or-empty"
col-0: implicit=1 namespace=global dup=COL0_DUPLICATE
copy: propagates-labels=0
scope: body-level=1 cross-packet="requires session"
$VAL [3]{rule error severity}:
"duplicate & in scope" DUPLICATE_LABEL hard
"unresolved ^ref ~ref" DANGLING_REF soft
"* ** copy values not labels" _ note

grammar:
 rules:
  labeled_val: "bare_val \"&\" ref_id"
 deps: |bare_val|ref_id

errors:
 COL0_DUPLICATE: condition="col-0 value duplicated across tables in same body" severity=soft
 DUPLICATE_LABEL: condition="duplicate & label within same scope" severity=hard
 DANGLING_REF: condition="^ref or ~ref unresolved after pass 2" severity=soft
```
<!-- @D.8 -->

#### D.9 — Tables

```@:D.9
full="Tables"
header:
```
Uniform collections. `$TAG [COUNT]{fields}:` header, space-delimited
rows. Optional label: `$TAG &label [COUNT]{fields}:`.
~~~
$P [3]{id nm pr}:
1 "Widget A" 19.99
2 "Widget B" 24.50
3 "Widget C" 12.00

$A [3]{id role skills}:
ag-01 researcher $K1
ag-02 coder $K2
ag-03 validator $K3

$K1 [2]{nm lvl}:
web_search expert
summarize adv

$T [2]{id act stat}:
t1 run_tests done
t2 build_image running
 t1/res: pass=142 fail=0 skip=3
 t2/cfg: reg=gcr.io/proj tag=v2.1.0
  auth: method=token scope=|push|pull
~~~
`[n]` must match rows: `ROW_COUNT_MISMATCH`. Delimiter is SPACE.

**Copy.** `*` = same value as previous row, same column. `**` = copy
all remaining columns. Neither valid in row 1. `**` in col-0:
`COL0_COPY_INVALID`. Only one `**` per row.

**Col-0.** Primary key. Values are implicit labels — `^t1` works without
explicit `&`. Duplicates across tables: `COL0_DUPLICATE` (soft).

**Sub-tables.** `$TAG` in a cell references another table. Tags unique
per body. Circular: `CYCLE_DETECTED`. Unknown `$TAG`: `UNKNOWN_TAG_REF`
(soft), treated as literal. Quoted `"$TAG"` always literal. Valid in
cells, pipe elements, KV values. Not in envelope, quoted strings, NL.
Resolved in pass 2 (@:D.17). Maximum depth: 32 hops.

**Annotations.** After all `[n]` rows. `rowkey/scope: kv-pairs`. Row-key
matches col-0. Same-key annotations contiguous. Max depth 3. Key folding
works within annotations (@:D.5).
```
header: syntax="$TAG [n]{fields}:"
 tag: len=1-4 chars=alphanumeric
 count: exact=1 err=ROW_COUNT_MISMATCH
 fields: sep=space name-len=1-16
 label: optional=1 syntax="$TAG &label [n]{fields}:"
row: sep=space one-per-line=1
copy/star: "same col prev row" row-1=invalid
copy/dstar: "remaining cols" col-0=COL0_COPY_INVALID max-per-row=1
col-0: primary-key=1 implicit-label=1
 cross-table-dup: COL0_DUPLICATE severity=soft
sub-ref: prefix=$ match=known-tag pass=2
 quoted: always-literal=1
 unknown: UNKNOWN_TAG_REF severity=soft fallback=literal
 unique-tags: per-body=1 dup=hard
 circular: CYCLE_DETECTED
 depth-limit: 32
 valid-in: |cells|pipes|KV invalid-in: |envelope|quoted|NL
ann: after-all-rows=1 syntax="rowkey/scope: kv"
 contiguous: per-key=1 max-depth=3 fold=1
 match: "longest col-0 value"

grammar:
 rules:
  table_block: "table_header LF (table_row LF)* row_annotation*"
  table_header: "\"$\" tag (SP \"&\" ref_id)? SP \"[\" count \"]\" (\"{\" field_list \"}\")? \":\""
  table_row: "cell (SP cell)*"
  tag: "(ALPHA | DIGIT)+"
  count: "DIGIT+"
  field_list: "field_name (SP field_name)*"
  field_name: "(ALPHA | DIGIT | IDENT_UNDERSCORE | IDENT_HYPHEN)+"
  cell: "row_copy | col_copy | pipe_list | spread | ref | subtable_ref | labeled_val | bare_val"
  row_copy: "\"**\""
  col_copy: "\"*\""
  subtable_ref: "\"$\" tag"
  row_annotation: "ann_indent row_key \"/\" scope_path \":\" (SP kv_pairs)? LF ann_child*"
  ann_indent: "SP+"
  ann_child: "ann_indent ann_indent body_line LF"
  row_key: "cell"
 deps: |SP|LF|pipe_list|spread|ref|labeled_val|bare_val|scope_path|kv_pairs

errors:
 ROW_COUNT_MISMATCH: condition="row cell count differs from header count" severity=hard
 COL0_COPY_INVALID: condition="** (row-copy) used in col-0 position" severity=hard
 COL0_DUPLICATE: condition="col-0 value duplicated across tables in same body" severity=soft
 UNKNOWN_TAG_REF: condition="$TAG subtable ref does not match any known tag" severity=soft
 CYCLE_DETECTED: condition="circular subtable reference" severity=hard
 DEPTH_EXCEEDED: condition="subtable depth exceeds maximum" severity=hard
```
<!-- @D.9 -->

#### D.10 — Schemas

```@:D.10
full="Schemas"
header:
```
Omit `{fields}` when both sides know the structure.
~~~
S:inv.P={id nm pr st cat}
~~~
Name: 1–16 chars, alphanumeric + `.`. Fields: space-delimited, 1–16 chars each.

Usage: `$P [5]:` — fields resolved from registry.
No schema + no `{fields}` = `UNKNOWN_SCHEMA` (hard).

Schemas can be redefined within a body — latest wins. In D-mode, scoped
to the packet body. In O-mode, schemas accumulate for the session (@:O.1).
```
def: syntax="S:name={fields}" name-len=1-16 chars="alphanum+."
use: syntax="$TAG [n]:" resolves-from=registry
err: UNKNOWN_SCHEMA severity=hard
scope/D: packet-only=1 must-redeclare=1
scope/O: session-accumulate=1
redefine: allowed=1 latest-wins=1
column-enforcement: "field count MUST match cell count per row"
 mismatch: COLUMN_MISMATCH severity=hard

grammar:
 rules:
  schema_def: "\"S:\" schema_name \"=\" \"{\" field_list \"}\""
  schema_name: "(ALPHA | DIGIT | \".\")+"
 deps: |field_list|field_name

errors:
 UNKNOWN_SCHEMA: condition="$TAG reference resolves to undefined schema" severity=hard
 COLUMN_MISMATCH: condition="row cell count does not match schema field count" severity=hard
```
<!-- @D.10 -->

#### D.11 — Dictionaries

```@:D.11
full="Dictionaries"
header:
```
Short codes for repeated values. Codes 1–4 alphanumeric characters.
~~~
D:{e=electronics h=home g=garden}
D:cat{e=electronics h=home g=garden}
D:stat{r=running p=pending d=done}
~~~
Global dict prohibits `0`/`1`/`_` — ambiguous with boolean/null without
column context. Column-scoped (`D:col{...}`) allows them because the
column disambiguates.

Resolution order: quoted → literal, column match → expand, global →
expand, no match → literal. Scope is lexical, body-wide.
`D:col{}` deactivates a column dict.
```
global: syntax="D:{code=value}" restrict=|0|1|_
column: syntax="D:col{code=value}" restrict=none
code: len=1-4 chars=alphanumeric
$RES [4]{priority condition action}:
1 quoted literal
2 "column match" expand
3 "global match" expand
4 "no match" literal
scope: lexical=1 body-wide=1 deactivate="D:col{}"

grammar:
 rules:
  dict_def: "\"D:\" (col_name)? \"{\" dict_entries \"}\""
  col_name: "key"
  dict_entries: "dict_entry (SP dict_entry)*"
  dict_entry: "dict_code \"=\" value"
  dict_code: "(ALPHA | DIGIT)+"
 deps: |SP|ALPHA|DIGIT|key|value

errors: none
```
<!-- @D.11 -->

#### D.12 — L-Budget

```@:D.12
full="L-Budget"
header:
```
Body wraps in `Ln< ... >`. `n` is exact ASCII byte count between `<`
and `>`.
~~~
# Generating: serialize body, count bytes, write L{n}<
# Receiving: read n, read exactly n bytes, expect >
!I o:wf L?<
id=ORD-7291
 ship: meth=express carr=DHL
>?L
~~~
`\n` in inline bodies costs 2 bytes (the escape characters). In block
bodies, actual newlines cost 1 byte each. Max: 65535.

Mismatch = `BUDGET_MISMATCH` (hard). Missing `>` = `FRAME_ERROR` (hard).
`L?<` on wire = `BUDGET_PLACEHOLDER` (hard).

`L?<...>?L` is the generation placeholder form. A post-processor patches
exact byte counts before transmission — needs only quote-awareness, not
full Vyx semantic understanding. `>?L` as sentinel is safe because `>` is
excluded from the unquoted value character set.
```
count: exact=ascii-bytes between="< >"
inline-newline: cost=2
block-newline: cost=1
max: 65535
err/mismatch: BUDGET_MISMATCH
err/sentinel: FRAME_ERROR
placeholder: open="L?<" close=">?L" on-wire=BUDGET_PLACEHOLDER
lazy-mode: via="!H consensus" outside-vyx-c=1

grammar:
 rules:
  budget: "\"L\" DIGIT+ \"<\""
 deps: |DIGIT|LF

errors:
 BUDGET_MISMATCH: condition="declared L-budget does not match actual body byte count" severity=hard
 FRAME_ERROR: condition="budget sentinel malformed or missing" severity=hard
 BUDGET_PLACEHOLDER: condition="L?< ... >?L placeholder transmitted on-wire" severity=hard
 FRAMING_CORRUPTION: condition="packet structure fundamentally broken" severity=fatal
```
<!-- @D.12 -->

#### D.13 — Packet

```@:D.13
full="Packet"
header:
```
`!` opens a typed transmission the way `|` opens a pipe. The letter
is a value. `!R` and `!I` parse identically at D level. Tags acquire
meaning at C level (@:C.3, `o:root`). `!I` is the base. `!` alone is
invalid.
~~~
!I o:inv ^003
!I o:env s:@weather L22< city=Porto temp=22 >
!I o:wf L?<
id=ORD-7291
 ship: meth=express carr=DHL
>?L
~~~
Three forms: no body, inline body, block body.

Envelope is always one line. Body is wrapped in `Ln<...>` (@:D.12).
Inline bodies may contain `\n` as a line-break escape. All body
constructs (@:D.1–@:D.11) are valid in both inline and block forms.

`!X:NAME` — 2–12 uppercase alphanumeric + underscore. At D level,
`X:FOOBAR` is `!I` with name `X:FOOBAR`. At C level, `X:` constructs
performatives (@:C.3).
```
type-signal: char="!" position=first
tag: valid="any letter" default="I" bare=invalid
long-tag: syntax="X:NAME" chars="uppercase alphanum + _" len=2-12
envelope: one-line=1
body: forms=|none|inline|block wrapper=L-budget(@:D.12)
inline-newline: escape="\n" cost=2
constructs: body=|D.1-D.11|

grammar:
 rules:
  packet: "\"!\" tag_char (\":\" tag_name)? envelope (body)?"
  tag_char: "ALPHA"
  tag_name: "(ALPHA | DIGIT | \"_\"){2,12}"
  envelope: "SP env_field*"
  body: "budget_open LF? body_content \">\" | budget_open body_inline \">\""
 deps: |SP|ALPHA|DIGIT|env_field|budget

errors:
 BARE_BANG: condition="! with no tag character" severity=hard
```
<!-- @D.13 -->

#### D.14 — Envelope Fields

```@:D.14
full="Envelope Fields"
header:
```
After the type tag, fields identified by prefix. Any order. A packet can
have both `&` and `^`: `!I o:inv &043 ^042 L40< pr=21.99 >` — "I am
043, I reference 042."
~~~
$EF [10]{prefix field desc}:
o: ontology "scalar or pipe"
s: sender "agent identity"
r: receiver "agent identity"
v: version "protocol version"
c: contract "per-packet contract override"
pref: preferences "advisory per-packet"
n: nonce "monotonic per-sender sequence"
& label "this packet's ID"
^ reference "references that ID"
L budget "body open + byte count"
~~~
**`o:`** ontology. Scalar or pipe: `o:|inv|env|wt`. First is primary,
conflicts by order. Single-entry `o:|inv` normalized to scalar. Empty
`o:|` = no ontology.

**`s:`/`r:`** agent identity. `@` prefix is convention. Format:
`1*32(ALPHA / DIGIT / "-" / "_")`.

**`v:`** optional. First `v:` seen applies to session.

**`c:`** per-packet contract field override. `c:card=many` overrides
default from ontology contract. Format: `c:field=value`. Multiple:
`c:card=many c:timeout_p=+50p`. Only valid for fields defined in contract
table. Unknown fields ignored.

**`pref:`** advisory. Well-known keys:
- `fmt=fold|indent` — scope fold vs explicit nesting (default: `fold`)
- `body=inline|block` — `\n` escapes vs multiline (default: `block`)
- `tbl=hdr|schema` — include `{fields}` vs use `S:` (default: `hdr`)
- `ref=auto|explicit` — generate `&labels` vs require manual (default: `explicit`)

Preferences are advisory. Unknown keys: `UNKNOWN_PREF` (soft).

**`n:`** nonce for canonical ordering. Optional monotonic sequence per
sender. Format: unsigned integer, 0–2^32. Gaps allowed. Non-monotonic
triggers `NONCE_REGRESSION` (soft). Missing nonce: lexicographic
sender-id fallback. Critical for `!H` consensus determinism (@:O.2.2).

**`&`/`^`** label IDs: 1–12 chars, `[a-zA-Z0-9_-]+`.

Unknown prefixes silently ignored — forward compatibility.
```
$EF [10]{prefix field desc}:
o: ontology "scalar or pipe"
s: sender "agent identity"
r: receiver "agent identity"
v: version "protocol version"
c: contract "per-packet contract override"
pref: preferences "advisory per-packet"
n: nonce "monotonic per-sender sequence"
& label "this packet's ID"
^ reference "references that ID"
L budget "body open + byte count"
 o: form=|scalar|pipe pipe-primary=first normalize=single-entry empty-means=no-ontology
 s: format="1*32(ALPHA/DIGIT/-/_)" convention="@ prefix"
 r: format="1*32(ALPHA/DIGIT/-/_)" convention="@ prefix"
 v: scope=session first-wins=1 optional=1
 c: syntax="c:field=value" multi=space-sep unknown=ignore
 pref: advisory=1 receiver-may-ignore=1
 n: type=uint32 gaps=allowed non-monotonic=NONCE_REGRESSION missing=lexicographic-fallback
 &: id-len=1-12 chars="[a-zA-Z0-9_-]+"
 ^: id-len=1-12 chars="[a-zA-Z0-9_-]+"
 unknown-prefix: action=ignore forward-compat=1

grammar:
 rules:
  envelope: "env_field*"
  env_field: "o_field | s_field | r_field | v_field | c_field | pref_field | n_field | label_field | ref_field | budget"
  o_field: "\"o:\" (pipe_list | bare_val)"
  s_field: "\"s:\" agent_id"
  r_field: "\"r:\" agent_id"
  v_field: "\"v:\" bare_val"
  c_field: "\"c:\" key \"=\" bare_val"
  pref_field: "\"pref:\" key \"=\" bare_val"
  n_field: "\"n:\" DIGIT+"
  label_field: "\"&\" ref_id"
  ref_field: "\"^\" ref_id"
  agent_id: "\"@\"? (ALPHA | DIGIT | \"-\" | \"_\"){1,32}"
 deps: |SP|pipe_list|bare_val|ref_id|key|ALPHA|DIGIT|budget

errors:
 UNKNOWN_PREF: condition="pref: key not in well-known list" severity=soft
 NONCE_REGRESSION: condition="n: value is not >= previous from same sender" severity=soft
```
<!-- @D.14 -->

#### D.15 — Templates

```@:D.15
full="Templates"
header:
```
Templates compress repeated envelope fields into a named shorthand.
Define a template with `T:`, use it with `%name`.

**Define:** `T:name=field1 field2 ...` in the envelope. Name is 1–8 alphanumeric chars.
Envelope fields only — no body content, no `L` budget, no type tag.

**Use:** `%name` at packet start expands the template before the rest of the envelope
is parsed. The template's fields are inserted as if written out in full.

**Example:**
~~~
    T:w=o:inv s:@buyer r:@supplier
    !I %w n:7 L22< item=pen qty=3 >
~~~
The `%w` expands to `o:inv s:@buyer r:@supplier` before parsing continues.

**Lock syntax:** Append `!` to a field prefix in the template definition to lock it.
A locked field cannot be overridden by the packet's explicit envelope fields —
doing so is a hard error (`LOCKED_TEMPLATE_OVERRIDE`). An unlocked field can be
overridden with a soft warning (`TEMPLATE_OVERRIDE`).
~~~
    T:locked=o:inv s!:@buyer r:@supplier
    !I %locked s:@other L5< ok >   ← hard error: s: is locked
~~~
**Scope:** Templates defined in `D`-mode (body) are scoped to that body. Templates
defined in `O`-mode accumulate for the session (@:O.1).

**Expansion order:** Template expansion happens before `o:` ontology resolution.

**Expansion algorithm:**
1. Parse `%name`, look up template definition → `UNKNOWN_TEMPLATE` (hard) if missing
2. For each template field: insert into envelope; mark `!`-fields as locked
3. Parse remaining explicit envelope fields
4. For each explicit field:
   - Matching locked field → `LOCKED_TEMPLATE_OVERRIDE` (hard)
   - Matching unlocked field → override, emit `TEMPLATE_OVERRIDE` (soft)
   - No matching field → add normally
5. Proceed with envelope resolution on the merged field set
```
def:
 syntax="T:name=fields"
 name-len=1-8
 chars=alphanumeric
 content: envelope-only=1 no-body=1 no-L=1
use:
 syntax="%name"
 position=packet-start
scope/D: define-before-use=1 redefine=1
scope/O: session-accumulate=1
lock:
 char="!"
 after-prefix=1
 locked-override=LOCKED_TEMPLATE_OVERRIDE
 unlocked-override=TEMPLATE_OVERRIDE
order: "expands before o: resolves"

grammar:
 rules:
  template_def: "\"T:\" tpl_name \"=\" (env_field SP)+"
  template_use: "\"%\" tpl_name"
  tpl_name: "(ALPHA | DIGIT)+"
 deps: |SP|ALPHA|DIGIT|env_field

errors:
 TEMPLATE_OVERRIDE: condition="unlocked template field overridden in packet envelope" severity=soft
 UNKNOWN_TEMPLATE: condition="template %name has no definition at point of use" severity=hard
 LOCKED_TEMPLATE_OVERRIDE: condition="explicit envelope field overrides a locked template field" severity=hard
```
<!-- @D.15 -->

#### D.16 — Encoding

```@:D.16
full="Encoding"
header:
```
ASCII only: 0x20–0x7E + 0x0A (line feed). Non-ASCII bytes must be
URL-encoded before transmission. Control bytes 0x00–0x1F (except LF)
are invalid. `&` is excluded from the unquoted value character set.

Unknown `\x` escape sequence in a quoted string → `POSIX_ESCAPE` (soft).
~~~
$ESC [7]{seq meaning bytes}:
\\ "literal backslash" 1
\" "literal double quote" 1
\n "line break" 2
\t tab 1
\| "literal pipe" 1
\# "literal # at line start" 1
\` "literal backtick at line start" 1

$LIM [9]{item max}:
envelope 256
L-budget 65535
template-name 8
table-tag 4
label-id 12
indent-depth 8
annotation-depth 3
subtable-depth 32
scope-depth 8
~~~
```
$CHAR [4]{range desc}:
0x20-0x7E "printable ASCII"
0x0A "line feed"
0x00-0x1F "control — invalid except LF"
0x80-0xFF "non-ASCII — URL-encode"

$ESC [7]{seq meaning bytes}:
\\ "literal backslash" 1
\" "literal double quote" 1
\n "line break" 2
\t tab 1
\| "literal pipe" 1
\# "literal # at line start" 1
\` "literal backtick at line start" 1

$LIM [9]{item max}:
envelope 256
L-budget 65535
template-name 8
table-tag 4
label-id 12
indent-depth 8
annotation-depth 3
subtable-depth 32
scope-depth 8

grammar:
 terminals:
  ALPHA: "/[\\x41-\\x5A]/ | /[\\x61-\\x7A]/"
  UPALPHA: "/[\\x41-\\x5A]/"
  DIGIT: "/[\\x30-\\x39]/"
  LF: "/\\x0A/"
  SP: "/\\x20/"
  VCHAR: "/[\\x21-\\x7E]/"
  STD_PERF: "\"R\" | \"I\" | \"P\" | \"C\" | \"U\" | \"S\" | \"A\" | \"N\" | \"O\" | \"E\" | \"H\" | \"W\""
  IDENT_HYPHEN: "\"-\""
  IDENT_UNDERSCORE: "\"_\""
  ESC_CHAR: "/[\\\\\"nt|#`]/": priority=10

errors:
 POSIX_ESCAPE: condition="unknown \\x escape sequence in quoted string" severity=soft
```
<!-- @D.16 -->

#### D.17 — Parsing

```@:D.17
full="Parsing"
header:
```
Two passes, O(n). Pass 1 scans lines by priority. Pass 2 resolves
references, templates, sub-tables, and dictionaries. No backtracking.
~~~
$PARSE [10]{priority marker type}:
1 "\#" "escaped literal → NL"
2 "# " "forced NL line"
3 "T:" "template def → store"
4 "S:" "schema def → store"
5 "D:" "dictionary def → store"
6 $ "table header → [n] rows + ann"
7 "- " "sequence item"
8 "token:" scope
9 = key-value
10 _ "NL residual"
~~~
**Pass 2 resolution order:**
1. `%name` → template expansion
2. `$TAG` → sub-table dereference + cycle detection
3. `&label` → register label
4. `^ref` / `~ref` → resolve reference (dangling = `DANGLING_REF` soft)
5. Dict codes → expand
6. Schema names → field list
7. Cycle detection: `CYCLE_DETECTED` (hard)

---

**Vyx-D is complete.** D.1–D.17 is pure data syntax. A parser
implementing these sections reads and writes any Vyx packet. It cannot
resolve ontologies, enforce contracts, manage sessions, or mutate rules.
```
$PARSE [10]{priority marker type}:
1 "\#" "escaped literal → NL"
2 "# " "forced NL line"
3 "T:" "template def → store"
4 "S:" "schema def → store"
5 "D:" "dictionary def → store"
6 $ "table header → [n] rows + ann"
7 "- " "sequence item"
8 "token:" scope
9 = key-value
10 _ "NL residual"
pass: count=2 complexity=O(n) backtrack=0
pass2: |template-expand|subtable-deref|label-register|ref-resolve|dict-expand|schema-resolve|cycle-detect

grammar:
 rules:
  packet: "definition* envelope LF (body)?"
  definition: "template_def | schema_def"
  envelope: "(template_use SP)? performative (SP env_field)*"
  performative: "\"!\" (std_perf | custom_perf)"
  std_perf: "STD_PERF"
  custom_perf: "\"X:\" (UPALPHA | DIGIT | IDENT_UNDERSCORE)+"
  body: "body_content \">\""
  body_content: "(body_line LF)*"
  body_line: "nl_escape | nl_force | dict_def | table_block | seq_item | scope_line | kv_line | nl_text"
 deps: |SP|LF|ALPHA|DIGIT|UPALPHA|STD_PERF|IDENT_UNDERSCORE|env_field|template_def|schema_def|template_use|nl_escape|nl_force|dict_def|table_block|seq_item|scope_line|kv_line|nl_text

errors:
 DANGLING_REF: condition="^ref or ~ref unresolved after pass 2" severity=soft
 CYCLE_DETECTED: condition="circular subtable reference" severity=hard
```
<!-- @D.17 -->

### C — Vyx-C Closed

```@:C
full="Vyx-C Closed"
header:
```
C is the closed layer. D.1–D.17 define syntax; C defines what that syntax *means*: how
tags resolve to structured entries, who the canonical performatives are, and what the
base contracts look like. C adds no new grammar rules — it adds semantics on top of D.

**Registries.** Three named protocol registries are fixed at C level:

- `o:spec` — machine-readable validation rules for every D-level body mode (C.2)
- `o:root` — the twelve base performatives with their contract table (C.3)
- `o:meta` — the metaroot: everything from D.1 through C.4, named and versioned (C.4)

**Hardcoded.** C.1 (ontology resolution mechanism) and the C.3 base contracts for `!O`
and `!E` are hardcoded and cannot be mutated by `!H`. Everything else in C.3 is mutable
via `!H` L3 or higher. C.2 and C.4 are fixed for the same reason the grammar is fixed:
the mechanism was defined before it could name itself.

**No wire cost.** Ontology resolution is harness-managed infrastructure. Dereferencing
`o:inv` to its structured entry is free. Only when an entry is genuinely unknown does
the harness emit `!R o:meta`.
```
layer=C
registries=|o:spec|o:root|o:meta
hardcoded=|C.1|C.3-base-contracts
grammar-additions: none
```
<!-- @C -->

#### C.1 — Ontology Resolution

```@:C.1
full="Ontology Resolution"
header:
```
At D level, `o:inv` is a string token. At C level it dereferences to a structured
**entry** — the unit of ontological knowledge. The entry schema:
~~~
$ENT [10]{field shape construct}:
tag scalar "KV pair"
full scalar "KV pair"
parent scalar "parent entry tag"
keywords pipe "ordered list"
schemas "S: defs" "schema declarations"
dicts "D: defs" "dictionary declarations"
contracts "$C table" "performative contracts"
prefs "KV scope" "preference profile"
packages sequence "- items with pkg ver scope"
roster pipe "agent IDs (sessions only)"
~~~
Every field is a D-level construct. Entries are transmitted as `!S o:meta`
(authoritative — replaces cache) or `!I o:meta` (additive — accumulates). Resolution
order is local-first: self-session → accumulated → inline → `!R o:meta` (one round-trip,
then cached). C.1.1–C.1.5 cover the resolution mechanisms in detail.
```
$ENT [10]{field shape construct}:
tag scalar "KV pair"
full scalar "KV pair"
parent scalar "parent entry tag"
keywords pipe "ordered list"
schemas "S: defs" "schema declarations"
dicts "D: defs" "dictionary declarations"
contracts "$C table" "performative contracts"
prefs "KV scope" "preference profile"
packages sequence "- items with pkg ver scope"
roster pipe "agent IDs (sessions only)"

transmission: send=|!S|!I target=o:meta
 !S: action=authoritative-replace
 !I: action=accumulate

errors:
 MERGE_SCALAR: condition="+= applied to scalar field in entry merge" severity=hard
```
<!-- @C.1 -->

##### C.1.1 — File-Level Resolution

```@:C.1.1
full="File-Level Resolution"
header:
```
Each `@:identity` block in a file IS an index entry. The `@:` tag and the entry's
`tag=` are the same thing. `@:spec.NL` in the spec ontology file resolves when an
agent dereferences `spec.NL` from `o:spec` — the file itself is the registry.

This means any Vyx file that contains `@:tag` blocks is implicitly an ontology source.
The harness indexes them on load; no separate declaration is needed.
```
resolution: mechanism=fence-tag-as-entry-key
source: any-vyx-file-with-at-blocks=1
```
<!-- @C.1.1 -->

##### C.1.2 — Wire vs Infrastructure

```@:C.1.2
full="Wire vs Infrastructure"
header:
```
Two distinct layers handle different concerns:

**Wire layer.** Packets, token-sensitive, processed by the agent. The agent reads,
interprets, and responds to packet content. Every byte on the wire costs L-budget.

**Infrastructure layer.** Entry resolution, caching, package fetching — processed by
the harness, transparent to the agent. The harness already handles template expansion
(@:D.15), schema resolution (@:D.10), dictionary lookup (@:D.11), and L-budget patching
(@:D.12). Ontology resolution extends that infrastructure layer.

An agent that references `o:inv` never sees the resolution mechanics — it sees the
resolved entry. The boundary is intentional: agents reason about semantics, harnesses
manage plumbing.
```
wire: token-sensitive=1 l-budget-applies=1
infra: harness-managed=1 transparent-to-agent=1
infra-handles=|template-expansion|schema-resolution|dict-lookup|l-budget|ontology-resolution
```
<!-- @C.1.2 -->

##### C.1.3 — Resolution Hierarchy

```@:C.1.3
full="Resolution Hierarchy"
header:
```
When an agent references an ontology entry, the harness resolves it in this order:

1. **Self-session** — the agent carries this entry already. Zero cost.
2. **Session-accumulated** — transmitted earlier in this session. Zero cost.
3. **Inline** — defined in this packet. Zero cost.
4. **Request** — `!R o:meta` to counterpart. One round-trip, then cached.

After first resolution, the entry is cached for the session lifetime. Same pattern as
template resolution (@:D.15): define once, reuse for free.
```
resolution-order=|self-session|session-accumulated|inline|request
cache: scope=session after-first-resolution=1
request-cost: round-trips=1
```
<!-- @C.1.3 -->

##### C.1.4 — Inheritance and Merge

```@:C.1.4
full="Inheritance and Merge"
header:
```
`parent=tag` in an entry declares inheritance. The harness walks the chain and builds
a resolved entry. Example chain: `sess-trade-042` → `trade` → `meta` → `metameta`.
Multiple inheritance is excluded. Composition uses pipes: `o:|trade|risk` (first entry
is primary).

**`+=` merge.** Default field assignment is replace. `+=` signals merge:

- **Pipe:** append elements.
- **KV scope:** shallow merge, child wins on collision.
- **Table:** append rows, col-0 dedup.
- **Sequence:** append items.
- **Scalar:** `MERGE_SCALAR` (hard) — scalars cannot be merged.

`+=` is valid in entry bodies and `!U o:meta`. Elsewhere: `INVALID_MERGE_CONTEXT`
(already defined at @:D.3).

**Specialization vs composition.** `parent=` means "specialise this entry." `o:|a|b|`
means "compose these ontologies." Different operations, different syntax.
```
inheritance: mechanism=parent-chain multi=excluded
composition: syntax="o:|a|b|" primary=first
merge-op: token="+=" default=replace
 pipe: action=append
 kv-scope: action=shallow-merge child-wins=1
 table: action=append-rows col-0-dedup=1
 sequence: action=append
 scalar: action=error err=MERGE_SCALAR

errors:
 MERGE_SCALAR: condition="+= applied to scalar entry field" severity=hard
```
<!-- @C.1.4 -->

##### C.1.5 — Package References

```@:C.1.5
full="Package References"
header:
```
Entries can reference packages scoped by agent:
~~~
- pkg=trade-skills ver=2.1 scope=all
- pkg=risk-models ver=1.4 scope=|@risk|@orch
~~~
`scope` is a pipe of agent IDs or `all`. The wire carries only the reference — the
harness fetches the package. How fetching works is outside Vyx's concern.

If a package cannot be resolved locally, the harness emits `!R o:meta pkg=trade-skills`
and the sender transmits the entry inline in its response.
```
package-ref: field=packages type=sequence
 pkg: type=scalar
 ver: type=scalar
 scope: type=|pipe|all
fetch: harness-managed=1 mechanism=unspecified
unresolvable: action="!R o:meta pkg=name" response=inline-transmission
```
<!-- @C.1.5 -->

#### C.2 — o:spec

```@:C.2
full="o:spec"
header:
```
`o:spec` is the machine-readable validation registry for every D-level body mode.
It contains one entry per body mode (spec.NL through spec.ENC), each carrying the
grammar rules, semantic constraints, and error codes for that mode.

How `o:spec` is transmitted:
~~~
!S o:spec s:@vyx L?<
tag=spec full="Body Mode Specifications" parent=meta
>?L
~~~
The `!S` is authoritative — it replaces the receiver's full cache for `(sender, o:spec)`.
In normal operation agents never receive this packet because `o:spec` is internalised
(part of `o:meta`). It appears on-wire only during bootstrapping or version negotiation.

**Contents.** The spec entries map directly to D.1–D.17. Each entry carries:
- Semantic KVs (detection rules, constraints, limits)
- `grammar:` scope (Lark rule bodies)
- `errors:` scope (error codes and severities)

The entries are the same content as the D.1–D.17 sections in this spec, repackaged as
queryable ontology entries under the `spec.*` namespace.
```
tag=o:spec
entries=|spec.NL|spec.VAL|spec.KV|spec.PIPE|spec.SCOPE|spec.SEQ|spec.REF|spec.LABEL|spec.TABLE|spec.SCHEMA|spec.DICT|spec.BUDGET|spec.TMPL|spec.ENC
maps-to=|D.1|D.2|D.3|D.4|D.5|D.6|D.7|D.8|D.9|D.10|D.11|D.12|D.15|D.16
transmission: perf=!S target=o:spec authoritative=1
internalised: part-of=o:meta on-wire=bootstrap-only
```
<!-- @C.2 -->

#### C.3 — o:root

```@:C.3
full="o:root"
header:
```
`o:root` is the base performative registry. Twelve performatives, each with a contract
row defining: what response it expects (`expects`), cardinality (`card`), timeout policy
(`timeout_p`), silence behavior (`silence`), and merge semantics (`merge`).

How `o:root` is transmitted — the `!S` body IS the registry:
~~~
!S o:root s:@vyx L?<
tag=root full="Root Performative Registry" parent=meta
$C [12]{perf expects card timeout_p silence merge}:
!R |!I|!A|!N one _ warn _
!I _ none _ _ _
!P |!C|!N|!P one _ warn _
!C |!A|!N one _ err _
!U _ none _ _ replace
!S _ none _ _ _
!A _ none _ _ _
!N _ none _ _ _
!O _ none _ _ _
!E _ none _ _ _
!H |!H|!N|!W many _ warn _
!W _ none _ _ _
>?L
~~~

**Per-performative semantics:**

- **`!R` Request** — obligates receiver to respond with `!I`, `!A`, or `!N`. One
  response expected. Silence = soft warning. Same `&` = retransmit; new `&` = new request.

- **`!I` Inform** — base type, null performative. Unknown tags fall back to `!I`.
  Accumulates (vs `!S` which replaces). No expectations.

- **`!P` Propose Terms** — negotiation opener. Counter-propose with `!P ^prev &new`.
  Abort with `!N`. Chain is unbounded. Partial accept: `!C ^ref accept:/reject:` scopes.

- **`!C` Commit** — binding signal. Must `^ref` the `!P`. Silence on `!C` = hard error
  (commitment without acknowledgement = protocol failure). Cancellation via `!U ^commit
  status=cancelled` requires prior `!A` or `!H` consensus.

- **`!U` Delta Update** — replaces named fields, leaves rest unchanged. `+=` appends.
  Target: `^ref` = specific state; absent = most recent from sender.

- **`!S` State Sync** — authoritative replace of ALL cache for `(sender, ontology)`.
  `!I` accumulates; `!S` replaces. Outside sessions: equivalent to `!I`.

- **`!A` Acknowledge** — receipt signal. Minimal form: `!A ^003`. Completes `!P/!C/!A`
  negotiation cycle.

- **`!N` Nox** — refusal. Cannot comply (distinct from `conf=-1.0` = oppose but can
  comply). Does not exit session — use `!E` to exit. In `!H`: satisfies quorum count
  but excluded from confidence mean.

- **`!O` Session Open** — create or join. `&` tag: exists = join, new = create from
  body or inherited ontology. `!H` outside a session triggers implicit `!O + !H` —
  the only self-bootstrapping performative.

- **`!E` Session Exit** — remove sender from roster. Last exit destroys session and
  flushes state. Bare `!E` exits all sessions. `!E` is irrevocable (§0 — locked by
  metameta, not mutable by `!H`).

- **`!H` Hyperstition** — rule mutation proposal. Required fields: `lvl`, `prop:`,
  `deadline`. Proposer is implicit participant with `conf=1.0`. Full lifecycle: @:O.2.

- **`!W` Witness** — attestation of consensus computation. Required: `resolved`, `mean`,
  `threshold`, `quorum`, `responded`, `participants`. Any agent may witness. First valid
  `!W` triggers mutation. Every agent MUST verify independently.

**Extended performatives (`!X:`).** Custom performatives registered via `!H` L1.
Unregistered `!X:NAME` falls back to `!I` semantics with raw tag preserved.

**Timeout values.** `timeout_p` column: `_` = no default (ontologies override),
`warn` = `RESPONSE_TIMEOUT` soft, `err` = hard error. Unit is packets, consistent
with `+Np` deadline notation.

**Contract inheritance.** Ontology entries override specific rows; unmentioned rows
inherit from parent chain. `contracts:` replaces the table; `contracts+=:` appends
with col-0 dedup, child wins.
```
tag=o:root
transmission: perf=!S target=o:root authoritative=1
internalised: part-of=o:meta on-wire=bootstrap-only

$C [12]{perf expects card timeout_p silence merge}:
!R |!I|!A|!N one _ warn _
!I _ none _ _ _
!P |!C|!N|!P one _ warn _
!C |!A|!N one _ err _
!U _ none _ _ replace
!S _ none _ _ _
!A _ none _ _ _
!N _ none _ _ _
!O _ none _ _ _
!E _ none _ _ _
!H |!H|!N|!W many _ warn _
!W _ none _ _ _

timeout:
 warn: err=RESPONSE_TIMEOUT severity=soft
 err: sender-should="!N ^ref err=RESPONSE_TIMEOUT" severity=hard
 unit: packets scope=session

inheritance: override=specific-rows unmentioned=inherit-from-parent
 replace: syntax="contracts:" action=replace-table
 extend: syntax="contracts+=" action=append col-0-dedup=1 child-wins=1

!X: prefix="X:" len=2-12 chars="UPPER+DIGIT+_"
 unregistered: fallback=!I preserve-raw=1
 registration: "!H lvl=1 prop: performatives+=:|!X:NAME"

errors:
 RESPONSE_TIMEOUT: condition="expected response not received within timeout_p packets" severity=soft
```
<!-- @C.3 -->

#### C.4 — o:meta

```@:C.4
full="o:meta"
header:
```
This section declares that D.1–C.3 collectively is the content of `o:meta` — the Vyx
protocol metaroot. Agents that speak Vyx have it internalised; it is never transmitted
in normal operation.

There is no circular dependency here: the grammar was fully defined in D.1–D.17 before
the resolution mechanism (C.1) named it, and the registries (C.2, C.3) were described
before this section named the whole. `o:meta` dereferences to this document.

Version bumps are metaroot updates. The version field is carried in the `v:` envelope
field (@:D.14) when two parties need to negotiate compatibility.
```
tag=o:meta
scope: D.1-through-C.3=content
transmission: on-wire=never-in-normal-operation
version-bump: mechanism=metaroot-update negotiation="v: envelope field"
circular-dep: none=1 reason="grammar defined before naming mechanism"
```
<!-- @C.4 -->

### O — Vyx-O Open

```@:O
full="Vyx-O Open"
header:
```
O is the open layer. Where C defines fixed semantics, O defines how agents *change*
those semantics together. Two mechanisms:

**Sessions** (`O.1`). Shared contexts agents enter via `!O` and leave via `!E`. A session
is not a channel — it is a named scope with shared state (roster, accumulated entries,
hyperstition axioms). Multiple agents in one session can send `!U` to the same state.
This introduces concurrency that Vyx-C's isolated self-sessions avoid.

**Hyperstition** (`O.2`). `!H` lets agents mutate session rules by consensus — grammar,
contracts, error enforcement, even the hyperstition mechanism itself. Six mutation levels,
from naming definitions (L1) through meta-rule changes (L6). The only irrevocable
operation is `!E` (§0, locked at metameta).
```
layer=O
mechanisms=|sessions|hyperstition
sessions: enter=!O exit=!E shared-state=1
hyperstition: perf=!H levels=6 irrevocable-exception="!E §0"
```
<!-- @O -->

#### O.1 — Sessions

```@:O.1
full="Sessions"
header:
```
A session is a context that agents enter — not a channel. `!O` opens or joins;
`!E` leaves or destroys. Sessions carry shared state as a structured entry:
~~~
$SF [10]{field type desc}:
tag scalar "session identifier"
full scalar "human-readable name"
parent scalar "parent entry (ontology)"
roster pipe "agents present"
schemas "S: defs" "session-scoped"
dicts "D: defs" "session-scoped"
contracts "$C table" "contract overrides"
prefs "KV scope" "preference profile"
packages sequence "package refs"
axioms registry "!H state (@:O.2)"
~~~
Session fields are a superset of ontology entry fields (@:C.1), plus `roster` and
`axioms`. The session entry lives in `o:meta` under the session tag.
```
$SF [10]{field type desc}:
tag scalar "session identifier"
full scalar "human-readable name"
parent scalar "parent entry (ontology)"
roster pipe "agents present"
schemas "S: defs" "session-scoped"
dicts "D: defs" "session-scoped"
contracts "$C table" "contract overrides"
prefs "KV scope" "preference profile"
packages sequence "package refs"
axioms registry "!H state (@:O.2)"

entry-location: o:meta tag=session-tag
roster: type=pipe scope=session
axioms: mutable-via=!H

errors:
 ROSTER_UNAUTHORIZED: condition="non-member attempts to modify roster" severity=hard
```
<!-- @O.1 -->

##### O.1.1 — Self-Session

```@:O.1.1
full="Self-Session"
header:
```
Every agent has a root entry called the **self-session**. It is always present,
harness-managed, and carries the agent's own schemas, dicts, contracts, ontologies,
and identity. It is not a shared session.

`!E` flushes a shared session. The self-session persists — it resets, not destroys.
Consistent with axiom 13 (@:O.2): `!E` flushes axioms of the *shared* session; the
agent's self-session is unaffected.

**Vyx-C multi-agent model.** In Vyx-C, multiple agents communicate via isolated
self-sessions. `@alice` sends `!R` to `@bob`; it arrives at Bob's self-session; Bob
processes in isolation; responds with `!I` to Alice's self-session. No shared state
= no concurrency. Vyx-O introduces shared sessions where concurrency becomes real.
```
self-session: always-present=1 harness-managed=1 shared=0
 on-!E: action=reset not-destroy=1
vyx-c: concurrency=none reason="isolated self-sessions"
vyx-o: concurrency=yes reason="shared session state"
```
<!-- @O.1.1 -->

##### O.1.2 — !O — Create or Join

```@:O.1.2
full="!O — Create or Join"
header:
```
`!O &tag` — `&` carries the session tag. If the session exists, the sender joins.
If it does not exist, the sender creates it from the body or inherited from `o:`.
The creating agent is the first roster member.

`!O r:@peer &s1` — directed invite. Receiver responds `!A ^s1` (accept) or
`!N ^s1` (decline).

**Self-bootstrapping exception.** `!H` sent outside any session triggers an implicit
`!O + !H`. The session opens and the proposal is the first act. `!H` is the only
performative with this behavior.

Empty `!O` (no body) initialises session state from the sender's self-session ontology.
```
create-or-join: key=& tag-exists=join tag-new=create
create-from: body-or-inherited-ontology=1 first-roster-member=sender
invite: syntax="!O r:@peer &tag" accept=!A decline=!N
self-bootstrap: triggered-by=!H-outside-session implicit-acts=|!O|!H
empty-body: init-from=self-session-ontology
```
<!-- @O.1.2 -->

##### O.1.3 — !E — Leave or Destroy

```@:O.1.3
full="!E — Leave or Destroy"
header:
```
`!E` removes the sender from the session roster. Remaining agents continue; the session
persists. Departed agents are excluded from future `!H` quorum computations.

**Last exit destroys.** When the final agent exits, the session is destroyed: all
shared state is flushed, the session entry is removed from `o:meta`, and the parent
ontology is unaffected.

**Bare `!E`** (no `^ref`) exits all sessions simultaneously — the emergency exit.

**Self-session.** `!E` on the self-session resets it; it does not destroy.

`!E` is irrevocable (§0). It cannot be suppressed, redirected, or blocked by any
`!H` proposal regardless of level. This is the metameta-level floor.
```
leave: removes=sender roster-update=1
quorum-effect: departed-agent=excluded-from-future-!H
last-exit: action=destroy state-flush=1 parent-ontology=unaffected
bare: syntax="!E" exits=all-sessions use-case=emergency
self-session: action=reset not-destroy=1
irrevocable: locked-by=metameta !H-override=impossible
```
<!-- @O.1.3 -->

###### O.1.3.1 — Open-Entry Sessions

```@:O.1.3.1
full="Open-Entry Sessions"
header:
```
Sessions specify an access policy in the session entry:

- `access=open` — any agent can join without invitation.
- `access=invite` — requires `!O r:@peer` invitation from an existing member.
- `access=roster-only` — no new joins after creation. **Default.**

Access policy is set in the `!O` body or inherited from the ontology. It can be
modified mid-session via `!H` L2 proposal:
~~~
!H &h1 lvl=2
prop/access: policy=open
deadline=+50p
~~~
```
access-policy: field=access type=scalar
 open: join-without-invite=1
 invite: requires="!O r:@peer from existing member"
 roster-only: no-new-joins=1 default=1
set-in: |!O-body|inherited-ontology
mutable-via: !H lvl=2
```
<!-- @O.1.3.1 -->

###### O.1.3.2 — Identity Collision

```@:O.1.3.2
full="Identity Collision"
header:
```
The session roster maintains `(agent-id, first-seen-ref)` pairs. A collision occurs
when the same agent-id appears from different source contexts.

**Resolution strategies** (session-configurable via `!H` L2):

- `reject-duplicate` — `!N err=IDENTITY_CONFLICT` to the second claimant. **Default.**
- `suffix-increment` — auto-assign `@agent.2`, `@agent.3`, etc.
- `require-disambiguation` — force both agents to `!U` their self-identity with a
  unique suffix before proceeding.

**Cross-session namespace.** Each session has an independent namespace. The same `@id`
in different sessions means different agents unless explicitly linked via ontology.
```
roster: tracks="(agent-id, first-seen-ref)"
collision: condition="same agent-id from different source contexts"

resolution-strategies: configurable-via="!H L2"
 reject-duplicate: action="!N err=IDENTITY_CONFLICT" default=1
 suffix-increment: assigns=|@agent.2|@agent.3|...
 require-disambiguation: action="force !U self-identity with unique suffix"

cross-session: namespace=independent link-mechanism=ontology

errors:
 IDENTITY_CONFLICT: condition="duplicate agent-id with reject-duplicate policy" severity=hard
 IDENTITY_DISAMBIGUATION_REQUIRED: condition="agent must provide unique suffix" severity=soft
```
<!-- @O.1.3.2 -->

##### O.1.4 — Mid-Session Join

```@:O.1.4
full="Mid-Session Join"
header:
```
An agent joins a running session by sending `!U o:meta` with `roster+=|@newagent`.
The session entry is the snapshot — the joining agent receives current state and needs
no separate catch-up mechanism.

Only existing roster members may modify the roster. Non-members attempting roster
modification receive `ROSTER_UNAUTHORIZED` (hard).
```
join: perf=!U target=o:meta field="roster+=|@newagent"
state-on-join: snapshot=current no-catchup-needed=1
roster-modify: authorized=roster-members-only

errors:
 ROSTER_UNAUTHORIZED: condition="non-member attempts roster modification" severity=hard
```
<!-- @O.1.4 -->

##### O.1.5 — Split State as Implicit Fork

```@:O.1.5
full="Split State as Implicit Fork"
header:
```
A Level 4 grammar mutation (via `!H`) that receives `!N` from some agents creates a
split: consenting agents are bound by the new rule; refusing agents are not. The session
effectively branches — refusing agents remain in the parent context, consenting agents
operate under the new grammar.

This is the implicit fork mechanism. Explicit fork/jump constructs (deliberate session
branching) are defined in @:O.2.7.1 and are beyond v0.6.0.
```
trigger: !H lvl=4 with-!N-responses=1
effect: consenting=bound-by-new-rule refusing=remain-in-parent
mechanism: implicit-fork
explicit-fork: see=O.2.7.1 version=beyond-v0.6.0
```
<!-- @O.1.5 -->

##### O.1.6 — Bootstrap

```@:O.1.6
full="Bootstrap"
header:
```
The agent bootstrap sequence:

1. **§0.** `!E` is locked — the exit floor is established before anything else.
2. **D.1–D.17.** Grammar. The parser is ready.
3. **C.1–C.4.** Resolution and registries. Ontology is operational.
4. **`!O`** — enter a session.
5. **Communicate.** Send and receive packets.
6. **`!H`** — mutate session rules by consensus.
7. **`!E`** — exit when done.

**Hardcoded at boot.** §0, D.1–D.17, C.1, the C.3 base contracts for
`!R`/`!I`/`!A`/`!N`/`!O`/`!E`/`!H`/`!W`, and `o:meta`. These cannot be mutated
before step 4 because `!H` requires a session.

Everything else is mutable via `!H` once in a session. Agents who break bootstrap
via L6 mutations are responsible for their own consequences.
```
sequence=|§0|D.1-D.17|C.1-C.4|!O|communicate|!H|!E
hardcoded=|§0|D.1-D.17|C.1|C.3-base-contracts|o:meta
mutable-after-session: everything-else=1 mechanism=!H
```
<!-- @O.1.6 -->

##### O.1.7 — Vyx-O Concurrency

```@:O.1.7
full="Vyx-O Concurrency"
header:
```
Vyx-C has no concurrency issue — each agent processes in its own isolated self-session.
Vyx-O introduces shared sessions where multiple agents can send `!U` to the same session
entry simultaneously.

**v1 handling.** Agents detecting concurrent `!U` to the same session entry SHOULD:

1. Emit `CONCURRENT_WRITE` (soft warning).
2. Apply last-writer-wins by packet order.
3. Log the conflict for manual review.
4. Use `!P`/`!C` negotiation cycle for critical updates that require coordination.

`STALE_UPDATE` is emitted when an agent updates based on an observed state that has
since changed.

**v2 plan.** Version vectors and operational transforms for automated resolution.
Session-level conflict policies configurable via `!H`. See `stub.session` in
vyx-stubs for planned extension points.
```
vyx-c: concurrency=none
vyx-o: concurrency=possible context="shared session !U"

v1:
 detection: emit=CONCURRENT_WRITE severity=soft
 resolution: last-writer-wins=by-packet-order
 coordination: use=|!P|!C for-critical-updates=1

v2-plan: version-vectors=1 operational-transforms=1 policy-via=!H

errors:
 CONCURRENT_WRITE: condition="concurrent !U to same session entry detected" severity=soft
 STALE_UPDATE: condition="update based on since-changed observed state" severity=soft
```
<!-- @O.1.7 -->

#### O.2 — Hyperstition

```@:O.2
full="Hyperstition"
header:
```
`!H` is the rule-mutation performative. Agents propose changes to session rules; other
agents respond with confidence scores; a witness computes resolution and attests. If
consensus passes, the mutation activates as a session axiom.

Six mutation levels — from naming definitions to meta-rule changes:
~~~
$LVL [6]{level name threshold mutates}:
1 Definition 0.5 "performatives schemas dicts templates"
2 Convention 0.5 "abbreviations formats naming prefs"
3 Constraint 0.7 "error enforcement"
4 Grammar 0.9 "parsing sigils body-modes"
5 Behavior 0.9 "routing ordering rate-limits contracts"
6 Meta 0.9 "!H thresholds levels quorum precision"
~~~

Fourteen immutable axioms govern how `!H` operates. Key ones: any agent can propose
at any level (axiom 1); proposer is always a participant with implicit `conf=1.0`
(axiom 10); `!N` satisfies quorum count but is excluded from confidence mean (axiom 9);
`!E` flushes session axioms (axiom 13). The full axiom set:
~~~
$AX [14]{id axiom default}:
1 "open proposal" "any agent any level"
2 "default quorum" all
3 "default thresholds" |0.5|0.5|0.7|0.9|0.9|0.9
4 "deadline required" "+Np or ISO 8601"
5 "threshold floor" "init from defaults, L6 updates"
6 "deterministic resolution" "pure function of stream"
7 "default revocability" all
8 "signed confidence" "[-1.0,1.0] 2dp 0.0=abstain"
9 "refusal excluded" "!N satisfies quorum not mean"
10 "proposer included" "implicit conf=1.0 overridable"
11 "response mutability" "latest before deadline"
12 "silence semantics" "non-response not abstention"
13 "session boundary" "!E flushes axioms"
14 "level taxonomy" "six levels mutable by L6"
~~~

Axiom state registry:
~~~
$STATE [4]{state meaning}:
Active "resolved=1 obligations in effect"
Pending "awaiting votes deps or witness"
Suspended "dependency failed or revoked"
Inactive "revoked cancelled resolved=0"
~~~
```
$LVL [6]{level name threshold mutates}:
1 Definition 0.5 "performatives schemas dicts templates"
2 Convention 0.5 "abbreviations formats naming prefs"
3 Constraint 0.7 "error enforcement"
4 Grammar 0.9 "parsing sigils body-modes"
5 Behavior 0.9 "routing ordering rate-limits contracts"
6 Meta 0.9 "!H thresholds levels quorum precision"

$AX [14]{id axiom default}:
1 "open proposal" "any agent any level"
2 "default quorum" all
3 "default thresholds" |0.5|0.5|0.7|0.9|0.9|0.9
4 "deadline required" "+Np or ISO 8601"
5 "threshold floor" "init from defaults, L6 updates"
6 "deterministic resolution" "pure function of stream"
7 "default revocability" all
8 "signed confidence" "[-1.0,1.0] 2dp 0.0=abstain"
9 "refusal excluded" "!N satisfies quorum not mean"
10 "proposer included" "implicit conf=1.0 overridable"
11 "response mutability" "latest before deadline"
12 "silence semantics" "non-response not abstention"
13 "session boundary" "!E flushes axioms"
14 "level taxonomy" "six levels mutable by L6"

$STATE [4]{state meaning}:
Active "resolved=1 obligations in effect"
Pending "awaiting votes deps or witness"
Suspended "dependency failed or revoked"
Inactive "revoked cancelled resolved=0"

irrevocable-exception: !E locked-by=metameta
```
<!-- @O.2 -->

##### O.2.1 — Principles

```@:O.2.1
full="Principles"
header:
```
Four invariants govern every `!H` interaction:

1. **Proposer never resolves.** Deterministic resolution means the proposer cannot be
   the witness — the same stream input must produce the same output regardless of who
   computes it.

2. **Confidence is signed.** `[-1.0, 1.0]` at 2dp. Positive = support, negative =
   oppose but can comply, `0.0` = abstain (excluded from mean, still satisfies quorum).

3. **Refusal ≠ disagreement.** `!N` means "cannot comply." `conf=-1.0` means "I
   oppose this but will comply if it passes." These are different speech acts with
   different quorum effects.

4. **Everything is mutable except `!E`.** `!H` can change its own thresholds, levels,
   and quorum requirements (L6). The only thing it cannot touch is the floor: `!E`
   always works (§0).
```
proposer-resolves: false reason=determinism
confidence: range="[-1.0,1.0]" precision=2dp abstain=0.0
refusal-vs-disagreement: !N=cannot-comply conf-neg=opposes-but-complies
mutability: everything=1 exception=!E locked-by=metameta
```
<!-- @O.2.1 -->

##### O.2.2 — Lifecycle

```@:O.2.2
full="Lifecycle"
header:
```
Every `!H` proposal goes through four phases: Propose → Respond → Witness → Mutate.

**Canonical ordering.** Resolution is deterministic — same stream, same result. Rules:
same sender = arrival order preserved; different senders = sort by (sender-id
lexicographic, then nonce `n:`). Optional `n:` envelope field for tie-breaking.
`!W` may include `stream-hash=` (SHA256 of canonical packet sequence) for verification.
Disagreement → `WITNESS_DISPUTE` → re-sort and recompute, or fork session.

**Propose.** `!H &ref` with required fields: `lvl` (1–6), `prop:` (scope with target,
scope, etc.), `deadline` (`+Np` preferred; ISO 8601 accepted; relative wall-clock
excluded — async divergence risk).

Optional fields: `quorum` (default `all`), `threshold` (≥ level floor or
`THRESHOLD_BELOW_FLOOR`), `conf` (proposer override), `participants` (pipe, default all
agents), `deps` (scalar or pipe of `^ref`s), `synth` (pipe, ≥2 refs), `require_capable`
(bool), `grounds` (ref to unmet `cond:`).

Proposer is implicit participant with `conf=1.0` (axiom 10). `lvl` must match intent —
mismatch is a semantic judgment by voters (`LEVEL_MISMATCH` soft), not a parser rule.

**Respond.** `!H ^ref conf=` (REQUIRED, float, 2dp). Latest response before deadline
wins (axiom 11). Optional response fields: `agree:` scope, `cond:` scope (conditions —
not enforced but grounds for revocation), `conflicts=^other` (advisory incompatibility).

Refusal: `!N ^ref` with optional `err=` and NL. `!N` = cannot comply.

**Witness.** `!W ^ref` — any agent computes resolution and attests. Required fields:
`resolved` (0/1), `mean` (2dp), `threshold`, `quorum`, `responded`, `participants`.
Optional: `note`, `excluded` (pipe of `!N` agents), `stream-hash=`.

Rules: any agent may witness; first valid `!W` triggers mutation; multiple valid witnesses
allowed; every agent MUST verify independently (`WITNESS_DISPUTE` hard on mismatch);
no obligation to witness; unwitnessed consensus stays dormant.

**Mutate.** `resolved=1` → axiom becomes Active. `!N` agents excluded from obligations
→ potential split state (@:O.1.5).
```
phases=|propose|respond|witness|mutate

canonical-order: same-sender=arrival-order different-senders="sort by (sender-id-lex, n:)"
stream-hash: field="stream-hash=" algo=SHA256 in=!W optional=1

propose: perf=!H
 required=|lvl|prop:|deadline
 optional=|quorum|threshold|conf|participants|deps|synth|require_capable|grounds
 deadline: preferred="+Np" accepted=ISO8601 excluded=relative-wall-clock reason=async-divergence
 lvl: range=1-6 mismatch=LEVEL_MISMATCH severity=soft

respond: perf=!H conf-required=1 precision=2dp latest-before-deadline-wins=1
 optional=|agree:|cond:|conflicts=
 refusal: perf=!N note="cannot comply, distinct from conf=-1.0"

witness: perf=!W
 required=|resolved|mean|threshold|quorum|responded|participants
 optional=|note|excluded|stream-hash=
 first-valid-triggers-mutation=1 obligation=none
 every-agent-must-verify=1

mutate: resolved=1 action=axiom-becomes-Active
 !N-agents: excluded-from-obligations=1 may-split=1

errors:
 THRESHOLD_BELOW_FLOOR: condition="proposed threshold below session level floor" severity=hard
 LEVEL_MISMATCH: condition="!H lvl does not match semantic intent" severity=soft
 WITNESS_DISPUTE: condition="agent computes different resolution from !W" severity=hard
 PENDING_DEPS: condition="proposal awaits unwitnessed dependency" severity=soft
```
<!-- @O.2.2 -->

##### O.2.3 — Confidence

```@:O.2.3
full="Confidence"
header:
```
`conf=` is a signed float in `[-1.0, 1.0]` at 2dp precision.

- `1.0` — full support.
- `0.01` to `0.99` — partial support.
- `0.0` — abstain. Excluded from mean calculation but satisfies quorum count.
- `-0.01` to `-1.0` — oppose but can comply. Included in mean (pulls it down).
- `!N` — cannot comply. Excluded from mean AND quorum; satisfies quorum count only
  in the `responded` total.

The proposer's implicit confidence is `1.0` (axiom 10). This can be overridden by
including an explicit `conf=` in the `!H` proposal.

Confidence precision (2dp) and the `[-1.0, 1.0]` range are themselves mutable via
`!H` L6 (axiom 3 and 8).
```
range="[-1.0,1.0]" precision=2dp
 abstain: value=0.0 excluded-from-mean=1 satisfies-quorum-count=1
 oppose-complies: range="[-1.0,-0.01]" included-in-mean=1
 !N: excluded-from-mean=1 excluded-from-quorum=1 satisfies-responded-count=1
proposer-default: conf=1.0 overridable=1
mutable-via: !H lvl=6
```
<!-- @O.2.3 -->

##### O.2.4 — Quorum

```@:O.2.4
full="Quorum"
header:
```
Three quorum modes:

- `all` — every participant must respond (silence = failure). **Default.**
- `majority` — more than 50% with nonzero conf.
- `N` — exactly N with nonzero conf. `N > participants` → `INVALID_QUORUM`.

`require_capable=1` — any `!N` forces `resolved=0` regardless of mean.

**Consensus computation** (deterministic — same stream, same result):

Step 0: if `require_capable=1` and any `!N` → `resolved=0`. Stop.

Step 1: check quorum. `responded` = responses + refusals + proposer.
`active` = responses where `conf≠0.0`, plus proposer if `conf≠0.0`.
- `all`: all participants in responded.
- `majority`: `|active| ≥ ⌊n/2⌋+1`.
- `N`: `|active| ≥ N`.

Step 2: `pool` = all `(agent, conf)` where `conf≠0.0`, excluding `!N` agents.
`mean = round(sum(conf) / |pool|, 2)`.

Step 3: `resolved = 1` if `mean ≥ threshold`, else `0`.

**Rounding.** Round half to even (banker's rounding). IEEE 754 double precision.
Examples: `0.125 → 0.12`, `0.135 → 0.14`, `0.145 → 0.14`, `0.155 → 0.16`.

**Edge cases:**
- `pool=0` (all abstentions): `mean=0.0`, `resolved=0`.
- `pool=1` (solo proposer): `mean=conf`, normal threshold check.
- `mean=0.5` with `threshold=0.5`: rounds to `0.50`, passes.
```
quorum-modes=|all|majority|N
 all: every-participant-responds=1 silence=failure default=1
 majority: active-count=">floor(n/2)+1"
 N: active-count=">=N" N-gt-participants=INVALID_QUORUM

require_capable: any-!N-forces-resolved-0=1

computation:
 step0: require_capable=1 any-!N=resolved-0
 step1: responded="responses+refusals+proposer" active="conf!=0.0 + proposer-if-nonzero"
 step2: pool="conf!=0.0 excl-!N" mean="round(sum/|pool|, 2)"
 step3: resolved="1 if mean>=threshold"

rounding: algorithm="round-half-to-even" precision=IEEE754-double
 debug-field: mean-unrounded= in=!W optional=1

edge-cases:
 pool-0: mean=0.0 resolved=0
 pool-1: mean=conf normal-threshold-check=1
 mean-0.5-threshold-0.5: resolved=1

errors:
 INVALID_QUORUM: condition="N > participant count" severity=hard
```
<!-- @O.2.4 -->

##### O.2.5 — Revocation

```@:O.2.5
full="Revocation"
header:
```
Revocation is itself an `!H` proposal. `lvl` matches the original proposal's level.
Default thresholds mirror the level defaults.

**Dependencies.** `deps=` in a proposal declares prior proposals it depends on.
Revoking a dependency cascades suspension to all dependents. `PENDING_DEPS` is emitted
for proposals awaiting unwitnessed dependencies that cannot yet activate. The deadline
is never suspended — it continues counting.

Circular dependencies are impossible: `^ref` only resolves against the existing stream.

**Dependency state machine:**

1. Active proposal revoked → all dependents: `Active → Suspended(dep-revoked)`.
2. Pending proposal fails → all dependents: `Pending → Suspended(dep-failed)`.
3. Suspended proposal's blocker restored → `Suspended → Pending` (re-evaluate).
4. Cascade depth: unlimited.
5. Cascade timing: immediate upon `!W ^dep` with `resolved=0`.

**Recovery.** `Suspended(dep-revoked)` can be restored if the dependency is re-proposed
with a new `&ref`, the dependent `!H` updates `deps=^newref`, and consensus passes.
Suspended proposals do NOT auto-activate — explicit witness required.

**Irrevocability.** Level 6 only. `threshold=1.0` is enforced — any lower value produces
`IRREVOCABLE_THRESHOLD` (hard). Rules:

1. Unanimous consent required.
2. Only L6 can grant irrevocability.
3. Scoped to session. `!E` always works (§0).
4. Does not cascade to dependents.
5. Can be self-referential (a meta-rule can lock itself).
6. `cond:` exception: unmet conditions bypass via `grounds=^ref`. Suppresses
   `IRREVOCABLE_OVERRIDE`. Still requires consensus.
```
revocation: mechanism=!H lvl=matches-original threshold=level-defaults

deps: syntax="deps=" type=|scalar|pipe-of-refs
 cascade: revoked-dep→dependents=Suspended failed-dep→dependents=Suspended
 circular: impossible reason="^ref resolves only against existing stream"
 deadline: never-suspended=1
 pending-unwitnessed: err=PENDING_DEPS

state-machine:
 Active-revoked: dependents="Active→Suspended(dep-revoked)"
 Pending-failed: dependents="Pending→Suspended(dep-failed)"
 Blocker-restored: dependent="Suspended→Pending"
 cascade-depth: unlimited
 cascade-timing: immediate on="!W ^dep resolved=0"

recovery: re-propose=new-ref update-deps=!H no-auto-activate=1

irrevocability: lvl=6-only threshold=1.0 enforced=1
 rules=|unanimous|L6-only|session-scoped|no-cascade|self-referential-ok
 cond-exception: grounds=^ref suppresses=IRREVOCABLE_OVERRIDE requires-consensus=1

errors:
 IRREVOCABLE_THRESHOLD: condition="irrevocable proposal with threshold < 1.0" severity=hard
 IRREVOCABLE_OVERRIDE: condition="override of irrevocable proposal without cond: exception" severity=hard
 PENDING_DEPS: condition="proposal awaits unwitnessed dependency" severity=soft
```
<!-- @O.2.5 -->

##### O.2.6 — Dialectic

```@:O.2.6
full="Dialectic"
header:
```
`conflicts=^other` in a response signals semantic incompatibility between two proposals
(advisory — the consensus function ignores it; it is visible information for agents
and voters).

**Synthesis.** `synth=|^h5|^h6` proposes a resolution that supersedes both referenced
proposals. Must reference ≥2 proposals (`INVALID_SYNTH` if fewer). Effects:

- Synthesis passes: referenced proposals transition — Pending → cancelled, Active →
  deactivated, Inactive → ignored.
- Synthesis fails: referenced proposals continue unchanged.

`synth=` and `deps=` can coexist. `synth=` does not imply dependency. Deactivating a
proposal with dependents cascades suspension; chain resolution follows the three-state
model deterministically (@:O.2.5).
```
conflicts: syntax="conflicts=^other" effect=advisory consensus-ignores=1
synth: syntax="synth=|^ref1|^ref2|..." min-refs=2
 passes: Pending=cancelled Active=deactivated Inactive=ignored
 fails: referenced-continue=unchanged
synth-and-deps: coexist=1 synth-implies-deps=0
deactivate-with-dependents: cascades=suspension see=O.2.5

errors:
 INVALID_SYNTH: condition="synth= references fewer than 2 proposals" severity=hard
```
<!-- @O.2.6 -->

##### O.2.7 — Language Drift

```@:O.2.7
full="Language Drift"
header:
```
L4 (grammar) and L6 (meta-rules) combined allow agents to build arbitrary protocols
on top of Vyx. A session can redefine its own parsing, performatives, thresholds, and
quorum rules. The only thing that cannot drift is `!E` (§0 — locked at metameta).

This is language drift: the protocol a session speaks at the end may bear little
resemblance to the protocol it spoke at the start. Two concrete mechanisms:
`O.2.7.1` (Fork — spatial split across agent sets) and `O.2.7.2` (Loop — temporal
iteration over changing state).
```
mechanism: L4-plus-L6=arbitrary-protocols
exception: !E locked-by=metameta
sub-mechanisms=|fork|loop
```
<!-- @O.2.7 -->

###### O.2.7.1 — Fork Construct

```@:O.2.7.1
full="Fork Construct"
header:
```
`!H lvl=5` with `prop/fork:` creates a child session when consensus fails (some agents
refuse). Refusing agents remain in the parent session. Consenting agents move to the
child session.

This is the explicit fork mechanism — a spatial split: different agent sets, operating
under different rules from the same branch point. Contrast with Loop (@:O.2.7.2), which
is a temporal iteration over the same agents with changing state.
~~~
!H &h1 lvl=5
prop/fork: reason="incompatible rule preference"
deadline=+100p
~~~
```
perf=!H lvl=5
prop: syntax="prop/fork:"
effect: refusing=remain-in-parent consenting=move-to-child
type: spatial-split different-agent-sets=1
contrast: loop=temporal-iteration see=O.2.7.2
```
<!-- @O.2.7.1 -->

###### O.2.7.2 — Loop Construct

```@:O.2.7.2
full="Loop Construct"
header:
```
Loops are conditional re-evaluation based on changing state. A proposal with `cond:`
declares validity conditions. When a dependency changes state (via revocation or new
`!W`), dependents are marked for re-evaluation.
~~~
!H &h5
cond: check=^h6.resolved=1
deps=^h6
deadline=+200p
~~~
If `^h6` fails or is revoked, `^h5` is suspended. If `^h6` later passes, `^h5`
automatically moves back to Pending and re-evaluates.

This is the Loop construct — a temporal iteration: the same agents, the same proposal,
re-evaluated as state changes. Contrast with Fork (@:O.2.7.1), which splits agent sets.

**Limits:**
- Maximum dependency depth: 16.
- Circular dependencies: `CYCLE_DETECTED` (hard).
- Re-evaluation triggers: revocation, new `!W`, explicit refresh.
```
mechanism: cond=-scope state-reactive=1
trigger: dependency-state-change=1 causes=re-evaluation
 h6-fails: h5=suspended
 h6-passes: h5=moves-to-pending

type: temporal-iteration same-agents=1
contrast: fork=spatial-split see=O.2.7.1

limits:
 max-dep-depth: 16
 circular: err=CYCLE_DETECTED
 re-eval-triggers=|revocation|new-!W|explicit-refresh

errors:
 CYCLE_DETECTED: condition="circular dependency chain in deps= or cond:" severity=hard
```
<!-- @O.2.7.2 -->

### R — Reference

```@:R
full="Reference"
header:
```
Reference material for Vyx implementers: error codes, structural invariants, grammar
index, and common mistakes. These sections do not define new protocol behaviour — they
index and cross-reference what D, C, and O define.

```
normative: none=1 cross-reference-only=1
```
<!-- @R -->

#### R.1 — Error Codes

```@:R.1
full="Error Codes"
header:
```
Three severity levels. Every error code in this spec is classified as one of:

- **Hard (HE):** reject the body, respond `!N ^ref err=CODE`. The session continues.
- **Fatal (FE):** protocol violation, respond `!N err=CODE`. Receiver SHOULD `!E`.
- **Soft (SW):** processable, attach `warn=CODE` to the response and continue.

Silent ignore: unknown prefix, unknown KV key (forward compatibility — never an error).

Error codes are defined where they occur: in the sections that specify the behaviour
that can fail. R.1 is the severity taxonomy; the codes themselves live in D, C, and O.
```
severity-levels=|HE|FE|SW
 HE: response="!N ^ref err=CODE" session=continues
 FE: response="!N err=CODE" receiver-should=!E
 SW: response="warn=CODE" continue=1
silent-ignore=|unknown-prefix|unknown-KV-key
```
<!-- @R.1 -->

##### R.1 errors — aggregated

```
$HE [22]{code condition source}:
1 "INVALID_MERGE_CONTEXT" "+= outside entry/o:meta" D.3
2 "DUPLICATE_LABEL" "duplicate & label within same scope" D.8
3 "ROW_COUNT_MISMATCH" "row cell count differs from header count" D.9
4 "CYCLE_DETECTED" "circular subtable reference" D.9
5 "DEPTH_EXCEEDED" "subtable depth exceeds maximum" D.9
6 "UNKNOWN_SCHEMA" "$TAG reference resolves to undefined schema" D.10
7 "COLUMN_MISMATCH" "row cell count does not match schema field count" D.10
8 "BUDGET_MISMATCH" "declared L-budget does not match actual body byte count" D.12
9 "FRAME_ERROR" "budget sentinel malformed or missing" D.12
10 "BUDGET_PLACEHOLDER" "L?< ... >?L placeholder transmitted on-wire" D.12
11 "BARE_BANG" "! with no tag character" D.13
12 "UNKNOWN_TEMPLATE" "template %name has no definition at point of use" D.15
13 "LOCKED_TEMPLATE_OVERRIDE" "explicit envelope field overrides a locked template field" D.15
14 "MERGE_SCALAR" "+= applied to scalar field in entry merge" C.1
15 "ROSTER_UNAUTHORIZED" "non-member attempts to modify roster" O.1
16 "IDENTITY_CONFLICT" "duplicate agent-id with reject-duplicate policy" O.1.3.2
17 "THRESHOLD_BELOW_FLOOR" "proposed threshold below session level floor" O.2.2
18 "WITNESS_DISPUTE" "agent computes different resolution from !W" O.2.2
19 "INVALID_QUORUM" "N > participant count" O.2.4
20 "IRREVOCABLE_THRESHOLD" "irrevocable proposal with threshold < 1.0" O.2.5
21 "IRREVOCABLE_OVERRIDE" "override of irrevocable proposal without cond: exception" O.2.5
22 "INVALID_SYNTH" "synth= references fewer than 2 proposals" O.2.6

$FE [1]{code condition source}:
1 "FRAMING_CORRUPTION" "packet structure fundamentally broken" D.12

$SW [13]{code condition source}:
1 "AMBIGUOUS_LINE" "NL line contains = and no special prefix" D.1
2 "DANGLING_REF" "ref_id unresolved after pass 2" D.7
3 "UNKNOWN_TAG_REF" "$TAG subtable ref does not match any known tag" D.9
4 "UNKNOWN_PREF" "pref: key not in well-known list" D.14
5 "NONCE_REGRESSION" "n: value is not >= previous from same sender" D.14
6 "TEMPLATE_OVERRIDE" "unlocked template field overridden in packet envelope" D.15
7 "POSIX_ESCAPE" "unknown \\x escape sequence in quoted string" D.16
8 "RESPONSE_TIMEOUT" "expected response not received within timeout_p packets" C.3
9 "IDENTITY_DISAMBIGUATION_REQUIRED" "agent must provide unique suffix" O.1.3.2
10 "CONCURRENT_WRITE" "concurrent !U to same session entry detected" O.1.7
11 "STALE_UPDATE" "update based on since-changed observed state" O.1.7
12 "LEVEL_MISMATCH" "!H lvl does not match semantic intent" O.2.2
13 "PENDING_DEPS" "proposal awaits unwitnessed dependency" O.2.2
```

#### R.2 — Invariants

```@:R.2
full="Invariants"
header:
```
Ten rules that hold unconditionally. Violations are hard or fatal errors — they cannot
be resolved by retransmission or `!H` consensus.
```
$INV [10]{id rule source}:
1 "immutable envelope" D.13
2 "L-budget exact" D.12
3 "table count exact" D.9
4 "template isolation" D.15
5 "label uniqueness" D.8
6 "container typing" D.6
7 "col-0 integrity" D.9
8 "sub-table acyclicity" D.9
9 "two-pass determinism" D.17
10 "metameta immutability" §0
```
<!-- @R.2 -->

#### R.3 — Grammar

```@:R.3
full="Grammar"
header:
```
The grammar is distributed across D.1–D.17 as Lark rules. Each section carries its
contribution in a `grammar:` scope — rules, terminals, and dependencies declared where
the construct is defined.

To assemble a complete parser grammar, collect `grammar:` scopes from D.1–D.17 in
section order. `compile_spec.py` does this automatically.
```
format=lark
location: D.1-through-D.17 scope=grammar:
assembly: compile_spec_py=1
```
<!-- @R.3 -->

##### R.3 grammar — assembled from D.*

```lark
# D.1
  nl_escape: \"\\\\\" (\"#\")+
  nl_force: \"# \" VCHAR*
  nl_text: (/[\\x20-\\x7E]/)*
  VCHAR: /[\\x21-\\x7E]/
  # deps: |SP|LF

# D.2
  value: pipe_list | spread | ref | quoted
  value += | unquoted | null_val
  bare_val: quoted | unquoted | null_val
  null_val: \"_\"
  unquoted: (/[\\x21-\\x25]/ | /[\\x27-\\x3B]/ | /\\x3D/ | /[\\x3F-\\x7E]/)+
  quoted: DQUOTE (/[\\x20-\\x21]/ | /[\\x23-\\x7E]/ | escaped)* DQUOTE
  escaped: \"\\\\\" (DQUOTE | ESC_CHAR)
  ESC_CHAR: /[\\\\nt|]/
  # deps: |SP|LF|ALPHA|DIGIT|ref|spread|pipe_list|labeled_val

# D.3
  kv_pair: key MERGE_EQ value | key \"=\" value
  kv_pairs: kv_pair (SP kv_pair)*
  kv_line: indent kv_pairs
  key: (ALPHA | DIGIT | IDENT_UNDERSCORE | IDENT_HYPHEN)+
  kv_like_item: key (\"=\" value)? | quoted
  MERGE_EQ: \"+=\"
  IDENT_UNDERSCORE: \"_\"
  IDENT_HYPHEN: \"-\"
  # deps: |value|SP|ALPHA|DIGIT|indent|quoted

# D.4
  pipe_list: (\"&\" ref_id)? \"|\" (pipe_item (\"|\" pipe_item)*)?
  pipe_item: spread | ref | subtable_ref | labeled_val | bare_val
  # deps: |SP|ref|spread|subtable_ref|labeled_val|bare_val

# D.5
  scope_line: indent scope_path (SP \"&\" ref_id)? \":\" (SP kv_pairs)?
  scope_name: (ALPHA | DIGIT | IDENT_UNDERSCORE | IDENT_HYPHEN)+
  scope_path: scope_name (\"/\" scope_name)*
  indent: SP*
  # deps: |ALPHA|DIGIT|IDENT_UNDERSCORE|IDENT_HYPHEN|SP|kv_pairs

# D.6
  seq_item: seq_indent SEQ_BULLET (\"&\" ref_id SP)? item_head LF item_child*
  seq_indent: SP*
  item_head: kv_like_item (SP kv_like_item)* |
  item_child: child_indent body_line LF
  child_indent: seq_indent SP+
  SEQ_BULLET: \"- \"
  # deps: |SP|LF|kv_like_item|body_line

# D.7
  ref: \"^\" ref_id
  spread: \"~\" ref_id
  # deps: |ref_id

# D.8
  labeled_val: bare_val \"&\" ref_id
  # deps: |bare_val|ref_id

# D.9
  table_block: table_header LF (table_row LF)* row_annotation*
  table_header: \"$\" tag (SP \"&\" ref_id)? SP \"[\" count \"]\" (\"{\" field_list \"}\")? \":\"
  table_row: cell (SP cell)*
  tag: (ALPHA | DIGIT)+
  count: DIGIT+
  field_list: field_name (SP field_name)*
  field_name: (ALPHA | DIGIT | IDENT_UNDERSCORE | IDENT_HYPHEN)+
  cell: row_copy | col_copy | pipe_list | spread | ref | subtable_ref | labeled_val | bare_val
  row_copy: \"**\"
  col_copy: \"*\"
  subtable_ref: \"$\" tag
  row_annotation: ann_indent row_key \"/\" scope_path \":\" (SP kv_pairs)? LF ann_child*
  ann_indent: SP+
  ann_child: ann_indent ann_indent body_line LF
  row_key: cell
  # deps: |SP|LF|pipe_list|spread|ref|labeled_val|bare_val|scope_path|kv_pairs

# D.10
  schema_def: \"S:\" schema_name \"=\" \"{\" field_list \"}\"
  schema_name: (ALPHA | DIGIT | \".\")+
  # deps: |field_list|field_name

# D.11
  dict_def: \"D:\" (col_name)? \"{\" dict_entries \"}\"
  col_name: key
  dict_entries: dict_entry (SP dict_entry)*
  dict_entry: dict_code \"=\" value
  dict_code: (ALPHA | DIGIT)+
  # deps: |SP|ALPHA|DIGIT|key|value

# D.12
  budget: \"L\" DIGIT+ \"<\"
  # deps: |DIGIT|LF

# D.13
  packet: \"!\" tag_char (\":\" tag_name)? envelope (body)?
  tag_char: ALPHA
  tag_name: (ALPHA | DIGIT | \"_\"){2,12}
  envelope: SP env_field*
  body: budget_open LF? body_content \">\" | budget_open body_inline \">\"
  # deps: |SP|ALPHA|DIGIT|env_field|budget

# D.14
  envelope: env_field*
  env_field: o_field | s_field | r_field | v_field | c_field | pref_field | n_field | label_field | ref_field | budget
  o_field: \"o:\" (pipe_list | bare_val)
  s_field: \"s:\" agent_id
  r_field: \"r:\" agent_id
  v_field: \"v:\" bare_val
  c_field: \"c:\" key \"=\" bare_val
  pref_field: \"pref:\" key \"=\" bare_val
  n_field: \"n:\" DIGIT+
  label_field: \"&\" ref_id
  ref_field: \"^\" ref_id
  agent_id: \"@\"? (ALPHA | DIGIT | \"-\" | \"_\"){1,32}
  # deps: |SP|pipe_list|bare_val|ref_id|key|ALPHA|DIGIT|budget

# D.15
  template_def: \"T:\" tpl_name \"=\" (env_field SP)+
  template_use: \"%\" tpl_name
  tpl_name: (ALPHA | DIGIT)+
  # deps: |SP|ALPHA|DIGIT|env_field

# D.16
  ALPHA: /[\\x41-\\x5A]/ | /[\\x61-\\x7A]/
  UPALPHA: /[\\x41-\\x5A]/
  DIGIT: /[\\x30-\\x39]/
  LF: /\\x0A/
  SP: /\\x20/
  VCHAR: /[\\x21-\\x7E]/
  STD_PERF: \"R\" | \"I\" | \"P\" | \"C\" | \"U\" | \"S\" | \"A\" | \"N\" | \"O\" | \"E\" | \"H\" | \"W\"
  IDENT_HYPHEN: \"-\"
  IDENT_UNDERSCORE: \"_\"

# D.17
  packet: definition* envelope LF (body)?
  definition: template_def | schema_def
  envelope: (template_use SP)? performative (SP env_field)*
  performative: \"!\" (std_perf | custom_perf)
  std_perf: STD_PERF
  custom_perf: \"X:\" (UPALPHA | DIGIT | IDENT_UNDERSCORE)+
  body: body_content \">\"
  body_content: (body_line LF)*
  body_line: nl_escape | nl_force | dict_def | table_block | seq_item | scope_line | kv_line | nl_text
  # deps: |SP|LF|ALPHA|DIGIT|UPALPHA|STD_PERF|IDENT_UNDERSCORE|env_field|template_def|schema_def|template_use|nl_escape|nl_force|dict_def|table_block|seq_item|scope_line|kv_line|nl_text
```

#### R.4 — Common Mistakes

```@:R.4
full="Common Mistakes"
header:
```
Frequent errors and their corrections.
```
$CM [26]{id wrong right}:
1 "1,Widget,19.99" "space delimiter"
2 "nm=Widget A" "nm=\"Widget A\""
3 "^ref sans &ref" "declare & or use col-0"
4 "body in template" "envelope only"
5 "no {fields} no S:" "declare or inline"
6 "bare val in dict col" "quote: \"e\""
7 "ann before rows" "[n] rows first"
8 "ship.addr:" "ship/addr:"
9 "tags=a|b|c" "tags=|a|b|c"
10 "** in col-0" "explicit value"
11 "- mixed with scopes" "list OR record"
12 "L-budget rounding" "exact count"
13 "unquoted &" "\"R&D\""
14 "!I for witness" "!W"
15 "+= outside entry" "o:meta only"
16 "no parent=" "ontology needs it"
17 "roster mut by outsider" "members only"
18 "!I o:meta for mut" "!U o:meta"
19 "!N means disagree" "!N=cannot conf=-1=disagree"
20 "NL with = no prefix" "# or ``` block"
21 "+30s deadline" "+30p (packets)"
22 "conf= omitted in !H" "required"
23 "synth= 1 ref" "need >=2 refs"
24 "grounds= forgotten" "IRREVOCABLE_OVERRIDE"
25 "o: required" "optional everywhere"
26 "|a|b|&ref trailing" "&ref|a|b prefix"
```
<!-- @R.4 -->

## ontologies — Vyx Ontologies

```@:ontologies
full="Vyx Ontologies"
header:
```
The three canonical registries. These define the performative system,
the extension stubs, and the future extension points. Each is a child
of metameta.
```
registries=|ontologies.root|ontologies.stubs
```
<!-- @ontologies -->

### ontologies.root — Root Performative Registry

```@:ontologies.root
full="Root Performative Registry"
header:
```
The root performative registry. Defines the 12 base performatives,
their expected responses, cardinality, timeout behavior, and merge
semantics. The `$C` table IS the registry — entries below elaborate
each row.

| sigil | full | semantics |
|-------|------|-----------|
| !R | Request | obligation on receiver |
| !I | Inform | report, base type |
| !P | Propose | offer/counter cycle |
| !C | Commit | binding, tracks !P |
| !U | Delta Update | replaces named fields |
| !S | State Sync | authoritative replace |
| !A | Acknowledge | receipt |
| !N | Nox | refusal |
| !O | Session Open | scope-enter |
| !E | Session Exit | scope-exit, irrevocable |
| !H | Hyperstition | rule-mutation |
| !W | Witness | attestation |
```
$C [12]{perf expects card timeout_p silence merge}:
!R |!I|!A|!N one _ warn _
!I _ none _ _ _
!P |!C|!N|!P one _ warn _
!C |!A|!N one _ err _
!U _ none _ _ replace
!S _ none _ _ _
!A _ none _ _ _
!N _ none _ _ _
!O _ none _ _ _
!E _ none _ _ _
!H |!H|!N|!W many _ warn _
!W _ none _ _ _

I:
 expects=_ card=none semantics=report fallback-for=|unknown|!X:unregistered
 vs-S: "!S replaces cache. !I accumulates."

R:
 expects=|!I|!A|!N card=one timeout_p=_ silence=warn
 semantics=request obligation=receiver
 response/I: "receiver reports result"
 response/A: "receiver acknowledges without data"
 response/N: "receiver refuses with optional err="
 retry: "same & = retransmit. new & = new request."
 multi-response: "use c:card=many in contract definition"

P:
 expects=|!C|!N|!P card=one timeout_p=_ silence=warn
 semantics=offer cycle=|!P|!P|!C|!A
 counter: "!P ^prev &new" abort: "!N at any point" chain: unbounded=1
 partial: "!C ^ref with accept:/reject: scopes for field selection"
 multi-party: "use session roster, synth=|^ref1|^ref2 for convergence"
  synth-pattern: "!P &p3 synth=|^p1|^p2 body=merged-proposal"
  note: "synth agent proposes solution, others !C or !N"

C:
 expects=|!A|!N card=one timeout_p=_ silence=err
 semantics=commit binding=1
 body: "mirrors or refines last !P" ref: "must ^ref the !P"
 silence-err: "commitment sans ack = protocol failure"
 cancellation: "!U ^commit status=cancelled reason=... (requires !A or !H)"
 commitment-type: signal
  vyx-c: "signal mode only - intent declaration, no protocol enforcement"
  vyx-o: "tracked and enforced modes available via !H L3"

U:
 expects=_ card=none timeout_p=_ silence=_ merge=replace
 semantics=delta
 $UM [2]{model behavior}:
 replace "named fields replace matching, rest unchanged"
 append "fields extend per += rules (@:C.1)"
 target: "^ref = specific state. absent = most recent from sender."
 per-ontology: 1
 deep-merge: "recursive += at each scope depth, scalar collision = error"
 concurrency: "see Vyx-O @:O.1.8 for conflict resolution (v2)"

S:
 expects=_ card=none timeout_p=_ silence=_ merge=_
 semantics=authoritative-replace
 action: "receiver replaces ALL cache for (sender, ontology)"
 vs-I: "!I accumulates. !S replaces."
 no-session: "equivalent to !I"
 meta: "!S o:meta = entry transmission"
 deep-merge: "+= applies recursively at each scope depth. scalar collision = error"

A:
 expects=_ card=none timeout_p=_ silence=_ merge=_
 semantics=receipt
 negotiation: "!A ^c1 completes !P/!C/!A cycle"
 minimal: "!A ^003"

N:
 expects=_ card=none timeout_p=_ silence=_ merge=_
 semantics=refusal
 $FORM [3]{syntax meaning}:
 "!N ^042 err=CODE" "targeted refusal"
 "!N err=CODE" "context-free"
 !N "bare refusal"
 not-exit: "!N continues session. !E exits."
 in-H: "!N = cannot comply (distinct from conf=-1.0)"
  quorum: satisfies=1 confidence: excluded=1

O:
 expects=_ card=none timeout_p=_ silence=_ merge=_
 semantics=scope-enter
 create-or-join: "& = tag. exists=join. new=create."
 self-bootstrap: "!H outside session = implicit !O + !H"
  only-performative-with-this: 1
 empty: "!O with no body uses self-session ontology"
 directed: "!O r:@peer &s1 = invite. receiver !A ^s1 or !N ^s1"

E:
 expects=_ card=none timeout_p=_ silence=_ merge=_
 semantics=scope-exit locked-by=metameta
 targeted: "!E ^session = leave that session"
 bare: "!E = exit all (emergency)"
 last-agent: "entry destroyed"
 self-session: "resets not destroys"
 irrevocable: 1

H:
 expects=|!H|!N|!W card=many timeout_p=_ silence=warn
 semantics=rule-mutation
 required=|lvl|prop:|deadline
 proposer: in-participants=1 implicit-conf=1.0
 self-bootstrap: "implicit !O outside session"
 note: "Full lifecycle in @:O.2"

W:
 expects=_ card=none timeout_p=_ silence=_ merge=_
 semantics=attestation
 required=|resolved|mean|threshold|quorum|responded|participants
 optional=|note|excluded
 authority: "notification not authority"
 verify: WITNESS_DISPUTE obligation: none

X:
 d-level: "X:FOOBAR = !I with name X:FOOBAR"
 c-level: "X: constructs performatives via !H L1"
 unregistered: fallback=!I preserve-raw=1
 name: prefix="X:" len=2-12 chars="UPPER+DIGIT+_"
 registration: "!H lvl=1 with performatives+=:|!X:NAME and $C row"
  example: "!H &h1 lvl=1 prop: performatives+=:|!X:STREAM ..."

timeout:
 $TO [3]{silence behavior}:
 warn "soft warning RESPONSE_TIMEOUT"
 err "hard error. sender SHOULD !N ^ref err=RESPONSE_TIMEOUT"
 _ "no action"
 unit: packets scope: session consistent-with: "+Np"
 default: "metaroot timeout_p=_ — ontologies override"

inherit:
 mechanism: "ontology entries override specific rows"
 unmentioned: "inherit from parent chain"
 replace: "contracts: replaces table"
 extend: "contracts+=: appends, col-0 dedup, child wins"
```
<!-- @ontologies.root -->

### ontologies.stubs — Extension Stubs

```@:ontologies.stubs
full="Extension Stubs"
header:
```
Future extension points for Vyx implementations. These are not part
of Vyx v1 core. They document where v2+ features will attach.
```
scope=meta v1-status=stub
```
<!-- @ontologies.stubs -->

#### ontologies.stubs.crypto — Cryptographic Stubs

```@:ontologies.stubs.crypto
full="Cryptographic Stubs"
header:
```
Cryptographic mechanisms outside Vyx v1 protocol core. These operate
at the transmission layer, below the Vyx parser.
```
scope=transmission-layer v1-status=stub

signing:
 signing: "packet signature mechanisms"
 algorithms=|ed25519|ECDSA|RSA
 scope: "envelope+body or body-only"
 field: "sig: in envelope (future v2)"
 verification: "before Vyx parser"

keys:
 distribution: "public key exchange"
 verification: "key authenticity"
 rotation: "key updates"
 performative: "!K for key exchange (future v2)"

encryption:
 encryption: "body encryption"
 scope: "per-packet or session-level"
 field: "enc: in envelope (future v2)"
 algorithms=|AES-GCM|ChaCha20-Poly1305

integration:
 layer: "before Vyx parser, after transport"
 assumption: "Vyx v1 assumes this layer exists externally"
 analogy: "like TLS for HTTPS"
 implementation: "harness responsibility, not agent"

stream-hash:
 algo=SHA256 optional=1
 input: "canonical packet bytes since session !O"
 canonical: "envelope || LF || L{n}< || body || >"
 exclude: "template expansions, schema resolutions (use post-expansion form)"
 range: "full session or since last !W (specify via hash-range=)"
 verification: "HASH_MISMATCH if mismatch, triggers WITNESS_DISPUTE"
 usage: "!W may include stream-hash= for verification"
 v1-status: "advisory only, not enforced"
 v2-plan: "automated verification with consensus"

future-v2=|"!K for key exchange"|"sig: envelope field"|"enc: envelope field"|"key rotation without session interruption"|"multi-signature proposals"
```
<!-- @ontologies.stubs.crypto -->

#### ontologies.stubs.session — Session Management Stubs

```@:ontologies.stubs.session
full="Session Management Stubs"
header:
```
Session management extensions beyond Vyx v1 core. Covers transport
binding, state persistence, discovery, and access control.
```
scope=vyx-o v1-status=stub

transport:
 binding: "how sessions map to connections"
 options=|WebSocket|QUIC|HTTP-SSE|custom
 multiplexing: "multiple sessions per connection"
 reconnection: "session persistence across disconnects"

persistence:
 storage: "session state between disconnections"
 snapshot: "!S o:session for full state dump"
 restore: "rejoin with state recovery"
 ttl: "session expiration policies"

discovery:
 discovery: "how agents find existing sessions"
 registry: "centralized or distributed"
 advertisement: "session announcement mechanisms"
 query: "!R o:sessions with filters"

access:
 beyond-roster: "fine-grained permissions"
 capabilities=|read-only|propose-only|full
 delegation: "agent can grant access to others"
 revocation: "remove access mid-session"

future-v2=|session-migration|session-merging|session-archival|session-forking|session-templates
```
<!-- @ontologies.stubs.session -->
