# Development

Follow the [README setup](../README.md#setup) first. The project uses Python
3.14+, uv, and the locked dependencies; no sibling checkout or Go capture run is
needed for the tests.

## Verification

Run the tests, formatting and type checks, CLI help, and whitespace check from
the repository root:

```bash
uv run pytest -q
uvx ruff format --check src tests
uvx ty check
uv run conftamer --help
uv run conftamer build --help
git diff --check
```

Tests cover consumer graph policy, the tracked small normalized capture, and
representative upstream-reader failures, including raw-input rejection. Synthetic
traces cover association boundaries. Larger local captures are not needed.
Exhaustive wire-schema validation belongs to the pinned ContextTrack package.
See the [example inventory and fixture policy](../examples/README.md) before
working with captures.

## Editor setup

For VS Code, select `.venv/bin/python` as the workspace interpreter. The
[Python](https://marketplace.visualstudio.com/items?itemName=ms-python.python),
[Ruff](https://marketplace.visualstudio.com/items?itemName=charliermarsh.ruff), and
[ty](https://marketplace.visualstudio.com/items?itemName=astral-sh.ty) extensions
provide Python integration, formatting, and type checking, respectively.

## Scope and design history

See [AGENTS.md](../AGENTS.md) for development scope and the
[normalized-input contract](superpowers/plans/2026-10-13-normalized-contexttrack-input.md)
for the implemented migration. Other plans retain their original implementation
steps as history; the [PR #8 review](pr-8-code-review.md) concerns a different
reviewed revision, not features available in this checkout.
