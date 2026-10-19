# ConfTamer

ConfTamer turns ContextTrack HTTP traces into a **per-module influence graph
(PMGraph)**: a directed graph of possible influence between a module's received
and sent messages. Build a graph from a capture, query node reachability, or
export it to GraphML.

The current implementation consumes **normalized ContextTrack schema-v1 JSONL**
only. Go hooks emit raw captures; normalize them separately with the installed
ContextTrack package before building. ConfTamer does not collect traces or prove
causality or capture completeness.

## Setup

Requires [uv](https://docs.astral.sh/uv/getting-started/installation/) and
Python 3.14 or newer. From the repository root, install Python and the locked
development dependencies:

```bash
uv python install 3.14
uv sync --locked --dev
```

The lockfile pins ContextTrack 0.2.0 to Git revision
`b014ae331865b36ae011b2fa00a7661763612ca1` (`contexttrack` subdirectory),
with Pydantic >=2.13.5,<3; no sibling checkout is needed at runtime.

## Quick start

Run the following in Bash from the repository root. A fresh temporary directory
keeps generated files separate from the source captures and avoids overwriting
previous output.

```bash
RUN=$(mktemp -d /tmp/conftamer-run.XXXXXX) &&
uv run conftamer build \
  examples/contexttrack/prometheus/TestTargetScraperScrapeOK/normalized.jsonl \
  --module-id example-module --output "$RUN/module.pmgraph.json"

# Query the received-request node in this capture.
uv run conftamer query "$RUN/module.pmgraph.json" --node n1

# Export the same graph to GraphML.
uv run conftamer export "$RUN/module.pmgraph.json" \
  --output "$RUN/module.graphml"
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
are in `$RUN`; both supplied source files (`raw.jsonl` and `normalized.jsonl`)
are unchanged. The normalized capture retains all 20 observations, including
eight received-response hooks, rather than deduplicating them into the four
semantic nodes.

The [example inventory](examples/README.md) also describes the larger `all-tests`
pair: 7,235 observations per file, producing 960 nodes and 117 edges with 373
warnings under the current conservative association policy. These are regression
results for these artifacts, not general graph-size guarantees or a verified
multi-module corpus.

For your own completed capture, pass its normalized v1 path to `build` and choose
`--module-id`. If you have raw JSONL, normalize it first into a **new file in an
existing directory**, then pass that output to `build`:

```bash
uv run contexttrack normalize /path/to/raw.jsonl --output /path/to/new-events.v1.jsonl
```

The module identity is supplied by you, not inferred from API IDs. Node IDs are
keys in the PMGraph JSON file's top-level `nodes` object, not API IDs or URLs.
Inspect the file to choose an exact ID:

```bash
uv run python -m json.tool "$RUN/module.pmgraph.json"
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

- **Inputs:** `build` reads normalized ContextTrack v1 UTF-8 JSONL; `query` and
  `export` read PMGraph JSON. PMGraph JSON loading rejects type coercion and unknown fields,
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
- **GraphML:** Export preserves directed named topology, isolates, and the graph
  attribute `module_id`. Vertices expose `name`, `kind`, `key`, `api_id`, `method`,
  `host`, `path`, `pattern`, and `status_code` as named attributes, not an embedded
  JSON document. Use `name` for original node IDs; readers may also expose
  writer-generated XML IDs. Native conversions can turn nulls into `"None"`,
  numeric `NaN`, or `False` for all-null attributes; large integers may lose
  precision. GraphML is not lossless PMGraph persistence; use PMGraph JSON for
  that. Export rejects XML-invalid characters and carriage returns in module/node
  IDs and every string-valued node field rather than silently altering them.

### Input compatibility

This is a breaking input-format and exception change, not a graph-schema change.
Raw, mixed-format, or unsupported-version captures now fail; there is no format
option, auto-detection, or raw fallback. Existing saved PMGraphs remain usable by
`query` and `export`.

Upstream validation rejects unknown kinds/fields, wrong-kind payload fields,
coercion, duplicate keys, BOM, and nonfinite numbers. Normalized `context` and
`message` objects are required (`{}` is valid incomplete evidence); paths must
be nonempty when present and response status must be a nonnegative integer or
null (`0` and `999` are valid; there is no 100–599 restriction). Only upstream raw
normalization converts an explicit empty raw path to `/`. Missing labels and
ambiguous associations still warn and omit conservatively. HTTP query strings,
handlers, and debug/context diagnostics do not become graph labels.

## Python API

The same operations are callable without the CLI:

```python
from conftamer.contexttrack import load_contexttrack
from conftamer.pmgraph.igraph_ops import query_node

graph = load_contexttrack(
    "examples/contexttrack/prometheus/TestTargetScraperScrapeOK/normalized.jsonl",
    module_id="example-module",
)
print(query_node(graph, "n1"))
```

For persistence, `conftamer.pmgraph.io` provides `load_pmgraph_json(path)` and
`write_pmgraph_json(graph, path)`. For conversion and export,
`conftamer.pmgraph.igraph_ops` provides `to_igraph(graph)` and
`write_graphml(graph, path)`.

The ContextTrack reader raises `contexttrack.EventFileError` (a `ValueError`)
for invalid input, retaining `.path`, physical `.line`, `.reason`, and the original
exception as `__cause__`. Clients catching the old raw parser's `TypeError` must
catch `EventFileError`/`ValueError` instead. Caller validation is unchanged:
nonstring `module_id` raises `TypeError`, and an empty string raises `ValueError`,
before input is opened. PMGraph JSON loading raises `ValueError` for invalid
data; filesystem failures remain `OSError`.

## Development

Run the tests, formatting and type checks, and CLI help:

```bash
uv run pytest -q
uvx ruff format --check src tests
uvx ty check
uv run conftamer --help
uv run conftamer build --help
```

Tests cover consumer graph policy, both supplied normalized real captures, and
representative upstream-reader failures, including raw-input rejection. They read
repository fixtures directly; no sibling checkout or Go capture run is needed.
Exhaustive wire-schema validation belongs to the pinned ContextTrack package.
See [AGENTS.md](AGENTS.md) for development scope and the
[normalized-input contract](docs/superpowers/plans/2026-10-13-normalized-contexttrack-input.md)
for the implemented migration. Other plans retain their original implementation
steps as history; the [PR #8 review](docs/pr-8-code-review.md) concerns a different
reviewed revision, not features available in this checkout.

For VS Code, select `.venv/bin/python` as the workspace interpreter. The
[Python](https://marketplace.visualstudio.com/items?itemName=ms-python.python),
[Ruff](https://marketplace.visualstudio.com/items?itemName=charliermarsh.ruff), and
[ty](https://marketplace.visualstudio.com/items?itemName=astral-sh.ty) extensions
provide Python integration, formatting, and type checking, respectively.

## License

[GPL-2.0-only](LICENSE).
