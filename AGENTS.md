# tool34 Agent Guide

## Purpose and authority

tool34 is being rewritten as ConfTamer's graph compiler and explorer. It starts
at files emitted by ContextTrack, ParamTrack, and gopls and ends at canonical,
queryable graphs and visualization GraphML.

The normative rewrite documents are:

- `docs/rewrite/architecture.md`: target-owned models, behavior, and APIs;
- `docs/rewrite/input-formats.md`: observed producer formats and provenance; and
- `docs/rewrite/implementation-plan.md`: ordered work and checkpoints.

Follow the implementation plan in order. During the transition, existing source
may still implement PMGraph v1 and legacy commands; do not preserve those
surfaces when the current plan task explicitly replaces them. Update contracts
before implementation when verified producer evidence contradicts them.

Sibling repositories and `ConfTamer_HotNets_2026.pdf` are read-only references.
Do not edit them unless the user explicitly expands the scope.

## Scope and boundaries

The target tool owns:

- permissive parsing of untrusted ContextTrack JSONL;
- parsing of targeted ParamTrack parameter CSV;
- parsing and normalization of verified gopls CType graph transports;
- conservative message matching and parameter enrichment;
- deterministic PMGraph v2 and AppGraph v1 documents;
- stitching, igraph analysis, queries, and visualization GraphML;
- diagnostics, CLI orchestration, tests, examples, documentation, and packaging.

It does not own producer execution, test discovery, Delve control,
instrumentation, parameter-key inference, CType inference, hierarchy/log
conversion, or upstream artifact production. Source adapters consume files; they
do not wrap producers.

The targeted ParamTrack CSV is a headered, variable-width upstream format. It is
unrelated to tool34's old headerless edge CSV. The rewrite retains the former
and removes the latter; never share their models or broaden the legacy parser.

## Target data flow

```text
ContextTrack JSONL
    -> contexttrack models + matching + semantic message fragment

ParamTrack CSV + Unmarshaler/Accessors CType graphs
    -> CType validation + unique method/path enrichment

message fragment + optional parameter enrichment
    -> canonical PMGraph v2

at least two PMGraphs
    -> conservative cross-module matching
    -> canonical AppGraph v1

PMGraph/AppGraph/CTypeGraph
    -> python-igraph query and visualization GraphML
```

Raw input models must not leak into canonical graph models. CType nodes remain
in `CTypeGraph`; partial message hooks do not become incomplete PM nodes;
parameter keys are consumed, not recalculated; and canonical JSON never depends
on igraph serialization.

## Target source layout

Production code belongs under these domain boundaries:

```text
src/conftamer/
├── cli.py
├── diagnostics.py
├── build.py
├── pmgraph/{__init__.py,models.py,io.py}
├── contexttrack/{__init__.py,models.py,matching.py,importer.py}
├── paramtrack/{__init__.py,models.py,importer.py}
├── ctype_graph/{__init__.py,models.py,io.py}
├── appgraph/{__init__.py,models.py,matching.py,stitch.py}
└── analysis/{__init__.py,igraph.py}
```

Keep orchestration in `cli.py` thin. Put validation and normalization with the
domain model, transport details in `io.py` or an importer, and matching near the
domain that owns it. Avoid generic service, repository, plugin, visitor, or
graph-wrapper layers; compatibility adapters for removed formats; duplicated
query implementations; and one-function modules without a real boundary.

## Design priorities

Apply these in order:

1. Correctness and deterministic output.
2. Conservative matching over false relationships.
3. Readability and simplicity.
4. Small changes scoped to the current ordered task.
5. Compatibility with target contracts, not superseded rewrite surfaces.

Prefer explicit functions, dataclasses, and Pydantic models over frameworks or
speculative abstractions. Do not add dependencies or raise Python's minimum
version without approval.

## Input and producer rules

Checked-in files under `examples/` are executable source-of-truth integration
inputs. Unit tests use the smallest explicit representation of an observed
shape; integration tests exercise the real files directly. Generated PMGraph,
AppGraph, and GraphML output does not belong in input example directories.

When changing an adapter:

1. read the relevant current producer implementation completely;
2. follow the path that emits every consumed field;
3. compare all checked-in examples for that producer;
4. distinguish observed input, retained downstream policy, target design,
   paper-derived concepts, and blocked formats; and
5. stop instead of guessing when evidence conflicts.

Unknown producer fields are accepted at raw boundaries but do not become
canonical semantics automatically. Preserve source line numbers and nested raw
structures needed for diagnostics and evidence. A bad independent record should
normally produce a diagnostic and be omitted; unreadable files and invalid
file-level contracts are errors.

CType `.text` JSON is accepted. `.gv` is reference-only. CType GraphML remains
blocked until real producer US and Accessors GraphML files establish namespaces,
keys, IDs, defaults, direction, and value encoding. Visualization GraphML is
never canonical input.

## Canonical graph rules

Use frozen, extra-forbidding Pydantic models for target-owned documents. Treat
semantic IDs, provenance, validation, normalization, evidence merging, and
ordering in `docs/rewrite/architecture.md` as one contract.

In particular:

- preserve the existing compact, sorted-key SHA-256 node hash algorithm;
- exclude evidence from semantic identity;
- normalize methods and empty HTTP paths only at the semantic boundary;
- reject dangling evidence and graph endpoints;
- merge evidence for semantically identical nodes and edges;
- retain isolated nodes;
- sort every canonical collection by its documented key; and
- write deterministic UTF-8 JSON ending in one newline.

PMGraph edges represent possible influence, not proven causality. Planned
importers create `Receive -> Send` and `Parameter -> Send Request` edges.
Behavior is schema-only until a producer contract exists.

AppGraph matching uses HTTP labels only, never host or `api_id` to choose a
module. Contract only mutually unique cross-module candidates and mark every
accepted match `unique-http-labels`. Match responses only through an accepted
request match. Retain unmatched nodes by default.

## ContextTrack conventions

ContextTrack JSONL is untrusted and line-oriented. Keep unknown fields, skip
blank lines, continue after malformed lines with diagnostics, and group
context-derived inference by `(pid, context_id)`. Events without a usable
`context.context_id` may produce independently convertible nodes but no context
edge; the raw `context` object remains required.

Preserve the five supported event kinds and the conservative route, response,
duplicate-hook, redirect, hostless-send, and context-order behavior specified in
the rewrite contracts. Prefer visible diagnostics and omitted relationships over
guesses. `module_id`, ContextTrack `api_id`, and ParamTrack `API` have different
meanings and must never be conflated.

## ParamTrack and CType conventions

Parse targeted CSV with the standard `csv` module. Require the observed header,
preserve variable-width quoted rows and physical line evidence, allow no-key
rows, and validate every CType directly against represented nodes in either the
Unmarshaler Subgraph or Accessors graph.

ParamTrack enrichment is aggregate and caller-asserted. Join only to one unique
semantic Send Request by normalized method/path. Never compare ParamTrack `API`
with ContextTrack `api_id`, spread a row across ambiguous hosts, or infer
per-occurrence causality. Deduplicate semantic parameters and edges while
retaining evidence from every supporting row.

For CType graphs, preserve names and upstream IDs exactly, preserve grouped
ordered AST paths, retain isolated vertices, discard generic graph-library
properties from semantic identity, and reject conflicting represented names,
duplicate endpoints, and missing edge endpoints as documented.

## Readability and line budget

Production Python under `src/conftamer` has a hard review gate of **3,000
physical lines** and a target of 2,500. Record the cumulative count at every
checkpoint:

```bash
find src/conftamer -name '*.py' -print0 | xargs -0 wc -l
```

Prefer files below 300 lines, with a 450-line ceiling for model-heavy files, and
linear functions below 40 lines where practical. Simplify before adding an
abstraction or crossing a budget. Tests and generated files do not count toward
the production limit.

## Test organization and workflow

Tests mirror domain packages:

- `tests/pmgraph/` for PMGraph models and I/O;
- `tests/contexttrack/` for reading, matching, and projection;
- `tests/ctype_graph/` for CType normalization and transport;
- `tests/paramtrack/` for CSV parsing and enrichment;
- `tests/appgraph/` for matching and stitching;
- `tests/analysis/` for igraph projection, query, and GraphML;
- `tests/test_build.py` and `tests/test_cli.py` for orchestration boundaries.

Before editing:

1. inspect `git status --short --branch` and preserve unrelated changes;
2. read the complete files involved and trace their callers/tests;
3. state acceptance criteria, design, expected files, assumptions, risks, and
   verification commands for non-trivial work; and
4. stop if a contract must change, a public API change is not already approved,
   producer evidence conflicts, or scope expands.

For every behavior change, use test-driven development: write the smallest
failing test, confirm the expected failure, implement minimally, and rerun the
focused test. Documentation-only contract alignment uses focused artifact and
link validation instead of manufactured unit tests.

After Python or TOML edits, format changed files:

```bash
uvx ruff format <changed-python-files>
uvx tombi format <changed-toml-files>
```

Run focused verification first, then fresh full checks:

```bash
uv run pytest -q <relevant-tests>
uvx ruff format --check src tests
uvx tombi format --check pyproject.toml
uvx ty check
uv run pytest -q
find src/conftamer -name '*.py' -print0 | xargs -0 wc -l
git diff --check
```

For CLI changes, run affected commands and help pages. Validate generated
canonical JSON through its Pydantic model, compare deterministic outputs
byte-for-byte, and re-read exported GraphML with `ig.Graph.Read_GraphML()`.
Before completion, inspect the complete diff including untracked files and
search for stale imports, old commands, and superseded format assumptions.

## Completion report

Report:

- changed files and their purpose;
- exact verification commands and fresh results;
- production line count;
- real-data and CLI smoke-test availability;
- compatibility impact and residual risks;
- warnings or incomplete behavior; and
- a concise proposed commit message with a subject and body after every
  implementation task.

Do not claim completion from an earlier run. Do not edit sibling repositories,
commit, push, or expand into producer work unless explicitly requested.
