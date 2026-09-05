# CType example artifacts

These are real, independent outputs from the gopls CType analysis used as
ConfTamer's executable integration inputs:

| Artifact | Producer role | Vertices | Edges | `List` mappings | Nonidentity aliases |
| --- | --- | ---: | ---: | ---: | ---: |
| `unmarshaler_subgraph.text` | Unmarshaler Subgraph | 57 | 90 | 58 | 1 |
| `accessors.text` | Accessors graph | 582 | 822 | 595 | 13 |

The producer implementation was inspected in read-only checkout
`../run-prmtrk/golang.org-x-tools` at revision
`27eb7264a2b4e89466594ae95821963e1b320907`. See
[`docs/rewrite/input-formats.md`](../../docs/rewrite/input-formats.md) for the
specific serializer sources and field contract.

Each `.text` file is one complete JSON document with `Edges`, `Vertices`, and
`List`; the suffix does not make it line-oriented text. The two files represent
different graph roles and must be loaded or exported independently.

Generated GraphML is visualization output. Write it to a temporary or dedicated
output directory, never back into `examples/`.
