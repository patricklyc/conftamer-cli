# ConfTamer

ConfTamer is being built to show how configuration parameters and HTTP messages
may influence one another inside an application module — and, once modules are
combined, across an entire application.

This branch provides three things: the Python data format for a per-module graph
(a **PMGraph**); a **stitcher** that fuses several PMGraphs into a single
cross-module graph (an **AppGraph**); and a **query** that, given one node,
returns the part of a graph connected to it plus the paths that run through it.

## Graph format

A PMGraph contains:

- an ID for the module;
- nodes representing configuration parameters or HTTP messages; and
- directed edges connecting those nodes.

Each node has a `kind` field that says what type of node it is. An edge stores the
IDs of its source and destination nodes. If the same edge appears more than once,
it is stored only once.

```python
from conftamer.pmgraph.models import PMGraph

graph = PMGraph.model_validate(
    {
        "module_id": "frontend",
        "nodes": {
            "parameter-1": {
                "kind": "parameter",
                "key": "timeout",
            },
            "message-1": {
                "kind": "send_request",
                "api_id": None,
                "method": "POST",
                "host": "backend:8080",
                "path": "/jobs",
            },
        },
        "edges": [["parameter-1", "message-1"]],
    }
)
```

In this example, the `timeout` parameter points to an HTTP request.

## AppGraph and stitching

A single PMGraph only sees one module. An **AppGraph** is the combined,
cross-module graph you get by *stitching* several PMGraphs together.

Stitching looks for message nodes in **different** modules that describe the two
ends of the same API call — one module's `send_request` and another's
`receive_request` (and, for responses, `receive_response` / `send_response`).
Two messages are treated as the same call when their `api_id`, `method`, and
response code agree and the sender's concrete path satisfies the receiver's route
pattern. Each matched pair is merged into one `LinkedMessage` node, and every
module's internal edges are rewritten onto those merged nodes. This is what lets
influence flow *across* modules: a config value in one module can be shown to
reach a module it never names directly, because the intermediate module's own
`receive → send` edge bridges the two links.

Finally, stitching keeps only what is reachable from a configuration
`Parameter` — so a parameter must feed a send for anything to survive.

```python
from conftamer.pmgraph.models import PMGraph
from conftamer.appgraph.stitch import stitch

frontend = PMGraph.model_validate(
    {
        "module_id": "frontend",
        "nodes": {
            "timeout": {"kind": "parameter", "key": "timeout"},
            "call-jobs": {
                "kind": "send_request",
                "api_id": "jobs-api",
                "method": "POST",
                "host": "backend:8080",
                "path": "/jobs",
            },
        },
        "edges": [["timeout", "call-jobs"]],
    }
)

backend = PMGraph.model_validate(
    {
        "module_id": "backend",
        "nodes": {
            "recv-jobs": {
                "kind": "receive_request",
                "api_id": "jobs-api",
                "method": "POST",
                "pattern": "/jobs",
            },
        },
        "edges": [],
    }
)

appgraph = stitch([frontend, backend])
# appgraph.nodes -> {"frontend::timeout": Parameter, "link0": LinkedMessage}
# appgraph.edges -> {("frontend::timeout", "link0")}
```

While stitching, node IDs are namespaced as `module_id::node_id` so IDs from
different modules can't collide. Because of this, `::` is not allowed inside a
module ID or a node ID.

## Querying

`query(graph, node_id, path_limit=-1)` works on **either** a PMGraph or an
AppGraph. Given one node it returns a `QueryResult` with:

- **`subgraph`** — the part of the graph connected to the queried node: the node
  itself, every node that can reach it (its ancestors), and every node it can
  reach (its descendants), with all edges among them. It comes back as the same
  graph type you passed in.
- **`paths`** — every path that runs from a root (a node with no incoming edges)
  to a leaf (a node with no outgoing edges) and passes through the queried node,
  as lists of node IDs.
- **`truncated`** — whether `path_limit` cut off any paths.

`path_limit` caps how many paths are returned; `-1` means no limit. A dense graph
can contain an enormous number of root-to-leaf paths, so a limit is worth setting
on large graphs.

```python
from conftamer.query import query

result = query(appgraph, "frontend::timeout")
# result.subgraph : an AppGraph with frontend::timeout and link0
# result.paths    : [["frontend::timeout", "link0"]]
# result.truncated: False
```

Querying an unknown node ID raises `ValueError`.

## Not yet wired up

The command-line program is still a simple greeting demo: stitching and querying
are available as a library, but not yet as CLI commands. The CLI also does not
yet read ContextTrack captures, save graph files, or export GraphML.

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