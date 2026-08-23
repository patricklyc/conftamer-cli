# ConfTamer PMGraph tool

Convert ContextTrack JSONL into a per-module message influence graph:

```bash
conftamer contexttrack events.jsonl \
  --module-id example.org/service
```

The default output is `events.jsonl.pmgraph.json`. Use `--output PATH` to choose
another location.

## PMGraph format

```json
{
  "format": "conftamer.pmgraph",
  "version": 1,
  "module_id": "example.org/service",
  "nodes": [
    {
      "id": "n:<hash>",
      "type": "Receive",
      "message": "Request",
      "api_id": "example.org/service",
      "method": "GET",
      "pattern": "/items/{id}"
    }
  ],
  "edges": [
    {"source": "n:<receive>", "target": "n:<send>"}
  ]
}
```

ContextTrack events map to nodes as follows:

| Event | Node |
| --- | --- |
| `Request received` | Receive Request |
| `Request sent` | Send Request |
| `Response received` | Receive Response |
| `Response sent` | Send Response |
| `Request routed` | Route metadata; no node |

The converter preserves ContextTrack's nested `message`, `context`, and
`request_id` structures until node conversion. It groups events by process and
context, pairs responses with requests, and creates an edge from every Receive
to every later Send in the same group.

`module_id` identifies the module whose PMGraph is being generated. An event's
`api_id` instead identifies the organization or API associated with that
communication; one module's PMGraph may therefore contain several API IDs.
Outbound API IDs are preserved from ContextTrack and copied to matched response
nodes.

During node conversion, an empty HTTP URL path is normalized to `/`. Nested
router events are combined into the full pattern seen by the original request,
including routes behind `StripPrefix`-style path rewriting. ContextTrack may
also emit both wire-level and client-level hooks for one received response;
these hooks are collapsed into one response node when their status and request
flow match, including redirects whose hooks report different paths.

## Limitations

- `--module-id` is required because ContextTrack does not export it. Inputs
  should contain events for that module.
- Events without enough endpoint information for a PMGraph label, such as an
  outbound request with no host, are accepted as ContextTrack input but omitted
  with a warning rather than guessed.
- Context edges are heuristic evidence of influence, not proof of causality.
- Malformed or ambiguous events are skipped with warnings on standard error.
- ContextTrack does not produce configuration Parameter nodes or edges.
