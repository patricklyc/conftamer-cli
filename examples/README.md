# CType example catalog

Files under [`ctype/`](ctype/) are real gopls producer inputs and executable
integration fixtures. They are independent one-document JSON files despite the
`.text` suffix:

- `ctype/unmarshaler_subgraph.text` — Unmarshaler Subgraph, 57 vertices and 90
  edges;
- `ctype/accessors.text` — Accessors graph, 582 vertices and 822 edges; and
- [`ctype/README.md`](ctype/README.md) — producer revision, mapping counts, and
  artifact provenance.

Export each graph in a separate invocation:

```bash
uv run conftamer export \
  examples/ctype/unmarshaler_subgraph.text \
  --output /tmp/unmarshaler.graphml

uv run conftamer export \
  examples/ctype/accessors.text \
  --output /tmp/accessors.graphml
```

The outputs are directed visualization GraphML suitable for tools such as Gephi.
Generated GraphML does not belong under `examples/`; use a temporary or output
directory.
