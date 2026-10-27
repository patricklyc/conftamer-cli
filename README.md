# ConfTamer

ConfTamer builds a **per-module influence graph (PMGraph)** from normalized
ContextTrack schema-v1 JSONL, queries its reachability, and exports GraphML.
It models possible influence between received and sent messages—not execution
replay, proven causality, or complete capture coverage.

This is a message-only, single-module consumer. It does not collect traces,
import raw captures, ingest parameters, stitch modules, or import/query GraphML.

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

# Print ancestors and descendants of the received-request node.
uv run conftamer query "$RUN/module.pmgraph.json" --node n1

# Export the same graph to GraphML.
uv run conftamer export "$RUN/module.pmgraph.json" \
  --output "$RUN/module.graphml"

# Inspect the graph and its exact node IDs.
uv run python -m json.tool "$RUN/module.pmgraph.json"
```

The query returns `{"ancestors": [], "descendants": ["n2"]}`. For your own capture,
replace the input path and choose `--module-id`; module identity is not inferred
from API IDs. Output files must be new and their parent directory must exist.

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

- [Reference](docs/reference.md): graph semantics, formats, errors, and Python API.
- [Examples](examples/README.md): capture inventory and fixture policy.
- [Development](docs/development.md): checks, editor setup, and design history.
- [License: GPL-2.0-only](LICENSE).
