# ConfTamer

ConfTamer is being built to show how configuration parameters and HTTP messages
may influence one another inside an application module.

This branch defines the Python data format for a per-module graph, called a
PMGraph.

## Graph format

A PMGraph contains:

- an ID for the module;
- nodes representing configuration parameters or HTTP messages; and
- directed edges connecting those nodes.

Each node has a `kind` field that says what type of node it is. An edge stores the
IDs of its source and destination nodes. If the same edge appears more than once,
it is stored only once.

```python
from conftamer.pmgraph.models import PMGraph

graph = PMGraph.model_validate(
    {
        "module_id": "frontend",
        "nodes": {
            "parameter-1": {
                "kind": "parameter",
                "key": "timeout",
            },
            "message-1": {
                "kind": "send_request",
                "api_id": None,
                "method": "POST",
                "host": "backend:8080",
                "path": "/jobs",
            },
        },
        "edges": [["parameter-1", "message-1"]],
    }
)
```

In this example, the `timeout` parameter points to an HTTP request.

This branch only defines the graph models. The command-line program is still a
simple greeting demo. It does not yet read ContextTrack captures, save graph
files, export GraphML, or query graphs.

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