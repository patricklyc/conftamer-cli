# ConfTamer

ConfTamer is being built to show how configuration parameters and HTTP messages
may influence one another inside an application module — and, once modules are
combined, across an entire application.

This branch provides three things: the Python data format for a per-module graph
(a **PMGraph**); a **stitcher** that fuses several PMGraphs into a single
cross-module graph (an **AppGraph**); and a **query** that, given one node,
returns the part of a graph connected to it plus the paths that run through it.
All of these are available from the `conftamer` command line, along with
building PMGraphs from ContextTrack captures and exporting to GraphML.

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
module ID or a node ID, and a module ID may not end with `:`.

### Seeing what was dropped

Stitching leaves messages out of the AppGraph for two reasons, and it can be
hard to tell from the AppGraph alone what went missing. `stitch_with_dropped`
stitches exactly like `stitch` and also returns a `DroppedMessage` for every
input message that didn't make it into the AppGraph:

- **`unmatched`**: no message in another module matched it. For example, a
  request to a service that isn't one of the stitched modules, or a sender and
  receiver whose `api_id`, method, status code, or path disagree.
- **`unreachable`**: it matched, but no `Parameter` reaches any of the links it
  was merged into, so they were pruned. Nothing creates `Parameter` nodes from
  a capture yet, so stitching PMGraphs built by `conftamer build` reports every
  matched message as `unreachable`.

A message merged into several links counts as kept if any one of them
survives. `Parameter` nodes are never dropped.

```python
from conftamer.appgraph.stitch import stitch_with_dropped

result = stitch_with_dropped([frontend, backend])
result.appgraph   # the same AppGraph that stitch() returns
result.dropped    # [DroppedMessage(module_id=..., node_id=..., reason=..., message=...)]
```

`dropped` is sorted by module ID and then node ID, and each entry carries the
original `Message` so you can see its `api_id`, method, path, and so on.

## Querying

`query(graph, node_id)` works on **either** a PMGraph or an AppGraph. Given one
node it returns a `QueryResult` with:

- **`subgraph`** — the part of the graph connected to the queried node: the node
  itself, every node that can reach it (its ancestors), and every node it can
  reach (its descendants), with all edges among them. It comes back as the same
  graph type you passed in.
- **`paths`** — every path that runs from a root (a node with no incoming edges)
  to a leaf (a node with no outgoing edges) and passes through the queried node.
  Each path is a list of steps, and each step is a list of node IDs. On a graph
  without cycles every step is a single node. Graphs with cycles work too; see
  [Cycles](#cycles).

Every path is always returned. A dense graph can contain an enormous number of
root-to-leaf paths, so a query on a large, densely connected graph can be slow
and use a lot of memory. Paths are returned in a deterministic order (by node
ID), so the same query always yields the same paths.

```python
from conftamer.query import query

result = query(appgraph, "frontend::timeout")
# result.subgraph : an AppGraph with frontend::timeout and link0
# result.paths    : [[["frontend::timeout"], ["link0"]]]
```

Querying an unknown node ID raises `ValueError`, as does querying a graph with
an edge that points at a node ID missing from `nodes`.

### Cycles

A graph can contain cycles, for example when a client's request is influenced by
an earlier response from the same API. Every node in a cycle influences every
other node in it, so listing each route around the cycle as its own path would
repeat the same information many times over: a cluster of a dozen densely
connected nodes can produce hundreds of thousands of such paths. Instead, each
group of nodes that all reach each other (a *strongly connected component*) is a
single step of a path, listed as its sorted node IDs:

```python
# r -> a -> b -> a -> b -> l   (a and b form a cycle)
query(graph, "a").paths   # [[["r"], ["a", "b"], ["l"]]]

# r -> a -> b -> a   (a and b loop forever; there is no leaf)
query(graph, "a").paths   # [[["r"], ["a", "b"]]]
```

A path starts in a group that nothing outside it points into and ends in a
group with no edge leaving it, so a cycle with no root above it or no leaf below
it can begin or end a path. A single node with no cycle is a group of one, which
is why a graph without cycles gets exactly the root-to-leaf paths described
above.

No influence is lost: one node influences another exactly when its group comes
before the other's on some path, and every node in the subgraph appears on at
least one path. Only the order in which a path moves around inside a cycle is
left out, and those edges are still in `subgraph`.

#### Why `paths` is a list of lists of lists

`paths` has the type `list[list[list[str]]]`, read from the outside in:

1. **The list of paths.** One entry per root-to-leaf path through the node.
2. **One path.** An ordered list of steps, from the start of the path to its end.
3. **One step.** The sorted node IDs of one strongly connected component. A
   node that is not in a cycle is a step of one node, such as `["link0"]`. A
   cycle is a step of several nodes, such as `["a", "b"]`.

A step has to be able to hold several nodes, because collapsing each cycle
into one step is what keeps the number of paths small. We picked this shape over
two alternatives:

- **Mixing bare IDs and lists** (`["r", ["a", "b"], "l"]`). This is shorter, but
  every consumer would have to check whether each step is a string or a list.
  The type would be `list[list[str | list[str]]]`, which is awkward to type-check
  and to describe in a JSON schema. With the nested form, every step is
  handled the same way.
- **Keeping `list[list[str]]` and naming each cycle with a made-up ID**
  (`["r", "scc0", "l"]`, plus a separate `components: {"scc0": ["a", "b"]}`
  map). A made-up ID could clash with a real node ID. Readers would also need
  to look every step up in a second map, so a path would no longer stand on its
  own.

The cost is that a graph without cycles wraps every node in a one-item list:
`[["a"], ["b"]]` instead of `["a", "b"]`. To get the plain form back when you
know a graph has no cycles, use `[[node for (node,) in path] for path in
result.paths]`. That line raises an error if any step has more than one node.

### igraph

Graphs are always stored as their pydantic models; querying converts them to
[igraph](https://python.igraph.org/) internally on every call and converts the
results back, so you never need to handle igraph objects yourself. The
conversion is available on its own as `to_igraph(graph)`, which returns a
directed `igraph.Graph` whose vertex `name` attribute is the node ID (vertices
are in sorted node-ID order):

```python
from conftamer.query import to_igraph

g = to_igraph(appgraph)
g.vs["name"]  # ["frontend::timeout", "link0"]
```

## Command line

```bash
uv run conftamer build capture.jsonl --module-id frontend --output frontend.json
uv run conftamer stitch frontend.json backend.json --output app.json
uv run conftamer stitch frontend.json backend.json --output app.json --dropped dropped.json
uv run conftamer query app.json --node frontend::timeout
uv run conftamer export app.json --output app.graphml
```

- **`build`** turns a ContextTrack JSONL capture into a PMGraph.
- **`stitch`** combines PMGraph files into an AppGraph. With `--dropped FILE`
  it also writes the messages that were left out as a JSON list of
  `DroppedMessage` (see [Seeing what was dropped](#seeing-what-was-dropped)).
  `stitch` checks the `--dropped` file before writing anything, so if it
  already exists or is the same file as `--output`, neither file is written.
- **`query`** prints a `QueryResult` (`subgraph`, `paths`) as JSON.
- **`export`** writes GraphML.

`query` and `export` work on either graph type and detect which one they were
given. Outputs are never overwritten. Errors print one line to stderr and exit
with code 2.

For a runnable example with sample PMGraphs for a three-module app, see
[`examples/`](examples/README.md).

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