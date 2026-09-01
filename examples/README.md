# Example input catalog

Files under `examples/` are executable producer inputs for ConfTamer workflows.
Generated `*.pmgraph.json`, `*.appgraph.json`, and `*.graphml` files do not
belong in these directories; write them to a temporary or output directory.

## ContextTrack traces

The checked-in traces were captured from instrumented Prometheus-related Go
tests. The caller must choose the module ID represented by a build; the examples
below use `github.com/prometheus/prometheus`.

| Input | Valid event lines | Purpose |
| --- | ---: | --- |
| `contexttrack/prometheus/scrape-ok.jsonl` | 20 | Small build and enrichment smoke input |
| `contexttrack/prometheus/package-tests.jsonl` | 5,530 | Package-level integration input |
| `contexttrack/prometheus/all-tests.jsonl` | 13,954 | Broad, noisy matching and omission input |

Counts describe these captures, not format limits or stable output counts.
Absolute source prefixes were normalized to `/go-conftamer/src/` before
check-in. Runtime values such as process IDs, ports, and temporary socket names
remain as captured.

### Build a message-only PMGraph

```bash
uv run conftamer build \
  --module-id github.com/prometheus/prometheus \
  --events examples/contexttrack/prometheus/scrape-ok.jsonl \
  --output /tmp/scrape-ok.pmgraph.json
```

The broad trace intentionally produces many conservative diagnostics. Redirect
standard error when inspecting it:

```bash
uv run conftamer build \
  --module-id github.com/prometheus/prometheus \
  --events examples/contexttrack/prometheus/all-tests.jsonl \
  --output /tmp/all-tests.pmgraph.json \
  2>/tmp/all-tests.diagnostics
```

## ParamTrack and CType artifacts

[`paramtrack/`](paramtrack/) contains real Prometheus outputs from ParamTrack
and the gopls CType analysis it consumes:

- `paramtrack/static/` contains the Unmarshaler Subgraph and Accessors graphs;
- `paramtrack/runs/target-scraper-all/parameters.csv` contains one 108-key row;
- `paramtrack/runs/manager-st-zero/parameters.csv` contains four rows whose
  union has 226 keys; and
- [the ParamTrack catalog](paramtrack/README.md) records provenance and observed
  counts.

### Build an enriched PMGraph

The target-scraper row matches one semantic `GET /` Send Request in the small
ContextTrack trace and produces 108 Parameter edges while retaining its message
edge:

```bash
uv run conftamer build \
  --module-id github.com/prometheus/prometheus \
  --events examples/contexttrack/prometheus/scrape-ok.jsonl \
  --paramtrack-csv examples/paramtrack/runs/target-scraper-all/parameters.csv \
  --unmarshaler examples/paramtrack/static/unmarshaler_subgraph.text \
  --accessors examples/paramtrack/static/accessors.text \
  --output /tmp/scrape-ok-enriched.pmgraph.json
```

Supplying these inputs is the caller's assertion that they describe a compatible
corpus; the producer files contain no shared verifiable run identity.

### Query a CType graph

```bash
uv run conftamer query \
  examples/paramtrack/static/accessors.text \
  scrape.targetScraper \
  --output /tmp/target-scraper-ctype.graphml
```

Query the enriched PMGraph by a parameter label:

```bash
uv run conftamer query \
  /tmp/scrape-ok-enriched.pmgraph.json \
  global.external_labels.data \
  --direction descendants \
  --output /tmp/target-scraper-parameter.graphml
```

### Reference-only files

Files ending in `.gv` are Graphviz topology views. Files named
`parameters_hierarchy.txt` are human-readable ParamTrack derivatives, and
`*.log` files are producer logs. They are retained as provenance and are not
ConfTamer machine inputs. Producer CType GraphML is not accepted because no
real producer GraphML contract is available.

## Stitch, query, and export module graphs

The repository does not contain a real multi-module trace corpus, so it would
be misleading to assign different module IDs to the Prometheus captures merely
to manufacture a stitch example. Given PMGraphs built from two actual modules,
stitch them with:

```bash
uv run conftamer stitch \
  /path/to/frontend.pmgraph.json \
  /path/to/backend.pmgraph.json \
  --output /tmp/application.appgraph.json
```

Then query or export the canonical AppGraph:

```bash
uv run conftamer query \
  /tmp/application.appgraph.json \
  '/items' \
  --all-matches \
  --output /tmp/items.graphml

uv run conftamer export \
  /tmp/application.appgraph.json \
  --output /tmp/application.graphml
```

The release workflow independently exercises multi-PMGraph stitching with
minimal generated client/server ContextTrack inputs. Every generated GraphML is
re-read with igraph during automated verification.
