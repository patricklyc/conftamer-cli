# ConfTamer Ground-Up Rewrite Architecture and Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current mixed ContextTrack/legacy-CSV tool with a clean pipeline that builds PMGraph v2 documents from ContextTrack JSONL and typed gopls GraphML, analyzes them with `python-igraph`, exports Gephi Lite GraphML, and stitches module PMGraphs into an AppGraph.

**Architecture:** Strict Pydantic PMGraph and AppGraph documents are the canonical representation. ContextTrack and gopls are independent input adapters that produce semantic PMGraph fragments; `python-igraph` is a one-way, disposable analysis and visualization projection. Cross-module stitching requires an explicit application manifest and contracts only mutually unique HTTP Send/Receive matches.

**Tech Stack:** Python 3.13+, Pydantic v2, python-igraph, Typer, GraphML, pytest, Ruff, ty, Tombi, and uv.

**Spec:** This document is the approved architecture specification and phased implementation plan.

## Global Constraints

- Delete the legacy CSV workflow rather than preserving compatibility shims.
- PMGraph v2 and the replacement CLI are intentionally breaking contracts.
- Parse one combined, typed GraphML document from the rewritten gopls analyzer.
- Derive configuration-key candidates in Python from the CType/accessor GraphML.
- Keep Parameters and runtime messages disconnected until a replacement for the old Delve bridge is explicitly designed.
- Include a Behavior node in the PMGraph schema, but do not invent Behavior instances from current inputs.
- Require an application manifest to bind runtime authorities to module IDs before stitching.
- Contract only mutually unique Send/Receive matches; retain and mark unmatched nodes by default.
- Keep Pydantic documents canonical and immutable; never treat igraph vertex indices as persistent identity.
- Treat Gephi GraphML as a visualization projection, not a round-trippable canonical format.
- Do not add dependencies or raise the Python version without separate approval.
- Treat `../conftamer`, `../golang.org-x-tools`, `../graph`, and `ConfTamer_HotNets_2026.pdf` as read-only references.
- Preserve malformed-line diagnostics and conservative route/response inference for ContextTrack JSONL.

---

## 1. Upstream Findings That Shape the Design

### 1.1 ContextTrack

The current ContextTrack producer emits five event kinds:

- `Request sent`
- `Request received`
- `Request routed`
- `Response sent`
- `Response received`

The implementation under `../conftamer/contexttrack` establishes these constraints:

- Context IDs are process-local and events must currently be grouped by `(pid, context_id)`.
- Route events are metadata and do not represent PMGraph nodes.
- Several route hooks may describe one nested routing chain.
- HTTP/1 instrumentation may emit both wire-level and client-level received-response hooks.
- Received responses do not carry a stable request-correlation ID; endpoint and goroutine matching are heuristics.
- `api_id` is derived from the local caller or handler package. It is not an authoritative destination-module identity.
- An outbound event has a concrete authority, but an inbound event does not identify its listener or deployment instance.
- Route patterns may use Go ServeMux syntax or httprouter syntax.

Therefore ContextTrack conversion must remain an explicit, versioned inference pipeline rather than pretending each hook is already a complete semantic message.

### 1.2 Current gopls analyzer

The current analyzer under `../golang.org-x-tools/gopls/internal/cmd/conftamer` emits two logical graphs:

1. an unmarshaler subgraph; and
2. an accessor graph.

Its graph content includes:

- CType aliases/names;
- methods;
- Go struct tags;
- graph membership;
- directed type relationships; and
- one or more ordered AST paths for an edge.

The current machine serialization is custom JSON and the visualization output is DOT. GraphML must preserve all of the semantic information currently held by the JSON form, not merely the bare type-name topology visible in DOT.

The old Delve phase supplies the missing runtime stack-to-CType join. Neither current ContextTrack JSONL nor current gopls graph data contains a shared key that can replace that join. The first PMGraph v2 release must therefore advertise that Parameter-to-message influence is unavailable rather than fabricating those edges.

### 1.3 Paper model

The paper defines a PMGraph as a per-module input-to-output influence summary:

```text
Parameter | Receive  ->  Send | Behavior
```

It defines AppGraph composition by combining matching Send and Receive nodes. The production design in this plan is more conservative than the illustrative paper algorithm:

- module ownership comes from an application manifest;
- unknown route syntax is never treated as a wildcard;
- ambiguous candidate components are not contracted; and
- unmatched endpoints remain inspectable by default.

---

## 2. Target Data Flow

```text
ContextTrack JSONL
    -> contexttrack/models.py
    -> contexttrack/reader.py
    -> contexttrack/routes.py + contexttrack/responses.py
    -> contexttrack/importer.py
    -> runtime PMGraph fragment
                                  \
                                   -> pmgraph/build.py -> PMGraph v2 JSON
                                  /
gopls typed GraphML
    -> static_analysis/graphml.py
    -> static_analysis/models.py
    -> static_analysis/parameters.py
    -> static_analysis/importer.py
    -> static Parameter fragment

PMGraph v2 JSON
    -> analysis/adapter.py
    -> igraph.Graph
    -> analysis/query.py
    -> analysis/graphml.py
    -> Gephi Lite GraphML

Application manifest + PMGraph v2 files
    -> appgraph/manifest.py
    -> appgraph/http_matching.py + appgraph/matching.py
    -> appgraph/stitch.py
    -> AppGraph JSON
    -> analysis adapter/query/export
```

### Boundary rules

- Raw source models do not leak into PMGraph models.
- CType/accessor nodes are static-analysis evidence, not PMGraph nodes.
- Partial ContextTrack hooks remain observations and diagnostics; they do not become weakly typed semantic nodes.
- Canonical JSON never depends on igraph serialization.
- Gephi GraphML is not accepted by the gopls GraphML importer.

---

## 3. Target Project Structure

```text
src/conftamer/
├── __init__.py
├── cli.py
├── diagnostics.py
│
├── pmgraph/
│   ├── __init__.py
│   ├── models.py
│   ├── identity.py
│   ├── io.py
│   └── build.py
│
├── contexttrack/
│   ├── __init__.py
│   ├── models.py
│   ├── reader.py
│   ├── routes.py
│   ├── responses.py
│   └── importer.py
│
├── static_analysis/
│   ├── __init__.py
│   ├── models.py
│   ├── graphml.py
│   ├── parameters.py
│   └── importer.py
│
├── appgraph/
│   ├── __init__.py
│   ├── models.py
│   ├── manifest.py
│   ├── http_matching.py
│   ├── matching.py
│   ├── stitch.py
│   ├── prune.py
│   └── io.py
│
└── analysis/
    ├── __init__.py
    ├── adapter.py
    ├── query.py
    └── graphml.py
```

Tests mirror these feature boundaries:

```text
tests/
├── pmgraph/
│   ├── test_models.py
│   ├── test_identity.py
│   └── test_io.py
├── contexttrack/
│   ├── test_reader.py
│   ├── test_routes.py
│   ├── test_responses.py
│   └── test_importer.py
├── static_analysis/
│   ├── test_graphml.py
│   ├── test_parameters.py
│   └── test_importer.py
├── appgraph/
│   ├── test_manifest.py
│   ├── test_http_matching.py
│   ├── test_matching.py
│   ├── test_stitch.py
│   └── test_prune.py
├── analysis/
│   ├── test_adapter.py
│   ├── test_query.py
│   └── test_graphml.py
├── fixtures/
│   └── gopls/combined.graphml
└── test_cli.py
```

Normative documentation lives in one place:

```text
docs/
├── architecture.md
├── architecture-rewrite-plan.md
└── formats/
    ├── pmgraph-v2.md
    ├── appgraph-v1.md
    ├── application-v1.md
    └── gopls-graphml-v1.md
```

Delete the duplicate interface snapshots under `context/interfaces/` after the replacement documentation is complete.

---

## 4. Canonical PMGraph v2

### 4.1 Graph shape

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

- `parameters`
- `observed-message-influence`
- `parameter-influence`
- `observable-behaviors`

A graph built from both accepted first-release inputs normally has `parameters` and `observed-message-influence`, but not the other two capabilities.

### 4.2 Node union

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

HTTP labels use structured value objects:

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

- `ParameterNode`: configuration-key candidate for this module.
- `BehaviorNode`: explicit observable output; current importers do not create one.
- `ReceiveRequestNode`: inbound route label.
- `SendRequestNode`: concrete outbound destination label.
- `ReceiveResponseNode`: corresponding outbound request label plus status.
- `SendResponseNode`: corresponding inbound route label plus status.

### 4.3 Edge invariant

A PMGraph edge is valid only when:

```text
source = Parameter or Receive
and
target = Send or Behavior
```

Additional rules:

- edge endpoints must exist;
- self-edges are forbidden;
- node IDs are unique;
- duplicate edges are rejected by direct validation;
- builders deduplicate semantically identical input before model construction;
- isolated nodes are valid.

### 4.4 Identity and evidence

Semantic IDs use SHA-256 over canonical JSON containing:

```text
schema identity + module_id + all normalized semantic fields
```

Evidence does not participate in semantic identity. Compact evidence records contain:

- source artifact digest;
- source record identity, such as `line:42` or a static GraphML canonical ID;
- derivation kind, such as `observed`, `route-inference`, `response-correlation`, or `static-key-inference`.

When semantic nodes or edges merge, evidence is unioned and sorted deterministically.

### 4.5 Normalization

- HTTP methods use a consistent uppercase representation.
- Empty HTTP paths normalize to `/` at the semantic boundary.
- Status codes are integers from 100 through 999.
- Missing outbound authority is a diagnostic and does not result in a fabricated node.
- `api_id` remains optional observed metadata and is not a stitching key.
- Node and edge arrays are sorted canonically before serialization.
- JSON is UTF-8, key-sorted, deterministic, and terminated by one newline.

---

## 5. Combined gopls GraphML Contract

### 5.1 Graph envelope

The GraphML document is a directed multigraph with scalar graph attributes:

```text
ct_format = "conftamer.gopls"
ct_version = "1"
module_id = full Go module path
producer_version = gopls/conftamer producer revision
go_version = Go toolchain version
```

### 5.2 CType vertices

```text
canonical_id       stable full qualified identity
node_kind          "ctype"
names_json         canonical JSON array of full qualified names
methods_json       canonical JSON array of full qualified method names
tags_json          canonical JSON object mapping field names to raw Go tags
in_unmarshaler     boolean
in_accessor        boolean
```

Machine output must preserve full names and must not apply the current display-only module-prefix trimming.

### 5.3 Edges

Emit one parallel GraphML edge for each ordered AST path:

```text
edge_kind          "contains" or "accesses"
layer              "unmarshaler" or "accessor"
path_index         stable integer represented consistently by the producer
ast_path_json      canonical JSON array of AST path steps
```

An empty AST path is represented as `[]`, not a missing attribute.

### 5.4 GraphML restrictions

- Use `canonical_id`, never an attribute called `id`.
- Encode arrays and maps as canonical JSON strings.
- Do not rely on GraphML mixed-type attributes.
- Preserve parallel edges.
- Reject inconsistent payloads when the same CType appears in both layers.
- Reject malformed JSON attributes rather than dropping individual records.
- Validate graph direction and edge endpoint existence.

### 5.5 Golden producer fixture

The checked-in fixture must be generated by the real rewritten producer and contain:

- aliases/multiple names;
- a CType belonging to both layers;
- multiple AST paths between one pair of types;
- YAML `inline`, ignored (`-`), explicit, and absent tags;
- an external type;
- a node with no edges; and
- at least two parameter paths sharing a CType.

---

## 6. Static Configuration-Key Derivation

`static_analysis/parameters.py` ports only the configuration-key semantics required from the current Go Delve implementation.

### 6.1 Algorithm

1. Select the unmarshaler layer.
2. Find its roots using layer-specific indegree.
3. Traverse using a bounded state `(vertex, accumulated_key)`.
4. For every edge AST path, inspect `Field:<name>` steps.
5. Resolve each field through the source CType's raw Go tag.
6. Apply YAML key rules:
   - `yaml:"name,..."` contributes `name`;
   - `yaml:",inline"` contributes no segment;
   - `yaml:"-"` excludes the field;
   - no YAML tag contributes the lowercased Go field name.
7. At each CType, identify tagged fields not represented by outgoing CType field edges and emit them as candidate parameters.
8. At graph leaves, append each leaf field; if the leaf has no fields, emit the accumulated path.
9. Deduplicate full dotted keys.
10. Attach CType/path evidence to each result.

### 6.2 Safety and failure behavior

- Detect layer cycles and report a fatal static-analysis diagnostic.
- Deduplicate repeated `(vertex, key)` states.
- Enforce a documented maximum number of traversal states and fail rather than silently truncate.
- Treat malformed tags as source-contract errors with the originating CType and field in the diagnostic.
- Do not infer JSON, TOML, environment-variable, or command-line configuration semantics from YAML data.

### 6.3 PMGraph projection

Each unique key becomes an isolated `ParameterNode`. CType and accessor nodes are not serialized as PMGraph nodes. The PMGraph records the source artifact and `parameters` capability, but not `parameter-influence`.

---

## 7. ContextTrack Importer

### 7.1 Input boundary

`contexttrack/models.py` defines permissive Pydantic models for the five event kinds. Models must:

- retain nested `message`, `context`, and `request_id` structures;
- permit unknown producer fields;
- preserve missing optional fields;
- parse numeric status strings to integers; and
- reject unsupported event kinds at the line boundary.

`contexttrack/reader.py`:

- skips blank lines;
- records original input line numbers;
- continues after malformed lines;
- computes a source artifact digest;
- assigns stable in-file event sequence numbers; and
- groups usable events by `(pid, context_id)`.

### 7.2 Route inference

`contexttrack/routes.py` preserves the existing conservative rules:

- method comparison is case-insensitive;
- concrete request paths compare exactly;
- later route paths may extend a chain only when they are a strict suffix of the previous path;
- ambiguous continuation emits `contexttrack.ambiguous_route_chain` and is not guessed;
- a route chain without an inbound request emits `contexttrack.route_without_request`;
- unmatched inbound requests fall back to their concrete path.

Normalized patterns carry a dialect:

- Go braces or Go method/host pattern syntax → `serve_mux`;
- `:name` or `*name` segments → `httprouter`;
- no wildcard syntax → `literal`;
- mixed or unsupported syntax → `unknown`.

### 7.3 Response inference

`contexttrack/responses.py` preserves the current behavior:

- requests are consumed at most once;
- exact method/path candidates are preferred;
- goroutine identity selects only a unique candidate;
- received responses may use method/goroutine fallback for redirected paths;
- endpoint-less hooks do not consume requests;
- a client hook is suppressed as a duplicate only after a compatible, successfully matched wire hook;
- a duplicate hook never consumes a newer request;
- missing and ambiguous usable matches produce diagnostics.

### 7.4 Semantic projection

`contexttrack/importer.py` converts only complete logical occurrences:

- inbound request → Receive Request;
- outbound request → Send Request;
- matched received response → Receive Response;
- matched sent response → Send Response;
- route event → evidence only;
- unmatched/partial response → evidence and diagnostic only.

Within each context group, every resolved Receive occurrence influences every later resolved Send occurrence.

---

## 8. PMGraph Build Orchestration

Primary interface:

```python
@dataclass(frozen=True)
class BuildResult:
    graph: PMGraph
    diagnostics: tuple[Diagnostic, ...]


def build_pmgraph(
    *,
    module_id: str | None = None,
    contexttrack: str | Path | None = None,
    static_analysis: str | Path | None = None,
) -> BuildResult: ...
```

Rules:

- require at least one input;
- require `module_id` for ContextTrack-only input;
- derive `module_id` from static GraphML when omitted;
- reject disagreement between explicit and GraphML module IDs;
- merge semantic nodes, edges, evidence, source artifacts, and capabilities;
- sort diagnostics by source, line, code, and message;
- emit `build.parameter_message_bridge_unavailable` when both source types are present;
- never create a synthetic static/runtime bridge.

---

## 9. Application Manifest

The manifest is the authoritative deployment binding used for stitching:

```json
{
  "format": "conftamer.application",
  "version": 1,
  "application_id": "example-app",
  "modules": [
    {
      "module_id": "example.org/frontend",
      "pmgraph": "frontend.pmgraph.json",
      "authorities": ["frontend:8080"]
    },
    {
      "module_id": "example.org/inventory",
      "pmgraph": "inventory.pmgraph.json",
      "authorities": ["inventory:8080"]
    }
  ]
}
```

Rules:

- resolve PMGraph paths relative to the manifest;
- require unique module IDs;
- require each normalized authority to belong to exactly one module;
- verify each PMGraph's module ID;
- permit modules with no inbound authority;
- preserve exact ports;
- do not infer module identity from `api_id`, source package, route path, IP proximity, or graph order;
- treat unbound outbound authorities as unmatched external/incomplete communication.

Multiple deployed instances of one module are out of scope for version 1. Supporting them requires a separate application-local `component_id` rather than overloading `module_id`.

---

## 10. AppGraph Matching and Contraction

### 10.1 Request candidates

A Send Request and Receive Request are candidates only when:

- they belong to different modules;
- the manifest binds the Send authority to the Receive module;
- both are HTTP requests;
- methods agree;
- any receive host constraint agrees; and
- the concrete path satisfies the receive route according to its declared dialect.

Pattern matching supports only documented forms:

- literal equality;
- Go ServeMux `{name}`, `{name...}`, `{$}`, and trailing-slash subtree behavior;
- httprouter `:name` and `*name` path segments.

An `unknown` dialect permits literal equality only.

### 10.2 Conservative uniqueness

Build the complete candidate bipartite graph. Contract a pair only when both endpoints have degree one. Leave all 1:N, N:1, and N:M components uncontracted and mark them ambiguous.

This mutual-degree-one rule prevents a many-to-one contraction from introducing cross-product reachability between otherwise unrelated senders.

### 10.3 Response candidates

Response matching is constrained by an accepted request match:

- reverse the matched client/server module direction;
- require response request labels corresponding to the matched request pair;
- require equal status codes; and
- require mutual degree-one uniqueness.

Responses are never matched independently using only status and path syntax.

### 10.4 Match states

Record deterministic match information:

- `matched`
- `unbound_authority`
- `no_candidate`
- `ambiguous`
- `unsupported_pattern`
- `missing_request_match`
- `not_applicable`

Ambiguous states include sorted candidate references.

### 10.5 Contraction model

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
- Matched AppNodes have exactly two members: one Send and one Receive.
- Matched members have the same protocol and message kind.
- AppGraph node IDs hash the application ID and sorted qualified member references.
- PMGraph influence edges are remapped through the contraction map, deduplicated, and sorted.
- Originating qualified PMGraph edges remain as evidence.

### 10.6 Pruning

Default stitching is lossless and retains unmatched nodes.

An explicit unmatched-pruning operation removes singleton unmatched message nodes and their incident edges. It does not:

- remove Parameters;
- remove Behaviors;
- remove matched communication nodes;
- recursively remove newly isolated nodes; or
- prune by Parameter reachability.

Parameter-reachability pruning is invalid until a Parameter-to-message bridge exists.

---

## 11. AppGraph Model and I/O

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

---

## 12. igraph Analysis Boundary

Public API:

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

- create all vertices before adding edges so isolated nodes survive;
- use canonical node IDs as igraph vertex `name`;
- expose `canonical_id` separately for visualization;
- preserve canonical node and edge order;
- never persist igraph indices;
- never reconstruct canonical JSON from igraph or Gephi output;
- return a normal mutable `ig.Graph` so callers can use any igraph algorithm.

Search examines curated semantic attributes, not arbitrary Python object representations. Exact canonical ID matches take precedence over case-insensitive substring matches.

The paper-style query result is the induced subgraph containing the selected vertices plus their transitive ancestors, descendants, or both.

---

## 13. Gephi Lite GraphML Projection

`analysis/graphml.py` exports a sanitized copy of the igraph projection.

Every vertex includes string-valued attributes:

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

Every edge includes:

```text
relation = "influence"
origin_count
```

Rules:

- nested/list values become canonical JSON strings;
- absent optional values become empty strings, never `None` or `"None"`;
- scalar attribute types are homogeneous;
- graph direction is preserved;
- PMGraph and AppGraph format metadata is retained as graph attributes;
- exported GraphML is read back with `ig.Graph.Read_GraphML()` in tests;
- canonical models are not reconstructed from the read-back graph.

A small exported fixture must also be loaded manually in Gephi Lite before release because igraph read-back cannot validate browser rendering and labels.

---

## 14. CLI

Replace the old commands with four noninteractive workflows.

### Build a PMGraph

```text
conftamer build
    [--events TRACE.jsonl]
    [--static-analysis STATIC.graphml]
    [--module-id MODULE]
    --output MODULE.pmgraph.json
```

### Stitch an AppGraph

```text
conftamer stitch
    APPLICATION.json
    --output APP.appgraph.json
    [--drop-unmatched]
```

### Query either canonical graph

```text
conftamer query
    GRAPH.json
    QUERY
    [--direction ancestors|descendants|both]
    [--all-matches]
    --output RESULT.graphml
```

An ambiguous text query prints candidates and exits nonzero unless `--all-matches` is supplied.

### Export either canonical graph

```text
conftamer export
    GRAPH.json
    --output GRAPH.graphml
```

CLI rules:

- transformation logic never lives in `cli.py`;
- diagnostics go to stderr;
- concise graph summaries go to stdout;
- output paths are explicit rather than inferred from obsolete CSV behavior;
- loading a canonical graph always validates it first.

---

## 15. Implementation Tasks

### Task 1: Freeze format contracts and the producer fixture

**Files:**
- Create: `docs/architecture.md`
- Create: `docs/formats/pmgraph-v2.md`
- Create: `docs/formats/appgraph-v1.md`
- Create: `docs/formats/application-v1.md`
- Create: `docs/formats/gopls-graphml-v1.md`
- Create: `tests/fixtures/gopls/combined.graphml`

**Produces:** Normative contracts consumed by every later task.

- [ ] Write the four format documents with all fields and invariants from this plan.
- [ ] Obtain a golden GraphML file from the rewritten gopls producer.
- [ ] Check that the fixture contains aliases, overlapping graph membership, parallel AST paths, tag cases, an external type, and an isolated node.
- [ ] Review the producer fixture before implementing its parser.
- [ ] Commit as `docs: define PMGraph v2 input and output contracts`.

### Task 2: Add shared diagnostics and PMGraph v2

**Files:**
- Create: `src/conftamer/diagnostics.py`
- Create: `src/conftamer/pmgraph/__init__.py`
- Create: `src/conftamer/pmgraph/models.py`
- Create: `src/conftamer/pmgraph/identity.py`
- Create: `src/conftamer/pmgraph/io.py`
- Create: `tests/pmgraph/test_models.py`
- Create: `tests/pmgraph/test_identity.py`
- Create: `tests/pmgraph/test_io.py`

**Interfaces:**

```python
def make_node_id(module_id: str, node: PMNodeWithoutID) -> str: ...

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

- [ ] Write failing tests for every node shape and edge direction.
- [ ] Write failing tests for invalid IDs, duplicate IDs, duplicate edges, missing endpoints, self-edges, status bounds, and noncanonical ordering.
- [ ] Write failing tests for evidence merging and semantic ID stability.
- [ ] Implement the minimal models and builders.
- [ ] Verify byte-identical serialization from shuffled inputs.
- [ ] Commit as `feat: define canonical PMGraph v2`.

### Task 3: Rebuild ContextTrack import

**Files:**
- Create: `src/conftamer/contexttrack/models.py`
- Create: `src/conftamer/contexttrack/reader.py`
- Rewrite: `src/conftamer/contexttrack/routes.py`
- Rewrite: `src/conftamer/contexttrack/responses.py`
- Create: `src/conftamer/contexttrack/importer.py`
- Rewrite: `src/conftamer/contexttrack/__init__.py`
- Create: `tests/contexttrack/test_reader.py`
- Create: `tests/contexttrack/test_routes.py`
- Create: `tests/contexttrack/test_responses.py`
- Create: `tests/contexttrack/test_importer.py`

**Produces:** A runtime PMGraph fragment plus diagnostics.

- [ ] Migrate every distinct current parsing, route, response, duplicate-hook, redirect, and conversion test.
- [ ] Add observation/evidence assertions for partial and unmatched hooks.
- [ ] Add route-dialect classification tests.
- [ ] Implement the reader and inference passes.
- [ ] Implement semantic projection and context-derived influence edges.
- [ ] Validate the checked-in small real trace through PMGraph v2.
- [ ] Commit as `feat: import ContextTrack traces into PMGraph v2`.

### Task 4: Parse combined gopls GraphML

**Files:**
- Create: `src/conftamer/static_analysis/__init__.py`
- Create: `src/conftamer/static_analysis/models.py`
- Create: `src/conftamer/static_analysis/graphml.py`
- Create: `tests/static_analysis/test_graphml.py`

**Produces:** A validated static-analysis graph preserving both layers and all AST paths.

- [ ] Write failing tests against the producer fixture.
- [ ] Test malformed graph markers, versions, JSON attributes, direction, endpoints, memberships, and parallel edges.
- [ ] Implement igraph GraphML reading followed by strict Pydantic validation.
- [ ] Compare every fixture semantic field with an explicit expected model.
- [ ] Commit as `feat: parse typed gopls GraphML`.

### Task 5: Derive Parameter candidates

**Files:**
- Create: `src/conftamer/static_analysis/parameters.py`
- Create: `src/conftamer/static_analysis/importer.py`
- Create: `tests/static_analysis/test_parameters.py`
- Create: `tests/static_analysis/test_importer.py`

**Produces:** Isolated PMGraph Parameter nodes with static evidence.

- [ ] Write failing tests for explicit, default, inline, ignored, and malformed YAML tags.
- [ ] Write failing tests for aliases, multiple AST paths, non-CType fields, leaf fields, cycles, and traversal-state limits.
- [ ] Implement the bounded key-propagation algorithm.
- [ ] Project unique keys to deterministic Parameter nodes.
- [ ] Assert that no Parameter-to-message edge is produced.
- [ ] Commit as `feat: derive configuration parameters from static analysis`.

### Task 6: Build complete PMGraphs

**Files:**
- Create: `src/conftamer/pmgraph/build.py`
- Add tests to: `tests/pmgraph/test_build.py`

**Consumes:** ContextTrack and static-analysis fragments.

**Produces:** `build_pmgraph()` and `BuildResult`.

- [ ] Test runtime-only, static-only, and combined builds.
- [ ] Test module-ID derivation and disagreement.
- [ ] Test capability union and source/evidence deduplication.
- [ ] Test the explicit missing-bridge diagnostic.
- [ ] Implement orchestration without source-specific logic.
- [ ] Commit as `feat: build PMGraphs from runtime and static evidence`.

### Task 7: Add igraph analysis and Gephi export

**Files:**
- Create: `src/conftamer/analysis/__init__.py`
- Create: `src/conftamer/analysis/adapter.py`
- Create: `src/conftamer/analysis/query.py`
- Create: `src/conftamer/analysis/graphml.py`
- Create: `tests/analysis/test_adapter.py`
- Create: `tests/analysis/test_query.py`
- Create: `tests/analysis/test_graphml.py`

**Produces:** `to_igraph()`, vertex search, influence queries, and visualization GraphML.

- [ ] Test isolated nodes, canonical ID mapping, direction, and attributes.
- [ ] Test exact and substring queries, ambiguity, ancestors, descendants, and induced edges.
- [ ] Test optional-value sanitization and nested JSON attributes.
- [ ] Export and re-read PMGraph GraphML through igraph.
- [ ] Commit as `feat: analyze and export PMGraphs with igraph`.

### Task 8: Add application manifests and AppGraph stitching

**Files:**
- Create: `src/conftamer/appgraph/__init__.py`
- Create: `src/conftamer/appgraph/models.py`
- Create: `src/conftamer/appgraph/manifest.py`
- Create: `src/conftamer/appgraph/http_matching.py`
- Create: `src/conftamer/appgraph/matching.py`
- Create: `src/conftamer/appgraph/stitch.py`
- Create: `src/conftamer/appgraph/prune.py`
- Create: `src/conftamer/appgraph/io.py`
- Create: `tests/appgraph/test_manifest.py`
- Create: `tests/appgraph/test_http_matching.py`
- Create: `tests/appgraph/test_matching.py`
- Create: `tests/appgraph/test_stitch.py`
- Create: `tests/appgraph/test_prune.py`

**Interfaces:**

```python
@dataclass(frozen=True)
class StitchResult:
    graph: AppGraph
    diagnostics: tuple[Diagnostic, ...]


def stitch_application(manifest_path: str | Path) -> StitchResult: ...

def prune_unmatched(graph: AppGraph) -> AppGraph: ...

def load_appgraph(path: str | Path) -> AppGraph: ...

def write_appgraph(graph: AppGraph, path: str | Path) -> None: ...
```

- [ ] Test manifest paths, module IDs, normalized authorities, and conflicts.
- [ ] Test literal, ServeMux, httprouter, and unknown-dialect matching.
- [ ] Test request matching for 1:1, 1:N, N:1, N:M, same-module, and unbound-authority cases.
- [ ] Test that response matching is constrained by request matches.
- [ ] Test contraction, evidence, edge remapping, and input-order determinism.
- [ ] Test explicit pruning and idempotence.
- [ ] Export and re-read AppGraph GraphML through the analysis package.
- [ ] Commit as `feat: stitch PMGraphs into AppGraphs`.

### Task 9: Replace the CLI

**Files:**
- Create: `src/conftamer/cli.py`
- Modify: `src/conftamer/__init__.py`
- Modify: `pyproject.toml`
- Rewrite: `tests/test_cli.py`

**Produces:** `build`, `stitch`, `query`, and `export` commands.

- [ ] Write failing help and command smoke tests.
- [ ] Implement thin orchestration over public package interfaces.
- [ ] Verify diagnostics use stderr and summaries use stdout.
- [ ] Verify query ambiguity is noninteractive and scriptable.
- [ ] Update the package entry point to `conftamer.cli:app`.
- [ ] Format Python and TOML files.
- [ ] Commit as `feat: replace CLI with PMGraph and AppGraph workflows`.

### Task 10: Remove v1 and CSV code, then update release surfaces

**Files to delete:**
- `src/conftamer/csv_graph.py`
- `src/conftamer/pmgraph.py`
- replaced ContextTrack v1 modules
- `tests/test_csv_graph.py`
- replaced v1 PMGraph and ContextTrack tests
- `examples/legacy/minimal.csv`
- `examples/legacy/synthetic.csv`
- `examples/legacy/synthetic-long.csv`
- stale files under `context/interfaces/`

**Files to update:**
- `README.md`
- `docs/technical-reference.md`
- `examples/README.md`
- `AGENTS.md`
- `.gitignore`
- `.github/workflows/release.yml`
- `uv.lock` if project metadata changes affect it

- [ ] Delete legacy code only after all replacement suites pass.
- [ ] Remove `contexttrack`, `graph`, and `subgraph` CLI commands.
- [ ] Remove `parse_contexttrack` and PMGraph v1 compatibility exports.
- [ ] Replace CSV examples and release smoke tests with static/runtime build, stitch, query, and export workflows.
- [ ] Document the missing Parameter-to-message bridge and absent Behavior producer prominently.
- [ ] Search for stale imports, command names, CSV text, and version-1 PMGraph references.
- [ ] Commit as `refactor: remove legacy CSV and PMGraph v1 workflows`.

---

## 16. Verification

Run focused tests after each task. After the final change, run fresh complete verification:

```bash
uv run pytest -q tests/pmgraph
uv run pytest -q tests/contexttrack
uv run pytest -q tests/static_analysis
uv run pytest -q tests/appgraph
uv run pytest -q tests/analysis
uv run pytest -q tests/test_cli.py

uvx ruff format --check src tests
uvx tombi format --check pyproject.toml
uvx ty check
uv run pytest -q

uv run conftamer --help
uv run conftamer build --help
uv run conftamer stitch --help
uv run conftamer query --help
uv run conftamer export --help

git diff --check
```

Additional release checks:

- validate generated PMGraph JSON with `PMGraph.model_validate_json()`;
- validate generated AppGraph JSON with `AppGraph.model_validate_json()`;
- compare repeated output byte-for-byte;
- re-read every generated GraphML file with `ig.Graph.Read_GraphML()`;
- manually load the visualization fixture in Gephi Lite;
- inspect the complete diff, including untracked files;
- confirm that sibling upstream repositories were not modified; and
- confirm no generated output under ignored `data/` was accidentally added.

## 17. Compatibility and Known Initial Limitations

This rewrite intentionally removes:

- legacy CSV parsing;
- `graph` and `subgraph` commands;
- PMGraph v1 JSON compatibility;
- the old `contexttrack` command name; and
- the `parse_contexttrack` compatibility import.

The first PMGraph v2 release intentionally does not provide:

- Parameter-to-message influence;
- observable Behavior discovery;
- application inference without a manifest;
- heuristic cross-module contraction without authority bindings;
- many-to-one contraction;
- replicas or multiple deployment instances of one module; or
- canonical GraphML round-tripping.

These limitations are represented through capabilities, diagnostics, and unmatched states rather than hidden by guessed edges.

## 18. Architectural Rule of Thumb

Source-specific complexity stays at the import boundaries. PMGraph and AppGraph contain only semantic influence nodes and edges. Pydantic JSON is canonical; igraph is the analysis engine; GraphML is the visualization format.
