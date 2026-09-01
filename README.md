# ConfTamer graph compiler and explorer

ConfTamer consumes files emitted by ContextTrack, ParamTrack, and the gopls
CType analysis. It builds deterministic canonical graphs, conservatively
stitches module graphs into an application graph, and exports query results as
GraphML for tools such as [Gephi Lite](https://lite.gephi.org/).

| Workflow | Input | Output |
| --- | --- | --- |
| `build` | ContextTrack JSONL, optionally ParamTrack CSV and two CType graphs | PMGraph v2 JSON |
| `stitch` | Two or more PMGraph v2 files | AppGraph v1 JSON |
| `query` | PMGraph, AppGraph, or CType `.text` | Reachability GraphML |
| `export` | PMGraph, AppGraph, or CType `.text` | Complete GraphML |

## Install and run

ConfTamer requires Python 3.13 or newer. From a checkout with
[uv](https://docs.astral.sh/uv/) installed:

```bash
uv sync
uv run conftamer --help
```

The examples below use `uv run conftamer`. If ConfTamer is installed in the
active environment, use `conftamer` directly.

### Standalone release binaries

The **Release binaries** GitHub Actions workflow publishes Linux x86-64, macOS
ARM64, and Windows x86-64 artifacts. Download the archive for your platform
from a successful workflow run, extract it, and make the executable runnable
on Linux or macOS:

```bash
chmod +x conftamer-*
./conftamer-* --help
```

Workflow artifacts are retained for 14 days. Tagged releases also publish the
executables and checksums on the repository's Releases page.

## Build a PMGraph

A message-only build requires a ContextTrack JSONL trace and the module ID
represented by the trace:

```bash
uv run conftamer build \
  --module-id github.com/prometheus/prometheus \
  --events examples/contexttrack/prometheus/scrape-ok.jsonl \
  --output /tmp/prometheus.pmgraph.json
```

ContextTrack does not provide a trustworthy module ID for the complete trace;
the caller supplies it. Recoverable malformed or unmatched records are omitted
with diagnostics on standard error. A concise output summary is written to
standard output.

### Add ParamTrack enrichment

An enriched build requires all three enrichment options together: one targeted
ParamTrack CSV and the Unmarshaler and Accessors CType graphs.

```bash
uv run conftamer build \
  --module-id github.com/prometheus/prometheus \
  --events examples/contexttrack/prometheus/scrape-ok.jsonl \
  --paramtrack-csv examples/paramtrack/runs/target-scraper-all/parameters.csv \
  --unmarshaler examples/paramtrack/static/unmarshaler_subgraph.text \
  --accessors examples/paramtrack/static/accessors.text \
  --output /tmp/prometheus-enriched.pmgraph.json
```

Enrichment is aggregate and caller-asserted: the current producer files do not
share a verifiable run identity. ConfTamer validates each CType and creates
parameter influence edges only when method and path select one unique semantic
Send Request.

## Stitch module graphs

Stitch two or more PMGraphs whose `module_id` values are distinct:

```bash
uv run conftamer stitch \
  frontend.pmgraph.json \
  inventory.pmgraph.json \
  --output application.appgraph.json
```

ConfTamer contracts only mutually unique cross-module HTTP request/response
matches. It retains unmatched nodes by default. To remove unmatched message
nodes from the output, add `--drop-unmatched`.

## Query a graph

`query` searches exact canonical IDs first, then case-insensitive substrings of
visualization attributes. Ambiguous searches fail unless `--all-matches` is
provided.

```bash
uv run conftamer query \
  /tmp/prometheus-enriched.pmgraph.json \
  global.external_labels.data \
  --direction descendants \
  --output /tmp/parameter-influence.graphml
```

`--direction` accepts `ancestors`, `descendants`, or `both` (the default). The
result contains the matched vertices and the requested transitive reachability
as an induced subgraph.

CType `.text` graphs can be queried directly:

```bash
uv run conftamer query \
  examples/paramtrack/static/accessors.text \
  scrape.targetScraper \
  --output /tmp/target-scraper-ctype.graphml
```

## Export a complete graph

```bash
uv run conftamer export \
  application.appgraph.json \
  --output application.graphml
```

GraphML is a visualization projection, not canonical persistence, and is not
accepted as PMGraph or AppGraph input.

## Accepted and reference-only files

Current machine inputs are ContextTrack JSONL, targeted ParamTrack CSV, gopls
CType `.text` JSON, PMGraph v2 JSON, and AppGraph v1 JSON. CType `.gv` files,
ParamTrack hierarchy files, and producer logs are reference-only. Producer
CType GraphML remains blocked until real producer artifacts establish its
transport contract.

See:

- the [example catalog](examples/README.md) for checked-in inputs and commands;
- the [technical reference](docs/technical-reference.md) for CLI and Python API
  behavior;
- the [target architecture](docs/rewrite/architecture.md) for canonical graph,
  matching, provenance, and serialization contracts; and
- [input formats and provenance](docs/rewrite/input-formats.md) for observed
  producer formats and evidence.

## License

ConfTamer is licensed under the GNU General Public License, version 2 only.
See [LICENSE](LICENSE).
