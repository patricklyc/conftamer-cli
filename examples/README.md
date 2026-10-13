# ConfTamer examples

This directory shows how to use ConfTamer **as it exists today**: three
hand-written PMGraphs, and a script that loads, stitches, and queries them.

> **What works right now.** ConfTamer is currently a Python library. You can
> load PMGraphs from JSON, **stitch** them into an AppGraph, and **query** either
> kind of graph. The `conftamer` command-line program is still a placeholder
> (`uv run conftamer World` prints `Hello World!`). On this branch nothing builds
> PMGraphs from captures, writes graph files, or exports GraphML. Because of
> that, the PMGraphs below are written by hand.

## Contents

```
examples/
├── README.md                  ← this file
├── walkthrough.py             ← runnable end-to-end tour
└── pmgraphs/
    ├── frontend.pmgraph.json
    ├── orders.pmgraph.json
    └── inventory.pmgraph.json
```

## Quick start

From the repository root (after `uv sync --locked --dev`):

```bash
uv run python examples/walkthrough.py
```

The script prints each step shown in the walkthrough below. The output is
deterministic, so yours should match exactly.

## The example application

The example is a small checkout flow spread across three modules (services):

```
             POST /carts/42/checkout                 PUT /stock/sku-123/reserve
 frontend  ───────────────────────────▶  orders  ───────────────────────────────▶  inventory
           ◀───────────────────────────          ◀───────────────────────────────
                       201                                      200
```

- **frontend** sends the checkout request and receives the `201` response. Its
  `checkout.timeout` parameter influences the checkout request. It also
  influences an analytics call to a service we have no PMGraph for.
- **orders** handles `POST /carts/{cart_id}/checkout` (a net/http-style
  pattern). While handling it, orders calls inventory, then sends the `201`. Its
  `inventory.max_retries` parameter influences the inventory call.
- **inventory** handles `PUT /stock/:sku/reserve` (an httprouter-style pattern).
  Its `db.pool_size` parameter influences the `200` response it sends.

Together, the three modules exercise every stitching behavior:

| Behavior | Where in the example |
|---|---|
| A concrete path matched to a `{name}` pattern | `/carts/42/checkout` ↔ `/carts/{cart_id}/checkout` |
| A concrete path matched to a `:name` pattern | `/stock/sku-123/reserve` ↔ `/stock/:sku/reserve` |
| A request/response round trip | each request has a matching response link |
| A chain through an intermediate module | frontend → orders → inventory and back |
| Unmatched messages are dropped | frontend's `send-analytics` (no analytics module) |

## PMGraph file format

A `*.pmgraph.json` file is a serialized `conftamer.pmgraph.models.PMGraph`:

```json
{
  "module_id": "orders",
  "nodes": {
    "<node-id>": { "kind": "...", ... }
  },
  "edges": [["<source-node-id>", "<target-node-id>"], ...]
}
```

An edge `A → B` means "A may influence B within this module". The usual cases
are a parameter influencing a message the module sends, or a received message
influencing a later sent message.

Node kinds:

| `kind` | Required fields | Notes |
|---|---|---|
| `parameter` | `key` | A configuration key, e.g. `"db.pool_size"`. |
| `send_request` | `api_id`, `method`, `host`, `path` | Client side: uses a **concrete** path. |
| `receive_response` | `api_id`, `method`, `host`, `path`, `status_code` | Client side: uses a **concrete** path. |
| `receive_request` | `api_id`, `method`, `pattern` (or `path`) | Server side: no `host`. |
| `send_response` | `api_id`, `method`, `pattern` (or `path`), `status_code` | Server side: no `host`. |

When writing PMGraphs by hand, follow these rules:

- **Node IDs and `module_id` must not contain `::`.** Stitching uses `::` to
  namespace IDs, as in `orders::param-max-retries`.
- **Matching messages must share an `api_id`.** Two messages are stitched only
  when they agree on `api_id`, `method`, and `status_code`, and the client's
  concrete `path` satisfies the server's `pattern`. A message with
  `"api_id": null` is never stitched.
- **Supported pattern syntaxes:** net/http (`{name}`, trailing `{name...}`) and
  httprouter (`:name`, trailing `*name`).
- **Messages only match across modules.** A send and a receive in the same
  module are never stitched together.

## Walkthrough

### 1. Load the PMGraphs

```python
from pathlib import Path
from conftamer.pmgraph.models import PMGraph

pmgraphs = [
    PMGraph.model_validate_json(path.read_text())
    for path in sorted(Path("examples/pmgraphs").glob("*.pmgraph.json"))
]
```

### 2. Stitch into an AppGraph

```python
from conftamer.appgraph.stitch import stitch

appgraph = stitch(pmgraphs)
```

```
  nodes:
    frontend::param-checkout-timeout   parameter checkout.timeout
    inventory::param-db-pool-size      parameter db.pool_size
    link0                              POST /carts/{cart_id}/checkout  [frontend::send-checkout => orders::recv-checkout]
    link1                              PUT /stock/:sku/reserve  [orders::send-reserve => inventory::recv-reserve]
    link2                              POST /carts/{cart_id}/checkout -> 201  [orders::send-checkout-201 => frontend::recv-checkout-201]
    link3                              PUT /stock/:sku/reserve -> 200  [inventory::send-reserve-200 => orders::recv-reserve-200]
    orders::param-max-retries          parameter inventory.max_retries
  edges:
    frontend::param-checkout-timeout -> link0
    inventory::param-db-pool-size -> link3
    link0 -> link1
    link0 -> link2
    link1 -> link3
    link3 -> link2
    orders::param-max-retries -> link1
```

How to read this:

- **Parameters are namespaced** as `module_id::node_id`.
- **Each `linkN` is one API call**, made by merging a sender's message with the
  matching receiver's message. `LinkedMessage` records both original nodes
  (`sender_module`/`sender_node`, `receiver_module`/`receiver_node`). Link
  numbers come from a deterministic sorted order. To find a particular link,
  look it up by those fields rather than hard-coding `link2`. `walkthrough.py`
  shows how.
- **Edges between links come from each module's own edges.** `link0 → link1` is
  orders' `recv-checkout → send-reserve` edge, moved onto the two merged nodes.
  Stitching never makes up a cross-module edge.
- **`send-analytics` is gone.** No module receives it, so it was never merged,
  and stitching drops messages that weren't merged.

### 3. Ask what can influence a behavior

Here the question is which configuration parameters, in any module, can
influence the checkout response that frontend receives (`link2`).

```python
from conftamer.query import query

result = query(appgraph, "link2")
```

```
paths (truncated=False):
    frontend::param-checkout-timeout -> link0 -> link2
    inventory::param-db-pool-size -> link3 -> link2
    frontend::param-checkout-timeout -> link0 -> link1 -> link3 -> link2
    orders::param-max-retries -> link1 -> link3 -> link2
```

All three modules' parameters show up. Two of them reach frontend only through
another module. For example, inventory's `db.pool_size` reaches frontend only
through orders. Neither frontend's PMGraph nor orders' PMGraph could show that
by itself. In this example every node is an ancestor of `link2`, so
`result.subgraph` is the whole AppGraph.

### 4. Ask what a parameter can affect

Querying a parameter gives the forward view:

```python
result = query(appgraph, "orders::param-max-retries")
```

```
subgraph:
  nodes:
    link1                              PUT /stock/:sku/reserve  [orders::send-reserve => inventory::recv-reserve]
    link2                              POST /carts/{cart_id}/checkout -> 201  [orders::send-checkout-201 => frontend::recv-checkout-201]
    link3                              PUT /stock/:sku/reserve -> 200  [inventory::send-reserve-200 => orders::recv-reserve-200]
    orders::param-max-retries          parameter inventory.max_retries
  edges:
    link1 -> link3
    link3 -> link2
    orders::param-max-retries -> link1
paths (truncated=False):
    orders::param-max-retries -> link1 -> link3 -> link2
```

The subgraph contains only the queried node and the nodes connected to it.
Unrelated parameters and the frontend→orders request (`link0`) are left out.

### 5. Cap the number of paths

The number of root-to-leaf paths can grow very quickly on large graphs. Set
`path_limit` to cap it. When paths were dropped, `truncated` is `True`. The
cap affects only `paths`; `subgraph` is always complete.

```python
result = query(appgraph, "link2", path_limit=2)
```

```
paths (truncated=True):
    frontend::param-checkout-timeout -> link0 -> link2
    inventory::param-db-pool-size -> link3 -> link2
```

Paths always come out in the same order, so a given limit always keeps the same
paths.

## Using your own graphs

Write one `*.pmgraph.json` per module, following the format above, then run
stitching and queries from an interactive session:

```bash
uv run python
```

```python
from pathlib import Path
from conftamer.pmgraph.models import PMGraph
from conftamer.appgraph.stitch import stitch
from conftamer.query import query
graphs = [PMGraph.model_validate_json(p.read_text()) for p in Path("my-graphs").glob("*.pmgraph.json")]
app = stitch(graphs)
sorted(app.nodes)                       # find the node ID you care about
result = query(app, "mymodule::my-param", path_limit=100)
print(result.subgraph.model_dump_json(indent=2))   # subgraph as JSON
result.paths
```

Things to keep in mind:

- **Stitching drops anything a `Parameter` can't reach.** If your PMGraphs have
  no parameter nodes, or no edges from a parameter to a send, the AppGraph will
  be empty.
- **Errors raise `ValueError`.** This happens for an unknown node ID, an edge
  that points at a missing node, a duplicate `module_id`, or an ID containing
  `::`.
- **You can save the AppGraph yourself.** `AppGraph.model_dump_json()` gives
  JSON, and `AppGraph.model_validate_json()` loads it back. ConfTamer has no
  writer for this on this branch.
- **`conftamer.query.to_igraph(graph)` gives you an `igraph.Graph`** if you
  want to run your own igraph analysis.

## Not available yet

- The `conftamer` CLI has no build, stitch, query, or export commands.
- Nothing builds PMGraphs from ContextTrack runtime captures on this branch.
- Nothing generates `Parameter` nodes automatically; you add them by hand.
- There is no file writer and no GraphML export on this branch.
