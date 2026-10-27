# ConfTamer reference

See the [README](../README.md) for setup and runnable build/query/export commands.
This reference describes the current message-only ContextTrack consumer, not the
broader system proposed in the paper.

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

The module identity is supplied by you through `--module-id`, not inferred from
API IDs. Node IDs are keys in the PMGraph JSON file's top-level `nodes` object,
not API IDs or URLs. Inspect the file to choose an exact ID; after the README's
quick start, use:

```bash
uv run python -m json.tool "$RUN/module.pmgraph.json"
```

## Files and errors

- **Inputs:** `build` reads normalized ContextTrack v1 UTF-8 JSONL; `query` and
  `export` read PMGraph JSON. PMGraph JSON loading rejects type coercion and
  unknown fields, and validates message field combinations, nonempty module/node
  IDs, and existing edge endpoints. PMGraph JSON output preserves node order and
  explicit nulls and sorts edge pairs.
- **Outputs:** `build` and `export` require `--output`. The parent directory must
  exist and the file must be new; existing files are never overwritten. Writes
  are not atomic, so a filesystem failure can leave a partial new file.
- **Diagnostics:** Build and export leave stdout empty on success; query prints
  indented JSON. Warnings go to stderr. Expected input or filesystem errors,
  including unknown node IDs, produce stderr diagnostics and exit code 2 without
  a traceback. Capture record diagnostics include the input path and physical
  line number.

## GraphML export

Export preserves directed named topology, isolates, and the graph attribute
`module_id`. Vertices expose `name`, `kind`, `key`, `api_id`, `method`, `host`,
`path`, `pattern`, and `status_code` as named attributes, not an embedded JSON
document. Use `name` for original node IDs; readers may also expose
writer-generated XML IDs.

Native conversions can turn nulls into `"None"`, numeric `NaN`, or `False` for
all-null attributes; large integers may lose precision. GraphML is not lossless
PMGraph persistence; use PMGraph JSON for that. Export rejects XML-invalid
characters and carriage returns in module/node IDs and every string-valued node
field rather than silently altering them.

## ContextTrack dependency and input compatibility

The lockfile pins ContextTrack 0.2.0 to Git revision
`b014ae331865b36ae011b2fa00a7661763612ca1` (`contexttrack` subdirectory),
with Pydantic >=2.13.5,<3; no sibling checkout is needed at runtime.

The normalized-only migration is a breaking input-format and exception change,
not a graph-schema change. Raw, mixed-format, or unsupported-version captures
fail; there is no format option, auto-detection, or raw fallback. Existing saved
PMGraphs remain usable by `query` and `export`.

Upstream validation rejects unknown kinds/fields, wrong-kind payload fields,
coercion, duplicate keys, BOM, and nonfinite numbers. Normalized `context` and
`message` objects are required (`{}` is valid incomplete evidence); paths must
be nonempty when present and response status must be a nonnegative integer or
null (`0` and `999` are valid; there is no 100–599 restriction). Only upstream raw
normalization converts an explicit empty raw path to `/`. Missing labels and
ambiguous associations still warn and omit conservatively. HTTP query strings,
handlers, and debug/context diagnostics do not become graph labels.

## Example data

The README's bundled capture produces four nodes and one edge, `n1 → n2`:
`n1` is a received request and `n2` is a sent response. Both supplied source files
(`raw.jsonl` and `normalized.jsonl`) remain unchanged by the quick start. The
normalized capture retains all 20 observations, including eight received-response
hooks, rather than deduplicating them into the four semantic nodes.

The [example inventory](../examples/README.md) also records historical results
for optional local `all-tests` captures. Those larger artifacts are not tracked
or required by the test suite; their results are not general graph-size
guarantees or evidence of a verified multi-module corpus.

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
