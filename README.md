## Development setup

Requirements:

- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- Python 3.14 (uv can install it for you)

From the repository root, install Python and the locked development dependencies:

```bash
uv python install 3.14
uv sync --locked --dev
```

Run the tests and verify the CLI:

```bash
uv run pytest -q
uv run conftamer --help
```

Optional formatting and type checks:

```bash
uvx ruff format --check src tests
uvx ty check
```

### VS Code

Install the official [Python](https://marketplace.visualstudio.com/items?itemName=ms-python.python), [Ruff](https://marketplace.visualstudio.com/items?itemName=charliermarsh.ruff), and [ty](https://marketplace.visualstudio.com/items?itemName=astral-sh.ty) extensions, (and uninstall Pylance). Then select `.venv/bin/python` as the workspace interpreter.