# ConfTamer technical reference

This is the current-release command-line and Python API guide. Start with the
[README](../README.md) for installation and short examples.

Normative details intentionally live in two focused contracts:

- [Target architecture](rewrite/architecture.md) defines canonical PMGraph v2,
  AppGraph v1, matching, provenance, deterministic serialization, igraph
  projection, and CLI behavior.
- [Input formats and provenance](rewrite/input-formats.md) records observed
  ContextTrack, ParamTrack, and gopls producer formats.

This guide links to those contracts instead of duplicating their schemas.

## Processing model

```text
ContextTrack JSONL
    -> message nodes and conservative context influence

ParamTrack CSV + Unmarshaler/Accessors CType .text graphs
    -> validated aggregate Parameter enrichment

message graph + optional enrichment
    -> canonical PMGraph v2

two or more PMGraphs
    -> conservative cross-module matching
    -> canonical AppGraph v1

PMGraph, AppGraph, or CTypeGraph
    -> python-igraph query/export
    -> visualization GraphML
```

Raw producer models do not enter canonical graph models. CType nodes remain in
CTypeGraph, and GraphML is never used as canonical persistence.

## Input and output boundaries

### Machine inputs

- ContextTrack JSONL containing the five supported HTTP event kinds;
- targeted, headered, variable-width ParamTrack parameter CSV;
- gopls CType JSON for the Unmarshaler and Accessors graphs, normally emitted
  with a `.text` suffix;
- canonical PMGraph v2 JSON; and
- canonical AppGraph v1 JSON.

The targeted ParamTrack CSV is unrelated to the removed prototype's headerless
edge CSV. It continues to use Python's standard `csv` module.

### Reference-only artifacts

CType `.gv` files are Graphviz views, hierarchy files are human-readable
ParamTrack derivatives, and gopls/ParamTrack/Delve logs are producer records.
They are retained for inspection but are not ConfTamer machine inputs.

Producer CType GraphML is also unsupported until real producer files establish
its namespaces, keys, IDs, direction, defaults, and collection encoding.
GraphML emitted by ConfTamer is visualization output only.

See [Input formats and provenance](rewrite/input-formats.md) for exact observed
file contracts and rejection policy.

## Command-line interface

The installed entry point is `conftamer.cli:app`. All commands are
noninteractive, require explicit output paths, print diagnostics to standard
error, and print concise summaries to standard output.

### `build`

```text
conftamer build --module-id MODULE --events EVENTS.jsonl
    [--paramtrack-csv PARAMETERS.csv
     --unmarshaler UNMARSHALER.text
     --accessors ACCESSORS.text]
    --output MODULE.pmgraph.json
```

`--module-id` identifies the module represented by the complete trace. A
message-only build omits all enrichment options. An enriched build requires all
three options together and assigns the CType graph roles explicitly.

Supplying the inputs together is the caller's assertion that they describe a
compatible corpus. ConfTamer cannot verify a shared run identity. ParamTrack
rows join only to one unique semantic Send Request selected by normalized
method/path; ParamTrack `API` is never compared with ContextTrack `api_id`.

The output is deterministic, validated PMGraph v2 JSON ending in one newline.

### `stitch`

```text
conftamer stitch MODULE_A.pmgraph.json MODULE_B.pmgraph.json
    [MORE.pmgraph.json ...]
    --output APPLICATION.appgraph.json
    [--drop-unmatched]
```

At least two PMGraphs with distinct module IDs are required. Matching uses HTTP
labels only: host and `api_id` do not select a destination module. A candidate
pair is contracted only when both sides are mutually unique. Responses can
match only through an accepted request match.

Unmatched nodes remain visible by default. `--drop-unmatched` removes singleton
unmatched message nodes and incident edges while retaining Parameters,
Behaviors, and matched communications.

### `query`

```text
conftamer query GRAPH.json|GRAPH.text QUERY
    [--direction ancestors|descendants|both]
    [--all-matches]
    --output RESULT.graphml
```

The input may be PMGraph v2, AppGraph v1, or verified CType JSON. CType
dispatch accepts `.text` or JSON-leading content and validates the producer
envelope. An exact canonical vertex name takes precedence over case-insensitive
substring search across projected attributes. No match is an error. Multiple
matches are an error unless `--all-matches` is supplied.

The output is the induced GraphML subgraph containing selected vertices and
their requested transitive reachability. `both` is the default direction.

### `export`

```text
conftamer export GRAPH.json|GRAPH.text --output GRAPH.graphml
```

`export` accepts the same graph inputs as `query` and projects the complete
validated graph to GraphML. PMGraph and AppGraph use canonical IDs as vertex
names. CType edges preserve each grouped ordered AST path in the
`ast_paths_json` attribute.

## Diagnostics and provenance

Independent malformed ContextTrack or ParamTrack records normally produce a
diagnostic and are omitted; unreadable files and invalid file-level contracts
are errors. Diagnostics have a stable code, message, optional source path, and
optional physical line. Build- or stitch-level diagnostics have no source.

Each canonical source records the SHA-256 digest of the exact input bytes.
Nodes and edges carry compact evidence references such as physical input lines
and derivation kinds. Evidence is merged but does not participate in semantic
node identity. See [Diagnostics and provenance](rewrite/architecture.md#diagnostics-and-provenance)
for the complete contract.

PMGraph edges represent possible influence, not proof of causality. AppGraph
matches are heuristic and visibly marked `unique-http-labels`.

## Python API

The high-level build boundary mirrors the CLI:

```python
from conftamer.build import build_pmgraph
from conftamer.pmgraph import write_pmgraph

result = build_pmgraph(
    module_id="example.org/service",
    events="events.jsonl",
)
write_pmgraph(result.graph, "service.pmgraph.json")

for diagnostic in result.diagnostics:
    print(diagnostic.code, diagnostic.message)
```

Add `paramtrack_csv`, `unmarshaler`, and `accessors` together for enrichment.
The direct ContextTrack adapter is `conftamer.contexttrack.import_contexttrack`.

Canonical PMGraph I/O and models are exported by `conftamer.pmgraph`:

```python
from conftamer.pmgraph import load_pmgraph, write_pmgraph

graph = load_pmgraph("service.pmgraph.json")
write_pmgraph(graph, "copy.pmgraph.json")
```

CType loading and projection:

```python
from conftamer.analysis import ctype_to_igraph
from conftamer.ctype_graph import load_ctype_graph

ctype = load_ctype_graph("accessors.text")
projected = ctype_to_igraph(ctype)
```

AppGraph stitching and I/O:

```python
from conftamer.appgraph import (
    load_appgraph,
    stitch_pmgraph_files,
    write_appgraph,
)

result = stitch_pmgraph_files(["frontend.pmgraph.json", "backend.pmgraph.json"])
write_appgraph(result.graph, "application.appgraph.json")
application = load_appgraph("application.appgraph.json")
```

Programmatic analysis uses the same implementation as the CLI:

```python
from conftamer.analysis import (
    find_vertices,
    influence_subgraph,
    to_igraph,
    write_graphml,
)

projected = to_igraph(application)
matches = find_vertices(projected, "timeout")
selected = influence_subgraph(projected, matches, direction="both")
write_graphml(selected, "timeout.graphml")
```

Canonical model and function signatures are defined in the
[architecture contract](rewrite/architecture.md). Loaders validate canonical
ordering and identity; they do not silently repair noncanonical documents.

## Current limitations

- ContextTrack input does not prove ownership by the supplied module ID.
- ParamTrack enrichment has no shared occurrence or run identity with
  ContextTrack and is therefore aggregate and caller-asserted.
- Ambiguous route, response, parameter, and cross-module matches are diagnosed
  or retained rather than guessed.
- Behavior nodes are schema-only because no producer contract creates them.
- CType GraphML input is blocked; the observed CType JSON transport is accepted
  from `.text` or JSON-leading content, while `.gv` remains unsupported.
- Stitching does not model deployment manifests, replicas, or many-to-one
  contraction.
- Canonical PMGraph/AppGraph JSON cannot be reconstructed from visualization
  GraphML.

## Development and verification

Production modules are organized by domain under `src/conftamer/`; tests mirror
those packages under `tests/`. Checked-in files under `examples/` are executable
integration inputs rather than generated-output directories.

Run the complete checks with:

```bash
uvx ruff format --check src tests
uvx tombi format --check pyproject.toml
uvx ty check
uv run pytest -q

uv run conftamer --help
uv run conftamer build --help
uv run conftamer stitch --help
uv run conftamer query --help
uv run conftamer export --help
```

## License

ConfTamer is licensed under the GNU General Public License, version 2 only.
See [LICENSE](../LICENSE).
