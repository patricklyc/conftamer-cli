# CType-to-GraphML MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce the current graph-compiler branch to a readable MVP that validates one gopls Unmarshaler or Accessors `.text` artifact per invocation and exports it as visualization GraphML.

**Architecture:** Keep one strict CType domain with three focused responsibilities: immutable normalized models, producer-JSON loading, and igraph/GraphML projection. Keep a thin Typer CLI with only `conftamer export INPUT.text --output OUTPUT.graphml`; callers run it once per artifact, and the two graphs are never merged. Delete PMGraph, AppGraph, ContextTrack, ParamTrack, query, stitching, and generic graph-dispatch code rather than hiding dormant surfaces.

**Tech Stack:** Python 3.13+, Pydantic v2, python-igraph, Typer, pytest, Ruff, ty, Tombi, uv, PyInstaller.

**Spec:** `docs/rewrite/architecture.md` and `docs/rewrite/input-formats.md`, narrowed to the MVP in Task 1; producer evidence remains the real files moved to `examples/ctype/` in Task 5.

## Global Constraints

- Preserve the verified gopls JSON envelope and field meanings from `docs/rewrite/input-formats.md`; do not infer new producer behavior.
- Accept only `.text` or JSON-leading CType JSON. Reject Graphviz/DOT, producer GraphML/XML, malformed JSON, and unrelated JSON.
- Producer GraphML input remains blocked because no real producer GraphML artifacts exist.
- Preserve upstream names and IDs exactly, grouped ordered AST paths, aliases, tags, methods, direction, and isolated vertices.
- Unknown producer fields remain accepted at the raw boundary but excluded from normalized semantics and GraphML.
- The Unmarshaler and Accessors artifacts are independent graphs. Do not combine, cross-link, or deduplicate them across files.
- Keep Pydantic, igraph, and Typer; do not add dependencies or raise the Python 3.13 minimum.
- Favor explicit functions and domain names over generic graph wrappers, service layers, or compatibility adapters.
- Use TDD for behavior changes and keep every checked-in GraphML round-trip readable by `ig.Graph.Read_GraphML()`.
- Production Python target: about **400 physical lines**, with a review range of **380–430** and a hard MVP ceiling of **450**.
- Do not edit sibling repositories or producer implementations.

---

## Scope and Acceptance Criteria

1. The only installed command is:

   ```text
   conftamer export INPUT.text --output OUTPUT.graphml
   ```

2. One invocation consumes one artifact. Exporting both real artifacts requires two invocations and creates two independent GraphML files.
3. The parser retains the current strict validation and canonical normalization behavior for `Edges`, `Vertices`, and `List`.
4. The GraphML is directed, retains isolated vertices, and retains one edge per producer `(Source, Target)` record.
5. Vertex `name` and `label` use the stable upstream CType ID. Human-readable `aliases`, `methods`, and `tags` attributes accompany lossless `names_json`, `methods_json`, and `tags_json` attributes.
6. Edge `ast_paths` is human-readable, while `ast_paths_json` losslessly preserves grouped paths and segment order.
7. All GraphML attribute values are strings so igraph emits a homogeneous, Gephi-friendly schema.
8. Real Unmarshaler export re-reads as 57 vertices and 90 edges. Real Accessors export re-reads as 582 vertices and 822 edges.
9. Invalid input exits nonzero, reports a concise error on stderr, and does not create an output file.
10. `build`, `stitch`, and `query` are absent, as are PMGraph/AppGraph/ContextTrack/ParamTrack Python packages and claims.
11. The README, technical reference, examples, CI/release smoke tests, and project guidance describe only this MVP.
12. GraphML is a visualization output. Semantic order is stable, but byte-for-byte GraphML identity is not a promised API because serialization belongs to python-igraph.

## Assumptions and Explicit Non-goals

- “Unmarshaller” in the request refers to the producer’s existing **Unmarshaler Subgraph** artifact and spelling.
- Role detection is unnecessary: both real files use the same verified producer envelope, and the input/output filenames communicate the role.
- No combined US+Accessors graph, querying, reachability, canonical JSON output, GraphML input, `.gv` fallback, or ParamTrack CSV processing belongs in this MVP.
- The normalized `CTypeGraph` remains an internal/public Python boundary because it makes validation testable and keeps igraph serialization from defining input semantics.

## Target File Map

### Production files retained or created

- `src/conftamer/__init__.py` — package marker only.
- `src/conftamer/cli.py` — one Typer `export` command and concise user-error handling.
- `src/conftamer/ctype_graph/__init__.py` — small public export list.
- `src/conftamer/ctype_graph/models.py` — frozen CType models and graph invariants.
- `src/conftamer/ctype_graph/io.py` — raw producer models, transport checks, loading, and normalization.
- `src/conftamer/ctype_graph/graphml.py` — CType-to-igraph projection and GraphML writing.

### Focused tests retained or created

- `tests/ctype_graph/test_io.py` — minimal producer-contract and real-artifact parser tests.
- `tests/ctype_graph/test_graphml.py` — projection attributes, direction, isolates, grouped paths, and GraphML read-back.
- `tests/test_cli.py` — single-command help, success, real artifacts, errors, and packaging entry point.

### Production files deleted

- `src/conftamer/analysis/`
- `src/conftamer/appgraph/`
- `src/conftamer/contexttrack/`
- `src/conftamer/paramtrack/`
- `src/conftamer/pmgraph/`
- `src/conftamer/build.py`
- `src/conftamer/diagnostics.py`

### Test trees deleted

- `tests/analysis/` after its CType coverage moves to `tests/ctype_graph/test_graphml.py`
- `tests/appgraph/`
- `tests/contexttrack/`
- `tests/paramtrack/`
- `tests/pmgraph/`
- `tests/test_build.py`

### Example layout after pruning

```text
examples/
├── README.md
└── ctype/
    ├── README.md
    ├── accessors.text
    └── unmarshaler_subgraph.text
```

## Production Line-count Estimate

| File | Estimated physical lines |
| --- | ---: |
| `src/conftamer/__init__.py` | 0 |
| `src/conftamer/ctype_graph/__init__.py` | 10–15 |
| `src/conftamer/ctype_graph/models.py` | 115–130 |
| `src/conftamer/ctype_graph/io.py` | 125–140 |
| `src/conftamer/ctype_graph/graphml.py` | 65–80 |
| `src/conftamer/cli.py` | 50–65 |
| **Estimated total** | **365–430; expected about 400** |

The current branch has 3,154 production Python lines. The expected reduction is roughly 2,750 lines, or 87%. The estimate intentionally leaves readable validation helpers intact instead of compressing the parser to minimize line count.

---

### Task 1: Replace Broad Contracts with the CType Export Contract

**Files:**
- Modify: `AGENTS.md`
- Modify: `docs/rewrite/architecture.md`
- Modify: `docs/rewrite/input-formats.md`
- Modify: `docs/rewrite/implementation-plan.md`
- Delete during execution: `docs/superpowers/plans/2026-09-03-flexible-build-artifacts.md`

**Interfaces:**
- Consumes: the verified CType sections in the current architecture/input-format documents.
- Produces: the exact MVP scope and acceptance criteria used by every later task.

- [ ] **Step 1: Record the clean baseline and current size**

  Run:

  ```bash
  git status --short --branch
  uv run pytest -q tests/ctype_graph/test_io.py tests/analysis/test_igraph.py tests/test_cli.py
  find src/conftamer -name '*.py' -print0 | xargs -0 wc -l
  ```

  Expected: clean `ctype-mvp` branch, 86 focused tests passing, and 3,154 production lines before implementation.

- [ ] **Step 2: Rewrite the architecture around one linear data flow**

  Replace the broad pipeline in `docs/rewrite/architecture.md` with:

  ```text
  gopls Unmarshaler Subgraph .text  ─┐
                                     ├─ one file per invocation
  gopls Accessors .text              ─┘
      -> strict raw validation
      -> normalized frozen CTypeGraph
      -> directed python-igraph graph
      -> visualization GraphML
  ```

  Define these public boundaries exactly:

  ```python
  def load_ctype_graph(path: str | Path) -> CTypeGraph: ...
  def to_igraph(graph: CTypeGraph) -> ig.Graph: ...
  def export_graphml(graph: CTypeGraph, path: str | Path) -> None: ...
  ```

  Include the normalization rules already implemented in `ctype_graph/models.py` and `ctype_graph/io.py`, the GraphML attributes from Acceptance Criteria 5–7, the single CLI command, the 450-line ceiling, and all explicit non-goals.

- [ ] **Step 3: Reduce the input-format document without weakening producer evidence**

  Keep the current inspected gopls producer revision, `.text` JSON envelope, vertex/edge/`List` contracts, real graph counts, unknown-field policy, and blocked GraphML explanation. Remove ContextTrack, ParamTrack CSV, PMGraph, AppGraph, and cross-producer join sections. State that `.gv` and producer logs are not retained as MVP examples and are not machine inputs.

- [ ] **Step 4: Make repository guidance executable**

  Rewrite `AGENTS.md` to name only the target files and focused checks. Replace `docs/rewrite/implementation-plan.md` with a concise ordered summary of this migration and a link to this detailed plan. Delete the superseded flexible-build plan so an executor cannot accidentally implement the old PMGraph direction.

- [ ] **Step 5: Validate the documentation changes**

  Run:

  ```bash
  rg -n "PMGraph|AppGraph|ContextTrack|ParamTrack CSV|build|stitch|query" \
    AGENTS.md docs/rewrite
  rg -n "Unmarshaler|Accessors|Edges|Vertices|List|GraphML|450" \
    AGENTS.md docs/rewrite
  git diff --check
  ```

  Expected: the first search finds only short historical/non-goal statements; the second finds the complete input/output contract and line gate; `git diff --check` is clean.

- [ ] **Step 6: Commit the contract checkpoint**

  ```bash
  git add AGENTS.md docs/rewrite docs/superpowers/plans
  git commit -m "docs: narrow ConfTamer to CType GraphML export"
  ```

---

### Task 2: Add a Focused, Human-readable CType GraphML Projection

**Files:**
- Create: `src/conftamer/ctype_graph/graphml.py`
- Create: `tests/ctype_graph/test_graphml.py`
- Modify: `src/conftamer/ctype_graph/__init__.py`

**Interfaces:**
- Consumes: `CTypeGraph`, `CTypeNode`, and `CTypeEdge` from `conftamer.ctype_graph.models`.
- Produces: `to_igraph(graph: CTypeGraph) -> ig.Graph` and `export_graphml(graph: CTypeGraph, path: str | Path) -> None`.

- [ ] **Step 1: Write the failing projection tests using a small explicit graph**

  Add a fixture with one root, one child, one isolated node, and one grouped-path edge:

  ```python
  def ctype_graph() -> CTypeGraph:
      child = CTypeNode(id="/child.Type", names=("/child.Type",), methods=(), tags=None)
      isolated = CTypeNode(
          id="/isolated.Type", names=("/isolated.Type",), methods=(), tags={}
      )
      root = CTypeNode(
          id="/root.Type",
          names=("/root.Type", "/alias.Type"),
          methods=("MethodA", "MethodB"),
          tags={"json": 'json:"root"', "yaml": 'yaml:"root"'},
      )
      return CTypeGraph(
          nodes=(child, isolated, root),
          edges=(
              CTypeEdge(
                  source=root.id,
                  target=child.id,
                  ast_paths=((), ("Field:a",), ("Field:z", "Tail")),
              ),
          ),
          name_to_node={
              "/alias.Type": root.id,
              child.id: child.id,
              isolated.id: isolated.id,
              root.id: root.id,
          },
      )
  ```

  Assert directedness, canonical vertex order, the isolate, edge direction, and exact root attributes:

  ```python
  assert root["name"] == "/root.Type"
  assert root["label"] == "/root.Type"
  assert root["aliases"] == "/alias.Type"
  assert root["methods"] == "MethodA\nMethodB"
  assert root["tags"] == 'json: json:"root"\nyaml: yaml:"root"'
  assert root["names_json"] == '["/root.Type","/alias.Type"]'
  assert root["methods_json"] == '["MethodA","MethodB"]'
  assert root["tags_json"] == '{"json":"json:\\"root\\"","yaml":"yaml:\\"root\\""}'
  assert edge["ast_paths"] == "(empty path)\nField:a\nField:z → Tail"
  assert edge["ast_paths_json"] == '[[],["Field:a"],["Field:z","Tail"]]'
  ```

- [ ] **Step 2: Run the new test to verify the boundary is absent**

  Run:

  ```bash
  uv run pytest -q tests/ctype_graph/test_graphml.py
  ```

  Expected: collection fails because `conftamer.ctype_graph.graphml` does not exist.

- [ ] **Step 3: Implement the minimal projection**

  In `graphml.py`, create all vertices before edges and use these explicit helpers:

  ```python
  def to_igraph(document: CTypeGraph) -> ig.Graph:
      graph = ig.Graph(n=len(document.nodes), directed=True)
      for index, node in enumerate(document.nodes):
          graph.vs[index].update_attributes(_node_attributes(node))
      indices = {node.id: index for index, node in enumerate(document.nodes)}
      graph.add_edges(
          (indices[edge.source], indices[edge.target]) for edge in document.edges
      )
      for projected, edge in zip(graph.es, document.edges, strict=True):
          projected.update_attributes(_edge_attributes(edge))
      return graph


  def export_graphml(document: CTypeGraph, path: str | Path) -> None:
      to_igraph(document).write_graphml(str(path))
  ```

  Use compact sorted UTF-8 JSON for each `*_json` value. Render aliases and methods one item per line; render sorted tag entries as `key: value`; render each AST path on one line with ` → ` between segments and `(empty path)` for `()`.

- [ ] **Step 4: Add and pass the GraphML read-back test**

  Write to `tmp_path / "types.graphml"`, reload with `ig.Graph.Read_GraphML()`, and assert directedness, names, readable attributes, lossless JSON attributes, AST paths, and edge direction survive.

  Run:

  ```bash
  uv run pytest -q tests/ctype_graph/test_graphml.py
  ```

  Expected: all focused projection and read-back tests pass.

- [ ] **Step 5: Export the new API and format it**

  Export `to_igraph` and `export_graphml` from `ctype_graph/__init__.py`. Then run:

  ```bash
  uvx ruff format src/conftamer/ctype_graph tests/ctype_graph/test_graphml.py
  uv run pytest -q tests/ctype_graph/test_graphml.py tests/ctype_graph/test_io.py
  uvx ty check src/conftamer/ctype_graph tests/ctype_graph
  ```

  Expected: focused tests and type checks pass.

- [ ] **Step 6: Commit the projection checkpoint**

  ```bash
  git add src/conftamer/ctype_graph tests/ctype_graph/test_graphml.py
  git commit -m "feat: export readable CType GraphML"
  ```

---

### Task 3: Replace the Multi-workflow CLI with One Export Command

**Files:**
- Modify: `src/conftamer/cli.py`
- Rewrite: `tests/test_cli.py`

**Interfaces:**
- Consumes: `load_ctype_graph(path)` and `export_graphml(graph, path)`.
- Produces: `conftamer export INPUT.text --output OUTPUT.graphml` and `conftamer.cli:app`.

- [ ] **Step 1: Rewrite CLI tests around the sole public workflow**

  Keep focused tests for:

  ```python
  @pytest.mark.parametrize("arguments", [("--help",), ("export", "--help")])
  def test_help_exposes_only_export(arguments): ...


  @pytest.mark.parametrize("removed", ["build", "stitch", "query"])
  def test_removed_commands_are_absent(removed): ...
  ```

  Add a minimal valid CType input test that invokes `export`, re-reads GraphML, and checks the stdout summary. Add malformed JSON, unrelated JSON, missing file, blocked `.gv`, and blocked `.graphml` cases; each must assert `exit_code != 0`, an `error:` message on stderr, and no output path.

- [ ] **Step 2: Run the CLI tests to verify the old surface fails the new contract**

  Run:

  ```bash
  uv run pytest -q tests/test_cli.py
  ```

  Expected: failures show `build`, `stitch`, and `query` are still exposed and the old dispatch code remains.

- [ ] **Step 3: Replace `cli.py` with thin orchestration**

  Keep only this flow:

  ```python
  @app.command("export")
  def export_command(
      input_path: Annotated[Path, typer.Argument()],
      output: Annotated[Path, typer.Option("--output")],
  ) -> None:
      with _user_errors():
          graph = load_ctype_graph(input_path)
          export_graphml(graph, output)
      _echo_summary(len(graph.nodes), len(graph.edges), output)
  ```

  Keep one `_user_errors()` context manager that catches `OSError`, `UnicodeError`, and `ValueError`, prints `error: ...` to stderr, and exits 1. Keep one summary function that reports singular/plural vertices and edges. Do not retain JSON discriminator dispatch, query helpers, diagnostics, generic graph unions, or imports from deleted domains.

- [ ] **Step 4: Prove invalid input never reaches GraphML writing**

  In the CLI error tests, pre-create no output file and assert it remains absent for every loading/validation failure. This is guaranteed by loading the complete normalized graph before calling `export_graphml`.

  Run:

  ```bash
  uv run pytest -q tests/test_cli.py
  ```

  Expected: every CLI test passes.

- [ ] **Step 5: Verify script and package entry points**

  Run:

  ```bash
  uv run conftamer --help
  uv run conftamer export --help
  uv run python src/conftamer/cli.py --help
  ```

  Expected: each command succeeds, and only `export` is listed at the root.

- [ ] **Step 6: Format and commit the CLI checkpoint**

  ```bash
  uvx ruff format src/conftamer/cli.py tests/test_cli.py
  uv run pytest -q tests/test_cli.py tests/ctype_graph
  uvx ty check src/conftamer/cli.py tests/test_cli.py
  git add src/conftamer/cli.py tests/test_cli.py
  git commit -m "refactor: reduce CLI to CType export"
  ```

---

### Task 4: Move Model Primitives into the CType Domain and Delete Dead Systems

**Files:**
- Modify: `src/conftamer/ctype_graph/models.py`
- Delete: production and test trees listed in the Target File Map
- Modify: `tests/ctype_graph/test_io.py` — pin strict/frozen model behavior before removing shared diagnostics primitives.

**Interfaces:**
- Consumes: passing CType parser, projection, and CLI tests from Tasks 2–3.
- Produces: a self-contained `conftamer.ctype_graph` package with no imports from deleted domains.

- [ ] **Step 1: Pin strict/frozen model behavior before refactoring**

  Ensure `tests/ctype_graph/test_io.py` directly asserts that CType models reject unknown fields, reject mutation, preserve strict strings, enforce canonical collection order, reject dangling endpoints, and freeze nested mappings. Run:

  ```bash
  uv run pytest -q tests/ctype_graph/test_io.py
  ```

  Expected: these preservation tests pass before moving the shared primitives.

- [ ] **Step 2: Make CType models self-contained**

  Replace the import from `conftamer.diagnostics` with local, domain-specific definitions:

  ```python
  NonEmptyString = Annotated[str, Field(strict=True, min_length=1)]


  class CTypeModel(BaseModel):
      model_config = ConfigDict(frozen=True, extra="forbid", strict=True)
  ```

  Make `CTypeNode`, `CTypeEdge`, and `CTypeGraph` inherit `CTypeModel`. Keep the existing small validation helpers instead of folding graph validation into one long function.

- [ ] **Step 3: Delete unrelated production packages**

  Run:

  ```bash
  rm -rf \
    src/conftamer/analysis \
    src/conftamer/appgraph \
    src/conftamer/contexttrack \
    src/conftamer/paramtrack \
    src/conftamer/pmgraph
  rm -f \
    src/conftamer/build.py \
    src/conftamer/diagnostics.py
  ```

  Do not add compatibility import modules.

- [ ] **Step 4: Delete superseded tests after their CType coverage has moved**

  Run:

  ```bash
  rm -rf \
    tests/analysis \
    tests/appgraph \
    tests/contexttrack \
    tests/paramtrack \
    tests/pmgraph
  rm -f tests/test_build.py
  ```

- [ ] **Step 5: Search for stale runtime imports and behavior**

  Run:

  ```bash
  rg -n "conftamer\.(analysis|appgraph|contexttrack|paramtrack|pmgraph|diagnostics)|build_pmgraph|stitch_pmgraphs|find_vertices|influence_subgraph" src tests
  find src/conftamer -name '*.py' -print0 | xargs -0 wc -l
  ```

  Expected: the search has no matches. The line count is at or below 450; if it is above 430, inspect repetition before proceeding, but do not compress validations into opaque expressions.

- [ ] **Step 6: Run the complete reduced test suite**

  ```bash
  uvx ruff format src tests
  uv run pytest -q
  uvx ty check
  ```

  Expected: all remaining parser, GraphML, and CLI tests pass.

- [ ] **Step 7: Commit the deletion checkpoint**

  ```bash
  git add -A src tests
  git commit -m "refactor: remove non-CType graph systems"
  ```

---

### Task 5: Prune Examples and Rewrite User Documentation

**Files:**
- Move: `examples/paramtrack/static/unmarshaler_subgraph.text` → `examples/ctype/unmarshaler_subgraph.text`
- Move: `examples/paramtrack/static/accessors.text` → `examples/ctype/accessors.text`
- Create: `examples/ctype/README.md`
- Modify: `examples/README.md`
- Modify: `README.md`
- Modify: `docs/technical-reference.md`
- Modify: `tests/ctype_graph/test_io.py`
- Modify: `tests/test_cli.py`
- Delete: all other tracked files under `examples/contexttrack/` and `examples/paramtrack/`

**Interfaces:**
- Consumes: the single-command CLI and real graph count assertions.
- Produces: two discoverable executable examples and documentation with copy/paste commands.

- [ ] **Step 1: Move the two source-of-truth artifacts and remove unrelated examples**

  Run:

  ```bash
  mkdir -p examples/ctype
  git mv examples/paramtrack/static/unmarshaler_subgraph.text examples/ctype/
  git mv examples/paramtrack/static/accessors.text examples/ctype/
  git rm -r examples/contexttrack examples/paramtrack
  ```

  The moved `.text` files must remain byte-identical. Record their SHA-256 values before and after the move with `sha256sum` if the executor’s Git tooling does not report pure renames.

- [ ] **Step 2: Update integration paths and prove both real artifacts export**

  Point `EXAMPLES` constants at `examples/ctype`. Parameterize CLI export over:

  ```python
  [
      ("unmarshaler_subgraph.text", 57, 90),
      ("accessors.text", 582, 822),
  ]
  ```

  For each case, invoke the installed Typer app, re-read the output using `ig.Graph.Read_GraphML()`, assert directedness and exact counts, and assert every vertex has `name`, `label`, `aliases`, `methods`, `tags`, `names_json`, `methods_json`, and `tags_json`.

- [ ] **Step 3: Write a small artifact catalog**

  In `examples/ctype/README.md`, record:

  - both artifacts’ producer roles;
  - the inspected producer revision already documented in input formats;
  - the 57/90/58/1 and 582/822/595/13 node/edge/mapping/alias facts;
  - that these are independent one-document JSON files despite the `.text` suffix; and
  - that generated GraphML belongs outside `examples/`.

- [ ] **Step 4: Rewrite the README as a one-screen quickstart**

  Include only installation, the two commands below, output meaning, accepted/rejected input, Python API links, and license:

  ```bash
  uv run conftamer export \
    examples/ctype/unmarshaler_subgraph.text \
    --output /tmp/unmarshaler.graphml

  uv run conftamer export \
    examples/ctype/accessors.text \
    --output /tmp/accessors.graphml
  ```

  Explain that `label`, `aliases`, `methods`, `tags`, and `ast_paths` are for people in Gephi-like tools, while the `*_json` companions preserve nested values without delimiter ambiguity.

- [ ] **Step 5: Rewrite the technical reference around the three public functions**

  Document the raw producer boundary, normalized models, GraphML attributes, CLI errors, and:

  ```python
  from conftamer.ctype_graph import export_graphml, load_ctype_graph, to_igraph

  graph = load_ctype_graph("accessors.text")
  projected = to_igraph(graph)
  export_graphml(graph, "accessors.graphml")
  ```

  State explicitly that GraphML cannot be converted back to the normalized model and that producer GraphML input remains blocked.

- [ ] **Step 6: Run real-data and link-oriented checks**

  ```bash
  uv run pytest -q tests/ctype_graph tests/test_cli.py
  rg -n "examples/(contexttrack|paramtrack)|PMGraph|AppGraph|build|stitch|query" \
    README.md docs examples tests src
  find examples -type f | sort
  git diff --check
  ```

  Expected: stale-surface search has no active claims; only the three focused example files appear under `examples/ctype/` plus `examples/README.md`; tests pass.

- [ ] **Step 7: Commit the user-surface checkpoint**

  ```bash
  git add -A README.md docs/technical-reference.md examples tests
  git commit -m "docs: focus examples on CType exports"
  ```

---

### Task 6: Align Packaging, Release Smoke Tests, and Final Verification

**Files:**
- Modify: `pyproject.toml`
- Modify: `.github/workflows/release.yml`
- Modify only if lock metadata changes: `uv.lock`
- Review without expected changes: `.github/workflows/ci.yml`, `.gitignore`

**Interfaces:**
- Consumes: final single-command package and real examples.
- Produces: release binaries and CI checks that exercise only the supported MVP.

- [ ] **Step 1: Update package metadata without changing dependencies**

  Set the project description to:

  ```toml
  description = "Validate gopls CType artifacts and export readable GraphML"
  ```

  Keep `requires-python = ">=3.13"`, the GPL-2.0-only license, existing dependency versions, and `conftamer = "conftamer.cli:app"`.

- [ ] **Step 2: Replace broad release smoke commands**

  Keep cross-platform PyInstaller construction, metadata validation, checksums, attestation, and publishing unchanged. Replace build/stitch/query fixtures and commands with:

  ```bash
  "$executable" --help
  "$executable" export --help
  "$executable" export \
    examples/ctype/unmarshaler_subgraph.text \
    --output smoke/unmarshaler.graphml
  "$executable" export \
    examples/ctype/accessors.text \
    --output smoke/accessors.graphml
  ```

  Re-read both files in the existing Python smoke block and assert `(vcount, ecount)` equals `(57, 90)` and `(582, 822)`, both graphs are directed, and both expose the human-readable and lossless attributes.

- [ ] **Step 3: Format TOML and validate the lock**

  ```bash
  uvx tombi format pyproject.toml
  uvx tombi format --check pyproject.toml
  uv lock --check
  ```

  Expected: no dependency resolution change. Do not rewrite `uv.lock` if `uv lock --check` succeeds.

- [ ] **Step 4: Run fresh full verification**

  ```bash
  uv run pytest -q tests/ctype_graph
  uv run pytest -q tests/test_cli.py
  uvx ruff format --check src tests
  uvx tombi format --check pyproject.toml
  uvx ty check
  uv run pytest -q

  uv run conftamer --help
  uv run conftamer export --help
  rm -f /tmp/unmarshaler.graphml /tmp/accessors.graphml
  uv run conftamer export \
    examples/ctype/unmarshaler_subgraph.text \
    --output /tmp/unmarshaler.graphml
  uv run conftamer export \
    examples/ctype/accessors.text \
    --output /tmp/accessors.graphml
  uv run python - <<'PY'
  import igraph as ig

  expected = {
      "/tmp/unmarshaler.graphml": (57, 90),
      "/tmp/accessors.graphml": (582, 822),
  }
  for path, counts in expected.items():
      graph = ig.Graph.Read_GraphML(path)
      assert graph.is_directed()
      assert (graph.vcount(), graph.ecount()) == counts
      assert {"name", "label", "aliases", "methods", "tags"} <= set(
          graph.vertex_attributes()
      )
      assert "ast_paths" in graph.edge_attributes()
  PY
  ```

  Expected: every command is freshly successful and both real outputs re-read with exact counts.

- [ ] **Step 5: Verify scope and line count**

  ```bash
  find src/conftamer -name '*.py' -print0 | xargs -0 wc -l
  find src/conftamer tests examples -type f | sort
  rg -n "PMGraph|AppGraph|ContextTrack|ParamTrack CSV|build_pmgraph|stitch_pmgraphs|find_vertices|influence_subgraph" \
    src tests README.md docs examples pyproject.toml .github
  git status --short
  git diff --check
  ```

  Expected: production code is at or below 450 lines and near 400; only intentional historical/non-goal references remain; no generated GraphML, PyInstaller output, cache, or unrelated file is staged.

- [ ] **Step 6: Build and smoke-test the local standalone executable when the platform toolchain is available**

  ```bash
  uv run --group build pyinstaller \
    --clean \
    --noconfirm \
    --onefile \
    --name conftamer \
    --paths src \
    --exclude-module tkinter \
    src/conftamer/cli.py
  ./dist/conftamer export \
    examples/ctype/unmarshaler_subgraph.text \
    --output /tmp/standalone-unmarshaler.graphml
  uv run python - <<'PY'
  import igraph as ig

  graph = ig.Graph.Read_GraphML("/tmp/standalone-unmarshaler.graphml")
  assert graph.is_directed()
  assert (graph.vcount(), graph.ecount()) == (57, 90)
  PY
  ```

  On Windows, invoke `dist/conftamer.exe`; on macOS/Linux, use the command above. If PyInstaller is unavailable on the local platform, record that explicitly and rely on the unchanged release matrix for platform coverage.

- [ ] **Step 7: Review the complete diff and commit**

  ```bash
  git diff --stat HEAD~5..HEAD
  git diff HEAD~5..HEAD -- . ':(exclude)examples/ctype/*.text'
  git status --short --untracked-files=all
  git add pyproject.toml uv.lock .github/workflows/release.yml
  git commit -m "chore: align release with CType MVP"
  ```

  Include `uv.lock` in the commit only if package metadata legitimately changed it.

---

## Final Review Checklist

- [ ] Both real `.text` files parse directly; no fixture-specific parser branches exist.
- [ ] Both exported GraphML files re-read through igraph with exact real counts and direction.
- [ ] Isolates, aliases, tags, methods, grouped AST paths, empty AST paths, and name mappings remain covered.
- [ ] Human-readable attributes and lossless JSON attributes are both present.
- [ ] Invalid or unsupported input fails before output creation.
- [ ] No second input is required or silently merged.
- [ ] No removed command, package, example, documentation claim, or release smoke remains.
- [ ] Production Python is at or below 450 lines; the exact final count is recorded.
- [ ] The complete diff contains no generated GraphML, binary, cache, or unrelated local change.

## Residual Risks to Report

- The parser is grounded in two real producer files and one inspected producer revision; future serializer changes require renewed evidence.
- Producer GraphML input is intentionally unsupported.
- Visualization GraphML is not canonical persistence and is not guaranteed byte-stable across igraph versions.
- Human-readable newline/arrow attributes are presentation aids; the `*_json` fields are the lossless nested representation.
- PyInstaller platform behavior is ultimately verified by the release matrix even when only one platform is available locally.

## Proposed Final Commit Message

```text
refactor: ship a focused CType GraphML MVP

Remove PMGraph, AppGraph, ContextTrack, ParamTrack, stitching, and query
surfaces. Keep strict gopls CType JSON normalization, export one Unmarshaler
or Accessors artifact per invocation, and expose readable plus lossless
GraphML attributes backed by real-artifact smoke tests.
```
