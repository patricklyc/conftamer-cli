# Examples and test fixtures

This directory contains real upstream ContextTrack HTTP artifacts used as
read-only source fixtures. Each capture directory contains an original
`raw.jsonl` and its supplied schema-v1 `normalized.jsonl`. ConfTamer consumes the
**normalized file directly**; Go's raw output still requires separate upstream
normalization. These files are observations, not generated PMGraphs.

## ContextTrack Prometheus captures

The pairs under [`contexttrack/prometheus/`](contexttrack/prometheus/) come from
instrumented Prometheus tests. Each JSONL record is one observation, not one
semantic graph node. Both pairs are repository test fixtures, not optional
sibling-checkout inputs.

| Capture directory | Observations per file | Current PMGraph | Warnings | Intended use |
| --- | ---: | --- | ---: | --- |
| [`TestTargetScraperScrapeOK/`](contexttrack/prometheus/TestTargetScraperScrapeOK/) | 20 | 4 nodes, 1 edge | 0 | Exact correlation and deduplication regression; CLI build and raw-input rejection |
| [`all-tests/`](contexttrack/prometheus/all-tests/) | 7,235 | 960 nodes, 117 edges | 373 | Larger importer regression with routing, multiple PIDs, and conflicting/incomplete associations |

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

### Broad test capture

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
The tests pin the graph counts, message-only receive-to-send direction,
representative routed labels, and warning reasons/locations. These results do not
authorize broader matching or establish complete capture coverage.

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

ContextTrack 0.2.0 at the repository's pinned revision reproduces both supplied
normalized files byte-for-byte. Normalization preserves observation order and
repeated hooks; association, label recovery, node deduplication, and influence
projection belong to the consumer. Exhaustive normalizer/schema tests belong to
the upstream package, not this repository.

## Fixture policy

- Do not edit, regenerate, or normalize the supplied artifacts in place to make
  tests pass. Importer tests read the supplied normalized fixtures directly.
- Use small synthetic traces for focused boundary-case tests.
- Write generated normalized copies, PMGraphs, and other outputs to a pytest
  temporary directory or another explicitly selected output directory, not
  beside these files.
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
