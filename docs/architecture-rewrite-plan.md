# ConfTamer Ground-Up Rewrite Architecture and Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite this repository as a focused graph compiler and explorer that consumes ContextTrack and parameter-influence JSONL plus gopls US/Accessors GraphML, builds canonical PMGraphs, stitches two or more PMGraph files into one AppGraph, analyzes both graph types with `python-igraph`, and exports GraphML for Gephi Lite.

**Architecture:** Source-specific parsers validate external artifacts and project them into strict Pydantic domain models. PMGraph and AppGraph JSON are canonical; igraph is a one-way, disposable analysis representation. This repository does not run module tests, control Delve, perform static analysis, or derive parameter influence.

**Tech Stack:** Python 3.13+, Pydantic v2, python-igraph, Typer, GraphML, JSONL, pytest, Ruff, ty, Tombi, and uv.

**Spec:** This document is the approved architecture specification and implementation plan for this repository only.

## Global Constraints

- Rewrite `AGENTS.md` in the first implementation task, before changing any source file, so execution follows the new architecture rather than the legacy CSV/v1 rules.
- Delete the legacy CSV workflow rather than preserving compatibility shims.
- PMGraph v2 and the replacement CLI are intentionally breaking contracts.
- Keep the final production implementation under 3,000 physical Python lines in `src/conftamer`; exceeding that budget requires explicit approval and an explanation of why simplification is insufficient.
- Consume two gopls GraphML files: Unmarshaler Subgraph and Accessors.
- Consume raw ContextTrack JSONL and a parameter-influence JSONL sidecar.
- Join parameter evidence to Send events only through an exact shared occurrence identity.
- Use US/Accessors GraphML for evidence validation and direct graph exploration; do not insert CType nodes into PMGraph.
- Do not reproduce the external runner's CType path, YAML tag, Delve stack, or goroutine analysis.
- Include a Behavior node in the PMGraph schema, but do not invent Behavior instances from current inputs.
- Require an application manifest to bind runtime authorities to module IDs before stitching.
- Contract only mutually unique Send/Receive matches; retain and mark unmatched nodes by default.
- Keep Pydantic documents canonical and immutable; never treat igraph vertex indices as persistent identity.
- Treat GraphML exported for Gephi as a visualization projection, not canonical persistence.
- Do not add dependencies or raise the Python version without separate approval.
- Treat sibling repositories and `ConfTamer_HotNets_2026.pdf` as read-only references.
- Preserve malformed-line diagnostics and conservative ContextTrack route/response inference.

---

## 1. Scope

### 1.1 In scope

This repository owns:

- parsing and validating ContextTrack event JSONL;
- parsing and validating parameter-influence JSONL;
- parsing and validating US GraphML;
- parsing and validating Accessors GraphML;
- validating parameter evidence against ContextTrack Send occurrences and CType identities;
- constructing deterministic PMGraph v2 documents;
- converting PMGraph and AppGraph documents to igraph;
- querying canonical and static graphs;
- exporting visualization GraphML for Gephi Lite;
- validating application manifests;
- loading two or more PMGraph files in one stitch operation;
- conservatively matching and contracting Send/Receive nodes across those PMGraphs;
- constructing one deterministic AppGraph document from all supplied PMGraphs;
- diagnostics, CLI behavior, documentation, examples, tests, and release packaging for these operations; and
- removing all legacy CSV and PMGraph v1 surfaces.

### 1.2 Out of scope

This repository does not plan or implement:

- changes to gopls;
- replacement of the old Go graph library;
- maintenance of the gopls type-name-to-node-hash list;
- module test discovery or execution;
- Delve launch, control, breakpoints, stack inspection, or expression evaluation;
- goroutine ancestry tracking;
- ContextTrack instrumentation;
- assignment of run, process, event, or Send occurrence IDs;
- parameter-key derivation from CType paths and Go tags;
- creation of the parameter-influence sidecar; or
- wrappers around the external analyzers or test runner.

Those systems are external producers. This repository defines only the contracts it accepts from them.

### 1.3 External input assumptions

A parameter-enriched PMGraph build assumes that the supplied files describe the same module and observed test run:

- ContextTrack events carry stable run/process identities and Send occurrence IDs.
- Parameter-influence records reference those exact Send occurrence IDs.
- Parameter metadata records the content digests of the exact US and Accessors files used by the external runner.
- Parameter records contain already-derived configuration keys and CType evidence.

If those assumptions are false, this tool reports the inconsistency and omits unsupported Parameter edges rather than guessing a join.

---

## 2. End-to-End Data Flow in This Repository

```text
ContextTrack events.jsonl
    -> contexttrack/models.py
    -> contexttrack/importer.py + contexttrack/matching.py
    -> semantic message fragment + Send occurrence index

parameter-influence.jsonl
    -> evidence.py
    -> Parameter nodes + Parameter -> Send edges

unmarshaler.graphml + accessors.graphml
    -> static_graph.py
    -> validated StaticGraph documents + CType indexes
    -> direct igraph query/export

message fragment + exact parameter join
    -> build.py
    -> PMGraph v2 JSON

PMGraph/AppGraph JSON
    -> analysis.py
    -> igraph.Graph
    -> query and Gephi Lite GraphML

application manifest + two or more PMGraph files
    -> appgraph/matching.py + appgraph/stitch.py
    -> one AppGraph JSON
    -> igraph query/export
```

### Boundary rules

- Raw input models do not leak into PMGraph or AppGraph models.
- CType/accessor nodes remain `StaticGraph` nodes, never PMGraph nodes.
- Partial ContextTrack hooks remain observations and diagnostics rather than incomplete semantic nodes.
- Parameter keys are consumed as runner results; this tool does not recalculate them.
- Canonical JSON never depends on igraph serialization.
- Gephi GraphML is not accepted as gopls GraphML.

---

## 3. Readability Budget and Target Project Structure

### 3.1 Readability budget

The implementation must remain small enough to review as a whole:

- hard review gate: at most 3,000 physical Python lines under `src/conftamer`;
- target: at most 2,500 physical Python lines;
- target file size: at most 300 lines, with a 450-line ceiling for model-heavy files;
- target function size: at most 40 lines, with a 60-line ceiling when linear control flow is clearer than extraction;
- no generic service, repository, plugin, visitor, or graph-wrapper layers;
- no duplicated PMGraph/AppGraph/static-graph query implementations;
- no compatibility adapters for removed CSV or PMGraph v1 behavior; and
- no one-function modules unless they establish a real dependency boundary.

The budget is checked after every implementation task. If a task would exceed it, simplify data structures and consolidate duplicated code before adding another abstraction or file.

### 3.2 Lean source tree

```text
src/conftamer/
├── __init__.py
├── cli.py                 # Typer orchestration only
├── diagnostics.py         # shared structured diagnostics
├── pmgraph.py             # PMGraph models, identity, validation, and JSON I/O
├── build.py               # evidence-to-PMGraph orchestration
├── evidence.py            # parameter sidecar models, reading, and exact join
├── static_graph.py        # US/Accessors GraphML models, reading, and igraph adapter
├── analysis.py            # canonical graph adapters, query, and Gephi export
│
├── contexttrack/
│   ├── __init__.py
│   ├── models.py          # permissive upstream event models
│   ├── matching.py        # route and response inference
│   └── importer.py        # JSONL reading and PMGraph projection
│
└── appgraph/
    ├── __init__.py
    ├── models.py          # manifest and AppGraph models plus JSON I/O
    ├── matching.py        # bounded HTTP candidate matching
    └── stitch.py          # multi-PMGraph contraction and pruning
```

Split one of these files only after it approaches its line ceiling and contains two independently testable responsibilities. The tree is a maximum useful decomposition, not a requirement to create empty wrappers.

### 3.3 Tests

```text
tests/
├── test_pmgraph.py
├── test_build.py
├── test_evidence.py
├── test_static_graph.py
├── test_analysis.py
├── contexttrack/
│   ├── test_reader.py
│   ├── test_matching.py
│   └── test_importer.py
├── appgraph/
│   ├── test_models.py
│   ├── test_matching.py
│   └── test_stitch.py
├── fixtures/
│   ├── contexttrack/
│   ├── parameter_influence/
│   └── gopls/
│       ├── unmarshaler.graphml
│       └── accessors.graphml
└── test_cli.py
```

Tests cover distinct behavior rather than every internal helper combination. Shared setup is extracted only when it is shorter and clearer than local setup.

### 3.4 Normative documentation

```text
docs/
├── architecture.md
├── architecture-rewrite-plan.md
└── formats/
    ├── contexttrack-input-v1.md
    ├── parameter-influence-v1.md
    ├── gopls-graphml-v1.md
    ├── pmgraph-v2.md
    ├── application-v1.md
    └── appgraph-v1.md
```

Delete duplicate interface snapshots under `context/interfaces/` after replacement documentation is complete.

---

## 4. Shared Source Identity

### 4.1 Send occurrence key

This tool identifies a Send occurrence with:

```python
@dataclass(frozen=True, order=True)
class SendOccurrenceKey:
    run_id: str
    process_instance_id: str
    send_occurrence_id: int
```

The values are opaque producer-assigned identities. This repository validates uniqueness and equality but does not assign or interpret them.

### 4.2 Event sequence

ContextTrack events additionally contain an `event_sequence` that is monotonic within one process instance. This tool uses it only for deterministic route, response, and context-order inference.

### 4.3 Forbidden fallback joins

If a parameter record does not resolve to exactly one Send event, this tool does not fall back to:

- method/path equality;
- authority equality;
- goroutine identity;
- file order;
- test name;
- `api_id`; or
- a nearest event.

The record produces a structured diagnostic and no Parameter edge.

---

## 5. Accepted ContextTrack JSONL

The existing nested ContextTrack event structures remain permissive. For exact parameter joining, accepted Send events also contain source identity fields:

```json
{
  "kind": "Request sent",
  "run_id": "run-uuid",
  "process_instance_id": "process-uuid",
  "send_occurrence_id": 17,
  "event_sequence": 83,
  "pid": 1234,
  "goroutine_id": 42,
  "message": {
    "req.Method": "GET",
    "req.URL.Host": "inventory:8080",
    "req.URL.Path": "/items"
  },
  "context": {
    "context_id": "id:7"
  },
  "request_id": {
    "method": "GET",
    "host": "inventory:8080",
    "path": "/items"
  },
  "api_id": "example.org/frontend"
}
```

Validation rules:

- `run_id` and `process_instance_id` are nonempty strings when parameter joining is requested.
- `event_sequence` is a nonnegative integer and unique within a process.
- `send_occurrence_id` is a nonnegative integer required on tracked Send events.
- Send occurrence keys are unique.
- Receive and route events do not require a Send occurrence ID.
- Unknown fields remain allowed and retained.
- Numeric status strings are parsed to integers.
- Unsupported event kinds are reported per input line.
- Blank lines are skipped.
- Malformed lines produce diagnostics while later lines continue to parse.
- Context grouping uses `(run_id, process_instance_id, context_id)` when the identities exist.

Old captures without the additional identities may still build message-only PMGraphs. They cannot be joined with parameter sidecars and do not advertise `parameter-influence`.

---

## 6. Accepted Parameter-Influence JSONL

### 6.1 Record shapes

The sidecar is a versioned JSONL file with one metadata record, zero or more influence records, and one terminal summary record.

Metadata:

```json
{
  "record": "metadata",
  "format": "conftamer.parameter-influence",
  "version": 1,
  "module_id": "example.org/service",
  "run_id": "run-uuid",
  "unmarshaler_sha256": "sha256:...",
  "accessors_sha256": "sha256:...",
  "runner_version": "..."
}
```

Influence:

```json
{
  "record": "influence",
  "run_id": "run-uuid",
  "process_instance_id": "process-uuid",
  "send_occurrence_id": 17,
  "parameter_key": "scrape_configs.job_name",
  "ctype_ids": ["example.org/service/config.ScrapeConfig"],
  "inference": ["control-flow", "data-flow"],
  "test_id": "example.org/service/pkg.TestName"
}
```

Summary:

```json
{
  "record": "summary",
  "status": "complete",
  "processes": 4,
  "influence_records": 123
}
```

### 6.2 File validation

- Metadata is first and unique.
- Summary is last and unique.
- Metadata and influence `run_id` values agree.
- `module_id` agrees with the requested PMGraph module.
- `parameter_key` is nonempty.
- `ctype_ids` are sorted, unique, and resolve in US or Accessors.
- `inference` is a sorted, unique subset of `control-flow` and `data-flow`.
- Graph digests match the supplied GraphML bytes.
- Every influence occurrence key resolves to exactly one ContextTrack Send.
- Identical repeated influence records are deduplicated.
- Different parameter keys for one occurrence remain distinct.
- A missing or non-complete summary marks the sidecar partial.

### 6.3 Partial and invalid evidence

- A graph digest mismatch is fatal for parameter enrichment.
- A structural sidecar error rejects parameter enrichment rather than guessing around it.
- An orphan influence record produces an error and no edge.
- A Send without parameter records remains a valid unparameterized Send.
- A partial sidecar may be inspected through diagnostics but does not add the `parameter-influence` capability.

### 6.4 Semantic aggregation

Input evidence is occurrence-specific; PMGraph nodes are semantic. If several Send occurrences collapse to one semantic Send, the graph contains the union of their Parameter edges. Each edge retains all exact supporting occurrence evidence.

---

## 7. Accepted gopls GraphML

### 7.1 Two graph documents

This tool accepts separate directed multigraphs:

- `graph_kind = "unmarshaler"`; and
- `graph_kind = "accessors"`.

Shared graph attributes:

```text
ct_format = "conftamer.gopls"
ct_version = "1"
graph_kind = "unmarshaler" or "accessors"
module_id = full Go module path
producer_version = producer revision
go_version = Go toolchain version
```

### 7.2 CType vertices

```text
canonical_id       stable full qualified node identity
node_kind          "ctype"
names_json         canonical JSON array of all full qualified type names
methods_json       canonical JSON array of full qualified method names
tags_json          canonical JSON object mapping field names to raw Go tags
```

Validation requires:

- full qualified names rather than display-trimmed names;
- a nonempty, unique canonical ID;
- nonempty, unique names within a vertex;
- each alias resolving to one vertex per graph;
- shared CType payloads agreeing between US and Accessors; and
- parameter-sidecar CType IDs resolving through canonical ID or an unambiguous alias.

### 7.3 Edges

Each ordered AST path is one parallel GraphML edge:

```text
edge_kind          "contains" for US or "accesses" for Accessors
path_index         stable nonnegative integer
ast_path_json      canonical JSON array of AST path steps
```

An empty path is `[]`, not a missing attribute.

### 7.4 GraphML restrictions

- Use `canonical_id`, never a data attribute named `id`.
- Encode arrays and objects as canonical JSON strings.
- Do not rely on mixed-type GraphML attributes.
- Preserve parallel edges and isolated vertices.
- Reject malformed JSON attributes.
- Validate graph direction, graph kind, and edge endpoints.
- Reject conflicting duplicate canonical IDs.

### 7.5 Static graph role

US and Accessors serve two purposes in this repository:

1. validate CType references and source digests in parameter-influence evidence; and
2. support direct igraph search, neighborhood queries, and Gephi export.

This repository does not derive parameter keys or PMGraph edges from AST paths.

---

## 8. Canonical PMGraph v2

### 8.1 Graph shape

```python
class PMGraph(BaseModel):
    format: Literal["conftamer.pmgraph"]
    version: Literal[2]
    module_id: NonEmptyString
    capabilities: tuple[PMGraphCapability, ...]
    sources: tuple[SourceArtifact, ...]
    nodes: tuple[PMNode, ...]
    edges: tuple[PMEdge, ...]
```

Capabilities are a sorted, unique subset of:

- `observed-message-influence`
- `parameter-influence`
- `observable-behaviors`

`parameter-influence` is present only after a complete sidecar, both static graphs, and the ContextTrack run validate together.

### 8.2 Node union

```python
PMNode = (
    ParameterNode
    | BehaviorNode
    | ReceiveRequestNode
    | SendRequestNode
    | ReceiveResponseNode
    | SendResponseNode
)
```

HTTP labels are structured:

```python
class HTTPDestination(BaseModel):
    method: NonEmptyString
    authority: NonEmptyString
    path: NonEmptyString


class HTTPRoute(BaseModel):
    method: NonEmptyString
    host: NonEmptyString | None
    pattern: NonEmptyString
    dialect: Literal["literal", "serve_mux", "httprouter", "unknown"]
```

Node meanings:

- `ParameterNode`: a configuration key reported as influencing at least one Send.
- `BehaviorNode`: an explicitly supplied observable output; current inputs do not create one.
- `ReceiveRequestNode`: an inbound HTTP route.
- `SendRequestNode`: a concrete outbound HTTP destination.
- `ReceiveResponseNode`: the corresponding outbound request plus status.
- `SendResponseNode`: the corresponding inbound route plus status.

### 8.3 Edge invariant

A PMGraph edge is valid only when:

```text
source = Parameter or Receive
and
target = Send or Behavior
```

Current inputs create:

- `Parameter -> Send` from parameter-influence evidence; and
- `Receive -> Send` from ContextTrack context evidence.

Additional rules:

- endpoints must exist;
- self-edges are forbidden;
- node IDs are unique;
- duplicate edges are rejected by direct validation;
- builders merge semantically identical inputs before construction;
- isolated nodes are valid; and
- a parameter record cannot target a Receive node.

### 8.4 Identity and evidence

Semantic node IDs use SHA-256 over canonical JSON containing:

```text
schema identity + module_id + normalized semantic fields
```

Evidence does not participate in semantic identity. Evidence includes:

- source artifact digest;
- ContextTrack input line;
- exact Send occurrence key;
- parameter sidecar line;
- CType canonical IDs;
- inference kind; and
- test ID when present.

When semantic nodes or edges merge, evidence is unioned and sorted deterministically.

### 8.5 Normalization

- HTTP methods use a consistent uppercase representation.
- Empty HTTP paths normalize to `/` at the semantic boundary.
- Status codes are integers from 100 through 999.
- Missing outbound authority produces a diagnostic, not a fabricated node.
- `api_id` remains optional metadata and is not a stitching key.
- Parameter keys are preserved exactly after nonempty-string validation.
- Node and edge arrays are sorted canonically.
- JSON is UTF-8, key-sorted, deterministic, and ends with one newline.

---

## 9. ContextTrack Import

### 9.1 Reader

The JSONL reader in `contexttrack/importer.py`:

- skips blank lines;
- records original input line numbers;
- continues after malformed lines;
- computes a source digest;
- validates event-sequence uniqueness per process;
- indexes Send events by occurrence key; and
- groups events by `(run_id, process_instance_id, context_id)` when available.

### 9.2 Route inference

Route inference in `contexttrack/matching.py` preserves conservative behavior:

- methods compare case-insensitively;
- concrete paths compare exactly;
- a later routed path extends a chain only when it is a strict suffix of the prior path;
- ambiguous continuation is diagnosed and not guessed;
- a route with no inbound request is diagnosed; and
- an inbound request with no route falls back to its concrete path.

Normalized routes carry a dialect:

- Go braces or Go method/host syntax → `serve_mux`;
- `:name` or `*name` path segments → `httprouter`;
- no wildcard syntax → `literal`;
- mixed or unsupported syntax → `unknown`.

### 9.3 Response inference

Response inference in `contexttrack/matching.py` preserves current behavior:

- consume each request at most once;
- prefer exact method/path candidates;
- use goroutine identity only to select a unique candidate;
- permit the existing received-response method/goroutine redirect fallback;
- do not let endpoint-less hooks consume requests;
- suppress a client hook only after a compatible, successfully matched wire hook;
- never let a duplicate hook consume a newer request; and
- diagnose missing and ambiguous usable matches.

### 9.4 Semantic projection

```python
@dataclass(frozen=True)
class ContextTrackImport:
    fragment: PMGraphFragment
    sends: Mapping[SendOccurrenceKey, str]
    diagnostics: tuple[Diagnostic, ...]
```

The occurrence index maps each exact Send occurrence to a semantic PMGraph node ID.

Conversion:

- inbound request → Receive Request;
- outbound request → Send Request;
- matched received response → Receive Response;
- matched sent response → Send Response;
- route event → evidence only;
- unmatched or partial response → diagnostic/evidence only.

Within each context group, every resolved Receive occurrence influences every later resolved Send occurrence.

---

## 10. Parameter Evidence Join

`evidence.py` validates the parameter sidecar and static references, then performs the only accepted parameter/message join.

For each valid influence record:

1. resolve the exact `SendOccurrenceKey`;
2. retrieve the semantic Send node ID;
3. create or reuse the semantic Parameter node;
4. create `Parameter -> Send`; and
5. attach occurrence, sidecar line, CType, inference, and test evidence.

Rules:

- no fallback matching;
- no parameter derivation from static paths;
- no edge from Parameter to Receive;
- identical edges merge evidence;
- several parameters may influence one Send;
- one parameter may influence several Sends; and
- several occurrences may support one semantic edge.

---

## 11. PMGraph Build Orchestration

Primary interface:

```python
@dataclass(frozen=True)
class BuildResult:
    graph: PMGraph
    diagnostics: tuple[Diagnostic, ...]


def build_pmgraph(
    *,
    module_id: str,
    events: str | Path,
    parameter_influence: str | Path | None = None,
    unmarshaler: str | Path | None = None,
    accessors: str | Path | None = None,
) -> BuildResult: ...
```

Rules:

- ContextTrack events are required.
- Message-only PMGraphs omit all three parameter/static inputs.
- If one parameter/static input is supplied, all three are required.
- Every module ID must agree.
- The sidecar run ID must match the events.
- Sidecar graph digests must match the GraphML bytes.
- Message nodes and Receive edges come from ContextTrack.
- Parameter nodes and Parameter edges come from the exact sidecar join.
- `observed-message-influence` is present when ContextTrack conversion succeeds.
- `parameter-influence` is present only for a complete validated sidecar.
- Diagnostics are sorted by source, line, code, and message.

---

## 12. Static Graph Exploration

US and Accessors are represented by a `StaticGraph` model independent of PMGraph.

```python
def load_gopls_graphml(path: str | Path) -> StaticGraph: ...

def static_to_igraph(graph: StaticGraph) -> ig.Graph: ...

def find_static_vertices(graph: ig.Graph, query: str) -> tuple[int, ...]: ...

def static_neighborhood(
    graph: ig.Graph,
    vertices: Iterable[int],
    *,
    direction: Literal["ancestors", "descendants", "both"],
) -> ig.Graph: ...
```

The igraph projection uses:

- CType canonical IDs as vertex `name`;
- aliases, methods, and tags as searchable attributes;
- AST paths as edge attributes;
- graph kind as graph metadata; and
- all isolated vertices and parallel edges.

Static graph querying reuses generic search/neighborhood helpers but not PMGraph models.

---

## 13. Application Manifest

The manifest contains application identity and authority bindings. PMGraph artifact paths are supplied directly to the stitch operation rather than embedded in deployment metadata:

```json
{
  "format": "conftamer.application",
  "version": 1,
  "application_id": "example-app",
  "modules": [
    {
      "module_id": "example.org/frontend",
      "authorities": ["frontend:8080"]
    },
    {
      "module_id": "example.org/inventory",
      "authorities": ["inventory:8080"]
    }
  ]
}
```

Rules:

- require unique manifest module IDs;
- require each normalized authority to belong to one module;
- require two or more PMGraph files in a stitch operation;
- require every supplied PMGraph module ID to have exactly one manifest entry;
- reject duplicate supplied module IDs rather than silently merging PMGraph files;
- permit manifest modules with no inbound authority;
- preserve exact ports;
- do not infer module identity from `api_id`, paths, IP proximity, source packages, file names, or graph order; and
- retain unbound authorities as unmatched external/incomplete communication.

Multiple deployed instances of one module are out of scope for version 1. Supporting them requires a separate application-local `component_id`.

---

## 14. AppGraph Matching and Contraction

### 14.1 Request candidates

A Send Request and Receive Request are candidates only when:

- they belong to different modules;
- the manifest binds the Send authority to the Receive module;
- both are HTTP requests;
- methods agree;
- any receive host constraint agrees; and
- the concrete path satisfies the receive route according to its dialect.

Supported patterns:

- literal equality;
- Go ServeMux `{name}`, `{name...}`, `{$}`, and trailing-slash subtree behavior;
- httprouter `:name` and `*name` segments.

An `unknown` dialect permits literal equality only.

### 14.2 Conservative uniqueness

Build the complete candidate bipartite graph. Contract a pair only when both endpoints have degree one. Leave 1:N, N:1, and N:M components uncontracted and mark them ambiguous.

This prevents many-to-one contraction from creating false cross-product reachability.

### 14.3 Response candidates

Response matching is constrained by an accepted request match:

- reverse the matched client/server module direction;
- require labels corresponding to the accepted request pair;
- require equal status codes; and
- require mutual degree-one uniqueness.

Responses are not matched independently using only status and path syntax.

### 14.4 Match states

- `matched`
- `unbound_authority`
- `no_candidate`
- `ambiguous`
- `unsupported_pattern`
- `missing_request_match`
- `not_applicable`

Ambiguous states include sorted candidate references.

### 14.5 Contraction model

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
- AppGraph IDs hash the application ID and sorted member references.
- PMGraph influence edges are remapped through the contraction map, deduplicated, and sorted.
- Qualified PMGraph origin edges remain as evidence.

### 14.6 Pruning

Default stitching retains unmatched nodes.

Explicit unmatched pruning removes singleton unmatched message nodes and their incident edges. It does not:

- remove Parameters;
- remove Behaviors;
- remove matched communication nodes; or
- recursively remove newly isolated nodes.

Parameter-reachability slicing may be added as a separate query operation; it is not conflated with destructive unmatched pruning.

---

## 15. AppGraph Model and I/O

```python
class AppGraph(BaseModel):
    format: Literal["conftamer.appgraph"]
    version: Literal[1]
    application_id: NonEmptyString
    modules: tuple[AppModule, ...]
    nodes: tuple[AppNode, ...]
    edges: tuple[AppEdge, ...]
```

Validation requires:

- unique module IDs;
- unique AppNode IDs;
- existing edge endpoints;
- no self-edges;
- canonical module, node, edge, member, candidate, and evidence ordering; and
- valid member/match-state combinations.

AppGraph JSON uses the same deterministic serialization policy as PMGraph JSON.

Composition is explicitly multi-file:

```python
def stitch_pmgraphs(
    graphs: Iterable[PMGraph],
    *,
    application: ApplicationManifest,
) -> StitchResult: ...


def stitch_pmgraph_files(
    paths: Sequence[str | Path],
    *,
    manifest_path: str | Path,
) -> StitchResult: ...
```

Both functions require at least two PMGraphs, reject duplicate module IDs, and produce one AppGraph whose canonical bytes are independent of input order.

---

## 16. igraph Analysis Boundary

Canonical graph API:

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
- expose `canonical_id` separately for visualization;
- preserve canonical order;
- never persist igraph indices;
- never reconstruct canonical JSON from igraph or Gephi output; and
- return normal mutable igraph graphs for arbitrary caller analysis.

Exact canonical ID matches take precedence over case-insensitive substring search. A paper-style query returns the induced subgraph containing selected vertices plus transitive ancestors, descendants, or both.

---

## 17. Gephi Lite GraphML Projection

PMGraph/AppGraph vertices expose string-valued visualization attributes:

```text
name
canonical_id
label
node_type
module_ids
match_status
protocol
message
method
authority
path
pattern
status
members_json
```

Static graph vertices expose:

```text
name
canonical_id
label
graph_kind
names_json
methods_json
tags_json
```

PMGraph/AppGraph edges include `relation="influence"`. Static edges preserve `edge_kind`, `path_index`, and `ast_path_json`.

Rules:

- nested values become canonical JSON strings;
- absent values become empty strings, never `None` or `"None"`;
- scalar attribute types are homogeneous;
- graph direction and parallel static edges are preserved;
- format metadata remains on the graph;
- tests re-read exported files with `ig.Graph.Read_GraphML()`; and
- canonical documents are not reconstructed from GraphML.

One checked-in visualization fixture is also loaded manually in Gephi Lite before release.

---

## 18. CLI

This repository exposes no analyzer, test-runner, or Delve command.

### Build a PMGraph

```text
conftamer build
    --module-id MODULE
    --events EVENTS.jsonl
    [--parameter-influence PARAMS.jsonl
     --unmarshaler UNMARSHALER.graphml
     --accessors ACCESSORS.graphml]
    --output MODULE.pmgraph.json
```

The three parameter/static options are supplied together or omitted together.

### Stitch multiple PMGraphs into an AppGraph

```text
conftamer stitch
    APPLICATION.json
    MODULE_A.pmgraph.json
    MODULE_B.pmgraph.json
    [MORE.pmgraph.json ...]
    --output APP.appgraph.json
    [--drop-unmatched]
```

`stitch` requires at least two PMGraph files and produces exactly one AppGraph. Input file order does not affect canonical output.

### Query a canonical or static graph

```text
conftamer query
    GRAPH.json|GRAPH.graphml
    QUERY
    [--direction ancestors|descendants|both]
    [--all-matches]
    --output RESULT.graphml
```

Only versioned gopls GraphML is accepted as GraphML input.

### Export a canonical graph

```text
conftamer export
    GRAPH.json
    --output GRAPH.graphml
```

CLI rules:

- transformation logic never lives in `cli.py`;
- diagnostics go to stderr;
- concise summaries go to stdout;
- commands are noninteractive and scriptable;
- ambiguous queries print candidates and fail unless `--all-matches` is supplied; and
- every loaded document is validated first.

---

## 19. Implementation Tasks

### Task 1: Rewrite project guidance and define accepted formats

**Files:**
- Rewrite: `AGENTS.md`
- Create: `docs/architecture.md`
- Create: `docs/formats/contexttrack-input-v1.md`
- Create: `docs/formats/parameter-influence-v1.md`
- Create: `docs/formats/gopls-graphml-v1.md`
- Create: `docs/formats/pmgraph-v2.md`
- Create: `docs/formats/application-v1.md`
- Create: `docs/formats/appgraph-v1.md`
- Create: `tests/fixtures/contexttrack/joined-events.jsonl`
- Create: `tests/fixtures/parameter_influence/joined-parameters.jsonl`
- Create: `tests/fixtures/gopls/unmarshaler.graphml`
- Create: `tests/fixtures/gopls/accessors.graphml`

**Produces:** New repository instructions, consumer contracts, and representative inputs for every parser. No source implementation begins until this task is reviewed.

- [ ] Rewrite `AGENTS.md` to remove CSV/v1 constraints and establish the lean source tree, 3,000-line hard gate, external-producer boundary, multi-PMGraph stitching contract, test placement, and verification commands.
- [ ] Search `AGENTS.md` for stale legacy command names, CSV requirements, and PMGraph v1 invariants.
- [ ] Specify all required, optional, and ignored fields.
- [ ] Specify exact Send occurrence-key comparison.
- [ ] Specify sidecar metadata, influence, summary, completeness, and digest behavior.
- [ ] Specify both GraphML graph kinds and scalar encoding.
- [ ] Ensure fixture parameter records resolve to exactly one fixture Send event.
- [ ] Ensure fixture CType IDs and graph digests validate.
- [ ] Review the rewritten `AGENTS.md` and format contracts before touching `src/`.
- [ ] Commit as `docs: redefine graph compiler architecture and contracts`.

### Task 2: Add shared diagnostics and PMGraph v2

**Files:**
- Create: `src/conftamer/diagnostics.py`
- Rewrite: `src/conftamer/pmgraph.py`
- Create: `tests/test_pmgraph.py`

**Interfaces:**

```python
def make_node_id(module_id: str, semantic_fields: Mapping[str, object]) -> str: ...

def make_pmgraph(
    *,
    module_id: str,
    capabilities: Iterable[PMGraphCapability],
    sources: Iterable[SourceArtifact],
    nodes: Iterable[PMNode],
    edges: Iterable[PMEdge],
) -> PMGraph: ...

def load_pmgraph(path: str | Path) -> PMGraph: ...

def write_pmgraph(graph: PMGraph, path: str | Path) -> None: ...
```

- [ ] Write failing tests for every node and edge shape.
- [ ] Test Parameter-to-Send and Receive-to-Send edges.
- [ ] Test invalid IDs, duplicate IDs, duplicate edges, missing endpoints, self-edges, and status bounds.
- [ ] Test evidence merging and semantic ID stability.
- [ ] Implement minimal models, identity, validation, and JSON I/O in `pmgraph.py`; split it only if it exceeds the 450-line model-file ceiling.
- [ ] Verify byte-identical serialization from shuffled inputs.
- [ ] Record the current production line count and confirm the cumulative total remains under budget.
- [ ] Commit as `feat: define canonical PMGraph v2`.

### Task 3: Parse and project ContextTrack input

**Files:**
- Create: `src/conftamer/contexttrack/models.py`
- Create: `src/conftamer/contexttrack/matching.py`
- Create: `src/conftamer/contexttrack/importer.py`
- Rewrite: `src/conftamer/contexttrack/__init__.py`
- Create: `tests/contexttrack/test_reader.py`
- Create: `tests/contexttrack/test_matching.py`
- Create: `tests/contexttrack/test_importer.py`

**Produces:** Message fragment, Send occurrence index, and diagnostics.

- [ ] Migrate every distinct current parsing, route, response, duplicate-hook, redirect, and conversion test.
- [ ] Test old and correlated input identities.
- [ ] Test event-sequence and Send occurrence-key uniqueness.
- [ ] Add route-dialect classification tests.
- [ ] Implement observation parsing and inference passes.
- [ ] Implement JSONL reading and semantic projection together in `importer.py`; keep route/response inference in `matching.py`.
- [ ] Validate the representative ContextTrack fixture.
- [ ] Remove superseded `events.py`, `routes.py`, `responses.py`, and `conversion.py` once migrated tests pass.
- [ ] Record the cumulative production line count and simplify repeated inference helpers before adding files.
- [ ] Commit as `feat: import correlated ContextTrack events`.

### Task 4: Parse and explore US/Accessors GraphML

**Files:**
- Create: `src/conftamer/static_graph.py`
- Create: `tests/test_static_graph.py`

**Produces:** Validated static models, CType indexes, and igraph projections.

- [ ] Test both graph kinds field-for-field.
- [ ] Test malformed markers, versions, JSON attributes, direction, endpoints, aliases, and parallel edges.
- [ ] Test shared CType payload agreement across graphs.
- [ ] Test static search and ancestor/descendant neighborhoods.
- [ ] Test GraphML export/read-back without losing isolated nodes or AST paths.
- [ ] Keep static models, parsing, validation, CType indexing, and the small igraph adapter in one readable module.
- [ ] Record the cumulative production line count.
- [ ] Commit as `feat: parse and explore gopls GraphML`.

### Task 5: Parse and join parameter-influence input

**Files:**
- Create: `src/conftamer/evidence.py`
- Create: `tests/test_evidence.py`

**Produces:** Parameter nodes, Parameter-to-Send edges, capability state, and diagnostics.

- [ ] Test metadata/influence/summary ordering.
- [ ] Test module, run, graph-digest, CType, and occurrence validation.
- [ ] Test complete and partial sidecars.
- [ ] Test duplicate records, several parameters for one occurrence, and several occurrences for one semantic Send.
- [ ] Test orphan and non-Send references without fallback matching.
- [ ] Implement sidecar models, reading, exact join, and evidence aggregation in one module without a generic evidence framework.
- [ ] Record the cumulative production line count.
- [ ] Commit as `feat: join parameter evidence to message sends`.

### Task 6: Build complete PMGraphs

**Files:**
- Create: `src/conftamer/build.py`
- Create: `tests/test_build.py`

**Consumes:** ContextTrack import plus optional parameter sidecar and static graphs.

**Produces:** `build_pmgraph()` and `BuildResult`.

- [ ] Test message-only and parameter-enriched builds.
- [ ] Test all-or-none parameter/static options.
- [ ] Test module, run, and digest disagreement.
- [ ] Test capability and evidence union.
- [ ] Test deterministic output under shuffled records.
- [ ] Validate generated PMGraph JSON against the v2 model.
- [ ] Keep build orchestration free of source parsing and graph algorithms.
- [ ] Record the cumulative production line count.
- [ ] Commit as `feat: build PMGraphs from accepted evidence`.

### Task 7: Add canonical igraph analysis and Gephi export

**Files:**
- Create: `src/conftamer/analysis.py`
- Create: `tests/test_analysis.py`

**Produces:** PMGraph/AppGraph adapters, search, influence queries, and visualization GraphML.

- [ ] Test isolated nodes, canonical ID mapping, graph direction, and semantic attributes.
- [ ] Test exact and substring queries, ambiguity, ancestors, descendants, and induced edges.
- [ ] Test optional-value sanitization and nested JSON attributes.
- [ ] Export and re-read PMGraph GraphML through igraph.
- [ ] Reuse query and GraphML-sanitization primitives with static graphs without merging domain models.
- [ ] Keep canonical adapters, queries, and Gephi export in one module unless it reaches the file ceiling.
- [ ] Record the cumulative production line count.
- [ ] Commit as `feat: analyze and export ConfTamer graphs with igraph`.

### Task 8: Add application manifests and AppGraph stitching

**Files:**
- Create: `src/conftamer/appgraph/__init__.py`
- Create: `src/conftamer/appgraph/models.py`
- Create: `src/conftamer/appgraph/matching.py`
- Create: `src/conftamer/appgraph/stitch.py`
- Create: `tests/appgraph/test_models.py`
- Create: `tests/appgraph/test_matching.py`
- Create: `tests/appgraph/test_stitch.py`

**Interfaces:**

```python
@dataclass(frozen=True)
class StitchResult:
    graph: AppGraph
    diagnostics: tuple[Diagnostic, ...]


def stitch_pmgraphs(
    graphs: Iterable[PMGraph],
    *,
    application: ApplicationManifest,
) -> StitchResult: ...


def stitch_pmgraph_files(
    paths: Sequence[str | Path],
    *,
    manifest_path: str | Path,
) -> StitchResult: ...


def prune_unmatched(graph: AppGraph) -> AppGraph: ...

def load_appgraph(path: str | Path) -> AppGraph: ...

def write_appgraph(graph: AppGraph, path: str | Path) -> None: ...
```

- [ ] Test manifest module IDs, authorities, and conflicts independently of PMGraph file paths.
- [ ] Test rejection of zero or one PMGraph, duplicate module IDs, missing manifest bindings, and malformed PMGraph files.
- [ ] Test literal, ServeMux, httprouter, and unknown-dialect matching.
- [ ] Test request matching for 1:1, 1:N, N:1, N:M, same-module, and unbound cases.
- [ ] Test response matching constrained by request matches.
- [ ] Test contraction across three or more PMGraphs, edge remapping, evidence, and input-file-order determinism.
- [ ] Test explicit unmatched pruning and idempotence.
- [ ] Export and re-read AppGraph GraphML.
- [ ] Keep manifest/AppGraph models and JSON I/O in `models.py`, HTTP candidate logic in `matching.py`, and contraction/pruning in `stitch.py`.
- [ ] Record the cumulative production line count and confirm the total remains below the 3,000-line hard gate.
- [ ] Commit as `feat: stitch multiple PMGraphs into AppGraphs`.

### Task 9: Replace the CLI

**Files:**
- Create: `src/conftamer/cli.py`
- Modify: `src/conftamer/__init__.py`
- Modify: `pyproject.toml`
- Rewrite: `tests/test_cli.py`

**Produces:** `build`, `stitch`, `query`, and `export` commands.

- [ ] Write failing help and command smoke tests.
- [ ] Verify no analyzer, test-runner, or Delve command exists.
- [ ] Implement thin orchestration over public interfaces.
- [ ] Verify parameter/static build options are all-or-none.
- [ ] Verify diagnostics use stderr and summaries use stdout.
- [ ] Verify query accepts canonical JSON and versioned gopls GraphML.
- [ ] Verify `stitch` accepts at least two PMGraph paths, loads every file, and emits one AppGraph independent of input order.
- [ ] Update the entry point to `conftamer.cli:app`.
- [ ] Format Python and TOML files.
- [ ] Record the final pre-cleanup production line count and simplify CLI/adapter duplication before proceeding.
- [ ] Commit as `feat: replace CLI with graph compiler workflows`.

### Task 10: Remove v1 and CSV code, then update release surfaces

**Files to delete:**
- `src/conftamer/csv_graph.py`
- `src/conftamer/main.py` after `cli.py` becomes the entry point
- replaced ContextTrack v1 modules after their behavior moves to the lean ContextTrack package
- `tests/test_csv_graph.py`
- `tests/test_main.py` after its distinct CLI behavior moves to `tests/test_cli.py`
- replaced v1 PMGraph and ContextTrack tests
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
- `uv.lock` if project metadata changes affect it

- [ ] Delete legacy code only after replacement suites pass.
- [ ] Remove `contexttrack`, `graph`, and `subgraph` CLI commands.
- [ ] Remove `parse_contexttrack` and PMGraph v1 compatibility exports.
- [ ] Replace CSV examples and release smoke tests with build, static query, three-PMGraph stitch, query, and export workflows.
- [ ] Document required external input fields without planning their producers.
- [ ] Confirm the early `AGENTS.md` rewrite still matches the final implementation and line budget; make only factual corrections if verification exposed a mismatch.
- [ ] Search for stale imports, old commands, CSV text, static parameter derivation, test-runner plans, PMGraph package paths, and PMGraph v1 references.
- [ ] Run the final line-count gate after deleting superseded code; stop for approval if production code exceeds 3,000 physical lines.
- [ ] Commit as `refactor: remove legacy CSV and PMGraph v1 workflows`.

---

## 20. Verification

Run focused tests after each task. After the final change, run fresh complete verification:

```bash
uv run pytest -q tests/test_pmgraph.py tests/test_build.py
uv run pytest -q tests/test_evidence.py tests/test_static_graph.py
uv run pytest -q tests/contexttrack tests/appgraph
uv run pytest -q tests/test_analysis.py tests/test_cli.py

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

Additional release checks:

- validate generated PMGraph JSON with `PMGraph.model_validate_json()`;
- validate generated AppGraph JSON with `AppGraph.model_validate_json()`;
- compare repeated output byte-for-byte;
- stitch at least three PMGraph files in two different input orders and compare AppGraph output byte-for-byte;
- confirm total production Python is at most 3,000 physical lines and no file exceeds 450 lines without approved justification;
- re-read every generated GraphML file with `ig.Graph.Read_GraphML()`;
- query both US and Accessors fixtures;
- verify every parameter sidecar occurrence key resolves exactly once;
- manually load the visualization fixture in Gephi Lite;
- inspect the complete diff, including untracked files;
- confirm sibling repositories were not modified; and
- confirm no ignored local data was accidentally added.

## 21. Compatibility and Initial Limitations

This rewrite intentionally removes:

- legacy CSV parsing;
- `graph` and `subgraph` commands;
- PMGraph v1 JSON compatibility;
- the old `contexttrack` command name; and
- the `parse_contexttrack` compatibility import.

This repository intentionally does not provide:

- static analysis;
- module test execution;
- Delve integration;
- ContextTrack instrumentation;
- source identity assignment;
- parameter-key inference;
- observable Behavior discovery;
- application inference without a manifest;
- heuristic parameter correlation;
- heuristic module matching without authority bindings;
- many-to-one contraction;
- replicas or multiple deployment instances of one module; or
- canonical GraphML round-tripping.

Parameter-enriched PMGraph construction is available only when the supplied files satisfy the documented occurrence, digest, module, and CType-reference contracts.

## 22. Architectural Rule of Thumb

This repository starts at files and ends at graphs. It validates external evidence, builds PMGraph/AppGraph documents, exposes them through igraph, and writes visualization GraphML. Anything that discovers, executes, instruments, or infers the external evidence belongs outside this repository.
