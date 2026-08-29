# ConfTamer Ground-Up Rewrite Architecture and Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite this repository as a focused graph compiler and explorer that consumes real ContextTrack JSONL, upstream ParamTrack CSV, and gopls US/Accessors graph output, builds canonical PMGraphs, stitches two or more PMGraphs into an AppGraph, analyzes canonical and CType graphs with `python-igraph`, and exports GraphML for Gephi Lite.

**Architecture:** Source-specific adapters validate files emitted by upstream tools and project them into strict Pydantic domain models. PMGraph and AppGraph JSON are tool34-owned target formats; igraph is a one-way analysis representation. Current gopls `.text` JSON normalizes into a CType graph model, and verified future GraphML will share that model only after the producer-contract gate. ParamTrack's aggregate `{API, Verb, Resource, CType}` rows join conservatively to unique semantic ContextTrack Send Requests.

**Tech Stack:** Python 3.13+, Pydantic v2, python-igraph, Typer, Python's standard `csv` and `json` modules, GraphML, JSONL, pytest, Ruff, ty, Tombi, and uv.

**Spec:** This document is the approved architecture specification and implementation plan for this repository only.

## Global Constraints

- Rewrite `AGENTS.md` in the first implementation task, before changing source files, so execution follows the new architecture rather than the legacy CSV/v1 rules.
- Delete only tool34's legacy edge-CSV workflow. Upstream ParamTrack CSV is a targeted input format and remains supported.
- PMGraph v2 and the replacement CLI are intentionally breaking contracts.
- Keep the final production implementation under 3,000 physical Python lines in `src/conftamer`; exceeding that budget requires explicit approval and an explanation of why simplification is insufficient.
- Consume ContextTrack JSONL in the schema demonstrated by `examples/contexttrack/`.
- Consume ParamTrack's variable-width CSV schema demonstrated by `examples/paramtrack/runs/target-scraper-all/parameters.csv` and `examples/paramtrack/runs/manager-st-zero/parameters.csv`.
- Consume current gopls `.text` JSON for the Unmarshaler Subgraph and Accessors.
- Add GraphML input only after real producer files establish its contract; until then, GraphML is output-only.
- Treat supplying ParamTrack and ContextTrack files together as the caller's assertion that they describe a compatible test corpus; current files contain no verifiable shared run identity.
- Join ParamTrack rows to ContextTrack Send Requests with an explicitly labeled aggregate heuristic, and only when normalized method and path identify one semantic Send node.
- Do not compare ParamTrack `API` with ContextTrack `api_id`; the real producers assign them different meanings.
- Use US/Accessors to validate ParamTrack CType references and support direct exploration; do not insert CType nodes into PMGraph.
- Do not reproduce ParamTrack's CType-path, YAML-tag, Delve-stack, or goroutine analysis.
- Include the paper's minimal Behavior node shape in PMGraph v2 as an explicit design decision, but do not create Behavior instances until a producer contract exists.
- Stitch directly from two or more PMGraphs; require no additional application or deployment metadata input.
- Match across modules by HTTP labels only, mark every accepted contraction as heuristic, and contract only mutually unique Send/Receive candidates.
- Retain and mark unmatched nodes by default.
- Keep Pydantic documents canonical and immutable; never treat igraph vertex indices as persistent identity.
- Treat GraphML exported for Gephi as a visualization projection, not canonical persistence.
- Do not add dependencies or raise the Python version without separate approval.
- Treat sibling repositories and `ConfTamer_HotNets_2026.pdf` as read-only references.
- Preserve malformed-line diagnostics and current tool34's conservative ContextTrack route/response inference.

### Provenance labels used by this plan

- **Observed input:** verified in checked-in artifacts or the current upstream serializer.
- **Current tool34 policy:** behavior already implemented downstream, not guaranteed by upstream.
- **Target design:** an explicit rewrite decision that tool34 will own.
- **Paper-derived:** a concept from the paper that may lack a current producer.
- **Blocked:** not implementation-ready until a real artifact defines the contract.

A target design is not an upstream fact. Each format document created in Task 1 must use these labels and keep observed fields separate from tool34 normalization.

---

## 1. Scope

### 1.1 In scope

This repository owns:

- parsing and validating ContextTrack event JSONL;
- parsing and validating upstream ParamTrack CSV;
- parsing and validating current gopls CType graph `.text` JSON;
- parsing and validating gopls CType GraphML only after the producer-contract gate passes;
- validating ParamTrack CType references against US and Accessors;
- heuristically matching aggregate ParamTrack message identities to unique semantic ContextTrack Send Requests;
- constructing deterministic PMGraph v2 documents;
- converting PMGraph, AppGraph, and CType graphs to igraph;
- querying all three graph types;
- exporting visualization GraphML for Gephi Lite;
- loading two or more PMGraphs in one stitch operation;
- conservatively matching and contracting Send/Receive nodes across PMGraphs;
- constructing one deterministic AppGraph from all supplied PMGraphs;
- diagnostics, CLI behavior, documentation, examples, tests, and release packaging; and
- removing the old edge-CSV parser, legacy examples, PMGraph v1, and old CLI surfaces.

### 1.2 Out of scope

This repository does not plan or implement:

- changes to gopls;
- replacement of the old Go graph library;
- module test discovery or execution;
- Delve launch, breakpoints, stack inspection, or expression evaluation;
- goroutine ancestry tracking;
- ContextTrack instrumentation;
- ParamTrack's parameter-key inference;
- production of ParamTrack CSV;
- wrappers around upstream analyzers or runners; or
- conversion of ParamTrack's hierarchy or log output into PMGraph data.

Those systems are external producers. This repository consumes their files as demonstrated by checked-in examples.

### 1.3 Authoritative real examples

The following files define the current producer behavior:

| File | Role in rewritten tool34 |
|---|---|
| `examples/contexttrack/prometheus/*.jsonl` | ContextTrack message input |
| `examples/paramtrack/runs/target-scraper-all/parameters.csv` | One-row ParamTrack input for the target-scraper run |
| `examples/paramtrack/runs/manager-st-zero/parameters.csv` | Four-row ParamTrack input demonstrating several CTypes for one message |
| `examples/paramtrack/static/unmarshaler_subgraph.text` | Current US machine input |
| `examples/paramtrack/static/accessors.text` | Current Accessors machine input |
| `examples/paramtrack/static/*.gv` | Reference visualization only; not parsed |
| `examples/paramtrack/runs/*/parameters_hierarchy.txt` | Human-readable derivatives; not parsed |
| `examples/paramtrack/static/*.log`, `examples/paramtrack/runs/*/*.log` | Producer logs; not parsed |

Observed fixture facts used for smoke verification:

- US `.text`: 57 vertices, 90 edges, 58 `List` entries, and 1 nonidentity alias.
- Accessors `.text`: 582 vertices, 822 edges, 595 `List` entries, and 13 nonidentity aliases.
- Every real edge contains `Properties.Attributes`, `Properties.Weight`, and `Properties.Data`.
- `Properties.Data` is a list of ordered AST paths; US has up to four paths on one edge.
- Both `parameters.csv` files use the same exact header and variable-width row shape.
- `runs/target-scraper-all/parameters.csv` contains one `Prometheus,GET,<empty>,/scrape.targetScraper` row with 108 sorted, unique parameter keys.
- `runs/manager-st-zero/parameters.csv` has four rows for the same `Prometheus,GET,/metrics` message identity.
- Its CType rows contain 133, 120, 201, and 108 individually sorted, unique parameter keys; their union contains 226 keys.
- The manager CTypes are `/scrape.scrapeLoop`, `/discovery.Manager`, `/scrape.Manager`, and `/scrape.targetScraper`.
- All four manager CTypes exist as represented vertices in Accessors and not in US.
- No checked-in example contains PMGraphs from two modules or demonstrates a real cross-module Send/Receive match; AppGraph matching remains a tool34 target design tested with explicit synthetic cases.

These counts are smoke-test expectations for these specific examples, not general schema limits.

---

## 2. Data Flow in This Repository

```text
ContextTrack events.jsonl
    -> contexttrack/models.py
    -> contexttrack/importer.py + contexttrack/matching.py
    -> semantic message fragment
    -> Send Request index keyed by normalized (method, path)

ParamTrack *.csv
    -> paramtrack/models.py + paramtrack/importer.py
    -> validate CType through US/Accessors
    -> unique normalized (Verb, Resource) match
    -> Parameter nodes + Parameter -> Send Request edges

US / Accessors
    accepted now: *.text JSON
    blocked input: *.graphml until real producer artifacts exist
        -> ctype_graph/models.py + ctype_graph/io.py
        -> one normalized CTypeGraph model per input
        -> CType name index
        -> direct igraph query/export

message fragment + parameter edges
    -> build.py
    -> PMGraph v2 JSON

PMGraph/AppGraph JSON
    -> analysis/igraph.py
    -> igraph.Graph
    -> query and Gephi Lite GraphML

two or more PMGraph files
    -> appgraph/matching.py + appgraph/stitch.py
    -> one AppGraph JSON
    -> igraph query/export
```

### Boundary rules

- Raw input models do not leak into PMGraph or AppGraph.
- CType nodes remain `CTypeGraph` nodes, never PMGraph nodes.
- Partial ContextTrack hooks remain diagnostics rather than incomplete semantic nodes.
- Parameter keys are consumed from ParamTrack and are not recalculated.
- ParamTrack joins only to Send Request nodes because its real CSV omits message type and is produced from HTTP client-send breakpoints.
- Canonical JSON never depends on igraph serialization.
- Gephi GraphML is not accepted as a gopls machine graph.
- `contexttrack/`, `paramtrack/`, and `ctype_graph/` consume files and never invoke producers.

---

## 3. Readability Budget and Project Structure

### 3.1 Readability budget

- hard review gate: at most 3,000 physical Python lines under `src/conftamer`;
- target: at most 2,500 physical Python lines;
- target file size: at most 300 lines, with a 450-line ceiling for model-heavy files;
- target function size: at most 40 lines, with a 60-line ceiling when linear flow is clearer than extraction;
- no generic service, repository, plugin, visitor, or graph-wrapper layers;
- no duplicated PMGraph/AppGraph/CType query implementations;
- no compatibility adapters for the removed edge CSV or PMGraph v1; and
- no one-function modules unless they establish a real dependency boundary.

The budget is checked after every implementation task. If a task would exceed it, simplify data structures and consolidate duplicated code before adding another abstraction.

### 3.2 Source tree

```text
src/conftamer/
├── __init__.py
├── cli.py                     # Typer orchestration only
├── diagnostics.py             # shared structured diagnostics
├── build.py                   # source imports to PMGraph orchestration
│
├── pmgraph/
│   ├── __init__.py
│   ├── models.py              # nodes, edges, validation, semantic IDs
│   └── io.py                  # deterministic PMGraph JSON
│
├── contexttrack/
│   ├── __init__.py
│   ├── models.py              # permissive event models
│   ├── matching.py            # route and response inference
│   └── importer.py            # JSONL reading and PMGraph projection
│
├── paramtrack/
│   ├── __init__.py
│   ├── models.py              # variable-width upstream CSV records
│   └── importer.py            # CSV validation, CType validation, unique join
│
├── ctype_graph/
│   ├── __init__.py
│   ├── models.py              # normalized US/Accessors graph records
│   └── io.py                  # .text loader, CType index, gated GraphML loader
│
├── appgraph/
│   ├── __init__.py
│   ├── models.py              # AppGraph models and deterministic JSON
│   ├── matching.py            # bounded heuristic HTTP candidate matching
│   └── stitch.py              # multi-PMGraph contraction and pruning
│
└── analysis/
    ├── __init__.py
    └── igraph.py              # adapters, queries, and Gephi export
```

A package gains another module only when a current module approaches its line ceiling and contains two independently testable responsibilities.

### 3.3 Tests

```text
tests/
├── test_build.py
├── pmgraph/
│   ├── test_models.py
│   └── test_io.py
├── contexttrack/
│   ├── test_reader.py
│   ├── test_matching.py
│   └── test_importer.py
├── paramtrack/
│   └── test_importer.py
├── ctype_graph/
│   └── test_io.py
├── appgraph/
│   ├── test_models.py
│   ├── test_matching.py
│   └── test_stitch.py
├── analysis/
│   └── test_igraph.py
└── test_cli.py
```

Focused tests create minimal inputs near the tested behavior. The real files under `examples/paramtrack/` and `examples/contexttrack/` are used by explicit integration/smoke tests, not copied into every unit test.

### 3.4 Documentation

```text
docs/
├── architecture.md
├── architecture-rewrite-plan.md
└── formats/
    ├── contexttrack-jsonl.md
    ├── paramtrack-csv.md
    ├── ctype-graph-text.md
    ├── ctype-graph-graphml.md
    ├── pmgraph-v2.md
    └── appgraph-v1.md
```

Delete duplicate interface snapshots under `context/interfaces/` after replacement documentation is complete.

---

## 4. Accepted ContextTrack JSONL

### 4.1 Real event shape

The parser accepts the nested structure currently emitted by ContextTrack:

```json
{
  "kind": "Request sent",
  "pid": 63118,
  "goroutine_id": 21,
  "thread_id": 0,
  "file": "/go-conftamer/src/net/http/transport.go",
  "line": 599,
  "message": {
    "req.Method": "GET",
    "req.URL.Host": "127.0.0.1:38151",
    "req.URL.Path": "",
    "req.URL.RawQuery": ""
  },
  "context": {
    "source": "req.Context()",
    "type": "context.Context",
    "context_id": "id:1"
  },
  "request_id": {
    "method": "GET",
    "host": "127.0.0.1:38151",
    "path": ""
  },
  "api_id": "github.com/prometheus"
}
```

The five accepted event kinds remain:

- `Request sent`
- `Request received`
- `Request routed`
- `Response sent`
- `Response received`

### 4.2 Reading and grouping

- Skip blank lines.
- Preserve original line numbers.
- Continue after malformed or unsupported lines.
- Permit and retain unknown producer fields.
- Assign an internal sequence from valid input order; no producer sequence field is required.
- Group context-derived inference by `(pid, context_id)`.
- A convertible event without a context ID may create a node but not a context edge.

### 4.3 Current tool34 route and response policy

These are downstream compatibility heuristics, not correlations guaranteed by ContextTrack:

- infer a likely full route pattern when later route hops have suffix-compatible paths;
- diagnose ambiguous route-chain continuation rather than taking the first candidate as upstream analysis does;
- fall back to the concrete inbound path when no route matches;
- match responses to unconsumed requests by method/path first;
- use goroutine identity only to select a unique candidate or for the current received-response redirect fallback;
- infer wire/client duplicate hooks from order, status, method, `api_id` presence, and a successful prior match because the producer emits no hook-type field;
- never let an inferred duplicate consume a newer request; and
- omit unresolved response hooks from semantic PMGraph nodes while retaining diagnostics, even though upstream's exploratory graph may represent raw unmatched hooks.

The redirect fallback is retained specifically for traces where the client-level hook labels a redirected response with the original request path. None of these rules creates an upstream request correlation ID.

### 4.4 Tool34 message normalization

- Prefer outbound `request_id` over `message` when present; `request_id` is another `(method, host, path)` label, not a unique request identifier.
- Normalize methods to uppercase.
- Normalize an empty HTTP path to `/` only at the semantic boundary.
- Omit a Send Request without a host and report `contexttrack.request_without_host`; this is a PMGraph policy, not an upstream-invalid event. In `all-tests.jsonl`, 5,820 of 7,159 Request-sent hooks have no host and would be omitted.
- Carry a matched outbound request's `api_id` to its Receive Response node; retain a differing response-hook `api_id` only as evidence.
- Exclude `req.URL.RawQuery` and `handler` from semantic node identity. Both remain accepted raw fields; nonempty queries and handlers may be retained as evidence.
- Treat protocol `HTTP` as tool34-derived context rather than an emitted input field.
- Preserve current tool34 edge assembly: within each `(pid, context_id)` group, connect every successfully converted Receive occurrence to every later successfully converted Send occurrence. These are possible-influence edges, not exact causal correlations.

---

## 5. Accepted ParamTrack CSV

### 5.1 Targeted CSV versus removed CSV

The rewrite removes the old tool34 edge CSV accepted by `csv_graph.py`. It intentionally adds a separate adapter for upstream ParamTrack's real CSV. The two formats share only their transport and must not share models or parsing code.

### 5.2 Header and row shape

The exact header is:

```csv
API,Verb,Resource,CType,Param key
```

Each data row is variable-width:

```text
API, Verb, Resource, CType, parameter_key_1, parameter_key_2, ...
```

The header names the repeated tail by its first column only. A data row has four identity columns followed by zero or more parameter-key columns; the real sample has 108 keys. The upstream writer can emit only the four identity columns when it finds no parameter keys.

One-row example prefix:

```csv
Prometheus,GET,,/scrape.targetScraper,global.external_labels.data,labels,...
```

Multi-CType example prefixes:

```csv
Prometheus,GET,/metrics,/scrape.scrapeLoop,...
Prometheus,GET,/metrics,/discovery.Manager,...
Prometheus,GET,/metrics,/scrape.Manager,...
Prometheus,GET,/metrics,/scrape.targetScraper,...
```

### 5.3 Field meanings

- `API`: debugger-captured HTTP `User-Agent` value; it is evidence, not a complete or stable API identity.
- `Verb`: debugger-captured HTTP request method; normalize to uppercase only after truncation checks.
- `Resource`: debugger-captured HTTP request path; normalize an empty string to `/` only after truncation checks.
- `CType`: a coarse type association found while ParamTrack scans recognized CType methods across user-goroutine stacks; it may be module-prefix-shortened with a leading `/`.
- remaining columns: parameter keys that ParamTrack infers the associated CType can access and conservatively associates with that message row. They are not proof of direct per-send causality.

The current debugger uses `MaxStringLen: 10` for `API`, `Verb`, and `Resource`. ParamTrack CSV does not say whether a value reaching that limit is complete or truncated.

The CSV does not contain:

- host or authority;
- response status;
- message direction/type;
- a ContextTrack `api_id`;
- a run or process identity;
- a Send occurrence identity;
- inference kind;
- test identity;
- graph digests; or
- completeness metadata.

The tool must not invent these fields.

### 5.4 Validation

- Require the exact five-field header.
- Parse with Python's `csv` module, including quoted values.
- Treat an empty `Verb` or `CType` as a row-local unusable-record diagnostic and continue with independent rows.
- Preserve `API` even when empty because it is evidence rather than a join key.
- Permit an empty `Resource` and normalize it to `/` only for an otherwise join-eligible row.
- Treat `Verb` or `Resource` values of at least 10 characters, or values containing a debugger truncation marker, as potentially truncated; retain the row as evidence but do not use it for a Send join.
- Permit a row with no parameter-key columns; it creates no Parameter nodes or edges.
- Diagnose and omit empty parameter-key cells because the current producer can serialize them.
- If no usable parameter keys remain, retain the row only as source evidence and create no Parameter nodes or edges.
- Preserve the source line number.
- Deduplicate repeated parameter keys within a row while preserving deterministic sorted output.
- Permit several rows with the same message identity but different CTypes.
- Do not rely on data-row order; the upstream writer iterates maps and does not define it.
- Treat filenames and containing run directories as labels only; they do not participate in row identity.
- Treat a wrong header or unreadable CSV as a file-level error.
- Treat malformed data rows as line-numbered row-local diagnostics and continue with independent rows; never reinterpret them as legacy edge CSV.

### 5.5 CType validation

Preserve CType identifiers exactly as upstream emits them, including module-local names with a leading slash such as:

```text
/scrape.targetScraper
```

Tool34 preserves raw CType names and requires no additional CType metadata. Validate each name directly against the `List`/name indexes from US and Accessors before joining. A CType may validly exist only in Accessors, as `/scrape.targetScraper` does in the real example.

### 5.6 Explicit aggregate ParamTrack-to-ContextTrack heuristic

The current files contain no common run, process, test, host, source digest, or occurrence identity. Supplying them to one build is therefore an explicit caller assertion that they describe a compatible corpus. Tool34 can test candidate uniqueness within those files, but cannot prove that the observations came from the same execution.

ParamTrack `API` and ContextTrack `api_id` are not comparable:

- ParamTrack `API` is the HTTP User-Agent (`Prometheus` in the example).
- ContextTrack `api_id` is inferred from a local package (`github.com/prometheus` in the example).

The common semantic fields are therefore:

```python
@dataclass(frozen=True, order=True)
class ParamMessageKey:
    method: str
    path: str
```

Build an index over distinct semantic `SendRequestNode` instances using `(method, path)`:

1. reject the row from joining if `Verb` or `Resource` may be truncated under the current 10-character debugger limit;
2. normalize a join-eligible `Verb` to uppercase;
3. normalize an empty join-eligible `Resource` to `/`;
4. find semantic Send Request candidates with the exact method/path;
5. if exactly one candidate exists, create Parameter edges to it;
6. if no candidate exists, emit `paramtrack.no_send_match` and omit the row's edges;
7. if several candidates exist, emit `paramtrack.ambiguous_send_match` with candidate IDs and omit the row's edges.

Do not use host-independent all-candidate matching. A method/path shared by several outbound hosts is ambiguous.

Record `match_basis="unique-method-path"` on resulting evidence and emit one build-level diagnostic explaining that the association is aggregate and caller-asserted rather than occurrence-correlated.

Each accepted parameter key creates or reuses a `ParameterNode` and creates:

```text
Parameter -> Send Request
```

Rows are aggregate evidence, not occurrences. If several rows with one message identity resolve to one Send node, union their parameter-key sets before constructing edges. Deduplicate a repeated `Parameter -> Send Request` edge across CTypes while retaining every supporting CSV line reference; the CType remains recoverable from that source record. For `runs/manager-st-zero/parameters.csv`, the four rows therefore represent 226 unique candidate Parameter edges, not 562 separate edges.

---

## 6. Accepted CType Graph `.text` JSON

### 6.1 Top-level shape

The current machine format is one JSON object, commonly serialized on one physical line:

```json
{
  "Edges": [],
  "Vertices": [],
  "List": {}
}
```

Do not treat zero newline count as an empty file; parse the entire byte stream as one JSON document. Accept unknown top-level fields for forward compatibility but exclude them from normalized CType semantics.

### 6.2 Vertices

Each vertex has these known fields demonstrated upstream:

```json
{
  "Names": ["/config.RemoteWriteConfig"],
  "Methods": [
    "(*github.com/prometheus/prometheus/config.RemoteWriteConfig).Validate"
  ],
  "Tags": {
    "Name": "yaml:\"name,omitempty\""
  }
}
```

- `Names` is a nonempty list; the first name is the current node hash.
- Additional names are aliases combined into the same node.
- `Methods` is a list and may be empty.
- `Tags` is either an object or `null`.
- Methods remain fully qualified even when module-local node names are prefix-shortened.
- Unknown vertex fields are accepted for forward compatibility but do not participate in normalized CType identity.

### 6.3 Edges

```json
{
  "Source": "/model/relabel.Config",
  "Target": "/model/relabel.Action",
  "Properties": {
    "Attributes": {},
    "Weight": 0,
    "Data": [
      ["StructType.Fields", "Field:Action", "FieldList.List", "Field.Type"]
    ]
  }
}
```

- `Source` and `Target` resolve through `List` to vertices.
- `Attributes` and `Weight` are generic graph-library properties. Current CType creation does not assign domain meaning to them; the adapter accepts their current `{}` and `0` defaults but excludes them from normalized CType semantics.
- `Data` is `null` or a list of AST paths; normalize `null` to no paths.
- Each AST path is an ordered list of strings and may itself be empty.
- Several AST paths remain grouped on one CType edge; do not split them into invented parallel edges.
- Unknown edge/property fields are accepted for forward compatibility but do not participate in normalized CType identity.

### 6.4 `List`

`List` maps known type names/aliases to node hashes. In a full US/Accessors output these entries describe represented vertices; an upstream queried subgraph may retain additional source-graph mappings:

```json
{
  "/alias.Name": "/canonical.Name"
}
```

Validation requires:

- every represented vertex name has a `List` entry pointing to that vertex's first name;
- every edge endpoint is the first name of an existing vertex;
- a represented alias resolves to only one vertex;
- extra `List` entries are allowed because the upstream query tool can serialize a subgraph with a superset mapping;
- a ParamTrack CType is valid only when its resolved target vertex is present in the loaded graph;
- duplicate `(Source, Target)` records are rejected rather than silently taking one; and
- US and Accessors may contain different node sets.

The internal `CTypeGraph` preserves strings exactly as serialized. It does not claim that a shortened or external-looking name is the original fully qualified source name.

---

## 7. Planned CType GraphML Input

### 7.1 Current status

No real GraphML producer output is present under `examples/paramtrack`, and the inspected upstream serializer still writes `.text` JSON plus DOT. GraphML is therefore a required rewrite target, not yet an accepted concrete contract.

Do not implement or approve a GraphML parser from a synthetic guess about GraphML key names, structural node IDs, namespaces, defaults, or collection encodings.

### 7.2 Semantic compatibility requirement

GraphML replaces transport rather than semantics. A real GraphML file must carry enough information to normalize to the same `CTypeGraph` model as `.text`, including:

- every vertex's names/aliases, methods, and nullable tags;
- every edge's source, target, and grouped ordered AST paths; generic omitted properties normalize to their `.text` defaults;
- isolated vertices;
- the mapping from every represented type name to its node.

Equivalent `.text` and GraphML inputs must normalize to equal semantic nodes, edges, and represented name mappings.

### 7.3 Implementation gate

Before GraphML parser code is written:

1. place real producer US and Accessors GraphML files under `examples/paramtrack/static/`;
2. inspect GraphML namespaces, `<key>` declarations, graph direction, structural IDs, defaults, and value types;
3. document the exact observed mapping in `docs/formats/ctype-graph-graphml.md`;
4. decide unknown-attribute behavior from the real file rather than retaining speculative metadata; and
5. add parity tests against equivalent `.text` content.

If those files are absent, `.text` support may be completed, but the GraphML task remains blocked and the CLI must not claim GraphML compatibility.

### 7.4 Format dispatch after the gate

After the real contract is documented, `load_ctype_graph(path)` dispatches by content/extension:

- `.text` or JSON-leading content → current JSON parser;
- verified `.graphml` or XML-leading content → GraphML parser;
- `.gv`/DOT → explicit unsupported-format error.

The generic CType model requires no caller-supplied graph role. During PMGraph construction, `--unmarshaler` and `--accessors` identify how each loaded graph is used.

---

## 8. Normalized CType Graph and Exploration

```python
class CTypeNode(BaseModel):
    id: NonEmptyString
    names: tuple[NonEmptyString, ...]
    methods: tuple[NonEmptyString, ...]
    tags: Mapping[str, str] | None


class CTypeEdge(BaseModel):
    source: NonEmptyString
    target: NonEmptyString
    ast_paths: tuple[tuple[str, ...], ...]


class CTypeGraph(BaseModel):
    nodes: tuple[CTypeNode, ...]
    edges: tuple[CTypeEdge, ...]
    name_to_node: Mapping[str, str]
```

Normalization rules:

- preserve upstream node IDs and represented type-name mappings exactly in the canonical static model;
- retain module-shortened names for ParamTrack lookup and display;
- sort nodes, name mappings, methods, tags, edges, and AST paths deterministically;
- reject missing edge endpoints and conflicting represented name mappings; and
- preserve isolated vertices.

Public interfaces:

```python
def load_ctype_graph(path: str | Path) -> CTypeGraph: ...


def ctype_to_igraph(graph: CTypeGraph) -> ig.Graph: ...
```

CType igraph projection exposes aliases, methods, tags, and grouped AST paths as searchable or display attributes.

---

## 9. Target PMGraph v2

This section is a tool34-owned target design, not an upstream format. PMGraph v2 retains the current flat HTTP labels and deterministic identity rules, then adds compact provenance and the paper-derived Behavior shape selected for this rewrite.

### 9.1 Provenance

```python
class SourceArtifact(BaseModel):
    id: NonEmptyString  # "sha256:" plus the input-byte digest
    kind: Literal[
        "contexttrack-jsonl",
        "paramtrack-csv",
        "ctype-graph",
    ]


class EvidenceRef(BaseModel):
    source_id: NonEmptyString
    records: tuple[NonEmptyString, ...]  # for example, ("line:2",)
    derivation: Literal[
        "observed",
        "context-order",
        "route-inference",
        "response-correlation",
        "paramtrack-unique-method-path",
    ]
```

Source paths and raw payloads are not serialized into PMGraph. Evidence references source digests and compact record identifiers. Evidence is sorted and deduplicated and does not participate in semantic node identity.

### 9.2 Nodes

All nodes contain `id` and `evidence`. Message nodes also contain optional `api_id` and uppercase `method`.

```python
StatusCode = Annotated[int, Field(ge=100, le=999)]


class PMNodeBase(BaseModel):
    id: NonEmptyString
    evidence: tuple[EvidenceRef, ...]


class MessageNode(PMNodeBase):
    api_id: NonEmptyString | None
    method: NonEmptyString


class ParameterNode(PMNodeBase):
    type: Literal["Parameter"]
    name: NonEmptyString


class BehaviorNode(PMNodeBase):
    type: Literal["Behavior"]
    name: NonEmptyString


class ReceiveRequestNode(MessageNode):
    type: Literal["Receive"]
    message: Literal["Request"]
    pattern: NonEmptyString


class SendRequestNode(MessageNode):
    type: Literal["Send"]
    message: Literal["Request"]
    host: NonEmptyString
    path: NonEmptyString


class ReceiveResponseNode(MessageNode):
    type: Literal["Receive"]
    message: Literal["Response"]
    host: NonEmptyString
    path: NonEmptyString
    status: StatusCode


class SendResponseNode(MessageNode):
    type: Literal["Send"]
    message: Literal["Response"]
    pattern: NonEmptyString
    status: StatusCode


PMNode = (
    ParameterNode
    | BehaviorNode
    | ReceiveRequestNode
    | SendRequestNode
    | ReceiveResponseNode
    | SendResponseNode
)
```

`BehaviorNode` is paper-derived and schema-only in this release. No current importer creates one, and no `observable-behaviors` capability or inferred boundary classification is added.

### 9.3 Edges and graph

```python
class PMEdge(BaseModel):
    source: NonEmptyString
    target: NonEmptyString
    evidence: tuple[EvidenceRef, ...]


class PMGraph(BaseModel):
    format: Literal["conftamer.pmgraph"]
    version: Literal[2]
    module_id: NonEmptyString
    sources: tuple[SourceArtifact, ...]
    nodes: tuple[PMNode, ...]
    edges: tuple[PMEdge, ...]
```

A PMGraph edge records possible influence, not proven causality. It is valid only when:

```text
source = Parameter or Receive
and
target = Send or Behavior
```

The planned importers create `Parameter -> Send Request` and `Receive -> Send` edges. Edge endpoints must exist, self-edges and duplicate endpoint pairs are forbidden, node and source IDs are unique, every evidence source ID must reference `PMGraph.sources`, isolated nodes are valid, and builders merge evidence for semantically identical nodes/edges before validation.

### 9.4 Identity and serialization

Preserve the current node-ID algorithm. `make_node_id` hashes canonical JSON containing exactly `module_id` plus all semantic node fields except `id` and `evidence`, using sorted keys and compact separators, and prefixes the SHA-256 digest with `n:`. PMGraph v2 adds no undefined schema token to this payload.

Normalization remains:

- HTTP methods uppercase;
- empty HTTP paths become `/`;
- status codes are integers from 100 through 999;
- a Send Request without a host is omitted with a diagnostic;
- ContextTrack `api_id` remains optional metadata;
- Parameter keys remain exact nonempty strings; and
- nodes sort by ID, edges by `(source, target)`, evidence by its complete tuple, and output ends with one newline.

The format document must include fixed ID vectors and one complete JSON example for every node shape before importer implementation begins.

---

## 10. PMGraph Build Orchestration

```python
@dataclass(frozen=True)
class BuildResult:
    graph: PMGraph
    diagnostics: tuple[Diagnostic, ...]


def build_pmgraph(
    *,
    module_id: str,
    events: str | Path,
    paramtrack_csv: str | Path | None = None,
    unmarshaler: str | Path | None = None,
    accessors: str | Path | None = None,
) -> BuildResult: ...
```

Rules:

- ContextTrack events are required.
- Message-only PMGraphs omit ParamTrack and CType graph inputs.
- If one ParamTrack/CType input is supplied, the CSV and both graphs are all required.
- `--unmarshaler` and `--accessors` identify each graph's role during the build.
- The caller supplies `module_id` only for PMGraph identity.
- Supplying ParamTrack and ContextTrack together asserts that they describe a compatible corpus; current files cannot verify that association.
- Validate the ParamTrack CType against represented nodes in the union of US and Accessors mappings.
- Message nodes and Receive edges come from ContextTrack.
- Parameter nodes and edges come from the unique-method/path aggregate heuristic.
- Never infer a match from `API == api_id`.
- Include each source file's SHA-256 as provenance, but do not expect hashes inside upstream files.
- Record the aggregate match basis on every Parameter edge and emit one visible diagnostic describing the unverified artifact association.
- Sort diagnostics by source, line, code, and message.

Real-data smoke expectations:

1. `scrape-ok.jsonl` plus `runs/target-scraper-all/parameters.csv`:
   - empty ParamTrack Resource and ContextTrack path both normalize to `/`;
   - `GET /` identifies one semantic Send Request;
   - `/scrape.targetScraper` validates through Accessors;
   - all 108 unique parameter keys produce Parameter nodes and edges; and
   - the existing ContextTrack message relationship remains present.
2. `runs/manager-st-zero/parameters.csv` parser/aggregation validation:
   - four rows share `Prometheus,GET,/metrics`;
   - all four CTypes validate through Accessors;
   - row parameter sets union to 226 unique keys; and
   - repeated keys across CTypes retain all supporting CSV line references on one semantic edge.
3. `runs/manager-st-zero/parameters.csv` against `all-tests.jsonl`:
   - under the specified Send Request identity `(api_id, method, host, path)`, the trace contains 47 semantic `GET /metrics` nodes with 47 distinct hosts;
   - the join is ambiguous;
   - tool34 emits `paramtrack.ambiguous_send_match`; and
   - no manager Parameter edges are created from that artifact pairing.

---

## 11. AppGraph Composition Inputs

Stitching consumes two or more validated PMGraphs directly. No authority map, deployment description, application ID, or additional metadata file is required.

Module membership comes from each PMGraph's `module_id`. Rules:

- require at least two PMGraphs;
- reject duplicate `module_id` values rather than silently merging graphs for the same module;
- qualify every source node and edge by its PMGraph `module_id`;
- preserve Send hosts as message labels, but do not use them to infer a receiving module; and
- make canonical output independent of PMGraph input order and filenames.

Multiple deployed instances represented by the same `module_id` are out of scope for version 1.

---

## 12. AppGraph Matching and Contraction

### 12.1 Request candidates

This is an experimental tool34 matching policy, not paper-equivalent CompTool correlation. A Send Request and Receive Request are candidates only when:

- they belong to different modules;
- methods agree; and
- the concrete Send path satisfies the Receive node's stored pattern under the supported subset below.

Send `host` is preserved but does not identify the receiver because upstream PMGraphs provide no host-to-module mapping. ContextTrack `api_id` is also excluded: it is a coarse, currently untrusted package-derived identity and opposing endpoints need not share it.

Pattern matching supports only:

- exact path equality;
- a trailing-slash subtree pattern such as `/api/v1/`;
- one-segment Go `{name}` wildcards; and
- httprouter `:name` and terminal `*name` wildcards.

Patterns containing method/host prefixes, `{name...}`, `{$}`, mixed wildcard grammars, or unsupported syntax produce `unsupported_pattern` unless they match literally. Tool34 does not persist or claim to infer a router dialect.

### 12.2 Global mutual uniqueness

Build the complete cross-module Send/Receive candidate graph. Contract a pair only when both endpoints have degree one across all supplied PMGraphs. Leave 1:N, N:1, and N:M components uncontracted and mark them ambiguous.

Every accepted request contraction records `match_basis="unique-http-labels"` and is explicitly heuristic: uniqueness within the supplied PMGraphs does not prove network delivery or deployment ownership. Emit one stitch-level diagnostic describing that limitation.

This deliberately deviates from the paper, which assumes a shared `API_ID` and permits many Send nodes to match one Receive node. The rewrite's previously selected mutual-uniqueness policy favors omitted matches over speculative contraction.

### 12.3 Response candidates

Response matching is constrained by an accepted request match:

- reverse the matched client/server module direction;
- require labels corresponding to the accepted request pair;
- require equal status codes; and
- require mutual degree-one uniqueness.

Responses are not matched independently using only status and path.

### 12.4 Match records

```python
class QualifiedNodeRef(BaseModel):
    module_id: NonEmptyString
    node_id: NonEmptyString


class MatchInfo(BaseModel):
    status: Literal[
        "matched",
        "no_candidate",
        "ambiguous",
        "unsupported_pattern",
        "missing_request_match",
        "not_applicable",
    ]
    basis: Literal["unique-http-labels"] | None
    candidates: tuple[QualifiedNodeRef, ...]
```

Only `matched` records have a basis. Ambiguous records contain sorted candidate references; other states use an empty candidate tuple unless the format specification explicitly says otherwise.

### 12.5 Contraction model

```python
class QualifiedPMNode(BaseModel):
    module_id: NonEmptyString
    node: PMNode


class AppNode(BaseModel):
    id: NonEmptyString
    members: tuple[QualifiedPMNode, ...]
    match: MatchInfo
```

Invariants:

- Parameter and Behavior AppNodes have one member and `not_applicable`.
- Unmatched message AppNodes have one member.
- Matched AppNodes have one Send and one Receive member.
- Matched members have the same protocol and message kind.
- AppNode IDs hash canonical JSON shaped exactly as `{"members":[{"module_id":"...","node_id":"..."},...]}` with members sorted by `(module_id, node_id)` and prefix the SHA-256 digest with `a:`.
- PMGraph edges are remapped through the contraction map, deduplicated, and sorted.
- Each AppEdge retains sorted qualified source-edge references as provenance.

### 12.6 Optional unmatched pruning

The selected tool34 policy deliberately deviates from paper §6.3 by retaining unmatched nodes after stitching. `--drop-unmatched` explicitly removes singleton unmatched message nodes and their incident edges, but does not remove Parameters, Behaviors, matched communications, or recursively remove newly isolated nodes.

Parameter-reachability slicing is a separate non-destructive query operation.

---

## 13. AppGraph Model and I/O

```python
class QualifiedEdgeRef(BaseModel):
    module_id: NonEmptyString
    source: NonEmptyString
    target: NonEmptyString


class AppEdge(BaseModel):
    source: NonEmptyString
    target: NonEmptyString
    origins: tuple[QualifiedEdgeRef, ...]


class AppGraph(BaseModel):
    format: Literal["conftamer.appgraph"]
    version: Literal[1]
    module_ids: tuple[NonEmptyString, ...]
    nodes: tuple[AppNode, ...]
    edges: tuple[AppEdge, ...]
```

Validation requires sorted unique module IDs and node IDs, existing endpoints, no self-edges, canonical ordering, and valid member/match-state combinations.

```python
@dataclass(frozen=True)
class StitchResult:
    graph: AppGraph
    diagnostics: tuple[Diagnostic, ...]


def stitch_pmgraphs(graphs: Iterable[PMGraph]) -> StitchResult: ...


def stitch_pmgraph_files(paths: Sequence[str | Path]) -> StitchResult: ...


def prune_unmatched(graph: AppGraph) -> AppGraph: ...


def load_appgraph(path: str | Path) -> AppGraph: ...


def write_appgraph(graph: AppGraph, path: str | Path) -> None: ...
```

Both stitch functions require at least two PMGraphs, reject duplicate module IDs, and produce bytes independent of input order.

---

## 14. igraph Analysis and Gephi Export

```python
GraphDocument = PMGraph | AppGraph


def to_igraph(graph: GraphDocument) -> ig.Graph: ...


def find_vertices(graph: ig.Graph, query: str) -> tuple[int, ...]: ...


def influence_subgraph(
    graph: ig.Graph,
    vertices: Iterable[int],
    *,
    direction: Literal["ancestors", "descendants", "both"],
) -> ig.Graph: ...
```

Rules:

- create all vertices before edges so isolated nodes survive;
- use canonical IDs as igraph vertex `name`;
- preserve canonical order;
- never persist igraph indices;
- never reconstruct canonical JSON from igraph or Gephi output;
- exact IDs take precedence over case-insensitive substring search; and
- query results are induced subgraphs over selected vertices plus requested transitive reachability.

PMGraph/AppGraph Gephi attributes include:

```text
name, canonical_id, label, node_type, module_ids, match_status,
message, api_id, method, host, path, pattern, status, members_json
```

CType graph attributes include:

```text
name, label, names_json, methods_json, tags_json
```

CType edge attributes include:

```text
ast_paths_json
```

Nested values become canonical JSON strings; absent values become empty strings; attribute types remain homogeneous; direction is preserved; and tests re-read every export with `ig.Graph.Read_GraphML()`.

---

## 15. CLI

This repository exposes no analyzer, test-runner, or Delve command.

### Build a PMGraph

```text
conftamer build
    --module-id MODULE
    --events EVENTS.jsonl
    [--paramtrack-csv PARAMETERS.csv
     --unmarshaler UNMARSHALER.text
     --accessors ACCESSORS.text]
    --output MODULE.pmgraph.json
```

The ParamTrack CSV and two CType graphs are supplied together or omitted together.

### Stitch multiple PMGraphs

```text
conftamer stitch
    MODULE_A.pmgraph.json
    MODULE_B.pmgraph.json
    [MORE.pmgraph.json ...]
    --output APP.appgraph.json
    [--drop-unmatched]
```

### Query a canonical or CType graph

```text
conftamer query
    GRAPH.json|GRAPH.text
    QUERY
    [--direction ancestors|descendants|both]
    [--all-matches]
    --output RESULT.graphml
```

### Export a canonical or CType graph

```text
conftamer export
    GRAPH.json|GRAPH.text
    --output GRAPH.graphml
```

After Task 5 passes against real producer artifacts, verified CType `.graphml` files are added to the same build, query, and export input positions. Visualization GraphML emitted by tool34 is never accepted as PMGraph/AppGraph canonical input.

CLI rules:

- transformation logic never lives in `cli.py`;
- diagnostics go to stderr;
- concise summaries go to stdout;
- commands are noninteractive and scriptable;
- ambiguous queries fail unless `--all-matches` is supplied; and
- every loaded input is validated first.

---

## 16. Implementation Tasks

### Task 1: Rewrite guidance and document real input formats

**Files:**
- Rewrite: `AGENTS.md`
- Create: `docs/architecture.md`
- Create: `docs/formats/contexttrack-jsonl.md`
- Create: `docs/formats/paramtrack-csv.md`
- Create: `docs/formats/ctype-graph-text.md`
- Create: `docs/formats/ctype-graph-graphml.md`
- Create: `docs/formats/pmgraph-v2.md`
- Create: `docs/formats/appgraph-v1.md`

**Produces:** Repository instructions and contracts grounded in `examples/contexttrack/` and `examples/paramtrack/`.

- [ ] Rewrite `AGENTS.md` to remove legacy edge-CSV/v1 constraints while explicitly retaining targeted ParamTrack CSV input.
- [ ] Document the exact variable-width ParamTrack row.
- [ ] Document the exact `.text` `Vertices`/`Edges`/`List` shapes.
- [ ] Document only the semantic requirements and blocked status of GraphML; do not define its wire fields before real producer files exist.
- [ ] Record which real example files are and are not tool inputs.
- [ ] Record the one-row target-scraper and four-row manager fixture statistics, including the 226-key manager union.
- [ ] Complete the PMGraph v2 and AppGraph v1 format documents with every field, discriminator, validator, ID payload, and full JSON example; do not leave model types implicit.
- [ ] Add focused minimal fixtures generated from the real shapes.
- [ ] Review contracts before touching `src/`.
- [ ] Commit as `docs: align graph compiler contracts with upstream output`.

### Task 2: Add shared diagnostics and PMGraph v2

**Files:**
- Create: `src/conftamer/diagnostics.py`
- Replace: `src/conftamer/pmgraph.py` with `src/conftamer/pmgraph/__init__.py`
- Create: `src/conftamer/pmgraph/models.py`
- Create: `src/conftamer/pmgraph/io.py`
- Create: `tests/pmgraph/test_models.py`
- Create: `tests/pmgraph/test_io.py`

- [ ] Write failing tests for every complete flat node shape, including schema-only Behavior.
- [ ] Test Parameter-to-Send Request and Receive-to-Send edges.
- [ ] Test invalid node/source IDs, dangling evidence references, duplicates, missing endpoints, self-edges, and status bounds.
- [ ] Add fixed vectors proving v2 preserves the current semantic node-ID algorithm while excluding evidence.
- [ ] Test compact evidence merging and semantic ID stability.
- [ ] Implement models, IDs, normalization, and validation.
- [ ] Verify byte-identical serialization from shuffled inputs.
- [ ] Record production line count.
- [ ] Commit as `feat: define canonical PMGraph v2`.

### Task 3: Parse current ContextTrack JSONL

**Files:**
- Create: `src/conftamer/contexttrack/models.py`
- Create: `src/conftamer/contexttrack/matching.py`
- Create: `src/conftamer/contexttrack/importer.py`
- Rewrite: `src/conftamer/contexttrack/__init__.py`
- Create: `tests/contexttrack/test_reader.py`
- Create: `tests/contexttrack/test_matching.py`
- Create: `tests/contexttrack/test_importer.py`

**Produces:** Semantic message fragment, normalized Send Request index, and diagnostics.

- [ ] Migrate every distinct current parsing, route, response, duplicate-hook, redirect, and conversion test.
- [ ] Test the actual fields, including `handler` and `req.URL.RawQuery`, and the absence of invented run/occurrence fields.
- [ ] Test `(pid, context_id)` grouping and internal input sequencing.
- [ ] Test suffix-based route reconstruction as a downstream heuristic and preserve the resulting pattern without a persisted dialect field.
- [ ] Test that unresolved response hooks remain diagnostics rather than semantic nodes and that raw hook `api_id` remains source evidence.
- [ ] Implement JSONL reading and semantic projection in `importer.py`.
- [ ] Keep route/response inference in `matching.py`.
- [ ] Validate `examples/contexttrack/prometheus/scrape-ok.jsonl`.
- [ ] Confirm the documented hostless-send omission count against `all-tests.jsonl` and report it as a deliberate PMGraph policy.
- [ ] Remove superseded ContextTrack modules once tests pass.
- [ ] Record cumulative line count.
- [ ] Commit as `feat: import ContextTrack events`.

### Task 4: Parse and explore current CType `.text` graphs

**Files:**
- Create: `src/conftamer/ctype_graph/__init__.py`
- Create: `src/conftamer/ctype_graph/models.py`
- Create: `src/conftamer/ctype_graph/io.py`
- Create: `tests/ctype_graph/test_io.py`

**Produces:** Normalized CTypeGraph, alias index, and igraph projection.

- [ ] Write minimal failing tests for nodes, aliases, tags, methods, grouped AST paths, and edge endpoints.
- [ ] Parse one-line JSON regardless of newline count.
- [ ] Accept unknown input fields without adding them to semantic identity.
- [ ] Validate represented `List` entries against vertex names and edge endpoints while permitting unresolved superset entries.
- [ ] Test that module-shortened and external-looking strings are preserved exactly as serialized, without claiming their original source names.
- [ ] Normalize `Data: null` to no AST paths and treat default `Attributes`/`Weight` as nonsemantic graph-library metadata.
- [ ] Reject duplicate `(Source, Target)` records deterministically.
- [ ] Parse the real US example and assert 57 vertices, 90 edges, 58 `List` entries, and 1 nonidentity alias.
- [ ] Parse the real Accessors example and assert 582 vertices, 822 edges, 595 `List` entries, and 13 nonidentity aliases.
- [ ] Assert all four CTypes from `runs/manager-st-zero/parameters.csv` resolve only in Accessors.
- [ ] Reject `.gv` with a specific unsupported-format error.
- [ ] Record cumulative line count.
- [ ] Commit as `feat: parse gopls CType graph output`.

### Task 5: Add equivalent GraphML input after the producer-contract gate

**Prerequisite:** Real upstream `static/unmarshaler_subgraph.graphml` and `static/accessors.graphml` examples are present. Stop this task without changing parser code if either file is absent.

**Files:**
- Modify: `docs/formats/ctype-graph-graphml.md`
- Modify: `src/conftamer/ctype_graph/io.py`
- Modify: `tests/ctype_graph/test_io.py`

**Produces:** Verified GraphML and `.text` inputs normalized to equal CTypeGraph values.

- [ ] Inspect the actual GraphML namespace, key declarations, structural IDs, defaults, and value encodings.
- [ ] Replace the semantic-only GraphML document with the exact observed contract.
- [ ] Test grouped AST paths according to the producer's real representation.
- [ ] Test represented name-map reconstruction and any serialized lookup data.
- [ ] Test that the real GraphML loads without caller-supplied graph metadata.
- [ ] Compare equivalent `.text` and GraphML normalized models.
- [ ] Re-read exported CType GraphML with igraph.
- [ ] Record cumulative line count.
- [ ] Commit as `feat: accept verified gopls CType GraphML`.

### Task 6: Parse and join targeted ParamTrack CSV

**Files:**
- Create: `src/conftamer/paramtrack/__init__.py`
- Create: `src/conftamer/paramtrack/models.py`
- Create: `src/conftamer/paramtrack/importer.py`
- Create: `tests/paramtrack/test_importer.py`

**Produces:** Parameter nodes, Parameter-to-Send Request edges, and diagnostics.

- [ ] Test the exact header and variable-width rows.
- [ ] Test several CType rows for one API message, overlapping parameter sets, deterministic row-order independence, and source-line evidence union on deduplicated edges.
- [ ] Test empty Resource normalization, quoted CSV values, duplicate keys, row-local malformed data, and multiple CTypes.
- [ ] Test that potentially truncated `Verb`/`Resource` values never create Send joins.
- [ ] Test no-key rows plus leading, interior, trailing, and only-empty parameter cells; diagnose and omit empty keys without rejecting otherwise usable rows.
- [ ] Test leading-slash CType preservation and direct validation through either graph.
- [ ] Test that ParamTrack `API`, including an empty or truncated value, is retained but never compared with ContextTrack `api_id`.
- [ ] Test one unique method/path candidate creates edges.
- [ ] Test zero candidates warns and creates no edge.
- [ ] Test candidates on different hosts are ambiguous and create no edge.
- [ ] Test `runs/target-scraper-all/parameters.csv` contains 108 sorted, unique keys.
- [ ] Test `runs/manager-st-zero/parameters.csv` has four same-message rows with 133, 120, 201, and 108 keys and a 226-key union.
- [ ] Export `import_paramtrack` and document that it imports upstream output without invoking ParamTrack.
- [ ] Record cumulative line count.
- [ ] Commit as `feat: import targeted ParamTrack CSV`.

### Task 7: Build complete PMGraphs

**Files:**
- Create: `src/conftamer/build.py`
- Create: `tests/test_build.py`

- [ ] Test message-only and parameter-enriched builds.
- [ ] Test all-or-none ParamTrack/CType options.
- [ ] Test that PMGraph `module_id` does not alter raw CType identifiers.
- [ ] Test the explicit caller association and `unique-method-path` evidence marker.
- [ ] Test source-artifact and compact evidence union.
- [ ] Test deterministic output under shuffled semantic inputs.
- [ ] Run the target-scraper smoke build and assert 108 Parameter edges join the unique `GET /` Send.
- [ ] Join the manager CSV to a minimal unique `GET /metrics` ContextTrack fixture and assert 226 deduplicated Parameter edges with all supporting CSV line references.
- [ ] Pair the manager CSV with real `all-tests.jsonl`, assert 47 distinct `(api_id, method, host, path)` candidates for `GET /metrics`, and verify that ambiguity creates no Parameter edges.
- [ ] Validate generated JSON through PMGraph v2.
- [ ] Keep orchestration free of source parsing and graph algorithms.
- [ ] Record cumulative line count.
- [ ] Commit as `feat: build PMGraphs from upstream artifacts`.

### Task 8: Add igraph analysis and Gephi export

**Files:**
- Create: `src/conftamer/analysis/__init__.py`
- Create: `src/conftamer/analysis/igraph.py`
- Create: `tests/analysis/test_igraph.py`

- [ ] Test isolated nodes, canonical ID mapping, direction, and semantic attributes.
- [ ] Test exact/substring search, ambiguity, ancestors, descendants, and induced edges.
- [ ] Test optional-value sanitization and nested JSON attributes.
- [ ] Export and re-read PMGraph and CType GraphML.
- [ ] Preserve grouped AST paths as `ast_paths_json`.
- [ ] Reuse query primitives across graph types without merging domain models.
- [ ] Record cumulative line count.
- [ ] Commit as `feat: analyze and export graphs with igraph`.

### Task 9: Add direct multi-PMGraph stitching

**Files:**
- Create: `src/conftamer/appgraph/__init__.py`
- Create: `src/conftamer/appgraph/models.py`
- Create: `src/conftamer/appgraph/matching.py`
- Create: `src/conftamer/appgraph/stitch.py`
- Create: `tests/appgraph/test_models.py`
- Create: `tests/appgraph/test_matching.py`
- Create: `tests/appgraph/test_stitch.py`

- [ ] Reject fewer than two PMGraphs and duplicate module IDs.
- [ ] Derive the sorted AppGraph `module_ids` directly from the PMGraphs.
- [ ] Test exact paths, trailing-slash subtrees, `{name}`, `:name`, and terminal `*name` matching.
- [ ] Test that method/host-prefixed, `{name...}`, `{$}`, and mixed or unknown patterns remain unsupported unless literally equal.
- [ ] Test 1:1, 1:N, N:1, N:M, same-module, and no-candidate request cases.
- [ ] Test a syntactically unique but unrelated Send/Receive pair and confirm the output visibly labels the contraction heuristic rather than verified delivery.
- [ ] Test that the paper-supported many-Send-to-one-Receive case remains ambiguous under the selected deviation.
- [ ] Test that Send `host` and `api_id` do not select a receiver module.
- [ ] Test `unique-http-labels` match records and the stitch-level heuristic diagnostic.
- [ ] Test responses only after accepted request matches.
- [ ] Test fixed AppNode ID vectors, contraction across at least three PMGraphs, edge remapping, provenance, and input-order determinism.
- [ ] Test explicit unmatched pruning and idempotence as a deliberate deviation from the paper's default pruning.
- [ ] Export and re-read AppGraph GraphML.
- [ ] Confirm cumulative production code remains below 3,000 lines.
- [ ] Commit as `feat: stitch multiple PMGraphs into AppGraphs`.

### Task 10: Replace the CLI

**Files:**
- Create: `src/conftamer/cli.py`
- Modify: `src/conftamer/__init__.py`
- Modify: `pyproject.toml`
- Rewrite: `tests/test_cli.py`

- [ ] Write failing help and command smoke tests.
- [ ] Verify no analyzer, runner, or Delve command exists.
- [ ] Implement thin orchestration.
- [ ] Verify ParamTrack/CType build options are all-or-none.
- [ ] Verify `.text` and verified GraphML query/export require no CType metadata options.
- [ ] Verify diagnostics use stderr and summaries use stdout.
- [ ] Verify stitch accepts two or more PMGraphs and is input-order independent.
- [ ] Update the entry point to `conftamer.cli:app`.
- [ ] Format Python and TOML files.
- [ ] Record final pre-cleanup line count.
- [ ] Commit as `feat: replace CLI with graph compiler workflows`.

### Task 11: Remove legacy surfaces and update release material

**Files to delete:**
- `src/conftamer/csv_graph.py`
- `src/conftamer/main.py` after `cli.py` becomes the entry point
- superseded ContextTrack modules
- `tests/test_csv_graph.py`
- `tests/test_main.py` after distinct behavior moves to `tests/test_cli.py`
- superseded PMGraph/ContextTrack tests
- `examples/legacy/minimal.csv`
- `examples/legacy/synthetic.csv`
- `examples/legacy/synthetic-long.csv`
- stale files under `context/interfaces/`

**Files to update:**
- `README.md`
- `docs/technical-reference.md`
- `examples/README.md`
- `.gitignore`
- `.github/workflows/release.yml`
- `uv.lock` if metadata changes affect it

- [ ] Delete legacy code only after replacement tests pass.
- [ ] Remove `contexttrack`, `graph`, and `subgraph` commands.
- [ ] Remove `parse_contexttrack` and PMGraph v1 exports.
- [ ] Retain the standard-library CSV dependency and ParamTrack CSV documentation.
- [ ] Replace legacy examples and smoke tests with ContextTrack build, ParamTrack enrichment, CType query, multi-PMGraph stitch, query, and export workflows.
- [ ] Document that `.gv`, hierarchy, and producer logs are not inputs.
- [ ] Confirm `AGENTS.md` matches the final architecture and line budget.
- [ ] Search for removed exact-correlation assumptions, invented GraphML metadata, split AST paths, legacy edge CSV, old commands, and PMGraph v1 references.
- [ ] Run the final 3,000-line gate.
- [ ] Commit as `refactor: remove legacy CSV and PMGraph v1 workflows`.

---

## 17. Verification

Run focused tests after each task. After final changes, run fresh complete verification:

```bash
uv run pytest -q tests/pmgraph tests/test_build.py
uv run pytest -q tests/paramtrack tests/ctype_graph
uv run pytest -q tests/contexttrack tests/appgraph
uv run pytest -q tests/analysis tests/test_cli.py

uvx ruff format --check src tests
uvx tombi format --check pyproject.toml
uvx ty check
uv run pytest -q

uv run conftamer --help
uv run conftamer build --help
uv run conftamer stitch --help
uv run conftamer query --help
uv run conftamer export --help

find src/conftamer -name '*.py' -print0 | xargs -0 wc -l
git diff --check
```

Real-data checks:

```text
US .text:             57 vertices, 90 edges, 58 name mappings, 1 nonidentity alias
Accessors .text:     582 vertices, 822 edges, 595 name mappings, 13 nonidentity aliases
Target scraper CSV:   1 row, 108 unique keys
Manager CSV:          4 same-message rows, 226 unique keys across 4 Accessor CTypes
Target join:         108 Parameter -> unique GET / Send Request edges
Broad manager join:  47 distinct (api_id, method, host, path) candidates, diagnostic, 0 Parameter edges
```

Additional release checks:

- validate generated PMGraph JSON with `PMGraph.model_validate_json()`;
- validate generated AppGraph JSON with `AppGraph.model_validate_json()`;
- compare repeated output byte-for-byte;
- stitch at least three PMGraphs in different orders and compare bytes;
- confirm production Python is at most 3,000 physical lines;
- re-read every generated GraphML file with `ig.Graph.Read_GraphML()`;
- compare equivalent `.text` and real GraphML CType models only after actual producer GraphML is present;
- verify ParamTrack row-order permutations produce identical nodes, edges, and merged evidence;
- manually load visualization output in Gephi Lite;
- inspect the complete diff, including untracked files;
- confirm sibling repositories were not modified; and
- confirm no unrelated local data was added.

## 18. Compatibility and Initial Limitations

This rewrite intentionally removes:

- the legacy tool34 edge CSV parser and graph model;
- `graph` and `subgraph` commands;
- legacy CSV examples;
- PMGraph v1 JSON compatibility;
- the old `contexttrack` command name; and
- the `parse_contexttrack` compatibility import.

This rewrite intentionally retains targeted CSV support for upstream ParamTrack outputs such as `runs/target-scraper-all/parameters.csv` and `runs/manager-st-zero/parameters.csv`.

This repository intentionally does not provide:

- static analysis;
- module test execution;
- Delve integration;
- ContextTrack instrumentation;
- parameter-key inference;
- parsing of ParamTrack hierarchy/log output;
- observable Behavior discovery;
- host-insensitive ambiguous ParamTrack joins;
- deployment-aware module matching;
- many-to-one AppGraph contraction;
- replicas or multiple deployment instances of one module; or
- canonical PMGraph/AppGraph GraphML round-tripping.

The current ParamTrack join is intentionally limited by real output: the caller asserts that the artifacts belong together, and method/path must identify one semantic Send Request within them. Every resulting edge is marked as an aggregate `unique-method-path` association. Ambiguous rows are reported and omitted rather than spread across hosts.

## 19. Architectural Rule of Thumb

This repository starts at the files upstream tools actually emit and ends at queryable graphs. It accepts current ContextTrack JSONL, targeted ParamTrack CSV, and current CType `.text`; after the producer-contract gate it also accepts verified CType GraphML. It validates and normalizes inputs, builds PMGraph/AppGraph JSON, stitches PMGraphs without an additional application metadata input, exposes graphs through igraph, and writes visualization GraphML. Anything that discovers, executes, instruments, or infers upstream evidence remains outside this repository.
