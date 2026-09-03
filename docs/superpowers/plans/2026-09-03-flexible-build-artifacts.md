# Flexible Build Artifacts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let `conftamer build` produce a deterministic PMGraph from every nonempty combination of ContextTrack JSONL, ParamTrack CSV, Unmarshaler CType, and Accessors CType artifacts.

**Architecture:** Treat each supplied file as an independent optional source and compose the semantic fragments that can be justified. ContextTrack contributes message nodes and edges; ParamTrack contributes isolated Parameter nodes after validation by either supplied CType graph and adds Parameter-to-Send edges only for unique ContextTrack method/path matches; CType inputs never contribute CType nodes to PMGraph. Missing partners are recoverable and visible through diagnostics, while a build with no upstream artifacts remains an error because PMGraph v2 requires at least one source.

**Tech Stack:** Python 3.13+, Pydantic v2, Typer, standard-library `csv`/`json`/`hashlib`, pytest, Ruff, ty, uv

**Spec:** `docs/rewrite/architecture.md` (update the contract in Task 1 before implementation; producer facts remain in `docs/rewrite/input-formats.md`)

## Global Constraints

- Keep every artifact option optional, but require at least one of `events`, `paramtrack_csv`, `unmarshaler`, or `accessors`.
- Preserve PMGraph v2 and its source, semantic-ID, evidence, canonical-ordering, and deterministic UTF-8 JSON contracts; do not introduce a schema version change.
- Preserve every supplied artifact's exact-byte SHA-256 source provenance, including CType sources that cannot contribute PMGraph nodes or edges.
- Never copy CType nodes into PMGraph and never accept `.gv`, producer GraphML, hierarchy files, or logs as machine input.
- Validate every contributing ParamTrack row's CType against the union of represented names in whichever Unmarshaler and/or Accessors graphs were supplied.
- A ParamTrack CSV with no CType graph is parsed, retained as a source, and diagnosed per otherwise identity-usable row; it produces no Parameter nodes or edges.
- A supplied CType graph with no ParamTrack CSV is validated, retained as a source, and reported once with `build.ctype_without_paramtrack`; it produces no PMGraph nodes or edges.
- A valid keyed ParamTrack row creates or reuses an observed Parameter node even when its method/path has zero or multiple Send candidates; only a unique Send candidate creates an edge.
- Preserve conservative matching: do not compare ParamTrack `API` with ContextTrack `api_id`, infer hosts, or spread a row across ambiguous sends.
- Keep diagnostics globally sorted and continue emitting diagnostics on stderr and summaries on stdout.
- Add no dependency and do not raise the `>=3.13` Python minimum.
- Keep production Python under the hard 3,300-line review gate (baseline: 3,154 physical lines); simplify touched code if needed.
- Use TDD for behavior changes. Format changed Python files before verification.
- Do not edit sibling repositories or the paper. Do not commit unless the user separately requests it.

## Acceptance Criteria

1. The Python API has this boundary:

   ```python
   def build_pmgraph(
       *,
       module_id: str,
       events: str | Path | None = None,
       paramtrack_csv: str | Path | None = None,
       unmarshaler: str | Path | None = None,
       accessors: str | Path | None = None,
   ) -> BuildResult: ...
   ```

2. All 15 nonempty presence combinations of the four artifact options succeed when the supplied files are valid. The empty combination raises `ValueError("at least one upstream artifact must be provided")` and the CLI writes no output.
3. Every supplied file is loaded and validated even if it cannot contribute semantic nodes or edges. Its exact-byte source is included in the canonical PMGraph source table.
4. ContextTrack semantics are unchanged when `events` is present and absent when it is not.
5. A keyed ParamTrack row contributes Parameter nodes only when at least one supplied CType graph represents its CType. Either graph role is sufficient; both roles are unioned.
6. Validated Parameter nodes survive zero-send and ambiguous-send matching as isolated nodes with merged `observed` CSV evidence. Existing `paramtrack.no_send_candidate` and `paramtrack.ambiguous_send_candidate` diagnostics remain, and no edge is guessed.
7. ParamTrack without CType emits `paramtrack.ctype_validation_unavailable` on each otherwise identity-usable row with message `CType cannot be validated because no CType graph was supplied` and contributes no Parameter semantics.
8. CType without ParamTrack emits one build-level `build.ctype_without_paramtrack` diagnostic with message `CType graphs are retained as sources but cannot contribute PMGraph semantics without ParamTrack CSV`.
9. `build.paramtrack_caller_association` remains present whenever ContextTrack and ParamTrack are supplied together, regardless of whether a row ultimately joins.
10. Canonical output remains deterministic, validates through `PMGraph`, ends in one newline, and remains byte-identical for repeated identical inputs.

## Combination Semantics

Let `E` mean ContextTrack events, `P` ParamTrack CSV, and `C` at least one of Unmarshaler or Accessors.

| Inputs | PMGraph semantics | Required diagnostics |
| --- | --- | --- |
| `E` | Existing message nodes/context edges | Existing ContextTrack diagnostics only |
| `P` | No nodes or edges; CSV source retained | `paramtrack.ctype_validation_unavailable` for each otherwise identity-usable row |
| `C` | Empty graph; CType source(s) retained | One `build.ctype_without_paramtrack` |
| `E + P` | Message fragment only | caller-association plus unavailable-CType row diagnostics |
| `E + C` | Message fragment; CType source(s) retained | One `build.ctype_without_paramtrack` |
| `P + C` | Isolated validated Parameter nodes | Existing zero-Send row diagnostics |
| `E + P + C` | Message and Parameter nodes; edges only for unique method/path sends | caller-association plus normal importer diagnostics |

Supplying both CType roles has the same semantic policy as supplying one: represented names are unioned, but both exact-byte sources are retained. No-artifact input is the only rejected presence combination.

## Expected File Map

- Modify `docs/rewrite/architecture.md`: make artifact composition and the build/CLI signatures normative.
- Modify `docs/rewrite/input-formats.md`: document optional CType validation and isolated Parameter projection without changing producer facts.
- Modify `docs/rewrite/implementation-plan.md`: append the ordered post-rewrite flexible-build checkpoint.
- Modify `src/conftamer/paramtrack/importer.py`: accept zero, one, or two CType graphs and decouple observed Parameter nodes from Send-edge matching.
- Modify `tests/paramtrack/test_importer.py`: drive optional CType validation and isolated-node behavior.
- Modify `src/conftamer/build.py`: independently load and merge each artifact and own build-level missing-partner diagnostics.
- Modify `tests/test_build.py`: exhaustively test all 15 nonempty combinations, the empty rejection, provenance, diagnostics, and real-data behavior.
- Modify `src/conftamer/cli.py`: make `--events` optional and delegate combination validation to `build_pmgraph`.
- Modify `tests/test_cli.py`: prove no-events partial builds and no-artifact rejection through Typer.
- Modify `README.md`: explain flexible build composition and give a parameter-only example.
- Modify `docs/technical-reference.md`: publish the new CLI/Python API and diagnostic policy.
- Modify `examples/README.md`: add an executable real-artifact parameter-only build.
- Modify `.github/workflows/release.yml`: smoke-test the packaged binary without ContextTrack or Unmarshaler.
- No new production module, model, canonical format, dependency, or example input file is needed.

## Assumptions and Risks

- “Any combinations” means every **nonempty** subset. Supporting zero inputs would require weakening PMGraph's nonempty source invariant and is intentionally excluded.
- The caller still supplies `module_id` because Parameter IDs require module ownership even when ContextTrack is absent.
- An isolated Parameter is justified only by a keyed ParamTrack row whose row-level identity/truncation checks pass and whose CType is represented by at least one supplied graph. Missing CType validation is never treated as success.
- Parameter identity remains `(module_id, type, name)`. Equal names from several validated rows or method/path groups merge into one isolated node and union observed evidence, as existing PMGraph identity requires.
- Ambiguous manager builds change compatibly at the schema level but observably at the content level: they retain 226 Parameter nodes while still creating zero Parameter edges.
- CType-only builds are valid but intentionally produce empty PMGraph semantics. The source table and warning make the non-contribution explicit.
- Loading every supplied artifact means an invalid unused CType file is still a file-level error; permissive combinations must not become permissive parsing.
- The 146-line production headroom is narrow. Prefer replacing all-or-none branches and reusing list accumulation over adding orchestration abstractions.

---

### Task 1: Align the normative contracts before code changes

**Files:**
- Modify: `docs/rewrite/architecture.md:48-118, 444-507, 737-750, 797-805`
- Modify: `docs/rewrite/input-formats.md:278-299, 442-455, 484-514`
- Modify: `docs/rewrite/implementation-plan.md:234-265`

**Interfaces:**
- Consumes: the accepted combination table and diagnostics in this plan.
- Produces: the normative `build_pmgraph` signature and projection rules used by Tasks 2-5.

- [ ] **Step 1: Update architecture decisions and data flow**

Replace the all-or-none language with these rules:

```markdown
- Every nonempty combination of ContextTrack, ParamTrack, Unmarshaler, and
  Accessors artifacts is accepted by the build boundary. Every supplied file is
  validated and retained in PMGraph provenance.
- ContextTrack contributes message semantics independently. A validated keyed
  ParamTrack row contributes an observed Parameter node independently, and
  contributes a Parameter -> Send Request edge only after one unique semantic
  method/path match.
- Either supplied CType role may validate a ParamTrack CType; represented names
  are unioned when both are supplied. Without a CType graph, keyed rows are
  diagnosed and omitted rather than trusted.
- CType inputs without ParamTrack remain CTypeGraph validation/provenance inputs;
  CType nodes are never inserted into PMGraph.
```

Update the data-flow diagram so the ContextTrack and ParamTrack branches are independently optional and converge at `make_pmgraph`. State explicitly that a source may be retained without being referenced by node/edge evidence when the supplied artifact has no PMGraph projection.

- [ ] **Step 2: Update ParamTrack enrichment and build boundary**

Document that eligible row keys create observed Parameter nodes before Send matching, while edge creation still requires exactly one candidate. Replace the build signature and contract with:

```python
def build_pmgraph(
    *,
    module_id: str,
    events: str | Path | None = None,
    paramtrack_csv: str | Path | None = None,
    unmarshaler: str | Path | None = None,
    accessors: str | Path | None = None,
) -> BuildResult: ...
```

Add the exact empty-input error and diagnostic codes/messages from Acceptance Criteria 7-9. Preserve the caller-assertion warning for `events + paramtrack_csv` and the rule that module identity never rewrites CType identifiers.

- [ ] **Step 3: Update the CLI contract and known behavior**

Use this synopsis:

```text
conftamer build --module-id MODULE
    [--events EVENTS.jsonl]
    [--paramtrack-csv PARAMETERS.csv]
    [--unmarshaler UNMARSHALER.text]
    [--accessors ACCESSORS.text]
    --output MODULE.pmgraph.json
```

State that at least one bracketed artifact option is required, all supplied inputs are validated, and recoverable non-contribution is diagnosed. Keep the existing blocked GraphML and no-CType-nodes boundaries unchanged.

- [ ] **Step 4: Align input policy without changing producer claims**

In `input-formats.md`, distinguish three downstream phases for a parsed ParamTrack row:

```text
parse row -> validate row labels and CType against supplied graph roles
          -> create observed Parameter nodes for valid keys
          -> optionally create edges after unique Send matching
```

Document `paramtrack.ctype_validation_unavailable` for no supplied graph, union validation for one or both roles, and update the broad-manager smoke expectation to 226 retained Parameters plus zero Parameter edges against 47 ambiguous sends.

- [ ] **Step 5: Append the ordered implementation checkpoint**

Add a new unchecked section after the completed rewrite tasks in `implementation-plan.md` titled `12. Accept flexible build artifact combinations`. List the contract, ParamTrack, build, CLI, documentation, real-data, deterministic-output, and 3,300-line checks from this plan, with checkpoint subject:

```text
feat: compose PMGraphs from partial upstream artifacts
```

Do not reopen or rewrite the historical completion records for tasks 1-11.

- [ ] **Step 6: Validate the documentation-only change**

Run:

```bash
if rg -n "all-or-none|all three|events are required|requires a ContextTrack|must all be provided" \
  docs/rewrite/architecture.md docs/rewrite/input-formats.md; then
  echo "stale normative build contract found" >&2
  exit 1
fi
rg -n "ctype_validation_unavailable|ctype_without_paramtrack|at least one upstream" \
  docs/rewrite/architecture.md docs/rewrite/input-formats.md docs/rewrite/implementation-plan.md
uv run python - <<'PY'
from pathlib import Path

for path in (
    Path("docs/rewrite/architecture.md"),
    Path("docs/rewrite/input-formats.md"),
    Path("docs/rewrite/implementation-plan.md"),
):
    for target in path.parent.glob("*.md"):
        assert target.exists()
print("rewrite documents readable")
PY
git diff --check
```

Expected: stale all-or-none wording is absent from `architecture.md` and `input-formats.md`; the new diagnostic names occur in the architecture/input policy; all commands exit zero. The implementation plan retains its explicitly historical task-7 statement and supersedes it in task 12. User-facing stale wording may remain in README/reference/examples until Task 5.

- [ ] **Step 7: Review checkpoint**

Inspect `git diff -- docs/rewrite` and confirm the contracts explicitly cover all seven rows in the Combination Semantics table before changing Python.

---

### Task 2: Decouple observed ParamTrack nodes from optional Send matching

**Files:**
- Modify: `tests/paramtrack/test_importer.py:67-81, 160-270, 299-322`
- Modify: `src/conftamer/paramtrack/importer.py:24-61, 130-250`

**Interfaces:**
- Consumes: optional CType roles and isolated-Parameter policy from Task 1.
- Produces:

  ```python
  def import_paramtrack(
      path: str | Path,
      *,
      module_id: str,
      send_requests: Iterable[SendRequestNode] = (),
      unmarshaler: CTypeGraph | None = None,
      accessors: CTypeGraph | None = None,
  ) -> ParamTrackResult: ...
  ```

  `ParamTrackResult.nodes` contains all valid observed keyed Parameters; `edges` contains only unique-Send joins.

- [ ] **Step 1: Stop the test helper from inventing empty CType graphs**

Change `import_csv` to forward optional roles exactly:

```python
def import_csv(
    path: Path,
    sends: tuple[SendRequestNode, ...] = (),
    *,
    unmarshaler: CTypeGraph | None = None,
    accessors: CTypeGraph | None = None,
):
    return import_paramtrack(
        path,
        module_id=MODULE,
        send_requests=sends,
        unmarshaler=unmarshaler,
        accessors=accessors,
    )
```

This ensures tests can distinguish “no graph supplied” from “an explicitly supplied empty graph.”

- [ ] **Step 2: Write failing tests for zero/one/two CType roles**

Add these focused cases:

```python
@pytest.mark.parametrize(
    ("use_unmarshaler", "use_accessors"),
    [(True, False), (False, True)],
)
def test_either_ctype_role_can_validate_isolated_parameters(
    tmp_path, use_unmarshaler, use_accessors
):
    path = write_csv(tmp_path, HEADER + "api,GET,/items,/Type,timeout\n")
    result = import_csv(
        path,
        unmarshaler=ctype_graph("/Type") if use_unmarshaler else None,
        accessors=ctype_graph("/Type") if use_accessors else None,
    )

    assert {node.name for node in result.nodes} == {"timeout"}
    assert result.edges == ()
    assert [item.code for item in result.diagnostics] == [
        "paramtrack.no_send_candidate"
    ]


def test_missing_ctype_validation_omits_parameters_with_line_diagnostic(tmp_path):
    path = write_csv(tmp_path, HEADER + "api,GET,/items,/Type,timeout\n")

    result = import_csv(path, (send_request("GET", "/items"),))

    assert result.records[0].ctype == "/Type"
    assert result.nodes == ()
    assert result.edges == ()
    assert [(item.line, item.code, item.message) for item in result.diagnostics] == [
        (
            2,
            "paramtrack.ctype_validation_unavailable",
            "CType cannot be validated because no CType graph was supplied",
        )
    ]
```

An explicitly supplied empty graph must continue to produce `paramtrack.unknown_ctype`, not `ctype_validation_unavailable`.

- [ ] **Step 3: Change the existing zero/ambiguous-candidate expectation**

Keep the four existing row diagnostics and edge assertion, but replace the empty-node assertion with:

```python
assert {node.name for node in result.nodes} == {
    "no-candidate-a",
    "no-candidate-b",
    "ambiguous-a",
    "ambiguous-b",
}
assert result.edges == ()
for node in result.nodes:
    assert evidence_records(node, "observed") in {
        ("line:2",),
        ("line:3",),
        ("line:4",),
        ("line:5",),
    }
```

This is the direct regression for the user-selected isolated-Parameter behavior.

- [ ] **Step 4: Run the focused tests and observe the expected failures**

Run:

```bash
uv run pytest -q \
  tests/paramtrack/test_importer.py::test_either_ctype_role_can_validate_isolated_parameters \
  tests/paramtrack/test_importer.py::test_missing_ctype_validation_omits_parameters_with_line_diagnostic \
  tests/paramtrack/test_importer.py::test_zero_and_several_send_candidates_are_diagnosed_for_each_row
```

Expected: fail because `import_paramtrack` still requires both graph arguments and currently creates nodes only after unique matching.

- [ ] **Step 5: Make CType roles and Send candidates optional**

Change the importer boundary exactly as published above. Build the represented-name set without substituting fake graphs:

```python
ctype_graphs = tuple(
    graph for graph in (unmarshaler, accessors) if graph is not None
)
represented = (
    set().union(*(graph.name_to_node.keys() for graph in ctype_graphs))
    if ctype_graphs
    else None
)
```

Pass `represented: set[str] | None` into `_eligible_records`. Validate `record.ctype` in this order so independent row errors remain visible:

```python
if not record.ctype:
    diagnostics.append(
        _diagnostic(
            source_name,
            record.input_line,
            "paramtrack.empty_ctype",
            "CType is empty",
        )
    )
    usable = False
elif represented is None:
    diagnostics.append(
        _diagnostic(
            source_name,
            record.input_line,
            "paramtrack.ctype_validation_unavailable",
            "CType cannot be validated because no CType graph was supplied",
        )
    )
    usable = False
elif record.ctype not in represented:
    diagnostics.append(
        _diagnostic(
            source_name,
            record.input_line,
            "paramtrack.unknown_ctype",
            f"CType {record.ctype!r} is not represented",
        )
    )
    usable = False
```

Keep existing empty-Verb, truncation, empty-key, and no-key behavior.

- [ ] **Step 6: Project nodes before matching and edges after matching**

Replace the combined `_join_records` node/edge accumulation with two linear helpers. Node evidence must include every eligible row carrying that key:

```python
def _parameter_nodes(
    records_by_message: dict[ParamMessageKey, list[ParamTrackRecord]],
    module_id: str,
    source: SourceArtifact,
) -> list[ParameterNode]:
    lines_by_name: dict[str, set[int]] = {}
    for records in records_by_message.values():
        for record in records:
            for name in record.keys:
                lines_by_name.setdefault(name, set()).add(record.input_line)
    return [
        ParameterNode(
            id=make_node_id(module_id, {"type": "Parameter", "name": name}),
            evidence=(
                EvidenceRef(
                    source_id=source.id,
                    records=tuple(f"line:{line}" for line in sorted(lines)),
                    derivation="observed",
                ),
            ),
            name=name,
        )
        for name, lines in sorted(lines_by_name.items())
    ]
```

Use a separate edge helper so zero or several candidates skip only edges, not nodes:

```python
def _parameter_edges(
    records_by_message: dict[ParamMessageKey, list[ParamTrackRecord]],
    module_id: str,
    source: SourceArtifact,
    source_name: str,
    send_requests: Iterable[SendRequestNode],
    diagnostics: list[Diagnostic],
) -> list[PMEdge]:
    sends_by_message: dict[ParamMessageKey, dict[str, SendRequestNode]] = {}
    for request in send_requests:
        key = ParamMessageKey(request.method, request.path)
        sends_by_message.setdefault(key, {})[request.id] = request

    edges = []
    for message_key, records in sorted(records_by_message.items()):
        candidates = tuple(sends_by_message.get(message_key, {}).values())
        if len(candidates) != 1:
            diagnostics.extend(
                _match_diagnostic(
                    source_name,
                    message_key,
                    record.input_line,
                    len(candidates),
                )
                for record in records
            )
            continue
        lines_by_name: dict[str, set[int]] = {}
        for record in records:
            for name in record.keys:
                lines_by_name.setdefault(name, set()).add(record.input_line)
        for name, lines in sorted(lines_by_name.items()):
            edges.append(
                PMEdge(
                    source=make_node_id(
                        module_id,
                        {"type": "Parameter", "name": name},
                    ),
                    target=candidates[0].id,
                    evidence=(
                        EvidenceRef(
                            source_id=source.id,
                            records=tuple(
                                f"line:{line}" for line in sorted(lines)
                            ),
                            derivation="paramtrack-unique-method-path",
                        ),
                    ),
                )
            )
    return edges
```

Call `_parameter_nodes` and `_parameter_edges` from `import_paramtrack`, then preserve the existing canonical node/edge sorting in `ParamTrackResult`.

- [ ] **Step 7: Run importer tests**

Run:

```bash
uv run pytest -q tests/paramtrack/test_importer.py
```

Expected: all tests pass; real target/manager fixture counts remain 108/226 nodes and edges under unique matching.

- [ ] **Step 8: Format and record the line budget**

Run:

```bash
uvx ruff format src/conftamer/paramtrack/importer.py tests/paramtrack/test_importer.py
uvx ruff format --check src/conftamer/paramtrack/importer.py tests/paramtrack/test_importer.py
find src/conftamer -name '*.py' -print0 | xargs -0 wc -l
git diff --check
```

Expected: formatting passes and total production Python remains below 3,300 lines.

- [ ] **Step 9: Review checkpoint**

Inspect the importer diff and verify observed Parameter evidence is independent of match cardinality, while edge evidence and diagnostics still depend on exact unique method/path matching.

---

### Task 3: Compose PMGraphs from all nonempty artifact combinations

**Files:**
- Modify: `tests/test_build.py:66-111, 113-232, 269-363`
- Modify: `src/conftamer/build.py:23-81`

**Interfaces:**
- Consumes: the optional `import_paramtrack` interface from Task 2.
- Produces: the optional `build_pmgraph` signature in Acceptance Criterion 1 and canonical source/fragment composition for the CLI.

- [ ] **Step 1: Write the exhaustive combination test**

Import `itertools.product` and add one parametrized test over all nonempty boolean combinations:

```python
from itertools import product


ARTIFACT_COMBINATIONS = [
    combination
    for combination in product((False, True), repeat=4)
    if any(combination)
]


@pytest.mark.parametrize(
    ("has_events", "has_csv", "has_unmarshaler", "has_accessors"),
    ARTIFACT_COMBINATIONS,
)
def test_build_accepts_every_nonempty_artifact_combination(
    tmp_path, has_events, has_csv, has_unmarshaler, has_accessors
):
    events = write_events(tmp_path, [request_sent()])
    parameters = write_csv(tmp_path, "agent,GET,/items,/Type,timeout\n")
    unmarshaler = write_ctype(tmp_path / "unmarshaler.text", "/Type", "/US")
    accessors = write_ctype(tmp_path / "accessors.text", "/Type", "/Accessors")

    result = build_pmgraph(
        module_id=MODULE,
        events=events if has_events else None,
        paramtrack_csv=parameters if has_csv else None,
        unmarshaler=unmarshaler if has_unmarshaler else None,
        accessors=accessors if has_accessors else None,
    )

    has_ctype = has_unmarshaler or has_accessors
    assert len(result.graph.sources) == sum(
        (has_events, has_csv, has_unmarshaler, has_accessors)
    )
    assert sum(isinstance(node, SendRequestNode) for node in result.graph.nodes) == int(
        has_events
    )
    assert sum(isinstance(node, ParameterNode) for node in result.graph.nodes) == int(
        has_csv and has_ctype
    )
    assert len(result.graph.edges) == int(has_events and has_csv and has_ctype)

    codes = [item.code for item in result.diagnostics]
    assert ("build.paramtrack_caller_association" in codes) == (
        has_events and has_csv
    )
    assert ("paramtrack.ctype_validation_unavailable" in codes) == (
        has_csv and not has_ctype
    )
    assert ("paramtrack.no_send_candidate" in codes) == (
        has_csv and has_ctype and not has_events
    )
    assert ("build.ctype_without_paramtrack" in codes) == (
        has_ctype and not has_csv
    )
```

The two CType fixture documents intentionally differ so their exact-byte source IDs remain distinct when both are supplied.

- [ ] **Step 2: Write empty-input and provenance tests**

Add:

```python
def test_build_requires_at_least_one_upstream_artifact():
    with pytest.raises(ValueError, match="at least one upstream artifact"):
        build_pmgraph(module_id=MODULE)


def test_ctype_only_build_retains_exact_sources_and_has_no_semantics(tmp_path):
    accessors = write_ctype(tmp_path / "accessors.text", "/Type")

    result = build_pmgraph(module_id=MODULE, accessors=accessors)

    assert result.graph.nodes == ()
    assert result.graph.edges == ()
    assert result.graph.sources[0].id == (
        f"sha256:{hashlib.sha256(accessors.read_bytes()).hexdigest()}"
    )
    assert [item.code for item in result.diagnostics] == [
        "build.ctype_without_paramtrack"
    ]
```

Retain the existing exact-byte CType loading race regression and enriched deterministic-output test.

- [ ] **Step 3: Update the broad-manager build regression**

Rename `test_manager_build_omits_parameters_for_47_ambiguous_sends` to `test_manager_build_retains_parameters_but_omits_edges_for_47_ambiguous_sends`. Assert:

```python
assert len(candidates) == 47
assert sum(isinstance(node, ParameterNode) for node in result.graph.nodes) == 226
assert not any(
    reference.derivation == "paramtrack-unique-method-path"
    for edge in result.graph.edges
    for reference in edge.evidence
)
assert [item.line for item in ambiguity] == [2, 3, 4, 5]
```

This keeps conservative ambiguity while preserving independently observed Parameters.

- [ ] **Step 4: Run the focused tests and observe failure**

Run:

```bash
uv run pytest -q \
  tests/test_build.py::test_build_accepts_every_nonempty_artifact_combination \
  tests/test_build.py::test_build_requires_at_least_one_upstream_artifact \
  tests/test_build.py::test_ctype_only_build_retains_exact_sources_and_has_no_semantics \
  tests/test_build.py::test_manager_build_retains_parameters_but_omits_edges_for_47_ambiguous_sends
```

Expected: fail because `events` is required and partial enrichment is rejected.

- [ ] **Step 5: Replace all-or-none orchestration with independent accumulation**

Use the published optional signature and begin with:

```python
artifacts = (events, paramtrack_csv, unmarshaler, accessors)
if not any(path is not None for path in artifacts):
    raise ValueError("at least one upstream artifact must be provided")

sources: list[SourceArtifact] = []
nodes = []
edges = []
diagnostics: list[Diagnostic] = []
```

When `events` is present, call `import_contexttrack`, then extend all four accumulators from its graph/result. When each CType role is present, call `_load_ctype` independently, retain both its `CTypeGraph` for optional validation and its `SourceArtifact` for output provenance.

When `paramtrack_csv` is present, call:

```python
parameters = import_paramtrack(
    paramtrack_csv,
    module_id=module_id,
    send_requests=(
        node for node in nodes if isinstance(node, SendRequestNode)
    ),
    unmarshaler=unmarshaler_graph,
    accessors=accessors_graph,
)
```

Extend sources, nodes, edges, and diagnostics from `parameters`. Do not special-case away CSV parsing when graphs or events are absent.

- [ ] **Step 6: Add exact build-level diagnostics**

Append `build.paramtrack_caller_association` whenever both `events` and `paramtrack_csv` are present. Append this diagnostic once whenever at least one CType role is present and `paramtrack_csv` is absent:

```python
Diagnostic(
    source=None,
    line=None,
    code="build.ctype_without_paramtrack",
    message=(
        "CType graphs are retained as sources but cannot contribute PMGraph "
        "semantics without ParamTrack CSV"
    ),
)
```

Finish every successful path through one canonical merge:

```python
return BuildResult(
    graph=make_pmgraph(
        module_id=module_id,
        sources=sources,
        nodes=nodes,
        edges=edges,
    ),
    diagnostics=sort_diagnostics(diagnostics),
)
```

This ensures all combinations receive the same deduplication, validation, and ordering.

- [ ] **Step 7: Run all build and PMGraph tests**

Run:

```bash
uv run pytest -q tests/test_build.py tests/pmgraph
```

Expected: all tests pass, including target-scraper 108-edge and manager 226-edge unique-match integrations; the broad manager integration retains 226 isolated Parameters and zero parameter edges.

- [ ] **Step 8: Verify deterministic serialization for partial builds**

Add a byte-level assertion to the parameter-only combination path or a focused test:

```python
first = build_pmgraph(
    module_id=MODULE,
    paramtrack_csv=parameters,
    accessors=accessors,
)
second = build_pmgraph(
    module_id=MODULE,
    paramtrack_csv=parameters,
    accessors=accessors,
)
first_path = tmp_path / "first.pmgraph.json"
second_path = tmp_path / "second.pmgraph.json"
write_pmgraph(first.graph, first_path)
write_pmgraph(second.graph, second_path)
assert first_path.read_bytes() == second_path.read_bytes()
assert first_path.read_bytes().endswith(b"\n")
assert load_pmgraph(first_path) == first.graph
```

Run the new test and expect PASS.

- [ ] **Step 9: Format and record the line budget**

Run:

```bash
uvx ruff format src/conftamer/build.py tests/test_build.py
uvx ruff format --check src/conftamer/build.py tests/test_build.py
find src/conftamer -name '*.py' -print0 | xargs -0 wc -l
git diff --check
```

Expected: total production Python remains below 3,300 lines.

- [ ] **Step 10: Review checkpoint**

Inspect `git diff -- src/conftamer/build.py tests/test_build.py` and match every tested combination to the Combination Semantics table. Confirm every supplied path is read and validated rather than merely accepted syntactically.

---

### Task 4: Expose flexible artifact composition through Typer

**Files:**
- Modify: `tests/test_cli.py:241-350`
- Modify: `src/conftamer/cli.py:34-61`

**Interfaces:**
- Consumes: optional `build_pmgraph` from Task 3.
- Produces: `conftamer build` with optional `--events`, `--paramtrack-csv`, `--unmarshaler`, and `--accessors`, plus required `--module-id`/`--output`.

- [ ] **Step 1: Replace partial-option rejection tests with no-artifact rejection**

Delete `test_build_rejects_partial_enrichment_options` and add:

```python
def test_build_rejects_no_upstream_artifacts_without_writing_output(tmp_path):
    output = tmp_path / "empty.pmgraph.json"

    result = invoke(
        "build",
        "--module-id",
        "example.org/service",
        "--output",
        str(output),
    )

    assert result.exit_code != 0
    assert "at least one upstream artifact must be provided" in result.output
    assert not output.exists()
```

- [ ] **Step 2: Add a CLI regression for omitted events and one CType role**

Add:

```python
def test_build_accepts_parameter_csv_and_one_ctype_without_events(tmp_path):
    parameters = tmp_path / "parameters.csv"
    parameters.write_text(
        "API,Verb,Resource,CType,Param key\n"
        "agent,GET,/items/1,/Type,timeout\n",
        encoding="utf-8",
    )
    accessors = tmp_path / "accessors.text"
    accessors.write_text(
        json.dumps(
            {
                "Edges": [],
                "Vertices": [{"Names": ["/Type"], "Methods": [], "Tags": None}],
                "List": {"/Type": "/Type"},
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "parameters.pmgraph.json"

    result = invoke(
        "build",
        "--module-id",
        "example.org/service",
        "--paramtrack-csv",
        str(parameters),
        "--accessors",
        str(accessors),
        "--output",
        str(output),
    )

    assert result.exit_code == 0, result.output
    graph = load_pmgraph(output)
    assert [node.name for node in graph.nodes if isinstance(node, ParameterNode)] == [
        "timeout"
    ]
    assert graph.edges == ()
    assert "paramtrack.no_send_candidate" in result.stderr
```

This command omits both `--events` and `--unmarshaler`, proving the public CLI reaches the new API path.

- [ ] **Step 3: Run CLI tests and observe expected failures**

Run:

```bash
uv run pytest -q \
  tests/test_cli.py::test_build_rejects_no_upstream_artifacts_without_writing_output \
  tests/test_cli.py::test_build_accepts_parameter_csv_and_one_ctype_without_events
```

Expected: Typer rejects the missing required `--events` option before `build_pmgraph` runs.

- [ ] **Step 4: Make events optional and remove duplicate combination policy**

Change only the option declaration and delete the all-or-none block:

```python
def build(
    module_id: Annotated[str, typer.Option("--module-id")],
    output: Annotated[Path, typer.Option("--output")],
    events: Annotated[Path | None, typer.Option("--events")] = None,
    paramtrack_csv: Annotated[Path | None, typer.Option("--paramtrack-csv")] = None,
    unmarshaler: Annotated[Path | None, typer.Option("--unmarshaler")] = None,
    accessors: Annotated[Path | None, typer.Option("--accessors")] = None,
) -> None:
```

Continue forwarding all values unchanged inside `_user_errors`. Keep the CLI thin: `build_pmgraph` owns the one-or-more policy and all build diagnostics.

- [ ] **Step 5: Run build CLI tests and help**

Run:

```bash
uv run pytest -q tests/test_cli.py -k 'build or help'
uv run conftamer build --help
```

Expected: all selected tests pass; help shows all four artifact options as optional and still shows `--module-id` and `--output` as required.

- [ ] **Step 6: Format and record the line budget**

Run:

```bash
uvx ruff format src/conftamer/cli.py tests/test_cli.py
uvx ruff format --check src/conftamer/cli.py tests/test_cli.py
find src/conftamer -name '*.py' -print0 | xargs -0 wc -l
git diff --check
```

Expected: total production Python remains below 3,300 lines.

- [ ] **Step 7: Review checkpoint**

Inspect the CLI diff and confirm it contains no artifact-combination branching beyond forwarding optional paths and translating API exceptions to user-facing errors.

---

### Task 5: Publish and smoke-test the new workflow

**Files:**
- Modify: `README.md:1-81, 133-141`
- Modify: `docs/technical-reference.md:17-96, 157-177, 231-242`
- Modify: `examples/README.md:20-80`
- Modify: `.github/workflows/release.yml:147-210`

**Interfaces:**
- Consumes: the completed CLI behavior from Task 4.
- Produces: current-release documentation and a packaged-binary smoke test for a partial artifact combination.

- [ ] **Step 1: Update the README workflow table and build guide**

Change the build input summary to “Any nonempty combination of ContextTrack JSONL, ParamTrack CSV, and one or both CType graphs.” Replace message-only/enriched-only language with the new synopsis and a concise policy table derived from Combination Semantics.

Keep the full enriched example, then add this real parameter-only example:

```bash
uv run conftamer build \
  --module-id github.com/prometheus/prometheus \
  --paramtrack-csv examples/paramtrack/runs/target-scraper-all/parameters.csv \
  --accessors examples/paramtrack/static/accessors.text \
  --output /tmp/prometheus-parameters.pmgraph.json
```

Explain that it produces 108 isolated Parameters and zero edges because no Send Requests are available. Explain that the warning is intentional, and that adding matching events permits unique Parameter-to-Send edges.

- [ ] **Step 2: Update the technical reference API and diagnostics**

Publish the optional CLI synopsis and Python call:

```python
result = build_pmgraph(
    module_id="example.org/service",
    paramtrack_csv="parameters.csv",
    accessors="accessors.text",
)
```

Document:

- at least one artifact is required;
- every supplied artifact is validated and represented in source provenance;
- either CType role validates represented names and both roles are unioned;
- isolated Parameters survive no/ambiguous Send matching;
- `paramtrack.ctype_validation_unavailable` and `build.ctype_without_paramtrack` are recoverable warnings;
- invalid supplied files remain errors; and
- caller-association remains heuristic only when ContextTrack and ParamTrack are both supplied.

- [ ] **Step 3: Add the executable example-catalog workflow**

Add the same parameter-only command to `examples/README.md` immediately before the full enriched build. State the expected 108 isolated nodes, no edges, and `paramtrack.no_send_candidate` diagnostics. Do not add generated output to `examples/`.

- [ ] **Step 4: Extend the packaged release smoke test**

After the full enriched build, run the packaged executable with the partial combination:

```bash
"$executable" build \
  --module-id github.com/prometheus/prometheus \
  --paramtrack-csv examples/paramtrack/runs/target-scraper-all/parameters.csv \
  --accessors examples/paramtrack/static/accessors.text \
  --output smoke/parameters-only.pmgraph.json
```

Load and assert it in the existing Python smoke block:

```python
parameters_only = load_pmgraph("smoke/parameters-only.pmgraph.json")
assert len(parameters_only.nodes) == 108
assert parameters_only.edges == ()
assert {source.kind for source in parameters_only.sources} == {
    "paramtrack-csv",
    "ctype-graph",
}
```

This one command proves the frozen binary accepts missing events and one missing CType role while preserving canonical output.

- [ ] **Step 5: Search for stale public-contract wording**

Run:

```bash
if rg -n "all-or-none|all three|events are required|requires a ContextTrack|must all be provided|Add .* together" \
  README.md docs/technical-reference.md examples/README.md \
  docs/rewrite/architecture.md docs/rewrite/input-formats.md src tests .github \
  --glob '*.md' --glob '*.py' --glob '*.yml'; then
  echo "stale public build contract found" >&2
  exit 1
fi
```

Expected: no stale statement claims ContextTrack is mandatory or the enrichment options are all-or-none. Historical prose in the dated plan may describe the old checkpoint only if it is explicitly marked superseded by task 12.

- [ ] **Step 6: Run focused real-data and CLI smoke tests**

Run:

```bash
tmpdir="$(mktemp -d)"
uv run conftamer build \
  --module-id github.com/prometheus/prometheus \
  --paramtrack-csv examples/paramtrack/runs/target-scraper-all/parameters.csv \
  --accessors examples/paramtrack/static/accessors.text \
  --output "$tmpdir/parameters-only.pmgraph.json"
uv run conftamer build \
  --module-id github.com/prometheus/prometheus \
  --events examples/contexttrack/prometheus/scrape-ok.jsonl \
  --paramtrack-csv examples/paramtrack/runs/target-scraper-all/parameters.csv \
  --accessors examples/paramtrack/static/accessors.text \
  --output "$tmpdir/one-ctype-enriched.pmgraph.json"
uv run conftamer build \
  --module-id github.com/prometheus/prometheus \
  --accessors examples/paramtrack/static/accessors.text \
  --output "$tmpdir/ctype-only.pmgraph.json"
OUTPUT_DIR="$tmpdir" uv run python - <<'PY'
import os
from pathlib import Path

from conftamer.pmgraph import load_pmgraph

root = Path(os.environ["OUTPUT_DIR"])
parameters = load_pmgraph(root / "parameters-only.pmgraph.json")
enriched = load_pmgraph(root / "one-ctype-enriched.pmgraph.json")
ctype_only = load_pmgraph(root / "ctype-only.pmgraph.json")
assert len(parameters.nodes) == 108 and parameters.edges == ()
assert len(enriched.edges) == 109
assert ctype_only.nodes == () and ctype_only.edges == ()
print("partial build smoke tests passed")
PY
```

Expected: all commands exit zero, diagnostics are visible on stderr, and all three outputs validate through the canonical model.

- [ ] **Step 7: Run fresh full verification**

Run every command freshly after the final edit:

```bash
uv run pytest -q tests/paramtrack tests/ctype_graph
uv run pytest -q tests/contexttrack tests/pmgraph tests/test_build.py
uv run pytest -q tests/appgraph tests/analysis tests/test_cli.py
uvx ruff format --check src tests
uvx tombi format --check pyproject.toml
uvx ty check
uv run pytest -q

uv run conftamer --help
uv run conftamer build --help
uv run conftamer stitch --help
uv run conftamer query --help
uv run conftamer export --help

find src/conftamer -name '*.py' -print0 | xargs -0 wc -l
git diff --check
git status --short
```

Expected: every check exits zero, the full suite passes, CLI help is available, and production Python is below 3,300 physical lines.

- [ ] **Step 8: Inspect the complete diff and residual compatibility impact**

Run:

```bash
git diff --stat
git diff -- docs/rewrite src/conftamer tests README.md docs/technical-reference.md \
  examples/README.md .github/workflows/release.yml
git ls-files --others --exclude-standard
```

Confirm there are no generated canonical/GraphML outputs, stale all-or-none tests, unrelated edits, or untracked artifacts. Record in the completion report that partial combinations now succeed, unmatched ParamTrack rows now retain isolated nodes, and no canonical schema changed.

## Completion Report Requirements

Report:

- each changed file and its purpose;
- the exact fresh verification commands and results;
- final production Python line count;
- successful real-data commands for parameter-only, one-CType enriched, and CType-only builds;
- packaged CLI smoke-test availability (workflow updated, but hosted matrix execution unavailable locally unless actually run);
- compatibility impact: optional API/CLI artifacts and retained isolated Parameters for zero/ambiguous Send matches;
- residual risks: caller-supplied module ownership, no verifiable cross-producer run identity, CType-only empty semantics, and blocked producer GraphML;
- warnings or incomplete behavior; and
- proposed commit message (do not commit):

  ```text
  feat: compose PMGraphs from partial upstream artifacts

  Accept every nonempty combination of ContextTrack, ParamTrack, and CType
  inputs while preserving source provenance and conservative matching. Retain
  validated ParamTrack keys as isolated Parameters when no unique Send exists,
  and document recoverable missing-partner diagnostics.
  ```
