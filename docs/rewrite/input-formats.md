# Input formats and provenance

This document records upstream formats observed in checked-in artifacts and
current producer implementations. It separates producer facts from ConfTamer
normalization policy. Stable target models and matching decisions live in
[Architecture](architecture.md).

## Evidence policy

The files under [`examples/`](../examples/) are the executable source of truth
for currently accepted producer behavior. Prose summarizes those files; it
does not replace them. When prose and an example disagree, inspect the producer
and update both the example and this document before changing a parser.

Labels used below:

- **Observed input:** verified in a checked-in artifact or current upstream
  serializer.
- **Current policy:** downstream behavior already implemented by tool34 and
  retained by the rewrite; it is not guaranteed by the producer.
- **Target design:** a contract the rewrite will own.
- **Paper-derived:** a concept from the paper without a current producer.
- **Blocked:** not implementation-ready until a real artifact defines it.

Unknown producer fields are accepted at input boundaries but do not
implicitly become canonical semantics. Sibling repositories and the paper are
references only.

### Inspected producer sources

Producer-only meanings below were checked against these read-only revisions:

| Checkout and revision | Relevant source contracts |
| --- | --- |
| `../conftamer` at `010683952e74dd0103c8b97b333d860ba9519d52` | `pkg/apimessages/http/http.go:GetMessageInfo` captures method, path, and User-Agent with `MaxStringLen: 10`; `parsetests/parse.go:(*AllTaint).Dump` writes the variable-width CSV |
| `../run-prmtrk/golang.org-x-tools` at `27eb7264a2b4e89466594ae95821963e1b320907` | `gopls/internal/cmd/conftamer/dlv/main.go:HandleMessageSend` associates recognized CType stack frames with sends; `dlv/params.go:ParamKeys` derives keys; `conftamer/output.go:Marshal` and `Serialize` write JSON plus optional DOT |

These revisions identify the implementations inspected for this rewrite; the
checked-in artifacts remain the parser's executable examples. If upstream is
updated, re-check the named functions and record the new revision before
changing field meanings.

## Authoritative artifact catalog

| Artifact | Producer role | ConfTamer role |
| --- | --- | --- |
| `examples/contexttrack/prometheus/*.jsonl` | ContextTrack event traces | Message input |
| `examples/paramtrack/runs/target-scraper-all/parameters.csv` | ParamTrack observations for one target-scraper run | Parameter input |
| `examples/paramtrack/runs/manager-st-zero/parameters.csv` | ParamTrack observations for one manager run | Parameter input |
| `examples/paramtrack/static/unmarshaler_subgraph.text` | gopls Unmarshaler Subgraph | CType graph input |
| `examples/paramtrack/static/accessors.text` | gopls Accessors graph | CType graph input |
| `examples/paramtrack/static/*.gv` | Graphviz visualization | Reference only; not parsed |
| `examples/paramtrack/runs/*/parameters_hierarchy.txt` | Human-readable ParamTrack derivative | Reference only; not parsed |
| `examples/paramtrack/static/*.log` | gopls log | Reference only; not parsed |
| `examples/paramtrack/runs/*/*.log` | ParamTrack/Delve log | Reference only; not parsed |

See [`examples/README.md`](../examples/README.md) and the
[ParamTrack artifact catalog](../examples/paramtrack/README.md) for capture
provenance and usage. Generated PMGraph, AppGraph, and GraphML output does not
belong in the example input directories.

## ContextTrack JSONL

### Observed event envelope

Each nonblank line is one JSON object. A representative observed event is:

```json
{
  "kind": "Request sent",
  "pid": 63118,
  "goroutine_id": 21,
  "thread_id": 0,
  "file": "/go-conftamer/src/net/http/transport.go",
  "line": 599,
  "message": {
    "req.Method": "GET",
    "req.URL.Host": "127.0.0.1:38151",
    "req.URL.Path": "",
    "req.URL.RawQuery": ""
  },
  "context": {
    "source": "req.Context()",
    "type": "context.Context",
    "context_id": "id:1"
  },
  "request_id": {
    "method": "GET",
    "host": "127.0.0.1:38151",
    "path": ""
  },
  "api_id": "github.com/prometheus"
}
```

**Observed input:** the five consumed kinds are:

- `Request sent`
- `Request received`
- `Request routed`
- `Response sent`
- `Response received`

The envelope may also carry unknown fields. Message keys vary by hook. The
adapter must preserve nested `message`, `context`, and `request_id` structures
until semantic projection.

`request_id` is an endpoint label `(method, host, path)`, not a unique request
correlation ID. ContextTrack does not currently emit a stable correlation ID or
producer sequence. `api_id` identifies an API/package association for an event;
it is not the module ID of the complete graph.

### Reader contract

**Current policy:**

- skip blank lines;
- validate each line independently with permissive Pydantic models;
- preserve original input line numbers;
- retain unknown fields for evidence and forward compatibility;
- assign an internal sequence from valid input order;
- continue after malformed or unsupported lines with diagnostics; and
- group context inference by `(pid, context_id)`, never context ID alone.

A convertible event without `context_id` may produce a semantic node, but it
cannot produce a context-derived edge.

### Fields used by semantic projection

| Raw field | Use |
| --- | --- |
| `kind` | Select request, response, or route handling |
| `pid`, `context.context_id` | Context grouping |
| `goroutine_id` | Conservative response disambiguation/fallback only |
| `message` method, host, path, status fields | Hook labels and matching evidence |
| `request_id.method`, `.host`, `.path` | Preferred outbound request labels when present |
| `api_id` | Message metadata and outbound response carry-through |
| route path/handler fields | Route reconstruction evidence |
| `message["req.URL.RawQuery"]` | Accepted evidence; excluded from node identity |
| `handler` | Accepted evidence; excluded from node identity |
| source `file` and `line` | Diagnostics/evidence, not semantic identity |

**Current policy:** normalize method case and empty paths only when constructing
semantic labels. A Send Request without a host cannot satisfy PMGraph labels
and is omitted with `contexttrack.request_without_host`. In the checked-in
`all-tests.jsonl`, 5,820 of 7,159 Request-sent hooks have no host; this is a
fixture observation and deliberate PMGraph omission policy, not an upstream
schema error.

Route reconstruction, response matching, duplicate-hook suppression, and
context-order edges are downstream heuristics described in
[Architecture](architecture.md#contexttrack-semantic-projection). They are not
producer guarantees.

### Checked-in traces

| Trace | Valid event lines | Intended use |
| --- | ---: | --- |
| `prometheus/scrape-ok.jsonl` | 20 | Quick message-conversion smoke test |
| `prometheus/package-tests.jsonl` | 5,530 | Package-level integration input |
| `prometheus/all-tests.jsonl` | 13,954 | Broad, noisy matching and omission input |

Counts describe the checked-in captures, not general schema limits or stable
PMGraph output contracts.

## ParamTrack CSV

### Distinction from removed legacy CSV

**Observed input:** ParamTrack emits a headered, variable-width parameter CSV.
It is unrelated to tool34's old headerless edge CSV. The rewrite removes the
legacy parser and adds a dedicated ParamTrack adapter; the formats must not
share models or row interpretation.

### Header and rows

The exact observed header is:

```csv
API,Verb,Resource,CType,Param key
```

A data row has four identity columns and zero or more parameter-key columns:

```text
API, Verb, Resource, CType, parameter_key_1, parameter_key_2, ...
```

The header labels only the first column of the repeated tail. The upstream
writer may emit only the four identity columns when no parameter keys are
found. Parsing must use Python's `csv` module so quoted values retain normal CSV
semantics.

Observed row prefixes include:

```csv
Prometheus,GET,,/scrape.targetScraper,...
Prometheus,GET,/metrics,/scrape.scrapeLoop,...
Prometheus,GET,/metrics,/discovery.Manager,...
Prometheus,GET,/metrics,/scrape.Manager,...
Prometheus,GET,/metrics,/scrape.targetScraper,...
```

### Field meanings and omissions

| Field | Observed meaning |
| --- | --- |
| `API` | Debugger-captured HTTP `User-Agent`; evidence, not a stable API identity |
| `Verb` | Debugger-captured HTTP request method |
| `Resource` | Debugger-captured HTTP request path |
| `CType` | Coarse CType association found while scanning recognized CType methods on user-goroutine stacks |
| repeated tail | Parameter keys associated conservatively with that message/CType row |

CType values may be module-prefix-shortened and begin with `/`. Preserve them
exactly. Parameter keys are producer results; ConfTamer does not recompute
them and does not interpret them as proof of per-send causality.

The current debugger uses `MaxStringLen: 10` for `API`, `Verb`, and `Resource`.
The CSV carries no flag saying whether a value at the limit is complete or
truncated.

The CSV does not contain:

- host or authority;
- response status or message direction/type;
- ContextTrack `api_id`;
- run, process, test, or Send occurrence identity;
- graph digests or source identity;
- inference kind; or
- completeness metadata.

ConfTamer must not invent these fields. In particular, ParamTrack `API`
(`Prometheus` in the examples) and ContextTrack `api_id`
(`github.com/prometheus`) have different producer meanings and are never
compared.

### Adapter validation

**Target design grounded in observed rows:**

- require the exact five-field header;
- treat a wrong header or unreadable CSV as a file-level error;
- preserve source line numbers;
- diagnose malformed rows locally and continue with independent rows;
- diagnose an empty `Verb` or `CType` as unusable;
- retain an empty `API` as evidence;
- permit empty `Resource` and normalize it to `/` only for joining;
- mark `Verb` or `Resource` values at least 10 characters long, or containing a
  debugger truncation marker, as `paramtrack.possibly_truncated_message` and do
  not use them for a Send join;
- permit no-key rows but create no Parameter nodes or edges from them;
- diagnose and omit empty key cells;
- deduplicate keys within a row and sort canonical output; and
- do not rely on upstream data-row order, filenames, or run-directory names for
  identity.

Several rows may describe one method/path through different CTypes. Their keys
are unioned only after CType validation and a unique semantic Send match, as
defined in [ParamTrack enrichment](architecture.md#paramtrack-enrichment).

### Real fixture facts

`runs/target-scraper-all/parameters.csv` contains one row:

```text
API=Prometheus, Verb=GET, Resource=<empty>, CType=/scrape.targetScraper
```

It has 108 sorted, unique parameter keys. The CType is represented in Accessors.
Its empty Resource and the matching quickstart ContextTrack path both normalize
to `/` at the semantic join boundary.

`runs/manager-st-zero/parameters.csv` contains four rows with
`API=Prometheus`, `Verb=GET`, and `Resource=/metrics`:

| CType | Keys |
| --- | ---: |
| `/scrape.scrapeLoop` | 133 |
| `/discovery.Manager` | 120 |
| `/scrape.Manager` | 201 |
| `/scrape.targetScraper` | 108 |

Each row's keys are sorted and unique. Their union has 226 keys. All four CTypes
are represented in Accessors and not in the Unmarshaler Subgraph. These are
fixture assertions, not CSV schema limits.

## CType graph `.text` JSON

### Top-level document

**Observed input:** the current machine format is one JSON object, often on one
physical line:

```json
{
  "Edges": [],
  "Vertices": [],
  "List": {}
}
```

Parse the complete byte stream as one JSON document; newline count has no
meaning. Unknown top-level fields are accepted for forward compatibility and
excluded from normalized semantics.

### Vertices

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

Observed properties:

- `Names` is nonempty; the first name is the current node hash/ID;
- additional names are aliases combined into the same node;
- `Methods` is a list and may be empty;
- `Tags` is an object or `null`;
- methods may remain fully qualified while node names are module-shortened; and
- unknown vertex fields do not participate in normalized CType identity.

### Edges

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

Observed properties:

- source and target are represented vertex IDs;
- current edges include `Attributes`, `Weight`, and `Data`;
- `Attributes: {}` and `Weight: 0` are generic graph-library defaults without
  observed CType domain meaning;
- `Data` is `null` or a list of ordered AST paths;
- each path is a string list, an empty list, or `null`; and
- several paths stay grouped on one edge rather than becoming invented
  parallel edges.

**Target normalization:** top-level `Data: null` means no paths and a null path
element means an empty path. Unknown edge/property fields and generic defaults
are excluded from semantic identity.

### Name mapping (`List`)

`List` maps known names and aliases to a node's first name:

```json
{
  "/alias.Name": "/canonical.Name"
}
```

For a full US or Accessors output, entries describe represented vertices. An
upstream queried subgraph may retain extra mappings from the source graph.
Validation therefore requires:

- every represented vertex name maps to that vertex's first name;
- every edge endpoint is the first name of an existing vertex;
- a represented alias resolves to only one vertex;
- extra unresolved `List` entries are allowed;
- ParamTrack CTypes are valid only when their target vertex is represented;
- duplicate `(Source, Target)` records are rejected; and
- US and Accessors are allowed to have different node sets.

The adapter preserves serialized strings exactly and does not claim that a
shortened or external-looking name is the original source name.

### Real graph facts

| Graph | Vertices | Edges | `List` entries | Nonidentity aliases |
| --- | ---: | ---: | ---: | ---: |
| Unmarshaler Subgraph | 57 | 90 | 58 | 1 |
| Accessors | 582 | 822 | 595 | 13 |

Every real edge contains `Properties.Attributes`, `Properties.Weight`, and
`Properties.Data`. US has up to four ordered AST paths grouped on one edge.
These counts are regression checks for the checked-in files, not format limits.

## CType GraphML

**Blocked:** no real producer GraphML is checked in, and the inspected upstream
serializer writes `.text` JSON plus DOT. Do not implement a parser from guesses
about namespaces, key names, structural IDs, defaults, or collection encoding.

GraphML is transport, not a new semantic graph. Before accepting it:

1. add real producer US and Accessors `.graphml` files beside the `.text`
   examples;
2. inspect namespaces, `<key>` declarations, direction, structural IDs,
   defaults, and value types;
3. document the exact field mapping here;
4. decide unknown-attribute behavior from those files; and
5. prove equivalent `.text` and GraphML inputs normalize to equal CTypeGraph
   nodes, edges, AST paths, isolated vertices, and represented-name mappings.

Until this gate passes, `.text` is the only accepted CType machine input and the
CLI must not claim GraphML input compatibility. `.gv` remains explicitly
unsupported. GraphML written by ConfTamer for visualization is never treated as
gopls machine input.

## Consumer dispatch and provenance

**Target design:** CType dispatch is content-aware:

- `.text` or JSON-leading content: parse the observed JSON contract;
- `.gv` or DOT content: unsupported-format error;
- `.graphml` or XML-leading content: blocked until verified producer examples
  pass the gate above.

When GraphML becomes accepted, callers still identify graph roles with
`--unmarshaler` and `--accessors` during PMGraph construction; the normalized
CType model itself requires no role metadata.

Canonical provenance uses SHA-256 of exact input bytes plus compact record
identifiers such as line numbers. Paths, fixture directories, and raw payloads
are not canonical identity. Reformatting an upstream file may therefore change
its source digest without changing normalized graph semantics.

## Integration smoke expectations

These expectations execute checked-in examples and should remain outside core
schema assumptions:

1. `scrape-ok.jsonl` plus target-scraper CSV and both CType graphs validates
   `/scrape.targetScraper`, finds one semantic `GET /` Send Request, creates 108
   Parameter edges, and preserves the ContextTrack message edge.
2. Manager CSV parsing yields four same-message CType rows and a 226-key union.
3. Against a minimal unique `GET /metrics` trace, those rows create 226
   deduplicated Parameter edges with all supporting source lines.
4. Against `all-tests.jsonl`, the selected Send identity produces 47 semantic
   `GET /metrics` candidates with distinct hosts; the join is ambiguous and
   creates no manager Parameter edges.
5. Reordering ParamTrack rows does not change semantic node IDs or edge endpoint
   pairs. The source digest and physical line references do change and must
   continue to identify the reordered bytes accurately.

If a real producer artifact invalidates an expectation, update the provenance
record and design deliberately rather than weakening validation around one
sample.
