# ConfTamer CType GraphML technical reference

This is the current CLI and Python API guide. The normative contracts are
[Architecture](rewrite/architecture.md) and
[Input formats and provenance](rewrite/input-formats.md).

## Processing model

```text
one gopls CType .text file
    -> strict producer-JSON validation
    -> immutable normalized CTypeGraph
    -> directed python-igraph graph
    -> visualization GraphML
```

Unmarshaler Subgraph and Accessors files share the verified transport but remain
independent graphs. Export them with separate invocations.

## Raw producer boundary

`load_ctype_graph` reads the complete UTF-8 file as one JSON document. The root
must contain:

- `Vertices`: vertex objects with nonempty `Names`, a `Methods` array that may
  be empty, and nullable `Tags`;
- `Edges`: edge objects with `Source`, `Target`, and nullable/grouped
  `Properties.Data` AST paths; and
- `List`: nonempty name-to-first-name string mappings.

Unknown raw fields are accepted but discarded from normalized semantics. The
loader validates represented names, mappings, unique vertex IDs, unique edge
endpoint pairs, and existing endpoints. It accepts `.text` or JSON-leading
content. Malformed/unrelated JSON, `.gv` or DOT, and `.graphml` or XML are
rejected. Producer GraphML input remains blocked because no real files define
its transport.

See [Input formats and provenance](rewrite/input-formats.md) for the exact
producer revision, examples, null handling, and real counts.

## Normalized models

`CTypeNode`, `CTypeEdge`, and `CTypeGraph` are strict, frozen Pydantic models.
They preserve upstream strings exactly, isolated vertices, direction, one edge
per producer endpoint record, and grouped ordered AST paths. Nodes, edges,
aliases, methods, equal paths, tag keys, and mapping keys use the canonical
ordering defined in [Architecture](rewrite/architecture.md#normalized-ctype-graph).
Nested mappings are read-only copies.

## Python API

```python
from conftamer.ctype_graph import export_graphml, load_ctype_graph, to_igraph

graph = load_ctype_graph("accessors.text")
projected = to_igraph(graph)
export_graphml(graph, "accessors.graphml")
```

The three public functions are:

```python
def load_ctype_graph(path: str | Path) -> CTypeGraph: ...
def to_igraph(graph: CTypeGraph) -> ig.Graph: ...
def export_graphml(graph: CTypeGraph, path: str | Path) -> None: ...
```

`to_igraph` creates all vertices before edges, preserving canonical order and
isolates. `export_graphml` delegates serialization to python-igraph. Semantic
projection is stable, but byte-for-byte GraphML identity is not promised across
igraph versions.

GraphML cannot be converted back to `CTypeGraph`: it is a visualization
projection and does not retain the normalized `name_to_node` mapping as a
reversible document. It is never accepted as producer input.

## GraphML schema

Every attribute value is a string. Vertices expose:

| Attribute | Meaning |
| --- | --- |
| `name`, `label` | stable upstream CType ID |
| `aliases` | aliases, one per line |
| `methods` | methods, one per line |
| `tags` | sorted `key: value` entries, one per line |
| `names_json` | lossless compact JSON names array |
| `methods_json` | lossless compact JSON methods array |
| `tags_json` | lossless compact sorted-key object or `null` |

Edges expose:

| Attribute | Meaning |
| --- | --- |
| `ast_paths` | one path per line; ` → ` joins segments and `(empty path)` represents `()` |
| `ast_paths_json` | lossless compact JSON preserving path groups and segment order |

Readable attributes are presentation aids. Use the `*_json` companions when
values must be recovered without delimiter ambiguity.

## Command-line interface

The installed entry point is `conftamer.cli:app`, and its only command is:

```text
conftamer export INPUT.text --output OUTPUT.graphml
```

The command loads and validates the complete normalized graph before writing.
On success it prints a concise vertex/edge summary to stdout. I/O, Unicode,
transport, and validation errors exit nonzero with a one-line `error: ...`
message on stderr. Loading and validation errors do not create the output file.

Examples:

```bash
uv run conftamer export \
  examples/ctype/unmarshaler_subgraph.text \
  --output /tmp/unmarshaler.graphml

uv run conftamer export \
  examples/ctype/accessors.text \
  --output /tmp/accessors.graphml
```

## Development verification

```bash
uv run pytest -q tests/ctype_graph tests/test_cli.py
uvx ruff format --check src tests
uvx tombi format --check pyproject.toml
uvx ty check
uv run pytest -q
uv run conftamer --help
uv run conftamer export --help
find src/conftamer -name '*.py' -print0 | xargs -0 wc -l
```

Every checked-in GraphML test re-reads with `ig.Graph.Read_GraphML()`. Real-data
checks assert directed 57/90 and 582/822 graphs. Production Python has a hard
450-line MVP ceiling.

## License

ConfTamer is licensed under the GNU General Public License, version 2 only. See
[LICENSE](../LICENSE).
