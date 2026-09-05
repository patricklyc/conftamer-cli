# tool34 Agent Guide

## Purpose and authority

tool34 ships a focused ConfTamer MVP: validate one gopls Unmarshaler Subgraph
or Accessors `.text` artifact per invocation and export visualization GraphML.
The two artifacts are independent graphs and are never merged.

Normative documents:

- `docs/rewrite/architecture.md` — owned models, APIs, and behavior;
- `docs/rewrite/input-formats.md` — verified producer transport and provenance;
- `docs/rewrite/implementation-plan.md` — ordered migration summary; and
- `docs/superpowers/plans/2026-09-03-ctype-graphml-mvp.md` — detailed plan.

Sibling repositories and `ConfTamer_HotNets_2026.pdf` are read-only references.
Do not edit or invoke producers unless the user explicitly expands the scope.

## Scope

The only installed workflow is:

```text
conftamer export INPUT.text --output OUTPUT.graphml
```

Production code belongs only in:

```text
src/conftamer/
├── __init__.py
├── cli.py
└── ctype_graph/
    ├── __init__.py
    ├── models.py
    ├── io.py
    └── graphml.py
```

The tool owns strict raw validation, immutable normalized CType models,
python-igraph projection, visualization GraphML, the thin Typer CLI, tests,
examples, documentation, and packaging. It does not own PMGraph, AppGraph,
ContextTrack, ParamTrack CSV, build, stitching, querying, producer execution,
GraphML input, DOT input, or reverse conversion from visualization GraphML.

## Producer and model rules

Checked-in files under `examples/ctype/` are executable source-of-truth inputs.
Before changing the adapter, compare both real artifacts and the producer
revision recorded in `docs/rewrite/input-formats.md`; stop instead of guessing
if evidence conflicts.

Accept `.text` or JSON-leading input with the verified `Edges`, `Vertices`, and
`List` envelope. Reject malformed or unrelated JSON, `.gv`/DOT, and
`.graphml`/XML. Unknown producer fields are accepted at the raw boundary but do
not enter normalized semantics or GraphML.

Use frozen, extra-forbidding, strict Pydantic models. Preserve upstream names
and IDs exactly, grouped ordered AST paths, aliases, tags, methods, direction,
producer edge cardinality, and isolated vertices. Enforce represented-name
mappings, endpoints, uniqueness, and canonical collection order as specified in
the architecture. Do not combine or deduplicate across input files.

GraphML is a presentation projection, not canonical persistence. All GraphML
attributes are strings. Human-readable attributes accompany compact, sorted-key
JSON strings for lossless nested values. Re-read checked-in GraphML tests with
`ig.Graph.Read_GraphML()`; semantic order is stable, but byte identity is not a
public contract.

## Readability and workflow

Production Python under `src/conftamer` has a hard MVP ceiling of **450 physical
lines**, with a review range of 380–430 and a target near 400. Prefer explicit
functions and domain names over generic wrappers, compatibility adapters, or
service layers.

Before editing:

1. inspect `git status --short --branch` and preserve unrelated changes;
2. read complete involved files and trace callers/tests;
3. state acceptance criteria, design, files, assumptions, risks, and checks for
   non-trivial work; and
4. stop if producer evidence conflicts or scope expands.

Use TDD for behavior changes: write the smallest failing test, confirm the
expected failure, implement minimally, and rerun the focused test. Format Python
or TOML edits before final verification.

Focused and final checks:

```bash
uv run pytest -q tests/ctype_graph tests/test_cli.py
uvx ruff format --check src tests
uvx tombi format --check pyproject.toml
uvx ty check
uv run pytest -q
uv run conftamer --help
uv run conftamer export --help
find src/conftamer -name '*.py' -print0 | xargs -0 wc -l
git diff --check
```

For real-data checks, export both `examples/ctype/*.text` files independently,
re-read them with igraph, and verify 57/90 and 582/822 vertex/edge counts.
Inspect the complete diff and untracked files before completion. Do not commit,
push, edit sibling repositories, or expand into producer work unless requested.

## Completion report

Report changed files, exact fresh checks and results, production line count,
real-data/CLI/standalone smoke-test availability, compatibility impact,
residual risks, warnings or incomplete behavior, and a concise proposed commit
message.
