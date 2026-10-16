# ConfTamer

ConfTamer turns ContextTrack HTTP traces into a **per-module influence graph
(PMGraph)**: a directed graph of possible influence between a module's received
and sent messages. Build a graph from a capture, query node reachability, or
export it to GraphML.

The current implementation consumes ContextTrack artifacts only. It does not
collect traces or prove causality or capture completeness.

## Setup

Requires [uv](https://docs.astral.sh/uv/getting-started/installation/) and
Python 3.14 or newer. From the repository root, install Python and the locked
development dependencies:

```bash
uv python install 3.14
uv sync --locked --dev
```

## Quick start

Run the following in Bash from the repository root. A fresh temporary directory
keeps generated files separate from the source captures and avoids overwriting
previous output.

```bash
output_dir=$(mktemp -d)

# Build a PMGraph from the bundled capture.
uv run conftamer build examples/contexttrack/prometheus/scrape-ok.jsonl \
  --module-id example-module --output "$output_dir/module.pmgraph.json"

# Query the received-request node in this capture.
uv run conftamer query "$output_dir/module.pmgraph.json" --node n1

# Export the same graph to GraphML.
uv run conftamer export "$output_dir/module.pmgraph.json" \
  --output "$output_dir/module.graphml"
```

The capture produces four nodes and one edge, `n1 → n2`. The query prints:

```json
{
  "ancestors": [],
  "descendants": [
    "n2"
  ]
}
```

Here, `n1` is a received request and `n2` is a sent response. The generated files
are in `$output_dir`.

For your own capture, change the input path and `--module-id`. The module identity
is supplied by you, not inferred from API IDs. Node IDs are keys in the PMGraph
JSON file's top-level `nodes` object, not API IDs or URLs. Inspect the file to
choose an exact ID:

```bash
uv run python -m json.tool "$output_dir/module.pmgraph.json"
```

## Graph semantics and limits

- **Nodes represent messages, not individual events.** The importer distinguishes
  sent/received requests and responses, correlates routing and response metadata,
  and deduplicates identical message labels.
- **Edges represent possible influence.** A received message can influence a later
  sent message within the same capture and `(pid, context_id)`. The result is not
  an execution replay or a complete call graph.
- **Queries report directed reachability.** Ancestors and descendants include
  indirect connections. Each list contains unique IDs in original node order and
  excludes the selected node, even in cycles or self-loops. An isolated node
  returns two empty lists.
- **Incomplete or ambiguous evidence emits warnings.** It does not become an
  invented association; unusable events or associations are omitted.
- Parameter ingestion, GraphML importing or querying, path explanation, and
  cross-module stitching are not implemented.

## Files and errors

- **Inputs:** `build` reads UTF-8 ContextTrack JSONL; `query` and `export` read
  PMGraph JSON. PMGraph JSON loading rejects type coercion and unknown fields,
  and validates message field combinations, nonempty module/node IDs, and existing
  edge endpoints. PMGraph JSON output preserves node order and explicit nulls
  and sorts edge pairs.
- **Outputs:** `build` and `export` require `--output`. The parent directory must
  exist and the file must be new; existing files are never overwritten. Writes
  are not atomic, so a filesystem failure can leave a partial new file.
- **Diagnostics:** Build and export leave stdout empty on success; query prints
  indented JSON. Warnings go to stderr. Expected input or filesystem errors,
  including unknown node IDs, produce stderr diagnostics and exit code 2 without
  a traceback. Capture record diagnostics include the input path and physical
  line number.
- **GraphML:** Export preserves directed named topology, isolated nodes, module
  identity, and complete node data. Each vertex has `name` and `kind` attributes;
  its complete model is stored as escaped JSON in `node_json`. Export rejects
  module or node IDs that XML cannot preserve exactly.

## Python API

The same operations are callable without the CLI:

```python
from conftamer.contexttrack import load_contexttrack
from conftamer.pmgraph.igraph_ops import query_node

graph = load_contexttrack(
    "examples/contexttrack/prometheus/scrape-ok.jsonl",
    module_id="example-module",
)
result = query_node(graph, "n1")
print(result)
```

For persistence, `conftamer.pmgraph.io` provides `load_pmgraph_json(path)` and
`write_pmgraph_json(graph, path)`. For conversion and export,
`conftamer.pmgraph.igraph_ops` provides `to_igraph(graph)` and
`write_graphml(graph, path)`.

The ContextTrack importer raises `TypeError` for invalid consumed types and
`ValueError` for malformed JSON or invalid values. PMGraph JSON loading raises
`ValueError` for invalid data; filesystem failures raise `OSError`.

## Development

Run the tests, formatting and type checks, and CLI help:

```bash
uv run pytest -q
uvx ruff format --check src tests
uvx ty check
uv run conftamer --help
```

For VS Code, select `.venv/bin/python` as the workspace interpreter. The
[Python](https://marketplace.visualstudio.com/items?itemName=ms-python.python),
[Ruff](https://marketplace.visualstudio.com/items?itemName=charliermarsh.ruff), and
[ty](https://marketplace.visualstudio.com/items?itemName=astral-sh.ty) extensions
provide Python integration, formatting, and type checking, respectively.

## License

[GPL-2.0-only](LICENSE).
