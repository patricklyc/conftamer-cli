## ContextTrack importer

Load one UTF-8 ContextTrack JSONL capture into a message-only PMGraph:

```python
from conftamer.contexttrack import load_contexttrack

graph = load_contexttrack(
    "examples/contexttrack/prometheus/scrape-ok.jsonl",
    module_id="example-module",
)
```

The caller supplies the module identity; it is not inferred from API IDs.
Invalid consumed types raise `TypeError`; malformed JSON and invalid values raise
`ValueError`. Capture diagnostics include the path and physical line. Incomplete
or ambiguous evidence emits warnings and is not used to invent associations.
Edges represent possible influence from received messages to later sent messages
in the same process-local context, not a replay or complete call graph.

## Build and save a PMGraph

```bash
uv run conftamer build examples/contexttrack/prometheus/scrape-ok.jsonl \
  --module-id example-module --output module.pmgraph.json
```

Both options are required. The output must be a new file in an existing directory;
existing files are never overwritten. Success leaves stdout empty, warnings go to
stderr, and expected input or filesystem errors produce stderr diagnostics and
exit code 2 without a traceback. The scaffold greeting (`conftamer NAME`) has been
removed; there is no `hello` alias.

For library use, `conftamer.pmgraph.io` exposes `load_pmgraph_json(path)` and
`write_pmgraph_json(graph, path)`. JSON loading uses strict UTF-8 and Pydantic
validation, rejecting coercion and unknown fields. Models validate message field
combinations, nonempty module/node IDs, and existing edge endpoints. Writing
preserves node order and explicit nulls, sorts edge pairs, and uses literal UTF-8
Unicode, two-space indentation, and a final newline. Filesystem failures can leave
a partial newly created output; writes are not atomic.

## Export a PMGraph to GraphML

```bash
uv run conftamer export module.pmgraph.json --output module.graphml
```

The exporter validates PMGraph JSON, preserves directed named topology, isolates,
module identity, and complete node data, and creates a new GraphML file without
overwriting existing output. For library use, `conftamer.pmgraph.igraph_ops`
exposes `to_igraph(graph)` and `write_graphml(graph, path)`. GraphML stores each
complete node as escaped JSON in the `node_json` vertex attribute; no reverse
GraphML importer is provided.

## Query a PMGraph node

```bash
uv run conftamer query module.pmgraph.json --node NODE_ID
```

The query selects one exact PMGraph node ID and prints its directed ancestors and
descendants as indented JSON. Results contain each reachable ID once in original
node order and exclude the selected node, including in cycles and self-loops. A
known isolate returns two empty lists. Unknown IDs and invalid input produce a
stderr diagnostic and exit code 2 with no stdout.

Queries report recorded possible influence, not proof of causality or capture
completeness. For library use, `conftamer.pmgraph.igraph_ops` exposes
`query_node(graph, node_id)`. Parameter ingestion, GraphML querying, path
explanation, and stitching are not implemented.

## Development setup

Requirements:

- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- Python 3.14 (uv can install it for you)

From the repository root, install Python and the locked development dependencies:

```bash
uv python install 3.14
uv sync --locked --dev
```

Run the tests and verify the CLI:

```bash
uv run pytest -q
uv run conftamer --help
```

Optional formatting and type checks:

```bash
uvx ruff format --check src tests
uvx ty check
```

### VS Code

Install the official [Python](https://marketplace.visualstudio.com/items?itemName=ms-python.python), [Ruff](https://marketplace.visualstudio.com/items?itemName=charliermarsh.ruff), and [ty](https://marketplace.visualstudio.com/items?itemName=astral-sh.ty) extensions, (and uninstall Pylance). Then select `.venv/bin/python` as the workspace interpreter.