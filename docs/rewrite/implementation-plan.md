# ConfTamer rewrite implementation plan

> Execute tasks in order. Use test-driven development and review each checkpoint
> before beginning the next task.

**Goal:** implement the target described in [Architecture](architecture.md)
against the producer evidence in [Input formats](input-formats.md) and the real
files under [`examples/`](../examples/).

## Execution rules

- Rewrite `AGENTS.md` before source changes so later work follows the target
  architecture rather than legacy CSV/PMGraph v1 guidance.
- Keep production Python under 3,000 physical lines; record the cumulative
  count at every checkpoint and simplify before adding abstractions.
- Write a failing focused test before each behavior change.
- Run focused checks first, then fresh full verification before each commit.
- Treat examples as executable source-of-truth integration inputs. Unit tests
  should use the smallest explicit representation of an observed shape.
- Stop rather than guessing if an input contradicts the documented evidence.
  If GraphML producer artifacts are absent, mark task 5 deferred and continue
  with task 6; the deferred task is not a release blocker.
- Do not edit sibling repositories or the paper.

## 1. Align repository guidance

**Files:** `AGENTS.md`, `docs/architecture.md`, `docs/input-formats.md`,
`docs/implementation-plan.md`

- [ ] Rewrite `AGENTS.md` for the graph-compiler architecture and 3,000-line
  gate; distinguish targeted ParamTrack CSV from removed edge CSV.
- [ ] Review the split documents against every checked-in example and current
  upstream serializer.
- [ ] Confirm target formats define every discriminator, validator, identity
  payload, evidence rule, and deterministic ordering rule.
- [ ] Confirm observed fields are never presented as target-owned guarantees.
- [ ] Add only focused minimal fixtures needed to express real shapes.
- [ ] Review contracts before touching `src/`.

**Checkpoint:** `docs: align graph compiler contracts with upstream output`

## 2. Add diagnostics and PMGraph v2

**Files:** `src/conftamer/diagnostics.py`,
`src/conftamer/pmgraph/{__init__.py,models.py,io.py}`,
`tests/pmgraph/{test_models.py,test_io.py}`

- [ ] Test every complete node shape, including schema-only Behavior.
- [ ] Test Parameter-to-Send Request and Receive-to-Send edges.
- [ ] Test IDs, status bounds, duplicates, endpoints, self-edges, source tables,
  and dangling evidence.
- [ ] Add fixed vectors proving semantic node IDs exclude evidence and preserve
  the existing hash algorithm.
- [ ] Implement immutable models, evidence merging, validation, normalization,
  and deterministic newline-terminated JSON.
- [ ] Prove byte-identical output from shuffled semantic inputs.

**Checkpoint:** `feat: define canonical PMGraph v2`

## 3. Import ContextTrack events

**Files:** `src/conftamer/contexttrack/{models.py,matching.py,importer.py}`,
`src/conftamer/contexttrack/__init__.py`, `tests/contexttrack/`

- [ ] Migrate distinct reader, route, response, duplicate-hook, redirect, and
  conversion behavior into failing tests.
- [ ] Cover actual nested fields, unknown fields, input sequence, line numbers,
  `(pid, context_id)` grouping, handler/query evidence, and absent context.
- [ ] Test conservative route suffix reconstruction and ambiguity.
- [ ] Test unresolved usable hooks, silent endpoint-less response hooks, hostless
  sends, and response `api_id` evidence.
- [ ] Implement permissive input models, JSONL reading, matching, and semantic
  projection without flattening raw events early.
- [ ] Run `scrape-ok.jsonl`; confirm the documented hostless-send count against
  `all-tests.jsonl`.
- [ ] Remove superseded ContextTrack modules only after replacement tests pass.

**Checkpoint:** `feat: import ContextTrack events`

## 4. Parse CType `.text` graphs

**Files:** `src/conftamer/ctype_graph/{__init__.py,models.py,io.py}`,
`tests/ctype_graph/test_io.py`

- [ ] Test vertices, aliases, methods, nullable tags, grouped AST paths, null
  normalization, endpoints, duplicate edges, and extra `List` mappings.
- [ ] Parse a complete one-line JSON document independent of newline count.
- [ ] Preserve names exactly; exclude unknown fields and generic properties from
  semantic identity.
- [ ] Reject `.gv` explicitly.
- [ ] Assert real US counts: 57 vertices, 90 edges, 58 mappings, 1 alias.
- [ ] Assert real Accessors counts: 582 vertices, 822 edges, 595 mappings,
  13 aliases.
- [ ] Prove all four manager CTypes resolve only through Accessors.

**Checkpoint:** `feat: parse gopls CType graph output`

## 5. Gate and add CType GraphML input

**Prerequisite:** real producer `unmarshaler_subgraph.graphml` and
`accessors.graphml` exist under `examples/paramtrack/static/`. If either is
absent, mark this task deferred, make no parser claim or code change, and
continue with task 6. A deferred task has no checkpoint commit.

**Files after gate:** `docs/input-formats.md`,
`src/conftamer/ctype_graph/io.py`, `tests/ctype_graph/test_io.py`

- [ ] Document observed namespaces, keys, IDs, defaults, direction, and value
  encodings.
- [ ] Test grouped AST paths, isolated nodes, aliases/name mappings, and unknown
  attributes according to the real files.
- [ ] Implement content/extension dispatch with no caller-supplied graph metadata.
- [ ] Prove equivalent `.text` and GraphML normalize identically.

**Checkpoint:** `feat: accept verified gopls CType GraphML`

## 6. Import and join ParamTrack CSV

**Files:** `src/conftamer/paramtrack/{__init__.py,models.py,importer.py}`,
`tests/paramtrack/test_importer.py`

- [ ] Test the exact header, variable-width/quoted rows, no-key rows, empty key
  cells, duplicate keys, malformed rows, and row-order-independent semantic
  IDs/edge endpoints with accurate reordered provenance.
- [ ] Test empty Resource normalization, potentially truncated labels, preserved
  API evidence, and exact leading-slash CType validation through either graph.
- [ ] Test overlapping keys across several CTypes and merged line evidence.
- [ ] Test one, zero, and several semantic method/path Send candidates; never
  compare ParamTrack `API` with ContextTrack `api_id`.
- [ ] Assert target-scraper has 108 keys and manager rows have 133, 120, 201,
  and 108 keys with a 226-key union.
- [ ] Export `import_paramtrack` as a file importer, not a producer wrapper.

**Checkpoint:** `feat: import targeted ParamTrack CSV`

## 7. Build complete PMGraphs

**Files:** `src/conftamer/build.py`, `tests/test_build.py`

- [ ] Test message-only builds and all-or-none ParamTrack/CType options.
- [ ] Test module identity, source digests, evidence union, the caller-association
  diagnostic, and `unique-method-path` evidence.
- [ ] Prove deterministic output under shuffled semantic inputs.
- [ ] Run the target-scraper integration and assert 108 edges to one `GET /` Send.
- [ ] Join manager CSV to a minimal unique `GET /metrics` trace and assert 226
  deduplicated edges with all source lines.
- [ ] Pair manager CSV with `all-tests.jsonl`; assert 47 candidates, an ambiguity
  diagnostic, and zero manager Parameter edges.
- [ ] Validate serialized output through PMGraph v2.

**Checkpoint:** `feat: build PMGraphs from upstream artifacts`

## 8. Add igraph analysis and export

**Files:** `src/conftamer/analysis/{__init__.py,igraph.py}`,
`tests/analysis/test_igraph.py`

- [ ] Test isolated nodes, canonical names, direction, and semantic attributes.
- [ ] Test exact/substring search, ambiguity, ancestors, descendants, and
  induced subgraphs.
- [ ] Test optional-value sanitization and canonical nested JSON attributes.
- [ ] Project PMGraph and CTypeGraph without merging their domain models.
- [ ] Preserve grouped CType paths in `ast_paths_json`.
- [ ] Export and re-read every tested GraphML with igraph.

**Checkpoint:** `feat: analyze and export graphs with igraph`

## 9. Stitch PMGraphs into AppGraph

**Files:** `src/conftamer/appgraph/{__init__.py,models.py,matching.py,stitch.py}`,
`src/conftamer/analysis/igraph.py`, `tests/appgraph/`,
`tests/analysis/test_igraph.py`

- [ ] Reject fewer than two PMGraphs and duplicate module IDs; union source
  tables and validate all embedded evidence.
- [ ] Test exact paths, trailing subtrees, `{name}`, `:name`, and terminal
  `*name`; reject unsupported syntax unless literal.
- [ ] Test 1:1, 1:N, N:1, N:M, same-module, and no-candidate cases.
- [ ] Prove host and `api_id` do not select a module and every accepted match is
  visibly labeled `unique-http-labels`.
- [ ] Match responses only through accepted request matches.
- [ ] Add fixed AppNode IDs; test three-module contraction, edge remapping,
  provenance, shuffled input order, and explicit unmatched pruning.
- [ ] Export and re-read AppGraph GraphML.

**Checkpoint:** `feat: stitch multiple PMGraphs into AppGraphs`

## 10. Replace the CLI

**Files:** `src/conftamer/cli.py`, `src/conftamer/__init__.py`,
`pyproject.toml`, `tests/test_cli.py`

- [ ] Write help and command smoke tests for `build`, `stitch`, `query`, and
  `export`; verify no analyzer, runner, or Delve command exists.
- [ ] Keep orchestration thin; diagnostics use stderr and summaries use stdout.
- [ ] Enforce all-or-none enrichment options and at least two stitch inputs.
- [ ] Accept canonical JSON and verified CType transports in query/export without
  extra graph metadata.
- [ ] Prove stitch output is input-order independent.
- [ ] Change the entry point to `conftamer.cli:app` and format Python/TOML.

**Checkpoint:** `feat: replace CLI with graph compiler workflows`

## 11. Remove legacy surfaces and release

**Delete:** `src/conftamer/csv_graph.py`, superseded `main.py`, old tests,
`examples/legacy/*.csv`, and stale `context/interfaces/` snapshots.

**Update:** `README.md`, `docs/technical-reference.md`, `examples/README.md`,
`.gitignore`, `.github/workflows/release.yml`, and `uv.lock` if required.

- [ ] Delete old code only after all replacement tests pass.
- [ ] Remove old commands, PMGraph v1, and `parse_contexttrack` exports while
  retaining standard-library CSV use for ParamTrack.
- [ ] Replace legacy examples and release smoke tests with build, enrichment,
  CType query, multi-PMGraph stitch, query, and export workflows.
- [ ] Make `docs/technical-reference.md` the current-release user/API guide;
  link to these contracts instead of repeating architecture or input schemas.
- [ ] Document `.gv`, hierarchy, and producer logs as reference-only.
- [ ] Search for stale imports, legacy CSV assumptions, invented GraphML fields,
  split CType AST paths, exact ParamTrack correlation, and old CLI names.
- [ ] Confirm final production code is at most 3,000 physical lines.

**Checkpoint:** `refactor: remove legacy CSV and PMGraph v1 workflows`

## Fresh verification after the final change

```bash
uv run pytest -q tests/pmgraph tests/test_build.py
uv run pytest -q tests/paramtrack tests/ctype_graph
uv run pytest -q tests/contexttrack tests/appgraph
uv run pytest -q tests/analysis tests/test_cli.py
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
```

Also validate generated PMGraph/AppGraph JSON through their Pydantic models;
compare repeated identical inputs and shuffled in-memory semantic inputs
byte-for-byte; verify reordered ParamTrack files preserve semantic IDs/endpoints
while updating source digests and line evidence; re-read every GraphML with
`ig.Graph.Read_GraphML()`; and inspect the complete diff including untracked
example files. Manually load one final
visualization in Gephi Lite when available.
