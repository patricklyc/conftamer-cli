# ConfTamer

ConfTamer builds a **per-module influence graph (PMGraph)** from normalized
ContextTrack schema-v1 JSONL, stitches the PMGraphs of several modules into one
**application graph (AppGraph)**, queries either graph, and exports GraphML.
It models possible influence between received and sent messages—not execution
replay, proven causality, or complete capture coverage.

```text
normalized.jsonl --build--> PMGraph (one per module) --stitch--> AppGraph
                               |                                    |
                               +--------- query / export -----------+
```

- A **PMGraph** is one module's graph. Its nodes are HTTP messages
  (`send_request`, `receive_request`, `send_response`, `receive_response`) and,
  in hand-written graphs, configuration `parameter`s. An edge `A → B` means A
  may influence B.
- An **AppGraph** joins several PMGraphs. A message sent by one module and the
  matching message received by another become one `linked_message` node, so
  influence can be followed across modules.

It consumes messages only. It does not collect traces, import raw captures,
ingest parameters, or import/query GraphML.

## Setup

Requires [uv](https://docs.astral.sh/uv/getting-started/installation/). Run these
commands in Bash from the repository root to install Python 3.14 and the locked
dependencies:

```bash
uv python install 3.14
uv sync --locked --dev
```

## Quick start

Build from the bundled normalized capture, query a node, and export the graph.
A fresh temporary directory keeps outputs separate from the source fixtures.

```bash
RUN=$(mktemp -d /tmp/conftamer-run.XXXXXX) &&
uv run conftamer build \
  examples/contexttrack/prometheus/TestTargetScraperScrapeOK/normalized.jsonl \
  --module-id example-module --output "$RUN/module.pmgraph.json"

# Print the subgraph of everything that can influence, or be influenced by,
# the received-request node.
uv run conftamer query "$RUN/module.pmgraph.json" --node n1

# Export the same graph to GraphML.
uv run conftamer export "$RUN/module.pmgraph.json" \
  --output "$RUN/module.graphml"

# Inspect the graph and its exact node IDs.
uv run python -m json.tool "$RUN/module.pmgraph.json"
```

The query prints a PMGraph JSON document holding `n1`, `n2`, and the edge between
them, which can be saved and passed to `export`. For your own capture, replace
the input path and choose `--module-id`; module identity is not inferred from
API IDs. Output files must be new and their parent directory must exist.

## Stitch modules

The bundled capture is a single module, and messages are only linked across
modules, so stitching it alone gives no links. `examples/pmgraphs/` holds three
**synthetic, hand-written** PMGraphs for a checkout application
(`frontend → orders → inventory`) to show stitching:

```bash
RUN=$(mktemp -d /tmp/conftamer-run.XXXXXX) &&
uv run conftamer stitch examples/pmgraphs/*.pmgraph.json \
  --output "$RUN/app.json"

# What can the parameter with this configuration key influence?
uv run conftamer query "$RUN/app.json" --key inventory.max_retries

# The same, also listing every path through that parameter.
uv run conftamer query "$RUN/app.json" --key inventory.max_retries --paths

uv run conftamer export "$RUN/app.json" --output "$RUN/app.graphml"
```

`stitch` writes two files: the AppGraph `app.json`, and `app.dropped.json`,
which lists every input message left out of the AppGraph and why. Here that is
one request to an analytics service that is not among the three modules.

The query prints the AppGraph nodes connected to `orders`' retry setting. With
`--paths` it also prints

```json
"paths": [[["orders::param-max-retries"], ["link1"], ["link3"], ["link2"]]]
```

which reads: the setting influences `orders`' request to `inventory` (`link1`),
which influences `inventory`'s response (`link3`), which influences the response
`orders` sends back to `frontend` (`link2`).
[`examples/README.md`](examples/README.md) walks through the example.

## Commands

| Command | What it does |
| --- | --- |
| `build CAPTURE.jsonl --module-id ID --output OUT.json` | Builds a message-only PMGraph from a normalized ContextTrack capture. |
| `stitch A.json B.json ... --output OUT.json [--dropped REPORT.json] [--prune-unconfigured]` | Stitches PMGraph files into one AppGraph and reports the messages left out. |
| `query GRAPH.json --node ID [--paths]` | Prints the subgraph around one node. |
| `query GRAPH.json --key KEY [--module MODULE] [--paths]` | The same, for the parameter with that configuration key. |
| `export GRAPH.json --output OUT.graphml` | Exports a graph to GraphML. |

`query` and `export` accept a PMGraph or an AppGraph file. Commands never
overwrite a file; on an expected error they print one diagnostic to stderr and
exit with code 2.

## Normalize raw captures

Go hooks emit raw JSONL, which must be normalized separately before `build`.
This example uses the bundled raw fixture; replace its path with your capture:

```bash
NORMALIZED=$(mktemp -d /tmp/conftamer-normalize.XXXXXX) &&
uv run contexttrack normalize \
  examples/contexttrack/prometheus/TestTargetScraperScrapeOK/raw.jsonl \
  --output "$NORMALIZED/events.v1.jsonl" &&
uv run conftamer build "$NORMALIZED/events.v1.jsonl" \
  --module-id example-module --output "$NORMALIZED/module.pmgraph.json"
```

## More

- [Reference](docs/reference.md): graph semantics, stitching rules and limits,
  formats, errors, and Python API.
- [Examples](examples/README.md): the synthetic application, capture inventory,
  and fixture policy.
- [Development](docs/development.md): checks, editor setup, and design history.
- [License: GPL-2.0-only](LICENSE).
