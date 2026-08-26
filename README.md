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

### Use a standalone binary in CI/CD

CI/CD jobs can use a standalone executable built by the **Release binaries**
GitHub Actions workflow instead of installing Python, `uv`, and the project
dependencies:

1. Open the repository's **Actions** tab.
2. Select **Release binaries** and open its latest successful run.
3. Under **Artifacts**, download the archive for the job's platform:
   - `conftamer-linux-x86_64`
   - `conftamer-macos-arm64`
   - `conftamer-windows-x86_64`
4. Extract the archive. On Linux or macOS, grant the extracted `conftamer-*`
   file execute permission with `chmod +x`. The Windows executable ends in
   `.exe`.
5. Invoke the extracted executable directly from the CI/CD job.

Actions artifacts are retained for 14 days, so download the executable while
the workflow run is still available.

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

The generated GraphML files are intended to be imported and explored with
[Gephi Lite](https://lite.gephi.org/).

The CSV file must be headerless. Each row must have one of these forms:

```text
Parameter,<module_id>,<parameter_name>,Send,<module_id>,<api_id>,<request_id>,<response_code>
Receive,<module_id>,<api_id>,<request_pattern>,<response_code>,Send,<module_id>,<api_id>,<request_id>,<response_code>
```

## Try the included examples

The repository includes small and large inputs for both conversion workflows.
Convert the ContextTrack quickstart trace with:

```bash
uv run conftamer contexttrack \
  examples/contexttrack/prometheus/scrape-ok.jsonl \
  --module-id github.com/prometheus \
  --output /tmp/scrape-ok.pmgraph.json
```

Try the minimal legacy graph without leaving generated output in the checkout:

```bash
cp examples/legacy/minimal.csv /tmp/conftamer-minimal.csv
uv run conftamer graph /tmp/conftamer-minimal.csv
```

See the [example catalog](examples/README.md) for larger vectors, expected
behavior, provenance notes, and additional commands.

## Further reference

See the [technical reference](docs/technical-reference.md) for conversion
behavior, the PMGraph schema, programmatic Python usage, limitations, and
development guidance.
