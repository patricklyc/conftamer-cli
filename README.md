# ConfTamer graph conversion tool

This repository builds directed configuration and message-flow graphs for
ConfTamer. It provides two workflows:

- convert ContextTrack JSONL traces into deterministic PMGraph JSON; and
- convert the original edge-oriented CSV format into GraphML with `igraph`.

The ContextTrack-to-PMGraph workflow is the primary implementation. The CSV
commands are retained for compatibility with the earlier prototype.

## Requirements and setup

The project requires Python 3.13 or newer. From a checkout, install the locked
dependencies with [uv](https://docs.astral.sh/uv/):

```bash
uv sync
uv run conftamer --help
```

The examples below use `uv run conftamer`. If the package is installed into the
active environment, invoke `conftamer` directly instead.

## Convert ContextTrack JSONL to PMGraph

Run:

```bash
uv run conftamer contexttrack events.jsonl \
  --module-id example.org/service
```

The command writes `events.jsonl.pmgraph.json`. Choose another destination with
`--output`:

```bash
uv run conftamer contexttrack events.jsonl \
  --module-id example.org/service \
  --output service.pmgraph.json
```

`--module-id` identifies the module whose execution produced the trace. It is
required because ContextTrack does not include that value in its output.

The input must contain one ContextTrack event object per nonblank line. Bad
lines do not stop the rest of the conversion: they are omitted and reported on
standard error with their original line number.

### Conversion pipeline

The implementation follows this data flow:

```text
ContextTrack JSONL
    -> validate and group events
    -> reconstruct routes and correlate responses
    -> convert events to PMGraph nodes
    -> connect, deduplicate, sort, and serialize the graph
```

1. **Read and validate.** Each nonblank line is validated as one of the five
   supported ContextTrack event kinds. Unknown fields are preserved so newer
   upstream fields do not destroy the nested `message`, `context`, or
   `request_id` structures.
2. **Group.** Valid events are grouped by `(pid, context_id)`. The process ID is
   part of the key because context IDs are not assumed to be globally unique.
3. **Match metadata.** Route events are matched to inbound requests, and
   response events are correlated with the appropriate inbound or outbound
   request.
4. **Convert.** Convertible request events and successfully matched response
   events become PMGraph message nodes. Flattening happens only at this
   boundary; the validated ContextTrack models remain nested.
5. **Connect.** Within each context group, every successfully converted
   `Receive` occurrence influences every later `Send` occurrence.
6. **Normalize output.** Duplicate nodes and edges are removed, then nodes and
   edges are sorted deterministically before JSON serialization.

Events map to PMGraph nodes as follows:

| ContextTrack event | PMGraph node | Label source |
| --- | --- | --- |
| `Request received` | Receive Request | method and matched route pattern, or request path |
| `Request sent` | Send Request | method, host, and path from `request_id` when present, otherwise `message` |
| `Response received` | Receive Response | matched outbound request plus response status |
| `Response sent` | Send Response | matched inbound request plus response status |
| `Request routed` | no node | metadata used to label Receive Request and Send Response nodes |

### Route and response matching

ContextTrack can emit several route records while a request passes through
nested routers. The converter reconstructs the full route pattern, including
prefixes removed by `StripPrefix`-style middleware. It refuses to choose when a
nested route can extend more than one active route chain. If no route can be
matched, the inbound request still uses its concrete request path as a
conservative fallback.

Responses with method and path data are matched to requests by exact method
and path first. When several requests share an endpoint, a unique goroutine
match can disambiguate them. If a received response has no exact endpoint
candidate, matching may fall back to method and goroutine; redirected requests
whose response hook reports a changed path are the motivating case, but the
trace does not identify redirects explicitly.

The Go HTTP instrumentation may report both a wire-level and a client-level
hook for one received response. A later client hook is treated as a duplicate
only when the most recent earlier received-response hook in the same context
was matched and their status and method are compatible. This prevents a
duplicate hook from consuming a newer request. Response hooks without method or
path cannot be matched independently and may be omitted without a warning or
node so that a later hook with usable endpoint data can represent the response.

### Labels and normalization

`module_id` and `api_id` have different meanings:

- `module_id` names the module represented by the entire PMGraph.
- `api_id` identifies the API or organization associated with an individual
  communication event.

A single module graph may therefore contain several API IDs. An outbound
request's `api_id` is preserved and copied to its matched Receive Response
node.

PMGraph requires nonempty HTTP labels. Empty request paths are normalized to
`/`. An outbound request with no host cannot be labeled safely, so it is
omitted with `request endpoint has no host` rather than assigned a guessed
host.

### Warnings and incomplete traces

Warnings have this form:

```text
warning: line 42: missing request match
```

The converter can report:

- malformed or unsupported JSONL events;
- events without a context ID;
- ambiguous nested route chains;
- routes without a matching inbound request;
- missing or ambiguous request/response matches when the response contains
  usable endpoint data;
- endpoints that cannot satisfy the PMGraph schema.

Warnings are sorted by input line. A convertible request event without a
context ID can still contribute a node, but it cannot contribute a
context-derived edge. The command writes the usable portion of the graph while
reporting omitted or unmatched data.

## PMGraph format

PMGraph is schema-validated, immutable Pydantic data serialized as JSON. A
graph has a fixed format marker and version. This abbreviated example is
internally valid; converter-generated IDs replace the descriptive suffixes with
SHA-256 digests:

```json
{
  "format": "conftamer.pmgraph",
  "version": 1,
  "module_id": "example.org/service",
  "nodes": [
    {
      "id": "n:receive-request",
      "type": "Receive",
      "message": "Request",
      "api_id": "example.org/service",
      "method": "GET",
      "pattern": "/items/{id}"
    },
    {
      "id": "n:send-request",
      "type": "Send",
      "message": "Request",
      "api_id": "example.org/inventory",
      "method": "POST",
      "host": "inventory:8080",
      "path": "/reserve"
    }
  ],
  "edges": [
    {
      "source": "n:receive-request",
      "target": "n:send-request"
    }
  ]
}
```

Supported node shapes are:

| Node | Required label fields |
| --- | --- |
| Parameter | `name` |
| Receive Request | `api_id`, `method`, `pattern` |
| Send Request | `api_id`, `method`, `host`, `path` |
| Receive Response | `api_id`, `method`, `host`, `path`, `status` |
| Send Response | `api_id`, `method`, `pattern`, `status` |

`api_id` may be `null`; the other label strings must be nonempty. HTTP methods
are normalized to uppercase, and status codes must be integers from 100 through
999.

Every edge must reference existing nodes. Its source must be a `Receive` or
`Parameter` node, its target must be a `Send` node, and self-edges are rejected.
ContextTrack currently produces message nodes only; it does not produce
Parameter nodes or configuration edges.

The converter generates node IDs from the module ID and the node's semantic
fields using canonical JSON and SHA-256. The graph builder sorts and
deduplicates nodes and edges, so converter output is deterministic for the same
normalized input. The PMGraph validator itself accepts any nonempty, unique
node IDs.

### Programmatic use

The supported ContextTrack entry point is exported from
`conftamer.contexttrack`:

```python
from conftamer.contexttrack import parse_contexttrack

result = parse_contexttrack(
    "events.jsonl",
    module_id="example.org/service",
)

print(result.graph)
for warning in result.warnings:
    print(warning.input_line, warning.message)
```

`result.graph` is a validated `PMGraph`; `result.warnings` is an input-line
ordered tuple of warnings.

## Legacy CSV to GraphML

Generate a full directed GraphML graph from the legacy edge format:

```bash
uv run conftamer graph edges.csv
```

The command prints an `igraph` summary and writes `edges.csv.graphml`.

Generate the subgraph containing the selected vertex and all vertices in its
incoming and outgoing components:

```bash
uv run conftamer subgraph edges.csv 12
```

This command prints the selected vertex IDs and subgraph, then writes the
result to the same `edges.csv.graphml` path.

The CSV parser accepts headerless rows in exactly two forms:

```text
Parameter,<module_id>,<parameter_name>,Send,<module_id>,<api_id>,<request_id>,<response_code>
Receive,<module_id>,<api_id>,<request_pattern>,<response_code>,Send,<module_id>,<api_id>,<request_id>,<response_code>
```

Rows that do not match either structural shape raise
`ValueError("parsing error")`; invalid field values, such as a non-integer
response code, surface Pydantic validation errors. This legacy graph model and
its GraphML output are separate from the PMGraph schema; new input formats
should target PMGraph rather than extend the CSV representation.

## Limitations

- A ContextTrack input should contain events for the module supplied through
  `--module-id`; the converter cannot verify module ownership from the trace.
- Context-derived edges are evidence of possible influence, not proof of
  causality.
- Response correlation is conservative because current traces do not contain a
  stable request/response correlation ID.
- Ambiguous routes and responses are reported rather than guessed.
- ContextTrack does not currently describe configuration Parameter nodes.

## Development

The implementation is organized by conversion stage:

```text
src/conftamer/
├── main.py                    # CLI orchestration
├── pmgraph.py                 # PMGraph schema, validation, IDs, serialization
├── csv_graph.py               # complete legacy CSV/igraph workflow
└── contexttrack/
    ├── events.py              # input models, JSONL reading, grouping
    ├── routes.py              # route matching and reconstruction
    ├── responses.py           # response correlation
    └── conversion.py          # event-to-PMGraph conversion and graph assembly
```

ContextTrack tests are split by the same behaviors in
`tests/test_contexttrack_*.py`.

Run formatting, type diagnostics, and tests with:

```bash
uvx ruff format --check src tests
uvx ty check
uv run pytest -q
```

For CLI changes, also run:

```bash
uv run conftamer --help
uv run conftamer contexttrack --help
uv run conftamer graph --help
uv run conftamer subgraph --help
```

## License

ConfTamer is licensed under the GNU General Public License, version 2 only.
See [LICENSE](LICENSE) for the complete terms.
