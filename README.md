# ConfTamer CLI

`conftamer` shows how configuration parameters can influence the HTTP messages
an application sends, first inside one module and then, once modules are
stitched together, across the whole application.

```
capture.jsonl --build-->  PMGraph (one per module)  --stitch-->  AppGraph
                               |                                   |
                               +------ query / export -------------+
```

- A **PMGraph** is one module's graph. Its nodes are configuration
  `parameter`s and HTTP messages (`send_request`, `receive_request`,
  `send_response`, `receive_response`). An edge `A -> B` means "A may
  influence the message B that this module sends".
- An **AppGraph** joins several PMGraphs. Each message sent by one module is
  matched with the same message received by another, and the pair becomes one
  `linked_message` node. That's how a parameter in one module can be traced to
  a module it never calls directly.

## Setup

Requires [uv](https://docs.astral.sh/uv/getting-started/installation/) and
Python 3.14 (uv can install it). From the repository root:

```bash
uv python install 3.14
uv sync --locked --dev
uv run conftamer --help
```

## Quick start

`examples/pmgraphs/` holds hand-written PMGraphs for a three-module checkout
app (`frontend -> orders -> inventory`):

```bash
uv run conftamer stitch examples/pmgraphs/*.pmgraph.json --output app.json --dropped dropped.json
uv run conftamer query app.json --key inventory.max_retries
uv run conftamer export app.json --output app.graphml
```

The query prints the part of the graph connected to that parameter, plus every
path through it:

```json
"paths": [[["orders::param-max-retries"], ["link1"], ["link3"], ["link2"]]]
```

In words: `orders`' retry setting influences its request to `inventory`
(`link1`), which influences `inventory`'s response (`link3`), which influences
the response `orders` sends back to `frontend` (`link2`).
[`examples/README.md`](examples/README.md) walks through the full output.

## Commands

| Command | What it does |
|---|---|
| `build CAPTURE.jsonl --module-id ID --output OUT.json` | Builds a PMGraph from a ContextTrack capture. |
| `stitch A.json B.json ... --output OUT.json [--dropped DROPPED.json]` | Stitches PMGraph files into one AppGraph. |
| `query GRAPH.json --node ID` | Queries one node by its ID. |
| `query GRAPH.json --key KEY [--module MODULE]` | Queries the parameter with that configuration key. |
| `export GRAPH.json --output OUT.graphml` | Exports a graph to GraphML. |

`query` and `export` accept a PMGraph or an AppGraph file. They tell the two
apart by whether the file has a `module_id`.

### `build`

Reads a ContextTrack JSONL capture of one module and writes its PMGraph. You
always supply the module ID; it's never guessed from the capture. The importer
never guesses connections either: when it can't tell which request a response
or route belongs to, it prints a warning and leaves that edge out.

### `stitch`

Two messages in **different** modules are joined into one link when **all** of
these are true:

- the `api_id`s are the same (a message with no `api_id` is never joined);
- the methods and status codes are the same;
- the sender's concrete path fits the receiver's route pattern, using net/http
  (`/items/{id}`, `/static/{rest...}`, `/{$}`, trailing `/` = whole subtree) or
  httprouter (`/items/:id`, `/static/*rest`) syntax. Unsupported pattern syntax
  is an error. When the receiver has only a plain path, the two must be equal.

Each module's own edges are then moved onto the links, and everything that no
`parameter` reaches is removed. In the AppGraph, parameters are named
`module::node` (so `::` isn't allowed in module or node IDs) and links are named
`link0`, `link1`, …. Link numbers can skip, because removed links still use up
a number.

`--dropped FILE` also writes every message that was left out, along with the
reason:

- `unmatched`: no message in another module matched it (for example, a call
  to a service you didn't stitch in);
- `unreachable`: it matched, but no parameter reaches its link.

Either both files are written or neither is.

### `query`

Name the node in exactly one of two ways:

- `--node ID`: any node ID, such as `link2` or `frontend::param-checkout-timeout`.
- `--key KEY`: a parameter's configuration key, matched exactly. If the key is
  in several modules, add `--module MODULE` to pick one. If no parameter or
  more than one matches, `query` lists the matching IDs and exits with code 2
  instead of guessing.

It prints JSON with two fields:

- **`subgraph`**: the queried node, everything that can reach it, everything
  it can reach, and all the edges among them. It uses the same format as the
  input file.
- **`paths`**: every path from a starting node to an ending node that passes
  through the queried node. A path is a list of *steps*, and each step is a list
  of node IDs. Without cycles, every step is one node.

There's no limit on the number of paths, so a query on a large, densely
branching graph can be slow.

### Cycles

Every node in a cycle influences every other node in it, so a cycle is one
step (its sorted node IDs) instead of one path per route around it:

```
r -> a -> b -> a, b -> l     paths: [[["r"], ["a", "b"], ["l"]]]
r -> a -> b -> a             paths: [[["r"], ["a", "b"]]]          (the cycle ends the path)
```

A step is a group of nodes that can all reach each other, so overlapping cycles
merge into one step. A node with an edge only to itself is a one-node step. The
edges inside a cycle are still in `subgraph`. To get plain ID lists from a graph
with no cycles: `[[node for (node,) in path] for path in paths]`.

### `export`

Writes into GraphML. Each vertex has `name` (the
node ID), `kind`, and `node_json` (the whole node). The export only goes one
way: GraphML files can't be read back or queried.


## Not implemented yet

- **Creating parameters from captures.** `build` produces only message nodes,
  so stitching captured PMGraphs gives an empty AppGraph, and every matched
  message is reported as `unreachable`. Use hand-written PMGraphs (like
  `examples/pmgraphs/`) to see full results.
- **Observable-behavior nodes** (such as file accesses or responses to outside
  clients). Paths end at the last link.
- **`query --message MODULE::NODE`** to query a link by one of its original
  messages. For now, find the link in the AppGraph whose
  `sender_module`/`sender_node` or `receiver_module`/`receiver_node` match,
  and use `--node linkN`.
- Searching by path, method or text, and querying several nodes at once.

## Python library

Every command is a thin wrapper over the library:

| Command | Function |
|---|---|
| `build` | `conftamer.contexttrack.load_contexttrack(path, module_id=...)` |
| `stitch` | `conftamer.appgraph.stitch.stitch(graphs)` / `stitch_with_dropped(graphs)` |
| `query` | `conftamer.query.query(graph, node_id)`, `find_parameters(graph, key, module=None)` |
| `export` | `conftamer.io.write_graphml(graph, path)` |
| (files) | `conftamer.io.load_graph_json`, `write_graph_json` |

`examples/walkthrough.py` (`uv run python examples/walkthrough.py`) tours the
example app through the library.

## Development

```bash
uv run pytest -q                    # tests
uvx ruff format --check src tests   # formatting (CI)
uvx ty check                        # type checking (CI)
```

VS Code: install the
[Python](https://marketplace.visualstudio.com/items?itemName=ms-python.python),
[Ruff](https://marketplace.visualstudio.com/items?itemName=charliermarsh.ruff), and
[ty](https://marketplace.visualstudio.com/items?itemName=astral-sh.ty)
extensions (uninstall Pylance), then select `.venv`'s Python as the interpreter.
