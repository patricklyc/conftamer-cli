# Examples and test fixtures

This directory holds two kinds of data:

- **A real capture.** A tracked upstream ContextTrack HTTP capture, used as a
  read-only source fixture. Each capture pair contains an original `raw.jsonl`
  and its supplied schema-v1 `normalized.jsonl`. ConfTamer consumes the
  **normalized file directly**; Go's raw output still requires separate upstream
  normalization. Larger `all-tests` captures may be present locally but are not
  tracked or required by tests. These files are observations, not generated
  PMGraphs.
- **Synthetic PMGraphs.** [`pmgraphs/`](pmgraphs/) holds three hand-written
  graphs for an invented checkout application. They were not captured from any
  program. They exist to show and test stitching, which the real capture cannot
  do because it is a single module. [`walkthrough.py`](walkthrough.py) runs the
  same tour through the Python library.

## ContextTrack Prometheus captures

The captures under [`contexttrack/prometheus/`](contexttrack/prometheus/) come
from instrumented Prometheus tests. Each JSONL record is one observation, not one
semantic graph node. Only the small scrape pair is a tracked test fixture; the
broad pair below is optional local data, retained here as a historical result.

| Capture directory | Observations per file | Current PMGraph | Warnings | Intended use |
| --- | ---: | --- | ---: | --- |
| [`TestTargetScraperScrapeOK/`](contexttrack/prometheus/TestTargetScraperScrapeOK/) | 20 | 4 nodes, 1 edge | 0 | Exact correlation and deduplication regression; CLI build and raw-input rejection |
| `all-tests/` (optional, untracked) | 7,235 | 960 nodes, 117 edges | 373 | Historical manual smoke check; not required by tests |

### Small scrape capture

`TestTargetScraperScrapeOK/normalized.jsonl` retains four sent requests, four
received requests, four sent responses, and eight received-response hooks. The
client host is `127.0.0.1:43203`. Consumer association and deduplication produce
four nodes in first-occurrence order:

- `n0`: sent `GET` request to `127.0.0.1:43203`, path `/`;
- `n1`: received `GET` request, path `/`;
- `n2`: sent response, path `/`, status 200; and
- `n3`: received response from the client request, status 200.

The only edge is `n1 → n2`. Wire/client response hooks remain separate
observations; they are not separate semantic nodes. The raw capture's explicit
empty client path becomes `/` during upstream normalization, not during import.
See the [quick start](../README.md#quick-start) for build/query/export using the
supplied normalized file.

### Optional broad capture

The local `all-tests` pair is intentionally not tracked. There is no test fixture
or regression requiring it; use synthetic traces and the small tracked capture
for automated verification. The following results describe a previous manual
smoke check, not a CI prerequisite.

`all-tests/normalized.jsonl` contains 69 PIDs with context-ID strings reused across
processes and 911 routing observations. Correlation remains scoped to
`(pid, context_id)` within this capture; routing supplies metadata, not nodes.

The current conservative importer emits 373 warnings:

- 370 response observations conflict with their matched request's known API ID;
- three responses have no preceding matching request, at normalized physical
  lines 1147–1149.

These unusable response observations are omitted without discarding other usable
evidence, including nonconflicting duplicate hooks. Warnings identify the file
actually imported and physical line, not producer debug `file`/`line` values.
The historical smoke check inspected graph counts, message-only receive-to-send
direction, representative routed labels, and warning reasons/locations. These
results do not authorize broader matching or establish complete capture coverage.

## Synthetic PMGraphs (`pmgraphs/`)

**These graphs are hand-written, not captured.** They model a checkout flow
across three modules and, unlike anything `build` produces, they contain
`parameter` nodes:

```text
             POST /carts/42/checkout                 PUT /stock/sku-123/reserve
 frontend  ───────────────────────────▶  orders  ───────────────────────────────▶  inventory
           ◀───────────────────────────          ◀───────────────────────────────
                       201                                      200
```

| Behavior | Where in the example |
| --- | --- |
| A concrete path matched to a net/http `{name}` pattern | `/carts/42/checkout` ↔ `/carts/{cart_id}/checkout` |
| A concrete path matched to an httprouter `:name` pattern | `/stock/sku-123/reserve` ↔ `/stock/:sku/reserve` |
| A request/response round trip | each request has a matching response link |
| A chain through an intermediate module | frontend → orders → inventory and back |
| A message with no counterpart | frontend's `send-analytics` (no analytics module) |

Run the tour from the repository root. It writes to a fresh temporary directory,
not beside these files:

```bash
RUN=$(mktemp -d /tmp/conftamer-run.XXXXXX)
```

### 1. Stitch the PMGraphs into an AppGraph

```bash
uv run conftamer stitch examples/pmgraphs/*.pmgraph.json --output "$RUN/app.json"
```

`$RUN/app.json` holds this AppGraph:

```text
nodes:
  frontend::param-checkout-timeout   parameter checkout.timeout
  inventory::param-db-pool-size      parameter db.pool_size
  orders::param-max-retries          parameter inventory.max_retries
  link0   POST /carts/{cart_id}/checkout         frontend::send-checkout     => orders::recv-checkout
  link1   PUT /stock/:sku/reserve                orders::send-reserve        => inventory::recv-reserve
  link2   POST /carts/{cart_id}/checkout -> 201  orders::send-checkout-201   => frontend::recv-checkout-201
  link3   PUT /stock/:sku/reserve -> 200         inventory::send-reserve-200 => orders::recv-reserve-200
edges:
  frontend::param-checkout-timeout -> link0
  inventory::param-db-pool-size -> link3
  link0 -> link1
  link0 -> link2
  link1 -> link3
  link3 -> link2
  orders::param-max-retries -> link1
```

- **Parameters are renamed** `module_id::node_id`.
- **Each `linkN` is one message**, made by merging the node that sent it with
  the node that received it. It records both original nodes
  (`sender_module`/`sender_node`, `receiver_module`/`receiver_node`). Adding or
  renaming a module can renumber the links, so find a particular call by those
  fields.
- **Edges between links come from each module's own edges.** `link0 → link1` is
  orders' `recv-checkout → send-reserve` edge, moved onto the two merged nodes.
  Stitching never makes up a cross-module edge.

`stitch` also wrote `$RUN/app.dropped.json`, the messages it left out:

```json
[
  {
    "module_id": "frontend",
    "node_id": "send-analytics",
    "reason": "unmatched",
    "message": {
      "kind": "send_request",
      "api_id": "analytics-api",
      "method": "POST",
      "host": "analytics:9000",
      "path": "/events",
      "pattern": null,
      "status_code": null
    }
  }
]
```

`unmatched` means no other module had a matching message. The report is written
even when it is empty (`[]`); `--dropped PATH` puts it somewhere else. The
[reference](../docs/reference.md#stitch) lists the other reasons.

### 2. Ask what can influence a behavior

Which configuration parameters, in any module, can influence the checkout
response that frontend receives (`link2`)?

```bash
uv run conftamer query "$RUN/app.json" --node link2 --paths
```

The output's `paths` are:

```text
frontend::param-checkout-timeout -> link0 -> link2
inventory::param-db-pool-size -> link3 -> link2
frontend::param-checkout-timeout -> link0 -> link1 -> link3 -> link2
orders::param-max-retries -> link1 -> link3 -> link2
```

All three modules' parameters show up. Inventory's `db.pool_size` reaches
frontend only through orders, which neither module's PMGraph could show by
itself. Every node can reach `link2`, so the `subgraph` in the output is the
whole AppGraph.

### 3. Ask what a parameter can affect

Name a parameter by its node ID or by its configuration key:

```bash
uv run conftamer query "$RUN/app.json" --node orders::param-max-retries
uv run conftamer query "$RUN/app.json" --key inventory.max_retries
```

Both print the same AppGraph JSON, holding the parameter and the links it can
reach:

```text
nodes:  orders::param-max-retries, link1, link2, link3
edges:  link1 -> link3, link3 -> link2, orders::param-max-retries -> link1
```

The other parameters and the frontend-to-orders request (`link0`) are left out.
If two modules had a parameter with that key, the command would fail and list
both IDs; add `--module orders` or use `--node`. Without `--paths` the output is
a graph file, so it can be saved and passed to `export`.

### 4. Export to GraphML

```bash
uv run conftamer export "$RUN/app.json" --output "$RUN/app.graphml"
```

Tools such as Gephi, yEd, or igraph can open the result. Each vertex has `name`
(the node ID) and one attribute per node field, such as `kind`, `pattern`, and
`sender_module`.

### Writing PMGraphs by hand

A `*.pmgraph.json` file is a serialized `conftamer.pmgraph.models.PMGraph`:

```json
{
  "module_id": "orders",
  "nodes": {
    "<node-id>": { "kind": "...", ... }
  },
  "edges": [["<source-node-id>", "<target-node-id>"], ...]
}
```

- Every edge must connect two nodes that exist in the file.
- Node IDs and `module_id` must not contain `::`, and `module_id` must not end
  with `:`. Stitching uses `::` to name parameters, as in
  `orders::param-max-retries`.
- A sent request and a received response carry `host` and `path`. A received
  request and a sent response carry exactly one of `pattern` and `path`, and no
  `host`. Responses carry a `status_code`; requests do not.
- Two messages link only across modules, and only when they share a nonempty
  `api_id`, agree on `method` and `status_code`, and the client's `path`
  satisfies the server's `pattern`. The
  [reference](../docs/reference.md#matching) gives the pattern syntax.

## Raw versus normalized workflow

Use the supplied `normalized.jsonl` files directly with `conftamer build`.
`raw.jsonl` is retained as source evidence and for raw-input rejection checks;
ConfTamer does not auto-detect or import it.

To reproduce normalization with the installed upstream package, write to a fresh
scratch directory rather than overwriting either artifact:

```bash
RUN=$(mktemp -d /tmp/conftamer-normalize.XXXXXX) &&
uv run contexttrack normalize \
  examples/contexttrack/prometheus/TestTargetScraperScrapeOK/raw.jsonl \
  --output "$RUN/events.v1.jsonl" &&
uv run conftamer build "$RUN/events.v1.jsonl" \
  --module-id example-module --output "$RUN/module.pmgraph.json"
```

Previous reproducibility checks with ContextTrack 0.2.0 at the repository's
pinned revision reproduced the supplied normalized captures byte-for-byte.
Normalization preserves observation order and repeated hooks; association,
label recovery, node deduplication, and influence projection belong to the consumer. Exhaustive normalizer/schema tests belong to
the upstream package, not this repository.

## Fixture policy

- Do not edit, regenerate, or normalize the supplied artifacts in place to make
  tests pass. Importer tests read the supplied normalized fixtures directly.
- Use small synthetic traces for focused boundary-case tests.
- Keep `all-tests` captures local and untracked. Do not add a test dependency on
  them or require them in CI.
- Write generated normalized copies, PMGraphs, stitched AppGraphs and their
  reports, and other outputs to a pytest temporary directory or another
  explicitly selected output directory, not beside these files.
- `pmgraphs/` is synthetic. Do not describe results from it as observations of a
  real application.
- The old flat `scrape-ok.jsonl`, `package-tests.jsonl`, and `all-tests.jsonl`
  artifacts are no longer the fixture inventory. Their historical 5,530/13,954
  counts do not describe the new `all-tests/` pair.
- Do not infer format limits or general graph sizes from these event counts.
- Do not treat these Prometheus captures as a verified multi-module application
  corpus. API IDs do not establish module ownership.

The captures reflect only events observed through the producer's instrumentation
and exercised test paths. ConfTamer models possible influence, not proof of
causality, execution replay, or complete call-graph coverage. Normalization is
not redaction: real artifacts can retain hosts, queries, handlers, and local
source paths; review sensitivity before adding or sharing further captures.
