# ConfTamer CType GraphML exporter

ConfTamer validates one gopls Unmarshaler Subgraph or Accessors `.text` CType
artifact and exports a directed, readable GraphML visualization. Each invocation
handles one artifact; the two graph roles are never merged.

## Install and run

ConfTamer requires Python 3.13 or newer. From a checkout with
[uv](https://docs.astral.sh/uv/) installed:

```bash
uv sync
uv run conftamer --help
```

Installed environments and standalone release binaries can invoke `conftamer`
directly.

## Export the real examples

```bash
uv run conftamer export \
  examples/ctype/unmarshaler_subgraph.text \
  --output /tmp/unmarshaler.graphml

uv run conftamer export \
  examples/ctype/accessors.text \
  --output /tmp/accessors.graphml
```

The first output has 57 vertices and 90 edges; the second has 582 vertices and
822 edges. Both preserve edge direction and isolated vertices.

Vertex `name` and `label` contain the stable upstream CType ID. The `aliases`,
`methods`, `tags`, and edge `ast_paths` attributes are formatted for people in
Gephi-like tools. Their `names_json`, `methods_json`, `tags_json`, and
`ast_paths_json` companions preserve nested values without delimiter ambiguity.
All GraphML attributes are strings.

## Input boundary

ConfTamer accepts the verified producer JSON envelope containing `Edges`,
`Vertices`, and `List`, normally with a `.text` suffix. JSON-leading files with
other suffixes are also accepted. Unknown producer fields are ignored after raw
validation.

Malformed or unrelated JSON, `.gv`/DOT, and `.graphml`/XML input are rejected.
Producer GraphML is not supported because no real producer artifacts establish
its transport contract. GraphML written by ConfTamer is visualization output,
not canonical persistence or input.

See the [technical reference](docs/technical-reference.md) for CLI and Python
APIs, the [architecture](docs/rewrite/architecture.md) for normalized semantics
and GraphML attributes, [input formats](docs/rewrite/input-formats.md) for
producer evidence, and the [example catalog](examples/README.md) for artifact
provenance.

## License

ConfTamer is licensed under the GNU General Public License, version 2 only. See
[LICENSE](LICENSE).
