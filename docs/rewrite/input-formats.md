# CType input format and provenance

This document records the gopls CType transport observed in checked-in artifacts
and the inspected producer implementation. It separates producer evidence from
ConfTamer normalization policy. Owned models and projection behavior live in
[Architecture](architecture.md).

## Evidence policy

The two files under [`examples/ctype/`](../../examples/ctype/) are executable
source-of-truth inputs. Prose summarizes those files; it does not replace them.
If an artifact conflicts with this document, inspect the producer and update the
contract deliberately before changing the parser.

Unknown producer fields are accepted at the raw boundary for forward
compatibility but do not implicitly become normalized semantics or GraphML
attributes. Sibling repositories and the paper are read-only references.

### Inspected producer revision

The gopls contracts were inspected in read-only checkout
`../run-prmtrk/golang.org-x-tools` at revision
`27eb7264a2b4e89466594ae95821963e1b320907`:

- `gopls/internal/cmd/conftamer/output.go:Marshal` writes the JSON graph;
- `gopls/internal/cmd/conftamer/output.go:Serialize` writes JSON plus optional
  DOT; and
- the graph serializer defines nullable edge `Data` path collections.

The checked-in files remain executable parser evidence. Reinspect and record a
new revision before assigning meaning to future serializer changes.

## Authoritative artifacts

| Artifact | Producer role | Counts |
| --- | --- | --- |
| `examples/ctype/unmarshaler_subgraph.text` | gopls Unmarshaler Subgraph | 57 vertices, 90 edges, 58 `List` entries, 1 nonidentity alias |
| `examples/ctype/accessors.text` | gopls Accessors graph | 582 vertices, 822 edges, 595 `List` entries, 13 nonidentity aliases |

The files are independent, complete JSON documents despite the `.text` suffix.
They are exported separately and never merged. Generated GraphML does not belong
under `examples/`.

The previous `.gv` files and producer logs are not retained as MVP examples and
are not machine inputs.

## Top-level JSON document

The current producer machine format is one JSON object, commonly on one physical
line:

```json
{
  "Edges": [],
  "Vertices": [],
  "List": {}
}
```

Parse the complete byte stream as one RFC 8259 JSON document; newline count has
no meaning. Reject non-standard `NaN`, `Infinity`, and `-Infinity` constants even
inside unknown fields. The root must be an object containing array `Edges`,
array `Vertices`, and object `List`. A missing field or wrong container type is
a file-level contract error. Unknown top-level fields are accepted and excluded
from normalized semantics.

## Vertices

A representative vertex is:

```json
{
  "Names": ["/config.RemoteWriteConfig"],
  "Methods": [
    "(*github.com/prometheus/prometheus/config.RemoteWriteConfig).Validate"
  ],
  "Tags": {
    "Name": "yaml:\"name,omitempty\""
  }
}
```

Observed meanings:

- `Names` is nonempty and its first value is the upstream node ID;
- additional names are aliases represented by the same node;
- `Methods` is a list and may be empty;
- `Tags` is an object or `null`; and
- methods may be fully qualified while names are module-shortened.

Every vertex must be an object with a nonempty `Names` array of nonempty
strings, a `Methods` array of nonempty strings, and `Tags` either `null` or an
object with string keys and values. Unknown vertex fields are accepted but do
not enter normalized identity.

ConfTamer preserves upstream strings exactly. It does not expand shortened names
or infer source types.

## Edges

A representative edge is:

```json
{
  "Source": "/model/relabel.Config",
  "Target": "/model/relabel.Action",
  "Properties": {
    "Attributes": {},
    "Weight": 0,
    "Data": [
      ["StructType.Fields", "Field:Action", "FieldList.List", "Field.Type"]
    ]
  }
}
```

Observed producer behavior:

- `Source` and `Target` identify represented vertex IDs;
- current files include `Attributes`, `Weight`, and `Data`;
- empty attributes and zero weight are generic graph-library defaults without
  observed CType meaning;
- `Data` may be `null` or a list of ordered AST paths;
- each path may be a string list, an empty list, or `null`; and
- multiple paths remain grouped on one edge rather than becoming parallel
  edges.

The checked-in files contain list-valued `Data`; nullable behavior is grounded
in the inspected serializer.

Every edge must be an object with nonempty string `Source` and `Target` and an
object `Properties`. `Properties.Data` is required and must be `null` or an
array whose items are `null` or arrays of strings. Unknown edge/property fields
are accepted. `Data: null` normalizes to no paths; a null path item normalizes
to an empty path. Segment order and path grouping are preserved. Duplicate
`(Source, Target)` records and missing represented endpoints are rejected.

## Name mapping (`List`)

`List` maps represented names and aliases to a vertex's first name:

```json
{
  "/alias.Name": "/canonical.Name"
}
```

Every key and value must be a nonempty string. Every represented vertex name
must occur and map to that vertex's first name. A represented alias may resolve
to only one vertex. Additional mappings retained by an upstream queried
subgraph are accepted only when their target resolves to a represented vertex;
unresolved extras are omitted from the normalized mapping. Missing or
conflicting represented mappings are errors, and mappings are never synthesized.

## Normalization summary

ConfTamer preserves the first name as stable ID, exact names, methods, tags,
ordered AST path segments, grouped paths, edge direction, producer edge
cardinality, and isolated vertices. It sorts and deduplicates aliases, methods,
and equal paths according to the architecture, and sorts normalized nodes,
edges, tag keys, and mapping keys. Unknown fields, graph-library attributes,
and weights are discarded from normalized semantics.

Real regression facts:

| Graph | Vertices | Edges | `List` entries | Nonidentity aliases | Maximum grouped paths |
| --- | ---: | ---: | ---: | ---: | ---: |
| Unmarshaler Subgraph | 57 | 90 | 58 | 1 | 4 |
| Accessors | 582 | 822 | 595 | 13 | 1 |

These counts validate the checked-in files; they are not schema limits.

## Transport dispatch and blocked formats

CType dispatch is content-aware within this narrow policy:

- `.text` or JSON-leading content: parse the verified JSON envelope;
- `.gv` or DOT-leading content: reject as unsupported;
- `.graphml` or XML-leading content: reject as unsupported and blocked; and
- malformed or unrelated JSON: reject as invalid CType input.

No real producer GraphML is checked in, and the inspected serializer emits JSON
plus optional DOT. Do not infer GraphML namespaces, keys, structural IDs,
defaults, direction, or collection encoding.

Before producer GraphML could be accepted, both real Unmarshaler and Accessors
files would need to be added, their transport documented, and equivalence tests
would need to prove identical normalized nodes, edges, grouped AST paths,
isolates, aliases, tags, methods, and mappings. Visualization GraphML written by
ConfTamer is never producer input.

The `.gv` transport and producer logs are not retained by this MVP. Their
presence, extension, or leading syntax must not trigger fallback parsing.
