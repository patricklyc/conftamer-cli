# tool34 Agent Guide

## Purpose and scope

tool34 builds directed configuration and message-flow graphs for ConfTamer. It
currently supports two intentionally separate workflows:

1. **ContextTrack JSONL to PMGraph JSON** — the primary workflow and target for
   new trace integrations.
2. **Legacy edge CSV to `igraph`/GraphML** — retained for compatibility with the
   original prototype.

The sibling repository `../conftamer`, especially `../conftamer/contexttrack`,
and `ConfTamer_HotNets_2026.pdf` are upstream references. Treat them as
read-only unless the user explicitly requests changes there.

## Architecture and data flow

The ContextTrack pipeline is organized by conversion stage:

```text
ContextTrack JSONL
    -> contexttrack/events.py
    -> contexttrack/routes.py + contexttrack/responses.py
    -> contexttrack/conversion.py
    -> pmgraph.py
```

- `src/conftamer/main.py`: thin Typer CLI orchestration and warning display.
- `src/conftamer/pmgraph.py`: PMGraph node/edge models, validation,
  deterministic IDs, deduplication, ordering, and serialization.
- `src/conftamer/csv_graph.py`: all legacy CSV models, parsing, `igraph`
  construction, and subgraph selection. Keep this workflow self-contained.
- `src/conftamer/contexttrack/events.py`: permissive Pydantic models for
  upstream events, JSONL validation, source-line tracking, warnings, and
  grouping by `(pid, context_id)`.
- `src/conftamer/contexttrack/routes.py`: route-to-request matching and nested
  route-pattern reconstruction.
- `src/conftamer/contexttrack/responses.py`: conservative request/response
  correlation, duplicate-hook handling, and redirect fallback.
- `src/conftamer/contexttrack/conversion.py`: public conversion orchestration,
  event-to-PMGraph node conversion, normalization, and context-derived edge
  assembly.
- `src/conftamer/contexttrack/__init__.py`: supported public ContextTrack
  exports, including `parse_contexttrack`.
- `tests/test_contexttrack_events.py`: input validation, reading, and grouping.
- `tests/test_contexttrack_routes.py`: route matching and reconstruction.
- `tests/test_contexttrack_responses.py`: response-correlation behavior.
- `tests/test_contexttrack_conversion.py`: end-to-end PMGraph conversion.
- `tests/test_pmgraph.py`: PMGraph shapes, invariants, and determinism.
- `pyproject.toml`: Python version, dependencies, and `conftamer` entry point.

Files under `data/` are ignored local samples and may be absent in another
checkout. Tests must create their own inputs rather than depend on those files.

## Design priorities

Apply these in order:

1. Correctness and deterministic output.
2. Readability and simplicity.
3. Conservative matching over false graph relationships.
4. Small, focused changes.
5. Compatibility with the CLI, PMGraph schema, and legacy CSV behavior unless
   the task explicitly changes them.

Prefer explicit functions and Pydantic models over generic frameworks. Keep
code near the transformation it implements, avoid speculative abstractions,
and preserve the current source and test layout unless a change demonstrably
improves clarity.

## Public behavior and compatibility

Do not change any of the following without explicit approval:

- CLI command names or options:
  - `conftamer contexttrack INPUT_PATH --module-id MODULE_ID [--output PATH]`
  - `conftamer graph FILENAME`
  - `conftamer subgraph FILENAME QUERY`
- the supported import `from conftamer.contexttrack import parse_contexttrack`;
- PMGraph `format`, `version`, node shapes, edge shape, or ID derivation;
- default ContextTrack output path `<input>.pmgraph.json`;
- GraphML output path `<csv>.graphml` for legacy commands;
- accepted legacy CSV row shapes; or
- warning-versus-error behavior for malformed or incomplete ContextTrack data.

Internal modules such as `routes.py` and `responses.py` are implementation
boundaries, not independent public APIs. Avoid compatibility shims for removed
internal layouts unless the user identifies a real external consumer.

Do not add dependencies or raise the Python version without approval. Do not
rewrite legacy CSV code while implementing ContextTrack behavior.

## ContextTrack input conventions

ContextTrack JSONL is untrusted external input:

- validate it with Pydantic at the boundary;
- preserve the nested `message`, `context`, and `request_id` structures while
  reading and matching;
- allow and retain unknown upstream fields (`extra="allow"`);
- preserve original input line numbers for warnings;
- skip blank lines;
- continue after malformed lines and report them visibly; and
- flatten only when constructing PMGraph labels.

The five supported event kinds are `Request sent`, `Request received`,
`Request routed`, `Response sent`, and `Response received`. If upstream adds a
kind or changes field meaning, verify it against the implementation under
`../conftamer/contexttrack`; do not infer a schema from one sample trace.

Group events by `(pid, context_id)`, not by context ID alone. Events without a
context ID may still produce a node when independently convertible, but they
must not produce context-derived edges.

Distinguish identifiers carefully:

- `module_id` identifies the module represented by the complete PMGraph and is
  supplied by the CLI because ContextTrack does not export it.
- `api_id` belongs to an individual communication event. A module graph may
  contain several API IDs, and outbound API IDs must carry through to matched
  Receive Response nodes.

## Route and response matching conventions

Keep matching conservative and warnings visible.

### Routes

- Match request methods case-insensitively and paths exactly.
- Reconstruct nested route chains when a later routed path is a suffix of the
  previous path, preserving prefixes removed by `StripPrefix`-style routing.
- If a route hop could continue more than one chain, warn with
  `ambiguous route chain` and do not guess.
- If a route chain has no matching inbound request, warn with
  `route has no request match`.
- When an inbound request has no matched route, conversion falls back to its
  concrete request path.

### Responses

- Match responses to unconsumed requests by method and path first.
- Use goroutine identity only to select a unique candidate, or as a method-only
  fallback when a received response has no exact endpoint candidate. Redirected
  requests with changed response paths motivate this fallback, but the matcher
  does not detect redirects explicitly.
- Report missing and ambiguous matches instead of choosing arbitrarily when a
  response contains usable method and path data. Endpoint-less response hooks
  may be omitted without a warning so a later usable hook can represent them.
- Current Go instrumentation can emit wire-level and client-level
  received-response hooks. Suppress a client hook as a duplicate only when the
  most recent earlier received-response hook in the context was successfully
  matched and status/method are compatible.
- A duplicate hook must never consume a newer request.
- An endpoint-less wire hook may remain unmatched so a later client hook with
  usable endpoint data can represent the response.

These are compatibility rules for the current upstream trace shape, not
features to generalize. If ContextTrack later emits stable correlation IDs,
full route patterns, or consistently normalized endpoints, simplify or remove
the corresponding heuristics in `routes.py`, `responses.py`, and
`conversion.py` rather than preserving obsolete machinery.

## PMGraph invariants

Use `src/conftamer/pmgraph.py` as the sole PMGraph representation.

- IDs generated by `make_node_id` are SHA-256 hashes of canonical JSON
  containing `module_id` and all semantic node fields. The PMGraph validator
  accepts any nonempty, unique IDs.
- HTTP methods are uppercase.
- Non-optional label strings are nonempty.
- Empty HTTP paths normalize to `/` at the PMGraph conversion boundary; raw
  ContextTrack events retain their original value.
- Status codes are integers in the inclusive range 100–999.
- Node IDs are unique.
- Edges are directed `(source, target)` influence relationships.
- Edge endpoints must exist in the graph.
- Sources must be Receive or Parameter nodes; targets must be Send nodes.
- Self-edges are forbidden.
- `make_pmgraph()` deduplicates nodes and edges, sorts nodes by ID, and sorts
  edges by `(source, target)`. Direct `PMGraph` validation does not normalize
  ordering or reject duplicate edges.

For each `(pid, context_id)` group, conversion connects every successfully
converted Receive occurrence to every later successfully converted Send
occurrence. Do not create edges from route events or unmatched response hooks.

An outbound request with no host cannot satisfy the PMGraph label schema. Omit
it with `request endpoint has no host`; do not invent a host. In general, reject
or report missing and ambiguous information instead of guessing labels.

ContextTrack currently creates message nodes only. Parameter nodes and
configuration edges are valid PMGraph concepts but are not inferred from trace
events.

## Legacy CSV conventions

The legacy parser accepts only these headerless row shapes:

```text
Parameter,<module_id>,<parameter_name>,Send,<module_id>,<api_id>,<request_id>,<response_code>
Receive,<module_id>,<api_id>,<request_pattern>,<response_code>,Send,<module_id>,<api_id>,<request_id>,<response_code>
```

Rows that do not match either structural shape raise
`ValueError("parsing error")`; invalid typed values surface Pydantic validation
errors. Preserve stable first-seen vertex ordering and directed edges. The
legacy node model and GraphML output are not PMGraph and must remain isolated in
`csv_graph.py`. New formats should convert to PMGraph rather than broaden this
representation.

## Upstream schema work

When comparing or integrating ContextTrack behavior:

1. Read the relevant implementation and documentation under
   `../conftamer/contexttrack` completely. Follow code paths that emit each
   consumed event; do not rely only on examples or the paper.
2. Distinguish raw runtime hooks from normalized graph nodes. Multiple hooks
   can describe one logical request or response.
3. Document how every consumed input field maps to a PMGraph field or matching
   decision.
4. Test against the smallest real trace that demonstrates the behavior when
   such a trace is available.
5. Prefer visible warnings and omitted edges over potentially false matches.
6. Check deterministic serialization and schema validation after changes.

Treat the sibling repository and paper as references only. Stop and ask before
editing them or before expanding the task into upstream instrumentation work.

## Test organization

Keep tests focused and behavior-oriented:

- parsing/model tests belong in `test_contexttrack_events.py`;
- nested route behavior belongs in `test_contexttrack_routes.py`;
- request/response matching belongs in `test_contexttrack_responses.py`;
- node labels, warnings, and graph semantics belong in
  `test_contexttrack_conversion.py`; and
- PMGraph schema/determinism belongs in `test_pmgraph.py`.

Keep test setup explicit and close to the behavior under test. Share helpers or
fixtures only when doing so is clearer than local setup. Keep only distinct
behavior tests; avoid redundant combinations, speculative impossible inputs,
and unrelated CSV coverage for ContextTrack changes.

## Development workflow

Before editing:

1. inspect `git status --short --branch` and preserve unrelated changes;
2. read the complete files involved and trace their callers/tests;
3. for non-trivial work, state acceptance criteria, proposed design, expected
   files, and verification commands; and
4. stop for clarification if an assumption is false, the public behavior must
   change, or scope expands.

After every Python implementation, format the changed files. Format every
changed TOML file with Tombi:

```bash
uvx ruff format <changed-python-files>
uvx tombi format <changed-toml-files>
```

Run focused verification first, then the complete checks. Include the Tombi
check whenever the change includes TOML files:

```bash
uv run pytest -q <relevant-tests>
uvx ruff format --check src tests
uvx tombi format --check <changed-toml-files>
uvx ty check
uv run pytest -q
```

If no automated test covers the behavior, run a focused Python or CLI smoke
test and report that limitation. For CLI changes, verify the affected command
and help output; for broad CLI changes, run all help pages:

```bash
uv run conftamer --help
uv run conftamer contexttrack --help
uv run conftamer graph --help
uv run conftamer subgraph --help
```

For ContextTrack output changes, validate generated JSON through
`PMGraph.model_validate_json()`. For deterministic-output changes, compare
serialized output across repeated runs or against a pre-change snapshot.

Before completion, run `git diff --check`, inspect the complete diff including
untracked files, and confirm no stale imports or documentation references
remain.

## Completion report

Report:

- changed files and their purpose;
- exact verification commands and results;
- whether real-data or CLI smoke tests were available;
- compatibility impact and residual risks;
- any warnings or known incomplete behavior; and
- a concise proposed commit message.

Do not claim completion from an earlier run. Verification evidence must be
fresh after the final change.
