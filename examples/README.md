# ConfTamer examples

This directory shows how to use ConfTamer **as it exists today**, using the
`conftamer` command-line tool. You'll need three hand-written PMGraphs (one per
module) and a real ContextTrack capture.

## Contents

```
examples/
├── README.md                  ← this file
├── walkthrough.py             ← the same tour, using the Python library
├── contexttrack/prometheus/
│   └── scrape-ok.jsonl        ← a ContextTrack capture of one Prometheus scrape
└── pmgraphs/
    ├── frontend.pmgraph.json
    ├── orders.pmgraph.json
    └── inventory.pmgraph.json
```

## Commands

Run these from the repository root after `uv sync --locked --dev`:

| Command | What it does |
|---|---|
| `conftamer build CAPTURE.jsonl --module-id ID --output OUT.json` | Builds a PMGraph from a ContextTrack capture. |
| `conftamer stitch A.json B.json ... --output OUT.json` | Stitches PMGraph files into one AppGraph file. |
| `conftamer query GRAPH.json --node ID [--path-limit N]` | Queries a node. Prints the subgraph, paths and `truncated` flag as JSON. |
| `conftamer export GRAPH.json --output OUT.graphml` | Exports a graph to GraphML. |

`query` and `export` accept either a PMGraph file or an AppGraph file. They tell
the two apart by whether the file has a `module_id`.

Commands never overwrite an existing output file. On an error they print one
line to stderr and exit with code 2. On success they print nothing to stdout,
except `query`, which prints its result.

## The example application

The example is a small checkout flow spread across three modules (services):

```
             POST /carts/42/checkout                 PUT /stock/sku-123/reserve
 frontend  ───────────────────────────▶  orders  ───────────────────────────────▶  inventory
           ◀───────────────────────────          ◀───────────────────────────────
                       201                                      200
```

The three modules exercise every stitching behavior:

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

When writing PMGraphs by hand, follow these rules:

- **Every edge must connect two nodes that exist** in the file.
- **Node IDs and `module_id` must not contain `::`, and `module_id` must not
  end with `:`.** Stitching uses `::` to namespace IDs, as in
  `orders::param-max-retries`.
- **`path` and `pattern` must be nonempty**, and each message sets exactly one
  of them.
- **Matching messages must share an `api_id`.** Two messages are stitched only
  when they agree on `api_id`, `method`, and `status_code`, and the client's
  concrete `path` satisfies the server's `pattern`. If the server has a `path`
  instead of a `pattern`, the two paths must be identical. Wildcard syntax in a
  `path` is taken literally. A message with `"api_id": null` is never stitched.
- **Supported pattern syntaxes:** net/http (`{name}`, trailing `{name...}`,
  trailing `{$}`, and a trailing `/` that matches the whole subtree) and
  httprouter (`:name`, trailing `*name`; a trailing `/` is literal). Patterns
  must start with `/`, so no method or host prefix. A pattern that mixes the
  two syntaxes or uses anything else makes `stitch` fail.
- **Messages only match across modules.** A send and a receive in the same
  module are never stitched together.

## Walkthrough

### 1. Stitch the PMGraphs into an AppGraph

```bash
uv run conftamer stitch examples/pmgraphs/*.pmgraph.json --output app.json
```

`app.json` now holds this AppGraph:

```
nodes:
  frontend::param-checkout-timeout   parameter checkout.timeout
  inventory::param-db-pool-size      parameter db.pool_size
  link0   POST /carts/{cart_id}/checkout         frontend::send-checkout    => orders::recv-checkout
  link1   PUT /stock/:sku/reserve                orders::send-reserve       => inventory::recv-reserve
  link2   POST /carts/{cart_id}/checkout -> 201  orders::send-checkout-201  => frontend::recv-checkout-201
  link3   PUT /stock/:sku/reserve -> 200         inventory::send-reserve-200 => orders::recv-reserve-200
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
  matching receiver's message. Each link records both original nodes
  (`sender_module`/`sender_node`, `receiver_module`/`receiver_node`). Link
  numbers come from a deterministic sorted order, but adding or renaming
  modules can renumber them. To find a particular call, look it up by those
  fields in `app.json`.
- **Edges between links come from each module's own edges.** `link0 → link1` is
  orders' `recv-checkout → send-reserve` edge, moved onto the two merged nodes.
  Stitching never makes up a cross-module edge.
- **`send-analytics` is gone.** No module receives it, so it was never merged,
  and stitching drops messages that weren't merged.

### 2. Ask what can influence a behavior

Here the question is which configuration parameters, in any module, can
influence the checkout response that frontend receives (`link2`).

```bash
uv run conftamer query app.json --node link2
```

The output's `paths` are:

```
frontend::param-checkout-timeout -> link0 -> link2
inventory::param-db-pool-size -> link3 -> link2
frontend::param-checkout-timeout -> link0 -> link1 -> link3 -> link2
orders::param-max-retries -> link1 -> link3 -> link2
```

All three modules' parameters show up. Two of them reach frontend only through
another module. For example, inventory's `db.pool_size` reaches frontend only
through orders. Neither frontend's PMGraph nor orders' PMGraph could show that
by itself. In this example every node is an ancestor of `link2`, so the
returned `subgraph` is the whole AppGraph.

### 3. Ask what a parameter can affect

Querying a parameter gives the forward view:

```bash
uv run conftamer query app.json --node orders::param-max-retries
```

```json
{
  "subgraph": {
    "nodes": {
      "link1": { "kind": "linked_message", "pattern": "/stock/:sku/reserve", ... },
      "link2": { "kind": "linked_message", "pattern": "/carts/{cart_id}/checkout", "status_code": 201, ... },
      "link3": { "kind": "linked_message", "pattern": "/stock/:sku/reserve", "status_code": 200, ... },
      "orders::param-max-retries": { "kind": "parameter", "key": "inventory.max_retries" }
    },
    "edges": [["link1", "link3"], ["link3", "link2"], ["orders::param-max-retries", "link1"]]
  },
  "paths": [["orders::param-max-retries", "link1", "link3", "link2"]],
  "truncated": false
}
```

The subgraph contains only the queried node and the nodes connected to it.
Unrelated parameters and the frontend→orders request (`link0`) are left out.

### 4. Export to GraphML

```bash
uv run conftamer export app.json --output app.graphml
```

This writes a GraphML file that tools such as Gephi, yEd or igraph can open.
Each node keeps its ID as `name`, its `kind`, and its full contents as JSON in
`node_json`.

### Building a PMGraph from a capture

`build` turns a ContextTrack capture into a PMGraph:

```bash
uv run conftamer build examples/contexttrack/prometheus/scrape-ok.jsonl \
  --module-id scraper --output scraper.pmgraph.json
```

The capture records one HTTP scrape, so the PMGraph has four message nodes:
the request sent and received, and the `200` response sent and received. It
also has one edge, `n1 → n2`: the request the server received influenced the
response it sent. Captures contain no configuration parameters. Stitching
keeps only what a parameter can reach, so a built PMGraph produces an empty
AppGraph until you add `Parameter` nodes and their edges by hand.

## Things to keep in mind

- **Stitching drops anything a `Parameter` can't reach.** If your PMGraphs have
  no parameter nodes, or no edges from a parameter to a send, the AppGraph will
  be empty.
- **The same steps work from Python.** `uv run python examples/walkthrough.py`
  stitches and queries the example PMGraphs with the library (`stitch()`,
  `query()`), and `conftamer.io` loads and writes graph files.

## Not available yet

- Nothing generates `Parameter` nodes automatically; you add them by hand.
- There are no observable-behavior nodes yet, so query paths end at the last
  link rather than at a file access or web response.
- GraphML export is one-way: there's no GraphML importer.
