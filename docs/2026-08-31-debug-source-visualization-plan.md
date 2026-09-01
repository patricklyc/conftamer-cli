# Debug Source Visualization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an explicitly diagnostic CLI workflow that parses and exports either a standalone targeted ParamTrack CSV or a standalone verified CType graph as visualization-only GraphML.

**Architecture:** Add a reusable ParamTrack file-reading boundary that preserves records and CSV-local diagnostics before enrichment, then project those records as an undirected row-centered igraph association graph. Add `debug paramtrack` and `debug ctype` Typer subcommands; the CType path reuses the existing loader and projector exactly, while neither path creates canonical PMGraph semantics.

**Tech Stack:** Python 3.13+, standard-library `csv`, dataclasses, Typer, python-igraph, pytest, Ruff, ty, uv.

**Spec:** `docs/rewrite/architecture.md` (updated by Task 1 before source changes)

## Global Constraints

- Keep production Python under the hard review gate of **3,300 physical lines**; the starting count is **3,154**.
- Target a net production increase of **95–125 lines** and a final count of **3,249–3,279**.
- Stop for approval if the implementation projects above **3,280 production lines**, requires a new production module, changes canonical PMGraph/AppGraph/CType models, or needs a dependency.
- Do not add dependencies or raise the Python minimum version.
- Do not accept CType GraphML or Graphviz `.gv`; only the existing verified `.text` or JSON-leading CType JSON transport remains accepted.
- ParamTrack-only debug output performs CSV-local validation only. It does not validate CType references, correlate ContextTrack, select Send Requests, or represent PMGraph influence.
- ParamTrack `API` remains raw producer metadata and must not become `module_id` or ContextTrack `api_id`.
- GraphML remains visualization output and is not canonical persistence or accepted graph input.
- Use test-driven development for every behavior change: write the smallest failing test, confirm the expected failure, implement minimally, and rerun the focused test.
- Preserve unrelated changes. Do not commit, push, edit sibling repositories, or add generated output under `examples/`.

---

## Public command and API contract

The command surface added by this plan is:

```text
conftamer debug paramtrack PARAMETERS.csv --output PARAMETERS.graphml
conftamer debug ctype GRAPH.text --output CTYPE.graphml
```

The additive Python APIs are:

```python
@dataclass(frozen=True)
class ParamTrackReadResult:
    source: SourceArtifact
    records: tuple[ParamTrackRecord, ...]
    diagnostics: tuple[Diagnostic, ...]


def read_paramtrack(path: str | Path) -> ParamTrackReadResult: ...


def paramtrack_to_igraph(
    records: Iterable[ParamTrackRecord],
) -> ig.Graph: ...
```

The ParamTrack projection is an undirected association graph with deterministic vertex and edge insertion order.

### ParamTrack vertices

| Category | `name` | Cardinality | Meaning |
| --- | --- | ---: | --- |
| Row | `row:<physical-line>` | One per structurally valid CSV row | One producer observation |
| CType | `ctype:<exact CType>` | One per distinct nonempty CType | Unvalidated raw CType reference |
| Parameter | `parameter:<exact key>` | One per distinct key | Raw parameter key |

Every vertex receives string-valued attributes:

```text
name, label, node_type, source_line, api, verb, resource, ctype, parameter_key
```

Attributes that do not apply to a vertex are the empty string. Row labels are `line N: VERB RESOURCE`; CType and Parameter labels preserve their exact values.

### ParamTrack edges

- One undirected Row—CType edge with `relation="ctype"` when the row CType is nonempty.
- One undirected Row—Parameter edge with `relation="parameter"` for every deduplicated nonempty key in the parsed row.
- A row with no keys remains as an isolated row or a row connected only to its CType.
- No edge has influence, causality, CType-validation, or Send-matching semantics.

CSV-local diagnostics emitted by `read_paramtrack` are:

```text
paramtrack.invalid_row
paramtrack.empty_key
paramtrack.empty_verb
paramtrack.empty_ctype
paramtrack.possibly_truncated_message
```

`paramtrack.unknown_ctype`, `paramtrack.no_send_candidate`, and `paramtrack.ambiguous_send_candidate` remain enrichment-only diagnostics produced after external graph/message context is available.

---

### Task 1: Update the normative contracts before implementation

**Files:**
- Modify: `docs/rewrite/architecture.md` (`Data flow`, `ParamTrack enrichment`, `igraph and GraphML boundary`, `CLI contract`, and compatibility text)
- Modify: `docs/rewrite/implementation-plan.md` (append a post-rewrite debug-source checkpoint)

**Interfaces:**
- Consumes: The command and API contract defined above.
- Produces: The normative contract against which Tasks 2–5 are implemented.

- [ ] **Step 1: Update the architecture data flow and boundaries**

Add a separate noncanonical path:

```text
ParamTrack parameters.csv
    -> standalone CSV records and CSV-local diagnostics
    -> undirected observation association graph
    -> visualization GraphML
```

State explicitly that this path does not perform CType validation, Send matching, enrichment, or canonical serialization.

- [ ] **Step 2: Add the public standalone read and projection signatures**

Document `ParamTrackReadResult`, `read_paramtrack`, and `paramtrack_to_igraph`, including the exact vertex attributes, prefixed names, undirected edges, relation values, deterministic order, and CSV-local diagnostic set specified above.

- [ ] **Step 3: Extend the CLI contract**

Change the “four noninteractive commands” statement to include the top-level `debug` command and its two subcommands. Preserve all existing rejection rules for GraphML and `.gv` input.

- [ ] **Step 4: Append implementation-plan task 12**

Add an unchecked task covering standalone ParamTrack reading, observation projection, nested debug commands, documentation, real-input smoke tests, and the 3,300-line checkpoint. Mark it complete only after Task 5 verification succeeds.

- [ ] **Step 5: Validate the contract edits**

Run:

```bash
rg -n "debug paramtrack|debug ctype|ParamTrackReadResult|paramtrack_to_igraph|undirected" \
  docs/rewrite/architecture.md docs/rewrite/implementation-plan.md
git diff --check
```

Expected: every new command/API appears in the architecture, task 12 is present and unchecked, and `git diff --check` is clean.

---

### Task 2: Extract standalone ParamTrack CSV reading

**Files:**
- Modify: `src/conftamer/paramtrack/models.py`
- Modify: `src/conftamer/paramtrack/importer.py`
- Modify: `src/conftamer/paramtrack/__init__.py`
- Test: `tests/paramtrack/test_importer.py`

**Interfaces:**
- Consumes: Existing `_read_records`, `ParamTrackRecord`, `Diagnostic`, `SourceArtifact`, and `sort_diagnostics` behavior.
- Produces: `ParamTrackReadResult` and `read_paramtrack(path: str | Path) -> ParamTrackReadResult` for Tasks 3 and 4.

- [ ] **Step 1: Add a failing standalone-reader test**

Import `read_paramtrack` and add a focused test using no CType graphs, module ID, or Send Request:

```python
def test_reads_paramtrack_without_enrichment_inputs(tmp_path):
    path = write_csv(
        tmp_path,
        HEADER
        + "api,,/ok,/Type,alpha,,alpha\n"
        + "api,GET,/123456789,,beta\n"
        + "too,short,for\n",
    )

    result = read_paramtrack(path)

    assert result.source.id == (
        f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"
    )
    assert [(record.input_line, record.keys) for record in result.records] == [
        (2, ("alpha",)),
        (3, ("beta",)),
    ]
    assert [(item.line, item.code) for item in result.diagnostics] == [
        (2, "paramtrack.empty_key"),
        (2, "paramtrack.empty_verb"),
        (3, "paramtrack.empty_ctype"),
        (3, "paramtrack.possibly_truncated_message"),
        (4, "paramtrack.invalid_row"),
    ]
    assert not any(
        item.code
        in {
            "paramtrack.unknown_ctype",
            "paramtrack.no_send_candidate",
            "paramtrack.ambiguous_send_candidate",
        }
        for item in result.diagnostics
    )
```

Keep existing unreadable UTF-8, malformed CSV, exact-header, multiline-row, key-deduplication, and source-line tests intact.

- [ ] **Step 2: Run the standalone-reader test and confirm failure**

Run:

```bash
uv run pytest -q tests/paramtrack/test_importer.py \
  -k reads_paramtrack_without_enrichment_inputs
```

Expected: collection/import failure because `read_paramtrack` is not defined or exported.

- [ ] **Step 3: Add the immutable read result**

In `src/conftamer/paramtrack/models.py`, add exactly:

```python
@dataclass(frozen=True)
class ParamTrackReadResult:
    source: SourceArtifact
    records: tuple[ParamTrackRecord, ...]
    diagnostics: tuple[Diagnostic, ...]
```

Reuse existing diagnostics and source models; do not create a canonical Pydantic document.

- [ ] **Step 4: Implement `read_paramtrack` by extracting existing work**

Move byte reading, SHA-256 source construction, UTF-8/header parsing, and CSV-local diagnostics behind:

```python
def read_paramtrack(path: str | Path) -> ParamTrackReadResult:
    source_path = Path(path)
    source_name = str(path)
    data = source_path.read_bytes()
    source = SourceArtifact(
        id=f"sha256:{hashlib.sha256(data).hexdigest()}",
        kind="paramtrack-csv",
    )
    records, diagnostics = _read_records(data, source_name)
    diagnostics.extend(
        diagnostic
        for record in records
        for diagnostic in _local_record_diagnostics(record, source_name)
    )
    return ParamTrackReadResult(
        source=source,
        records=tuple(records),
        diagnostics=sort_diagnostics(diagnostics),
    )
```

Implement `_local_record_diagnostics` using the existing codes and messages for empty Verb, empty CType, and labels of length 10 or greater. It must not inspect CType graphs or Send Requests.

- [ ] **Step 5: Reuse the read result from `import_paramtrack`**

Replace duplicate file/source parsing in `import_paramtrack` with `read_paramtrack(path)`. Initialize enrichment diagnostics from `list(read_result.diagnostics)`, then retain only external-context checks in `_eligible_records`:

- reject an empty Verb/CType or potentially truncated message without emitting a duplicate diagnostic;
- emit `paramtrack.unknown_ctype` only for a nonempty locally usable CType absent from both represented-name indexes;
- preserve no-key rows in `result.records` but do not join them;
- preserve all existing matching and evidence behavior.

Return the same `ParamTrackResult` shape using `read_result.source` and `read_result.records`.

- [ ] **Step 6: Export the additive API**

Update `src/conftamer/paramtrack/__init__.py` to export:

```python
ParamTrackReadResult
read_paramtrack
```

Do not remove or rename existing exports.

- [ ] **Step 7: Run focused ParamTrack tests**

Run:

```bash
uv run pytest -q tests/paramtrack/test_importer.py
```

Expected: all tests pass, including unchanged enrichment diagnostics and real-file counts.

- [ ] **Step 8: Format and record the first line checkpoint**

Run:

```bash
uvx ruff format \
  src/conftamer/paramtrack/models.py \
  src/conftamer/paramtrack/importer.py \
  src/conftamer/paramtrack/__init__.py \
  tests/paramtrack/test_importer.py
find src/conftamer -name '*.py' -print0 | xargs -0 wc -l
```

Expected: production count remains below approximately 3,190 lines. Stop and simplify before proceeding if it exceeds 3,200.

---

### Task 3: Project ParamTrack records as an observation graph

**Files:**
- Modify: `src/conftamer/analysis/igraph.py`
- Modify: `src/conftamer/analysis/__init__.py`
- Test: `tests/analysis/test_igraph.py`

**Interfaces:**
- Consumes: `Iterable[ParamTrackRecord]` from Task 2.
- Produces: `paramtrack_to_igraph(records: Iterable[ParamTrackRecord]) -> ig.Graph` for Task 4.

- [ ] **Step 1: Add a failing projection and GraphML round-trip test**

Construct records directly so the projection test remains independent of CSV transport:

```python
def test_paramtrack_projection_preserves_rows_and_shared_associations(tmp_path):
    records = (
        ParamTrackRecord(2, "api-a", "GET", "/", "/A", ("alpha", "shared")),
        ParamTrackRecord(3, "api-b", "POST", "/x", "/A", ("shared",)),
        ParamTrackRecord(4, "api-c", "GET", "/empty", "", ()),
    )

    graph = paramtrack_to_igraph(reversed(records))

    assert not graph.is_directed()
    assert graph.vs["name"] == [
        "row:2",
        "row:3",
        "row:4",
        "ctype:/A",
        "parameter:alpha",
        "parameter:shared",
    ]
    assert graph.vcount() == 6
    assert graph.ecount() == 5
    assert graph.vs.find(name="row:2")["api"] == "api-a"
    assert graph.vs.find(name="row:4")["ctype"] == ""
    assert graph.vs.find(name="parameter:shared")["parameter_key"] == "shared"
    assert sorted(graph.es["relation"]) == [
        "ctype",
        "ctype",
        "parameter",
        "parameter",
        "parameter",
    ]

    output = tmp_path / "paramtrack.graphml"
    write_graphml(graph, output)
    loaded = ig.Graph.Read_GraphML(str(output))
    assert not loaded.is_directed()
    assert loaded.vs["name"] == graph.vs["name"]
    assert loaded.es["relation"] == graph.es["relation"]
```

Also assert that every vertex attribute value is a string and that input iteration order does not affect vertex/edge order.

- [ ] **Step 2: Run the projection test and confirm failure**

Run:

```bash
uv run pytest -q tests/analysis/test_igraph.py \
  -k paramtrack_projection_preserves_rows
```

Expected: collection/import failure because `paramtrack_to_igraph` is not defined or exported.

- [ ] **Step 3: Implement the deterministic undirected projector**

In `src/conftamer/analysis/igraph.py`:

1. Materialize and sort records by `input_line`.
2. Collect distinct nonempty CTypes lexically.
3. Collect distinct parameter keys lexically.
4. Create row vertices first, then CType vertices, then Parameter vertices.
5. Assign all declared string attributes to every vertex, using `""` when not applicable.
6. Add row/CType and row/Parameter edges in row order and lexical value order.
7. Assign `relation` for every edge.

Do not use PMGraph node IDs, `module_id`, source digests, CType validation status, or evidence derivations. Do not add ParamTrack to `GraphDocument`, because it is not a canonical graph document.

- [ ] **Step 4: Export the projector**

Add `paramtrack_to_igraph` to `src/conftamer/analysis/__init__.py` without changing existing exports.

- [ ] **Step 5: Run focused analysis tests**

Run:

```bash
uv run pytest -q tests/analysis/test_igraph.py -k paramtrack
uv run pytest -q tests/analysis/test_igraph.py
```

Expected: the new test passes, followed by the complete analysis suite.

- [ ] **Step 6: Format and record the second line checkpoint**

Run:

```bash
uvx ruff format \
  src/conftamer/analysis/igraph.py \
  src/conftamer/analysis/__init__.py \
  tests/analysis/test_igraph.py
find src/conftamer -name '*.py' -print0 | xargs -0 wc -l
```

Expected: production count remains below approximately 3,245 lines. Stop and simplify before proceeding if it exceeds 3,255.

---

### Task 4: Add nested debug CLI commands

**Files:**
- Modify: `src/conftamer/cli.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `read_paramtrack`, `paramtrack_to_igraph`, `load_ctype_graph`, `ctype_to_igraph`, `write_graphml`, `_emit_diagnostics`, `_echo_summary`, and `_user_errors`.
- Produces: `conftamer debug paramtrack` and `conftamer debug ctype`.

- [ ] **Step 1: Add failing help tests**

Extend the help parameterization to cover:

```python
("debug", "--help")
("debug", "paramtrack", "--help")
("debug", "ctype", "--help")
```

Require top-level `--help` to include `debug` alongside `build`, `stitch`, `query`, and `export`.

- [ ] **Step 2: Add failing ParamTrack command tests**

Add one successful minimal CSV test that:

- invokes `debug paramtrack` without events, module ID, or CType options;
- reads the result with `ig.Graph.Read_GraphML()`;
- verifies the graph is undirected;
- verifies row, CType, and shared Parameter vertices and relation edges;
- verifies the summary is stdout and diagnostics are stderr.

Use a recoverable empty-key row to assert `paramtrack.empty_key` appears only on stderr. Add a separate exact-header failure test asserting exit code 1 and no output file.

- [ ] **Step 3: Add a failing CType command test**

Use the existing `write_ctype` helper and assert:

```python
result = invoke(
    "debug",
    "ctype",
    str(input_path),
    "--output",
    str(output),
)
assert result.exit_code == 0
assert ig.Graph.Read_GraphML(str(output)).vcount() == 3
```

The loaded graph must preserve the same direction and topology as existing CType export tests.

- [ ] **Step 4: Run the CLI debug tests and confirm failure**

Run:

```bash
uv run pytest -q tests/test_cli.py -k debug
```

Expected: failures because the `debug` command does not exist.

- [ ] **Step 5: Register the nested Typer group**

In `src/conftamer/cli.py`, add one subgroup:

```python
debug_app = typer.Typer(help="Inspect standalone producer artifacts.")
app.add_typer(debug_app, name="debug")
```

Do not create another CLI module or add format autodetection between CSV and CType; the explicit subcommand is the discriminator.

- [ ] **Step 6: Implement `debug paramtrack`**

The command must:

1. accept one positional `Path` and required `--output Path`;
2. call `read_paramtrack` inside `_user_errors()`;
3. call `paramtrack_to_igraph(result.records)`;
4. write with `write_graphml`;
5. emit `result.diagnostics` to stderr after successful writing;
6. print a concise `ParamTrack GraphML` node/edge summary to stdout.

Do not accept module, events, Unmarshaler, Accessors, or matching options.

- [ ] **Step 7: Implement `debug ctype`**

The command must:

1. accept one positional `Path` and required `--output Path`;
2. call `load_ctype_graph` and `ctype_to_igraph` inside `_user_errors()`;
3. write with `write_graphml`;
4. print a concise `CType GraphML` node/edge summary.

Do not duplicate CType loading or projection logic. Existing blocked-format errors must pass through unchanged.

- [ ] **Step 8: Run focused and complete CLI tests**

Run:

```bash
uv run pytest -q tests/test_cli.py -k debug
uv run pytest -q tests/test_cli.py
```

Expected: all debug tests and the complete existing CLI suite pass.

- [ ] **Step 9: Format and enforce the final production-line guard**

Run:

```bash
uvx ruff format src/conftamer/cli.py tests/test_cli.py
find src/conftamer -name '*.py' -print0 | xargs -0 wc -l
```

Expected: final production count is 3,249–3,279 lines. If it exceeds 3,280, simplify existing touched code before documentation or full verification. If remaining below 3,300 cannot be achieved within the approved files and behavior, stop and ask for approval rather than expanding scope.

---

### Task 5: Document and verify the complete workflow

**Files:**
- Modify: `README.md`
- Modify: `docs/technical-reference.md`
- Modify: `examples/README.md`
- Modify: `docs/rewrite/implementation-plan.md` (mark task 12 complete and record actual line count only after verification)

**Interfaces:**
- Consumes: The tested commands from Task 4.
- Produces: Current-release user guidance and a completed checkpoint record.

- [ ] **Step 1: Update the README workflow and examples**

Add `debug` to the workflow table and show both exact commands:

```bash
uv run conftamer debug paramtrack \
  examples/paramtrack/runs/target-scraper-all/parameters.csv \
  --output /tmp/paramtrack-debug.graphml

uv run conftamer debug ctype \
  examples/paramtrack/static/accessors.text \
  --output /tmp/accessors-debug.graphml
```

State that ParamTrack CType references are unvalidated in standalone mode and the result is an undirected observation graph, not PMGraph influence.

- [ ] **Step 2: Update the technical reference**

Document:

- the two debug subcommands and required output paths;
- ParamTrack vertex categories, attributes, association edges, and local diagnostics;
- the absence of CType validation and Send matching;
- CType reuse of the existing verified transport/projector;
- GraphML’s visualization-only status;
- the two additive Python APIs.

- [ ] **Step 3: Update the executable example catalog**

Add both real-input debug commands to `examples/README.md`. Keep generated GraphML paths under `/tmp`; do not create outputs in `examples/`.

- [ ] **Step 4: Run focused suites together**

Run:

```bash
uv run pytest -q \
  tests/paramtrack/test_importer.py \
  tests/analysis/test_igraph.py \
  tests/test_cli.py
```

Expected: all focused suites pass in one fresh run.

- [ ] **Step 5: Run real ParamTrack and CType smoke tests**

Run:

```bash
rm -f /tmp/paramtrack-debug.graphml /tmp/ctype-debug.graphml

uv run conftamer debug paramtrack \
  examples/paramtrack/runs/target-scraper-all/parameters.csv \
  --output /tmp/paramtrack-debug.graphml

uv run conftamer debug ctype \
  examples/paramtrack/static/accessors.text \
  --output /tmp/ctype-debug.graphml

uv run python - <<'PY'
import igraph as ig

paramtrack = ig.Graph.Read_GraphML("/tmp/paramtrack-debug.graphml")
ctype = ig.Graph.Read_GraphML("/tmp/ctype-debug.graphml")
assert not paramtrack.is_directed()
assert paramtrack.vcount() == 110
assert paramtrack.ecount() == 109
assert ctype.is_directed()
assert ctype.vcount() == 582
assert ctype.ecount() == 822
print("ParamTrack:", paramtrack.vcount(), paramtrack.ecount())
print("CType:", ctype.vcount(), ctype.ecount())
PY
```

Expected real ParamTrack count: one row + one CType + 108 Parameter vertices = 110 vertices; one CType association + 108 Parameter associations = 109 edges. Expected Accessors count: 582 vertices and 822 edges.

- [ ] **Step 6: Run all help-page smoke tests**

Run:

```bash
uv run conftamer --help
uv run conftamer build --help
uv run conftamer stitch --help
uv run conftamer query --help
uv run conftamer export --help
uv run conftamer debug --help
uv run conftamer debug paramtrack --help
uv run conftamer debug ctype --help
```

Expected: every command exits successfully, top-level help lists `debug`, and nested help exposes only the approved arguments/options.

- [ ] **Step 7: Run fresh full verification**

Run exactly:

```bash
uvx ruff format --check src tests
uvx tombi format --check pyproject.toml
uvx ty check
uv run pytest -q
find src/conftamer -name '*.py' -print0 | xargs -0 wc -l
git diff --check
```

Expected: every command succeeds and production Python remains below 3,300 lines.

- [ ] **Step 8: Inspect scope and stale assumptions**

Run:

```bash
git status --short
git diff --stat
git diff -- \
  src/conftamer/paramtrack \
  src/conftamer/analysis \
  src/conftamer/cli.py \
  tests/paramtrack/test_importer.py \
  tests/analysis/test_igraph.py \
  tests/test_cli.py \
  README.md docs examples/README.md
rg -n "four noninteractive commands|only four|CType references.*validated|debug" \
  README.md docs examples/README.md src tests
```

Expected: only the approved files changed; no generated GraphML is present; no documentation still claims the CLI has only four commands; no debug documentation claims standalone CType validation or PMGraph influence.

- [ ] **Step 9: Complete the implementation checkpoint**

After all fresh verification succeeds, mark implementation-plan task 12 complete and record:

- the actual production Python line count;
- real ParamTrack GraphML counts;
- real CType GraphML counts;
- GraphML re-read success;
- no dependency or canonical-format change.

Then rerun:

```bash
git diff --check
```

Expected: clean output.

---

## Completion report requirements

Report all of the following without claiming results from an earlier run:

- changed files and each file’s purpose;
- exact focused and full verification commands with fresh results;
- actual production Python line count and remaining margin below 3,300;
- real-data ParamTrack and CType smoke-test counts;
- confirmation that both GraphML files were re-read by igraph;
- additive public API and CLI compatibility impact;
- confirmation that ParamTrack debug CTypes remain unvalidated and edges are associations, not influence;
- residual risks or incomplete behavior;
- a concise proposed commit message with subject and body, without committing.
