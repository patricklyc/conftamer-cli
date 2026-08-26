# ConfTamer graph conversion tool

ConfTamer turns configuration and message-flow data into directed graphs. Choose
the workflow that matches your input:

| Input | Command | Output |
| --- | --- | --- |
| ContextTrack JSONL trace | `conftamer contexttrack` | Deterministic PMGraph JSON |
| Legacy edge CSV | `conftamer graph` or `conftamer subgraph` | GraphML |

## Install and run ConfTamer

### Run from a checkout

You need Python 3.13 or newer and [uv](https://docs.astral.sh/uv/). From the
repository root, install the locked dependencies and check that the command is
available:

```bash
uv sync
uv run conftamer --help
```

The rest of this guide uses `uv run conftamer`. If ConfTamer is already
installed in your active environment, you can use `conftamer` instead.

### Use a standalone binary from CI/CD

A standalone binary from a CI/CD job runs ConfTamer without installing Python,
uv, or project dependencies:

1. Open the repository's **Actions** tab.
2. Select the **Release binaries** workflow, then open its latest successful
   run.
3. In **Artifacts**, download the archive for your job's platform:
   - `conftamer-linux-x86_64`
   - `conftamer-macos-arm64`
   - `conftamer-windows-x86_64`
4. Extract the archive.
5. On Linux or macOS, make the extracted `conftamer-*` file executable:

   ```bash
   chmod +x conftamer-*
   ```

6. Run the extracted file directly. Windows binaries have an `.exe` extension.

Workflow artifacts are kept for 14 days, so download the binary before the
workflow run expires.

## Convert ContextTrack JSONL to PMGraph

Use this workflow when you have a ContextTrack trace. You need:

- a JSONL file with one ContextTrack event on each nonblank line; and
- a module ID for the module that produced the trace.

Run the conversion:

```bash
uv run conftamer contexttrack events.jsonl \
  --module-id example.org/service
```

ConfTamer writes the graph next to the input as
`events.jsonl.pmgraph.json`.

ContextTrack traces do not include the module ID, so `--module-id` is required.
Use the module represented by the complete trace, such as its Go module path.

To save the graph somewhere else, add `--output`:

```bash
uv run conftamer contexttrack events.jsonl \
  --module-id example.org/service \
  --output service.pmgraph.json
```

If a line is malformed or contains an unsupported event, ConfTamer skips that
line instead of stopping the whole conversion. It prints a warning with the
original line number to standard error and writes a graph from the events it
can use.

## Convert legacy CSV to GraphML

Use this workflow for the headerless edge CSV format supported by the original
ConfTamer prototype.

### Create the full graph

```bash
uv run conftamer graph edges.csv
```

ConfTamer prints an `igraph` summary and writes `edges.csv.graphml`.

### Create a smaller subgraph

Use `subgraph` to choose one vertex. The result keeps that vertex, every
vertex that can reach it, and every vertex it can reach:

```bash
uv run conftamer subgraph edges.csv config_a
```

The query can be either:

- a zero-based vertex ID, such as `0`; or
- a case-insensitive text fragment matched against all node attributes, such
  as `config_a`.

A unique text match is selected automatically. If several nodes match,
ConfTamer shows their full attributes and asks you to choose one. An invalid ID
or a query with no matches exits without writing a graph.

The selected subgraph is written to `edges.csv.graphml`, replacing an existing
file at that path.


You can open the generated GraphML file in a graph viewer such as
[Gephi Lite](https://lite.gephi.org/).

## Try the included examples

The repository includes sample inputs for both workflows.

### ContextTrack example

Convert the small quickstart trace:

```bash
uv run conftamer contexttrack \
  examples/contexttrack/prometheus/scrape-ok.jsonl \
  --module-id github.com/prometheus \
  --output /tmp/scrape-ok.pmgraph.json
```

The resulting graph is `/tmp/scrape-ok.pmgraph.json`.

### Legacy CSV example

Copy the example to a temporary directory first so the generated GraphML file
does not appear in your checkout:

```bash
cp examples/legacy/minimal.csv /tmp/conftamer-minimal.csv
uv run conftamer graph /tmp/conftamer-minimal.csv
```

The resulting graph is `/tmp/conftamer-minimal.csv.graphml`.

See the [example catalog](examples/README.md) for larger inputs, expected
behavior, provenance notes, and more commands.

## Learn more

See the [technical reference](docs/technical-reference.md) for detailed
conversion behavior, the PMGraph schema, Python API usage, limitations, and
development guidance.
