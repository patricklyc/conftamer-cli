# ConfTamer graph conversion tool

ConfTamer builds directed configuration and message-flow graphs. Use it to:

- convert ContextTrack JSONL traces into deterministic PMGraph JSON; or
- convert legacy edge-oriented CSV files into GraphML.

## Requirements and setup

ConfTamer requires Python 3.13 or newer. From a checkout, install the locked
dependencies with [uv](https://docs.astral.sh/uv/):

```bash
uv sync
uv run conftamer --help
```

The examples below use `uv run conftamer`. If ConfTamer is installed in the
active environment, invoke `conftamer` directly instead.

## Convert ContextTrack JSONL to PMGraph

Convert a ContextTrack trace with:

```bash
uv run conftamer contexttrack events.jsonl \
  --module-id example.org/service
```

The command writes `events.jsonl.pmgraph.json`. To choose another destination,
pass `--output`:

```bash
uv run conftamer contexttrack events.jsonl \
  --module-id example.org/service \
  --output service.pmgraph.json
```

`--module-id` identifies the module whose execution produced the trace. It is
required because ContextTrack does not include that value in its output.

The input must contain one ContextTrack event object per nonblank line.
Malformed or unsupported lines do not stop conversion: ConfTamer omits them,
reports warnings on standard error with their original line numbers, and
writes the usable portion of the graph.

## Convert legacy CSV to GraphML

Generate a full directed GraphML graph from a legacy edge CSV file:

```bash
uv run conftamer graph edges.csv
```

The command prints an `igraph` summary and writes `edges.csv.graphml`.

Generate the subgraph containing a selected vertex and all vertices in its
incoming and outgoing components:

```bash
uv run conftamer subgraph edges.csv 12
```

The command writes the selected subgraph to `edges.csv.graphml`.

The CSV file must be headerless. Each row must have one of these forms:

```text
Parameter,<module_id>,<parameter_name>,Send,<module_id>,<api_id>,<request_id>,<response_code>
Receive,<module_id>,<api_id>,<request_pattern>,<response_code>,Send,<module_id>,<api_id>,<request_id>,<response_code>
```

## Further reference

See the [technical reference](docs/technical-reference.md) for conversion
behavior, the PMGraph schema, programmatic Python usage, limitations, and
development guidance.
