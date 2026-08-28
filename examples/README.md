# Example inputs

These checked-in inputs are intended for trying ConfTamer workflows from a
repository checkout. They are examples and exploratory vectors, not fixtures
used by the unit test suite. Generated `*.pmgraph.json` and `*.graphml` files
are intentionally excluded from version control.

## ContextTrack traces

All three traces were captured from instrumented Go tests involving Prometheus
and related packages. Use `github.com/prometheus` as the module ID when
converting them.

| Input | Events | Purpose | Current conversion behavior |
| --- | ---: | --- | --- |
| `contexttrack/prometheus/scrape-ok.jsonl` | 20 | Small quickstart trace | 4 nodes, 1 edge, no warnings |
| `contexttrack/prometheus/package-tests.jsonl` | 5,530 | Larger package-level trace | 251 nodes, 17 edges, no warnings |
| `contexttrack/prometheus/all-tests.jsonl` | 13,954 | Broad, noisy stress trace | 1,091 nodes, 156 edges, many route-matching warnings |

The behavior counts describe the current converter and help users choose an
input; they are not a stable output contract. In particular, warnings from
`all-tests.jsonl` demonstrate how the converter reports relationships it
cannot match conservatively.

Convert the quickstart trace and validate the resulting PMGraph through the
CLI:

```bash
uv run conftamer contexttrack \
  examples/contexttrack/prometheus/scrape-ok.jsonl \
  --module-id github.com/prometheus \
  --output /tmp/scrape-ok.pmgraph.json
```

Try the package-level trace in the same way:

```bash
uv run conftamer contexttrack \
  examples/contexttrack/prometheus/package-tests.jsonl \
  --module-id github.com/prometheus \
  --output /tmp/package-tests.pmgraph.json
```

The broad trace intentionally produces substantial warning output. Redirect it
if you want to inspect the warnings separately:

```bash
uv run conftamer contexttrack \
  examples/contexttrack/prometheus/all-tests.jsonl \
  --module-id github.com/prometheus \
  --output /tmp/all-tests.pmgraph.json \
  2>/tmp/all-tests.warnings
```

### Provenance and normalization

These traces are real data from running `contexttrack` on prometheus.
Absolute source-file prefixes were normalized to
`/go-conftamer/src/` before check-in. Runtime values such as process IDs,
ports, and temporary socket names remain as captured because they exercise the
input format.

## ParamTrack artifacts

[`paramtrack/`](paramtrack/) contains real Prometheus outputs from ParamTrack
and the gopls CType analysis it consumes. The artifacts are grouped into:

- `paramtrack/static/` for the Unmarshaler Subgraph, Accessors, and reference
  analyzer output; and
- `paramtrack/runs/` for per-run parameter CSV, hierarchy, and log output.

See the [ParamTrack artifact catalog](paramtrack/README.md) for provenance,
file roles, and observed graph/row counts.

## Legacy CSV inputs

The legacy examples are synthetic, headerless edge CSV files:

| Input | Rows | Purpose |
| --- | ---: | --- |
| `legacy/minimal.csv` | 2 | Minimal graph smoke test |
| `legacy/synthetic.csv` | 99 | Larger synthetic graph |
| `legacy/synthetic-long.csv` | 99 | Longer synthetic message-flow graph |

The legacy command writes GraphML beside its input. Copy an example to a
temporary location to keep generated files outside the checkout:

```bash
cp examples/legacy/minimal.csv /tmp/conftamer-minimal.csv
uv run conftamer graph /tmp/conftamer-minimal.csv
```

The result is `/tmp/conftamer-minimal.csv.graphml`, which can be explored with
[Gephi Lite](https://lite.gephi.org/).
