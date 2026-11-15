# ConfTamer reference

See the [README](../README.md) for setup and runnable build/stitch/query/export
commands. This reference describes the current message-only ContextTrack
consumer, not the broader system proposed in the paper.

## Graph semantics and limits

- **Nodes represent messages, not individual events.** The importer distinguishes
  sent/received requests and responses, correlates routing and response metadata,
  and deduplicates identical message labels.
- **Edges represent possible influence.** A received message can influence a later
  sent message within the same capture and `(pid, context_id)`. The result is not
  an execution replay or a complete call graph.
- **Queries return a subgraph.** It holds the selected node, every node that can
  reach it, every node it can reach (indirect connections included), and every
  edge among those nodes, including edges that bypass the selected node. Nodes
  keep the input's order. An isolated node returns itself alone. See
  [Query](#query).
- **Incomplete or ambiguous evidence emits warnings.** It does not become an
  invented association; unusable events or associations are omitted.
- **Stitching joins modules through matching messages.** `stitch` merges a
  message one module sent with the matching message another received into one
  `linked_message` node and moves each module's edges onto those nodes. It adds
  no influence that a PMGraph did not record. See [Stitch](#stitch) for the
  rules and their limits.
- Parameter ingestion and GraphML importing or querying are not implemented.
  `build` produces message nodes only; parameters appear only in graphs from
  other sources, such as `examples/pmgraphs/`.

The module identity is supplied by you through `--module-id`, not inferred from
API IDs. Node IDs are keys in the PMGraph JSON file's top-level `nodes` object,
not API IDs or URLs. Inspect the file to choose an exact ID; after the README's
quick start, use:

```bash
uv run python -m json.tool "$RUN/module.pmgraph.json"
```

## Files and errors

- **Inputs:** `build` reads normalized ContextTrack v1 UTF-8 JSONL; `stitch`
  reads PMGraph JSON only; `query` and `export` read PMGraph or AppGraph JSON. A
  file with a top-level `module_id` is read as a PMGraph, any other as an
  AppGraph. Loading either graph type rejects type coercion and unknown fields,
  and validates message field combinations, nonempty module/node IDs, and
  existing edge endpoints. Graph JSON output preserves node order and explicit
  nulls and sorts edge pairs.
- **Outputs:** `build`, `stitch`, and `export` require `--output`. The parent
  directory must exist and the file must be new; existing files are never
  overwritten. Writes are not atomic, so a filesystem failure can leave a
  partial new file. `stitch` writes a second file, the dropped-message report;
  see [Stitch](#stitch).
- **Diagnostics:** Build, stitch, and export leave stdout empty on success;
  query prints indented graph JSON. Warnings go to stderr. Expected input or
  filesystem errors, including unknown node IDs, produce stderr diagnostics and
  exit code 2 without a traceback. Capture record diagnostics include the input
  path and physical line number; graph-file diagnostics include the file's path.

## Stitch

`stitch A.json B.json ... --output OUT` reads one PMGraph JSON file per module
and writes an AppGraph. One input is allowed; it yields no links. Module IDs
must be unique, module and node IDs must not contain `::`, and a module ID must
not end with `:`; otherwise the command fails.

### Matching

A message is linked to a message in a **different** module when all of these
hold. Requests pair a `send_request` with a `receive_request`; responses pair a
`send_response` with a `receive_response`.

- Both carry the same nonempty `api_id`. A message without one never links.
- The methods are equal and the status codes are equal.
- The client's concrete `path` satisfies the server's route `pattern`:
  - net/http syntax: `{name}` matches one nonempty segment, a trailing
    `{name...}` matches the rest of the path (which may be empty), a trailing
    `{$}` matches only the path ending there, and a trailing `/` matches the
    whole subtree.
  - httprouter syntax: `:name` matches one nonempty segment, a trailing `*name`
    matches the rest of the path (which may be empty), and a trailing `/` is
    literal.
  - A pattern may start with a method and a host as Go writes them
    (`GET /items/{id}`, `example.com/items/{id}`). The method must admit the
    message's method (`GET` also admits `HEAD`). The host must equal the
    client's destination host without its port, compared exactly.
- A server message that has a `path` instead of a `pattern` links only to an
  equal, nonempty client path. Wildcard syntax in a `path` is read literally.

A pattern the matcher cannot read (for example one mixing the two syntaxes) does
not stop the stitch. That message never links and is reported with the reason
`unsupported_pattern`.

### The AppGraph

- Parameters keep their node and are renamed `module::node`.
- Each matched pair becomes one `linked_message` node named `link0`, `link1`,
  and so on. It records the route (`api_id`, `method`, `pattern`,
  `status_code`) and both original nodes (`sender_module`, `sender_node`,
  `receiver_module`, `receiver_node`). The pattern is the server's label,
  unchanged.
- Each PMGraph edge is kept with its endpoints replaced by the links those
  messages joined. A message in several links has its edges repeated for each.
  An edge that touches a message with no link is not in the AppGraph.
- Link numbers follow a fixed order (requests before responses, each in sorted
  ID order), so the same inputs give the same file. Adding or renaming a module
  renumbers them. Find a particular call by its sender and receiver fields, not
  by its number.

### The dropped-message report

`stitch` always writes a second file listing every input message that is not in
the AppGraph, sorted by module ID and node ID. It is `[]` when nothing was left
out.

- **Path:** by default the output's name with one trailing `.json` removed and
  `.dropped.json` appended, in the same directory: `app.json` gives
  `app.dropped.json`, and `app` gives `app.dropped.json` too. `--dropped PATH`
  writes the report there instead.
- **Entries:** `module_id`, `node_id`, `reason`, and `message` (the original
  node). The reasons are `unmatched` (no message in another module matched it,
  for example a call to a service that was not stitched in),
  `unsupported_pattern` (see above), and `unreachable` (only with
  `--prune-unconfigured`).
- **It is not a graph file.** `query`, `export`, and `stitch` reject it. Keep the
  original PMGraphs: the report lists messages, not the edges that touched them.

Both output paths are checked before anything is written: they must differ, and
neither may exist, a dangling symlink included. If the report then cannot be
written, the AppGraph this call created is removed, and so is a partly written
report. The two writes are separate and not atomic; do not treat the pair as a
transaction.

### `--prune-unconfigured`

By default every matched link is kept. With `--prune-unconfigured`, links that
no parameter can influence are left out and reported as `unreachable`, as the
paper's CompTool does (§6.3). This only makes sense for inputs that carry
parameters. `build` output carries none, so pruning it leaves an empty AppGraph.

### Limits

- The tracked Prometheus capture is a single module, and messages in the same
  module are never linked. Stitching is therefore tested on synthetic graphs
  only; there is no verified multi-module corpus.
- Matching uses API ID, method, status, and path. The client's destination host
  is used only when a pattern names a host. An API ID identifies a package
  organisation, not a service, so unrelated services can share one.
- There is one link per pair of send node and receive node. One message can join
  several links, and edges are multiplied across them: a server's
  receive-to-respond edge with two clients becomes four edges, including one
  client's request to the response sent to the other. The paper (§6.3, Figure 2)
  instead describes one node per route and calling module, and an AppGraph no
  larger than its PMGraphs combined; an AppGraph written here can exceed that
  bound.
- A request links to every pattern it satisfies, not only the one a router would
  pick. A pattern ending in `/` is read as a Go subtree; httprouter treats it as
  literal, and the label cannot tell the two apart. The pattern `/` therefore
  matches every path, and it is the most common pattern in the local
  `all-tests` capture.
- Go labels a redirected request with a pattern its path does not satisfy, and
  logs decoded paths. Such requests stay unmatched.
- A self-loop on a message that joins two or more links becomes edges between
  those links; on a message in one link it disappears.

## Query

`query GRAPH` reads a PMGraph or AppGraph JSON file and takes exactly one
selector:

- `--node ID` selects a node by its exact ID.
- `--key KEY` selects the parameter whose configuration key is `KEY`. If several
  parameters share the key, the error lists their node IDs; narrow the choice
  with `--module MODULE` or use `--node`. `--module` matches a PMGraph's
  `module_id`, or in an AppGraph the `module::` prefix of a parameter's node ID.
  Graphs written by `build` hold no parameters, so `--key` applies to graphs
  from other sources, such as `examples/pmgraphs/`.

By default the command prints the subgraph as graph JSON of the same type as
its input. The output is formatted like `build` output, except that non-ASCII
characters are written as `\u` escapes so the result does not depend on the
terminal's encoding. It can be saved and passed to `export` or `query`.

`--paths` prints `{"subgraph": ..., "paths": [...]}` instead. `paths` lists
every root-to-leaf path through the selected node, in a fixed order. Each path
is a list of steps and each step is a list of node IDs. A step is one strongly
connected component, so a cycle is a single step and an acyclic graph has one
node per step. The number of paths grows exponentially on branching graphs, so
`--paths` can run very long or exhaust memory; the default output never
enumerates paths. The `--paths` object is not a graph file: `export` and
`query` reject it.

Every node in a cycle influences every other node in it, so a cycle is one step
holding its sorted node IDs, not one path per route around it:

```text
r -> a -> b -> a, b -> l     paths: [[["r"], ["a", "b"], ["l"]]]
r -> a -> b -> a             paths: [[["r"], ["a", "b"]]]      (the cycle ends the path)
```

Overlapping cycles merge into one step, and a node whose only cycle is an edge
to itself is a one-node step. The edges inside a cycle are still in `subgraph`.
For a graph without cycles, `[[node for (node,) in path] for path in paths]`
gives plain ID lists.

Compatibility: `query` used to print `{"ancestors": [...], "descendants": [...]}`
ID lists and now prints the subgraph. `conftamer.pmgraph.igraph_ops.query_node`
was removed; use `conftamer.query.query_subgraph`. `conftamer.query.to_igraph`
and `conftamer.io.write_graphml`, which came from the merged AppGraph branch,
are now the converter and writer described under GraphML export: vertices in
original node order, one attribute per node field, and no `node_json`
attribute.

The merged branch's `stitch` wrote the dropped-message report only with
`--dropped` and always pruned links no parameter reaches. The report is now
always written, and pruning is opt-in (`--prune-unconfigured`).

## GraphML export

The input may be a PMGraph or an AppGraph. Export preserves directed named
topology, isolates, and original node order, and writes each node field as a
named vertex attribute, not an embedded JSON document. Use `name` for original
node IDs; readers may also expose writer-generated XML IDs.

- **PMGraph:** the graph attribute `module_id`, and the vertex attributes
  `name`, `kind`, `key`, `api_id`, `method`, `host`, `path`, `pattern`, and
  `status_code`.
- **AppGraph:** no `module_id` graph attribute, and the vertex attributes
  `name`, `kind`, `key`, `api_id`, `method`, `pattern`, `status_code`,
  `sender_module`, `sender_node`, `receiver_module`, and `receiver_node`.

Native conversions can turn nulls into `"None"`, numeric `NaN`, or `False` for
all-null attributes; large integers may lose precision. GraphML is not lossless
graph persistence; use the JSON file for that. Export rejects XML-invalid
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

`examples/pmgraphs/` holds three synthetic, hand-written PMGraphs with
parameters, used to show and test stitching. They are not captured data. The
[example inventory](../examples/README.md) walks through them.

The [example inventory](../examples/README.md) also records historical results
for optional local `all-tests` captures. Those larger artifacts are not tracked
or required by the test suite; their results are not general graph-size
guarantees or evidence of a verified multi-module corpus.

## Python API

The same operations are callable without the CLI:

```python
from conftamer.contexttrack import load_contexttrack
from conftamer.query import query_subgraph

graph = load_contexttrack(
    "examples/contexttrack/prometheus/TestTargetScraperScrapeOK/normalized.jsonl",
    module_id="example-module",
)
print(query_subgraph(graph, "n1"))
```

`conftamer.query` also provides `query_paths(graph, node_id)` and
`find_parameters(graph, key, module=None)`. `conftamer.appgraph.stitch` provides
`stitch(graphs, prune_unconfigured=False)`, which returns the AppGraph, and
`stitch_with_dropped(...)`, which also returns the dropped messages; neither
touches the filesystem. For persistence, `conftamer.io`
provides `load_graph_json(path)` and `write_graph_json(graph, path)` for either
graph type, and `write_dropped_json(dropped, path)` for the report;
`conftamer.pmgraph.io` keeps `load_pmgraph_json(path)` and
`write_pmgraph_json(graph, path)`. For conversion and export,
`conftamer.igraph_ops` provides `to_igraph(graph)` and
`write_graphml(graph, path)`; `conftamer.pmgraph.igraph_ops` re-exports both.

The ContextTrack reader raises `contexttrack.EventFileError` (a `ValueError`)
for invalid input, retaining `.path`, physical `.line`, `.reason`, and the original
exception as `__cause__`. Clients catching the old raw parser's `TypeError` must
catch `EventFileError`/`ValueError` instead. Caller validation is unchanged:
nonstring `module_id` raises `TypeError`, and an empty string raises `ValueError`,
before input is opened. PMGraph JSON loading raises `ValueError` for invalid
data; filesystem failures remain `OSError`.
