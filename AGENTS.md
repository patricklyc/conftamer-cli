# tool34 Agent Guide

## Project purpose

tool34 builds directed configuration and message-flow graphs for ConfTamer.
The current CLI reads edge records, constructs an `igraph` graph, and exports
GraphML. The sibling repository `../conftamer` and
`ConfTamer_HotNets_2026.pdf` are upstream references; treat them as read-only
unless the user explicitly requests changes there.

## Repository map

- `src/conftamer/main.py`: Typer CLI commands.
- `src/conftamer/models.py`: Pydantic node models and node types.
- `src/conftamer/csv.py`: legacy CSV edge parser.
- `src/conftamer/graph.py`: graph construction and subgraph helpers.
- `pyproject.toml`: Python version, dependencies, and CLI entry point.
- `test_*.csv`: local sample inputs; CSV, GraphML, and PDF files are ignored by
  Git and may not be available in every checkout.

## Priorities

1. Correctness and deterministic output.
2. Readability and simplicity.
3. Small, focused changes.
4. Compatibility with existing CLI and CSV behavior unless a task explicitly
   changes them.

Prefer explicit functions and models over generic frameworks. Avoid premature
abstractions, duplicate representations, and speculative extensibility.

## Development workflow

- Inspect `git status` before editing and preserve unrelated user changes.
- For non-trivial work, first state the acceptance criteria, proposed design,
  files expected to change, and verification commands.
- Do not add dependencies, change public CLI behavior, or alter serialized
  schemas without explicit approval.
- If an assumption proves false or the required scope expands, stop and ask
  before proceeding.
- Run Ruff formatting after every Python implementation:

  ```bash
  uvx ruff format <changed-python-files>
  ```

- Run focused verification first, followed by the full available test suite:

  ```bash
  uv run pytest -q <relevant-tests>
  uv run pytest -q
  ```

  If no tests are configured for the affected behavior, perform a focused CLI
  or Python smoke test and clearly state that limitation.

- For CLI changes, also check:

  ```bash
  uv run conftamer --help
  ```

- Report exact commands and results. Include changed files, residual risks, and
  a concise proposed commit message in the final summary.

## Data and model conventions

- Use Pydantic for untrusted external input and serialized output boundaries.
- Preserve the nested shape and meaning of upstream ContextTrack data while
  parsing; flatten only when constructing the target graph representation.
- Keep graph edges directed as `(source, target)` influence relationships.
- Preserve stable node ordering and deterministic identifiers or output.
- Reject or report malformed input explicitly; do not silently guess when a
  route, response, or endpoint match is ambiguous.
- Keep the existing CSV pipeline isolated when adding another input format.
  Do not rewrite or broaden legacy behavior unless required by the task.

## Upstream schema work

When comparing or integrating ContextTrack output:

- Verify behavior against the implementation and documentation under
  `../conftamer/contexttrack`; do not rely only on examples or the paper.
- Distinguish raw runtime events from normalized graph nodes.
- Document how each consumed input field maps to the output schema.
- Prefer conservative matching with visible warnings over potentially false
  graph edges.
- Add only tests needed to establish parsing, matching, graph semantics, and
  deterministic serialization; avoid redundant tests and unrelated legacy CSV
  coverage.
