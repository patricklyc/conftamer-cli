# ConfTamer CType GraphML MVP architecture

This document defines the target owned by tool34. Verified producer facts and
provenance live in [Input formats](input-formats.md); ordered migration work
lives in the [Implementation plan](implementation-plan.md).

## Goal and scope

ConfTamer validates one gopls CType artifact and exports a directed visualization
GraphML file:

```text
gopls Unmarshaler Subgraph .text  ─┐
                                   ├─ one file per invocation
gopls Accessors .text              ─┘
    -> strict raw validation
    -> normalized frozen CTypeGraph
    -> directed python-igraph graph
    -> visualization GraphML
```

The Unmarshaler and Accessors artifacts are independent. A caller exports both
with two invocations; ConfTamer never combines, cross-links, or deduplicates
them across files.

The implementation uses Python 3.13+, Pydantic v2, python-igraph, Typer, pytest,
Ruff, ty, Tombi, uv, and PyInstaller. Adding dependencies or raising the Python
minimum requires approval.

This repository owns CType input validation and normalization, igraph
projection, GraphML output, one thin CLI command, tests, examples,
documentation, and packaging. It does not own producer execution, gopls
analysis, canonical graph JSON, reverse GraphML conversion, producer GraphML or
DOT parsing, graph merging, queries, reachability, or parameter processing.
PMGraph, AppGraph, ContextTrack, ParamTrack CSV, build, and stitch workflows are
outside this MVP.

## Input boundary

Accepted input is a `.text` file or JSON-leading content using the verified
producer envelope `Edges`, `Vertices`, and `List`. Parse the complete stream as
one JSON document. Unknown top-level and nested producer fields are accepted
for forward compatibility and excluded from normalized semantics.

Reject malformed JSON, unrelated JSON, Graphviz/DOT (`.gv` or DOT-leading), and
GraphML/XML (`.graphml` or XML-leading). Producer GraphML remains blocked until
real Unmarshaler and Accessors artifacts establish its exact transport. GraphML
written by this tool is visualization output and is never machine input.

Every input must validate completely before output writing begins. File I/O,
Unicode, transport, raw schema, and normalized graph failures are user errors;
the CLI reports a concise `error: ...` on stderr, exits nonzero, and creates no
output for loading or validation failures.

## Normalized CType graph

```python
NonEmptyString = Annotated[str, Field(strict=True, min_length=1)]


class CTypeModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)


class CTypeNode(CTypeModel):
    id: NonEmptyString
    names: Annotated[tuple[NonEmptyString, ...], Field(min_length=1)]
    methods: tuple[NonEmptyString, ...]
    tags: Mapping[str, str] | None


class CTypeEdge(CTypeModel):
    source: NonEmptyString
    target: NonEmptyString
    ast_paths: tuple[tuple[str, ...], ...]


class CTypeGraph(CTypeModel):
    nodes: tuple[CTypeNode, ...]
    edges: tuple[CTypeEdge, ...]
    name_to_node: Mapping[str, str]
```

Models are immutable and reject unknown fields. Nested mappings are copied into
sorted read-only mappings so validated documents cannot be mutated through the
caller's original dictionaries.

Normalization and validation rules:

- preserve each vertex's first upstream name as its stable ID and first `names`
  value;
- deduplicate and sort remaining aliases and methods;
- sort tag keys and `name_to_node` keys lexically;
- sort nodes by ID and edges by `(source, target)`;
- preserve segment order inside each AST path, deduplicate equal paths, and sort
  complete paths lexically while retaining grouped paths on one CType edge;
- normalize `Data: null` to no paths and a null path item to an empty path;
- preserve isolated vertices and one edge per producer `(Source, Target)`
  record;
- require every represented name and alias in raw `List` to map to that
  vertex's first name; do not synthesize mappings;
- retain only additional `List` mappings resolving to a represented vertex;
- reject empty names, missing endpoints, conflicting represented-name mappings,
  duplicate vertex IDs, duplicate `(source, target)` records, noncanonical
  normalized collection order, and dangling normalized mappings; and
- exclude unknown fields and generic graph-library attributes/weights from
  semantic identity.

Public loading boundary:

```python
def load_ctype_graph(path: str | Path) -> CTypeGraph: ...
```

## igraph and GraphML projection

```python
def to_igraph(graph: CTypeGraph) -> ig.Graph: ...


def export_graphml(graph: CTypeGraph, path: str | Path) -> None: ...
```

Create every vertex before adding edges so isolates survive. The graph is
directed, follows canonical node and edge order, and uses the upstream CType ID
for both `name` and `label`. igraph indices are never persistent identities.

All GraphML values are strings to produce a homogeneous, Gephi-friendly schema.
Before opening the destination, reject any projected string containing a
character forbidden by XML 1.0; never silently strip or replace an upstream
value. Serialize to a temporary sibling and atomically replace the destination
so a writer failure cannot leave partial GraphML.

Every vertex has:

| Attribute | Value |
| --- | --- |
| `name` | stable upstream CType ID |
| `label` | stable upstream CType ID |
| `aliases` | non-ID names, one per line |
| `methods` | methods, one per line |
| `tags` | sorted `key: value` entries, one per line |
| `names_json` | compact JSON array containing every name |
| `methods_json` | compact JSON array containing every method |
| `tags_json` | compact sorted-key JSON object, or `null` |

Every edge has:

| Attribute | Value |
| --- | --- |
| `ast_paths` | one path per line, segments joined by ` → `, with `(empty path)` for `()` |
| `ast_paths_json` | compact JSON preserving path grouping and segment order |

JSON attribute serialization uses UTF-8 semantics, sorted object keys, and
compact separators. The readable attributes are presentation aids; the JSON
companions preserve nested values without delimiter ambiguity.

GraphML must re-read through `ig.Graph.Read_GraphML()` with direction, counts,
attributes, isolates, and endpoints intact. Semantic projection order is stable,
but byte-for-byte GraphML identity is not promised because python-igraph owns
serialization. GraphML cannot reconstruct `CTypeGraph`, particularly its
`name_to_node` mapping, and is not canonical persistence.

## CLI contract

The only installed command is:

```text
conftamer export INPUT.text --output OUTPUT.graphml
```

The Typer callback loads the complete normalized graph before writing, exports
it, then reports a concise vertex/edge summary to stdout with correct singular
and plural forms. `conftamer.cli:app` remains the package entry point. There is
no generic document dispatch and no second input or role option.

## Layout and readability budget

```text
src/conftamer/
├── __init__.py
├── cli.py
└── ctype_graph/
    ├── __init__.py
    ├── models.py
    ├── io.py
    └── graphml.py
```

Production Python has a hard MVP ceiling of **450 physical lines**, a review
range of 380–430, and a target near 400. Keep orchestration in `cli.py`, raw
transport in `io.py`, invariants in `models.py`, and projection in `graphml.py`.
Favor explicit domain functions over generic graph wrappers, service layers,
plugins, or compatibility adapters.

Tests live in `tests/ctype_graph/` and `tests/test_cli.py`. Small fixtures pin
individual contracts; integration tests execute both real files under
`examples/ctype/` and assert 57 vertices/90 edges and 582 vertices/822 edges.
Generated GraphML belongs outside the example directory.

## Compatibility and limits

This MVP intentionally removes previous PMGraph/AppGraph, ContextTrack,
ParamTrack, build, stitch, and query surfaces. It accepts only the inspected
producer JSON transport. Future serializer changes require renewed producer
evidence. Producer GraphML and DOT are unsupported, the two graph roles remain
independent, and visualization GraphML is neither canonical nor reversible.
