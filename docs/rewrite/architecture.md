# ConfTamer target architecture

This document defines the stable target model and design decisions for the
tool34 rewrite. It describes what this repository owns and the contracts its
implementation must preserve. Upstream observations and their provenance live
in [Input formats](input-formats.md); ordered implementation work lives in the
[Implementation plan](implementation-plan.md).

## Goal

ConfTamer is a focused graph compiler and explorer. It consumes ContextTrack
message traces, ParamTrack parameter observations, and gopls CType graphs;
builds canonical PMGraphs; stitches two or more PMGraphs into an AppGraph;
projects canonical and CType graphs into `python-igraph`; and exports GraphML
for Gephi Lite.

The implementation uses Python 3.13+, Pydantic v2, python-igraph, Typer, the
standard `csv` and `json` modules, pytest, Ruff, ty, Tombi, and uv. Adding a
dependency or raising the Python version requires separate approval.

## Scope and boundaries

This repository owns:

- validation and normalization of the accepted upstream files;
- conservative ContextTrack route and response inference;
- validation of ParamTrack CType references against US and Accessors graphs;
- aggregate matching of ParamTrack rows to unique semantic Send Requests;
- deterministic PMGraph v2 and AppGraph v1 documents;
- multi-PMGraph stitching and optional unmatched-node pruning;
- igraph conversion, graph queries, and visualization GraphML export;
- diagnostics, CLI behavior, tests, examples, documentation, and packaging;
- removal of the legacy edge-CSV, PMGraph v1, and old CLI surfaces.

This repository does not own or invoke:

- gopls analysis or replacement of its graph library;
- test discovery or execution;
- Delve launch, breakpoints, stack inspection, or goroutine analysis;
- ContextTrack instrumentation;
- ParamTrack parameter-key, CType-path, or YAML-tag inference;
- production of upstream files; or
- conversion of ParamTrack hierarchy or log output.

Sibling repositories and `ConfTamer_HotNets_2026.pdf` are read-only references.
Source adapters consume files; they do not wrap producers.

## Global design decisions

- PMGraph v2 and the replacement CLI are intentionally breaking contracts.
- Delete only tool34's legacy edge-CSV workflow. Upstream ParamTrack CSV is a
  separate targeted input and remains supported.
- Checked-in files under `examples/` are executable source-of-truth inputs, not
  prose snapshots. Tests may derive small fixtures from them and integration
  tests should exercise them directly.
- Current gopls `.text` JSON is accepted. CType GraphML input remains blocked
  until real producer files establish its transport contract.
- Supplying ParamTrack and ContextTrack inputs together is the caller's
  assertion that they describe a compatible corpus; current inputs have no
  shared verifiable run identity.
- ParamTrack joins are explicitly aggregate and heuristic. They use a unique
  normalized method/path Send identity and never compare ParamTrack `API` with
  ContextTrack `api_id`.
- CType graphs validate ParamTrack references and support direct exploration;
  CType nodes are never inserted into PMGraph.
- The paper's minimal Behavior node is included in PMGraph v2, but no Behavior
  is created until a producer contract exists.
- Stitching consumes two or more PMGraphs directly. It requires no application,
  deployment, or authority manifest.
- Cross-module contractions use HTTP labels only, are always marked heuristic,
  and require mutual uniqueness.
- Unmatched nodes are retained and marked by default.
- Canonical Pydantic documents are immutable. igraph vertex indices are never
  persistent identities.
- GraphML is a visualization projection, not canonical persistence.
- Malformed-line diagnostics and conservative ContextTrack inference remain
  visible.

## Data flow

```text
ContextTrack events.jsonl
    -> contexttrack models, reader, and matching
    -> semantic message fragment
    -> Send Request index keyed by normalized (method, path)

ParamTrack parameters.csv
    -> variable-width CSV adapter
    -> CType validation through US and Accessors
    -> unique normalized (method, path) Send match
    -> Parameter nodes and Parameter -> Send Request edges

US / Accessors
    accepted: *.text JSON
    blocked:  *.graphml until the producer-contract gate passes
        -> one normalized CTypeGraph per input
        -> CType name index and direct exploration

message fragment + parameter edges
    -> PMGraph v2 JSON

PMGraph/AppGraph JSON or CTypeGraph
    -> igraph.Graph
    -> query and Gephi Lite GraphML

two or more PMGraph files
    -> cross-module candidate matching
    -> conservative contraction
    -> one AppGraph v1 JSON
```

Boundary rules:

- Raw input models do not leak into PMGraph or AppGraph.
- CType nodes remain in `CTypeGraph`.
- Partial ContextTrack hooks do not become incomplete semantic nodes.
- Parameter keys are consumed from ParamTrack and are not recalculated.
- ParamTrack joins only to Send Request nodes.
- Canonical JSON never depends on igraph serialization.
- Gephi GraphML is not accepted as PMGraph or AppGraph input.

## Diagnostics and provenance

Canonical output models are immutable and reject unknown fields:

```python
class CanonicalModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
```

Source paths and raw payloads are not serialized into canonical graphs. Each
input contributes a byte digest:

```python
class SourceArtifact(CanonicalModel):
    id: NonEmptyString  # "sha256:" plus the input-byte digest
    kind: Literal[
        "contexttrack-jsonl",
        "paramtrack-csv",
        "ctype-graph",
    ]


class EvidenceRef(CanonicalModel):
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

Evidence is sorted and deduplicated and does not participate in semantic node
identity. Diagnostics are structured and sort by source, line, code, and
message. A bad independent record should normally produce a diagnostic and be
omitted; unreadable files and invalid file-level contracts are errors.

## Normalized CType graph

Both accepted `.text` input and future verified GraphML normalize to:

```python
class CTypeNode(CanonicalModel):
    id: NonEmptyString
    names: tuple[NonEmptyString, ...]
    methods: tuple[NonEmptyString, ...]
    tags: Mapping[str, str] | None


class CTypeEdge(CanonicalModel):
    source: NonEmptyString
    target: NonEmptyString
    ast_paths: tuple[tuple[str, ...], ...]


class CTypeGraph(CanonicalModel):
    nodes: tuple[CTypeNode, ...]
    edges: tuple[CTypeEdge, ...]
    name_to_node: Mapping[str, str]
```

Normalization and validation rules:

- preserve upstream node IDs, names, aliases, and module-shortened identifiers;
- sort nodes, mappings, methods, tags, edges, and AST paths deterministically;
- retain grouped ordered AST paths on one CType edge;
- preserve isolated vertices;
- reject missing edge endpoints, conflicting represented-name mappings, and
  duplicate `(source, target)` records; and
- exclude generic graph-library properties and unknown input fields from
  normalized semantic identity.

Public boundary:

```python
def load_ctype_graph(path: str | Path) -> CTypeGraph: ...

def ctype_to_igraph(graph: CTypeGraph) -> ig.Graph: ...
```

## PMGraph v2

PMGraph is a canonical, immutable tool34 format. It retains flat HTTP labels and
semantic SHA-256 IDs, and adds compact provenance and the schema-only Behavior
shape.

### Nodes

```python
StatusCode = Annotated[int, Field(ge=100, le=999)]


class PMNodeBase(CanonicalModel):
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

`Parameter` and `Behavior` are selected by `type`; message shapes are selected
by the `(type, message)` pair. Deserialization must reject an unknown or
incomplete pair rather than fall through to a structurally similar shape.
`BehaviorNode` is paper-derived and schema-only. No current importer creates
one or infers behavior boundaries.

### Edges and document

```python
class PMEdge(CanonicalModel):
    source: NonEmptyString
    target: NonEmptyString
    evidence: tuple[EvidenceRef, ...]


class PMGraph(CanonicalModel):
    format: Literal["conftamer.pmgraph"]
    version: Literal[2]
    module_id: NonEmptyString
    sources: tuple[SourceArtifact, ...]
    nodes: tuple[PMNode, ...]
    edges: tuple[PMEdge, ...]
```

A PMGraph edge means possible influence, not proven causality. Sources must be
Parameter or Receive nodes; targets must be Send or Behavior nodes. Planned
importers create `Parameter -> Send Request` and `Receive -> Send` edges.
Endpoints must exist, self-edges and duplicate endpoint pairs are forbidden,
and every evidence source must appear in `sources`. Isolated nodes are valid.
Builders merge evidence for semantically identical nodes and edges.

### Identity and serialization

`make_node_id` hashes canonical JSON containing exactly `module_id` and every
semantic node field except `id` and `evidence`, using sorted keys and compact
separators, and prefixes the SHA-256 digest with `n:`.

Canonical normalization is:

- uppercase HTTP methods;
- `/` for empty HTTP paths;
- status integers from 100 through 999;
- omission, with a diagnostic, of a Send Request without a host;
- optional ContextTrack `api_id` metadata;
- exact nonempty Parameter names;
- sources sorted by `(kind, id)`, nodes by ID, edges by `(source, target)`, and
  evidence by its complete tuple; and
- JSON output ending in one newline.

## ContextTrack semantic projection

The adapter preserves nested raw events while reading and flattens only at the
semantic boundary. Group context-derived inference by `(pid, context_id)`. A
convertible event without context may create a node but no context edge.

Route and response matching are intentionally conservative downstream
heuristics:

- reconstruct likely full route patterns from suffix-compatible nested hops;
- diagnose ambiguous route-chain continuations rather than guessing;
- fall back to a concrete inbound path when no route matches;
- match responses to unconsumed requests by method/path first;
- use goroutine identity only to select a unique candidate or for the existing
  received-response redirect fallback;
- suppress a wire/client duplicate only after the prior compatible hook was
  successfully matched, so a duplicate never consumes a newer request;
- omit unresolved response hooks from semantic nodes; hooks with usable
  endpoints are diagnosed, while endpoint-less received-response hooks may be
  omitted silently so a later usable hook can represent the response; and
- within each context group, connect every converted Receive occurrence to
  every later converted Send occurrence.

Prefer outbound `request_id` labels over `message` labels when available.
Normalize paths only at the semantic boundary. Carry an outbound request's
`api_id` to its matched Receive Response. Raw query strings, handlers, and a
differing response-hook `api_id` may remain evidence but do not change semantic
identity.

## ParamTrack enrichment

ParamTrack observations do not contain a shared ContextTrack run, process,
host, or occurrence identity. The build indexes distinct semantic
`SendRequestNode` values by:

```python
@dataclass(frozen=True, order=True)
class ParamMessageKey:
    method: str
    path: str
```

For each join-eligible row:

1. reject joining if `Verb` or `Resource` may be truncated;
2. uppercase `Verb` and normalize empty `Resource` to `/`;
3. find exact semantic Send Request candidates by method/path;
4. create Parameter edges only when there is exactly one candidate;
5. diagnose zero or several candidates and create no edges; and
6. encode `match_basis="unique-method-path"` as
   `EvidenceRef.derivation="paramtrack-unique-method-path"` on each resulting
   edge, plus one build-level diagnostic explaining the aggregate,
   caller-asserted association.

Do not compare ParamTrack `API` with ContextTrack `api_id`, and do not spread a
row over candidates on different hosts. Validate each CType directly against
the represented-name indexes of US and Accessors before joining.

Each accepted key creates or reuses a `ParameterNode` and a
`Parameter -> Send Request` edge. Several CType rows for one message union their
keys. Repeated edges are deduplicated while retaining evidence for every
supporting CSV row. ParamTrack record identifiers are canonical
`line:<positive-decimal>` strings sorted numerically; the referenced source row
is the source of its CType, API, and parameter-key evidence. CType is not copied
into the PMGraph edge or its semantic identity. Row order does not affect
semantic Parameter node IDs or edge endpoint pairs. Reordering a source file
does change its exact-byte digest and may change physical line references;
canonical provenance reflects those changes rather than treating the files as
identical.

## PMGraph build boundary

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

ContextTrack events are required. Message-only builds omit all ParamTrack and
CType options. Enriched builds require the CSV and both CType graphs together;
`--unmarshaler` and `--accessors` assign their roles. The caller-provided
`module_id` affects PMGraph identity but never rewrites raw CType identifiers.

## AppGraph composition

Stitching consumes at least two validated PMGraphs. Module membership comes
from each graph's `module_id`.

- Reject duplicate module IDs.
- Qualify source nodes and edges by module ID.
- Preserve Send hosts as labels but never use them to infer a receiving module.
- Make output independent of PMGraph input order and filenames.
- Treat multiple deployed instances with one module ID as out of scope.

### Request candidates

A Send Request and Receive Request are candidates only when they belong to
different modules, methods agree, and the concrete Send path satisfies the
Receive pattern. Supported matching is deliberately bounded to:

- exact path equality;
- trailing-slash subtree patterns such as `/api/v1/`;
- one-segment Go `{name}` wildcards; and
- httprouter `:name` and terminal `*name` wildcards.

Method/host prefixes, `{name...}`, `{$}`, mixed wildcard grammars, and unknown
syntax are unsupported unless they match literally. No router dialect is
persisted or inferred. Send `host` and `api_id` never select a receiver module.

Build the complete cross-module candidate graph and contract a pair only when
both endpoints have degree one. Leave 1:N, N:1, and N:M components uncontracted
and marked ambiguous. Every accepted contraction uses
`match_basis="unique-http-labels"` and emits a stitch-level diagnostic that
uniqueness does not prove network delivery. This conservative policy
intentionally differs from the paper's many-Send-to-one-Receive matching.

Response matching is allowed only after an accepted request match between a
client Send Request and server Receive Request. For that request pair:

- a client Receive Response must be in the client module and equal the client
  Send Request's method, host, and path;
- a server Send Response must be in the server module and equal the server
  Receive Request's method and pattern;
- the two response statuses must be equal; and
- `api_id` is retained as metadata but excluded from response candidate
  selection.

Build candidates only within that accepted request pair, then require mutual
uniqueness again. Responses with no accepted request pair remain
`missing_request_match`; they are never matched independently by status/path.

### AppGraph model

```python
class QualifiedNodeRef(CanonicalModel):
    module_id: NonEmptyString
    node_id: NonEmptyString


class MatchInfo(CanonicalModel):
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


class QualifiedPMNode(CanonicalModel):
    module_id: NonEmptyString
    node: PMNode


class AppNode(CanonicalModel):
    id: NonEmptyString
    members: tuple[QualifiedPMNode, ...]
    match: MatchInfo


class QualifiedEdgeRef(CanonicalModel):
    module_id: NonEmptyString
    source: NonEmptyString
    target: NonEmptyString


class AppEdge(CanonicalModel):
    source: NonEmptyString
    target: NonEmptyString
    origins: tuple[QualifiedEdgeRef, ...]


class AppGraph(CanonicalModel):
    format: Literal["conftamer.appgraph"]
    version: Literal[1]
    module_ids: tuple[NonEmptyString, ...]
    sources: tuple[SourceArtifact, ...]
    nodes: tuple[AppNode, ...]
    edges: tuple[AppEdge, ...]
```

Only matched records have a basis. Ambiguous records have sorted candidate
references. Parameter and Behavior AppNodes have one member and
`not_applicable`; unmatched message nodes have one member; matched nodes have
complementary Send/Receive members of the same Request/Response kind.

AppNode IDs hash canonical JSON shaped as
`{"members":[{"module_id":"...","node_id":"..."},...]}`, with members sorted
by `(module_id, node_id)`, and use the `a:` prefix. PMGraph edges are remapped,
deduplicated, and sorted. AppEdges retain sorted qualified origin edges.
Sources are unioned from input PMGraphs, and all embedded evidence must resolve.

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

Default stitching retains unmatched nodes. `prune_unmatched` removes singleton
unmatched message nodes and incident edges, but not Parameters, Behaviors,
matched communications, or nodes newly isolated by pruning. Parameter slicing
is a separate non-destructive query.

## igraph and GraphML boundary

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

Create all vertices before edges so isolated nodes survive. Use canonical IDs
as igraph vertex `name`, preserve canonical order, and never persist igraph
indices or reconstruct canonical JSON from igraph. Exact IDs take precedence
over case-insensitive substring search. Query output is the induced subgraph
of selected vertices and requested transitive reachability.

PMGraph/AppGraph visualization attributes include:

```text
name, canonical_id, label, node_type, module_ids, match_status,
message, api_id, method, host, path, pattern, status, members_json
```

CType vertices expose `name`, `label`, `names_json`, `methods_json`, and
`tags_json`; CType edges expose `ast_paths_json`. Nested values use canonical
JSON strings, absent values are empty strings, scalar types are homogeneous,
and direction is preserved. Every exported GraphML is read back with igraph in
tests.

## CLI contract

The replacement CLI has four noninteractive commands:

```text
conftamer build --module-id MODULE --events EVENTS.jsonl
    [--paramtrack-csv PARAMETERS.csv
     --unmarshaler UNMARSHALER.text
     --accessors ACCESSORS.text]
    --output MODULE.pmgraph.json

conftamer stitch MODULE_A.pmgraph.json MODULE_B.pmgraph.json
    [MORE.pmgraph.json ...] --output APP.appgraph.json [--drop-unmatched]

conftamer query GRAPH.json|GRAPH.text QUERY
    [--direction ancestors|descendants|both] [--all-matches]
    --output RESULT.graphml

conftamer export GRAPH.json|GRAPH.text --output GRAPH.graphml
```

Verified CType `.graphml` joins these input positions only after the producer
contract gate passes. Visualization GraphML never becomes canonical input.
Transformation logic stays outside `cli.py`; diagnostics go to stderr, concise
summaries to stdout, ambiguous queries fail without `--all-matches`, and every
input is validated before use. No analyzer, runner, or Delve command is added.

## Target source layout and readability budget

```text
src/conftamer/
├── cli.py
├── diagnostics.py
├── build.py
├── pmgraph/{models.py,io.py}
├── contexttrack/{models.py,matching.py,importer.py}
├── paramtrack/{models.py,importer.py}
├── ctype_graph/{models.py,io.py}
├── appgraph/{models.py,matching.py,stitch.py}
└── analysis/igraph.py
```

Production code under `src/conftamer` has a hard review gate of 3,000 physical
Python lines and a 2,500-line target. Prefer files below 300 lines, with a
450-line ceiling for model-heavy files, and linear functions below 40 lines
where practical. Do not add generic service, repository, plugin, visitor, or
graph-wrapper layers; compatibility adapters for removed formats; duplicated
query implementations; or one-function modules without a real dependency
boundary.

Tests mirror domain packages. Unit tests use explicit minimal inputs near the
behavior under test; dedicated integration/smoke tests execute the real files
under `examples/`.

## Compatibility and known limits

The rewrite intentionally removes the legacy edge-CSV parser and examples,
PMGraph v1, `contexttrack`, `graph`, and `subgraph` commands, and the
`parse_contexttrack` compatibility import. It retains targeted upstream
ParamTrack CSV support.

Initial limitations include no observable Behavior production, no verified
CType GraphML input, no deployment-aware module identity, no many-to-one
AppGraph contraction, no replicas of one module ID, and no canonical
PMGraph/AppGraph GraphML round-trip. Ambiguous associations are diagnosed and
omitted rather than guessed.

## Rule of thumb

ConfTamer starts at files emitted by upstream tools and ends at queryable
graphs. It validates and normalizes evidence, creates deterministic canonical
documents, projects them for analysis, and writes visualization output.
Discovery, execution, instrumentation, and upstream inference remain outside
this repository.
