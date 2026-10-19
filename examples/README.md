# Examples and test fixtures

This directory contains real **raw** ContextTrack HTTP event captures used as
read-only source fixtures. ConfTamer consumes only normalized schema-v1 JSONL;
these files require a separate upstream normalization step. They are not generated
PMGraphs or a set of runnable command examples.

## ContextTrack Prometheus captures

The files under [`contexttrack/prometheus/`](contexttrack/prometheus/) are
raw newline-delimited JSON (JSONL) captures from an instrumented Prometheus test
run. Each line contains one observation, not one normalized graph node.

| File | Raw observations | Intended use |
| --- | ---: | --- |
| [`scrape-ok.jsonl`](contexttrack/prometheus/scrape-ok.jsonl) | 20 | Small correlation and graph-projection regression fixture |
| [`package-tests.jsonl`](contexttrack/prometheus/package-tests.jsonl) | 5,530 | Larger integration fixture |
| [`all-tests.jsonl`](contexttrack/prometheus/all-tests.jsonl) | 13,954 | Broad, noisy integration fixture |

Only `scrape-ok.jsonl` is committed in this checkout. The two larger files are
optional local artifacts and may be absent in a fresh clone; CI does not depend
on them. Counts describe these specific raw captures, not normalized graph sizes.
See the [quick start](../README.md#quick-start) for normalization into a fresh
scratch directory followed by build/query/export.

Observed raw event kinds include:

- `Request sent`
- `Request received`
- `Request routed`
- `Response sent`
- `Response received`

`Request routed` records provide routing metadata; they do not represent an
additional semantic message. Context IDs are process-local, so consumers must
scope correlation to a capture and `(pid, context_id)` rather than treating a
context ID as globally unique.

## Fixture policy

Treat these captures as read-only source fixtures:

- Do not edit or normalize them in place to make tests pass.
- Normalize separate copies with installed `contexttrack.normalize_file` or
  `uv run contexttrack normalize INPUT --output NEW`. Tests use a shared fixture
  that writes normalized input to `tmp_path`; no generated capture is checked in.
- Use small synthetic traces for focused boundary-case tests.
- Write generated PMGraphs and other outputs to a pytest temporary directory
  or another explicitly selected output directory, not beside these files.
- Do not infer format limits or expected graph sizes from these event counts.
- Do not treat these Prometheus captures as a representative multi-module
  application corpus.

The captures reflect only the events observed through the producer's
instrumentation and the exercised test paths. They model possible influence;
they are not proof of causality, execution replay, or complete call-graph
coverage.
