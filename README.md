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

The parser preserves ContextTrack's nested `message`, `context`, and
`request_id` structures until node conversion. It groups events by process and
context, pairs responses with requests, and creates an edge from every Receive
to every later Send in the same group.

## Limitations

- `--module-id` is required because ContextTrack does not export it.
- Outbound API IDs remain unresolved (`null`); ContextTrack identifies the local
  caller, not the destination API owner.
- Context edges are heuristic evidence of influence, not proof of causality.
- Malformed or ambiguous events are skipped with warnings on standard error.
- ContextTrack does not produce configuration Parameter nodes or edges.
