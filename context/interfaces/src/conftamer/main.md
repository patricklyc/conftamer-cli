# `src/conftamer/main.py`


## Responsible for
- Registering the top-level Typer application and its commands.
- Dispatching ContextTrack conversion and legacy CSV graph operations.
- Resolving legacy subgraph queries as integer vertex IDs or attribute searches,
  including ambiguous interactive choices.
- Choosing output paths and writing PMGraph or GraphML files.
- Printing conversion warnings to standard error and graph summaries to
  standard output.

## Public interface
```python
app = typer.Typer()


def contexttrack(
    input_path: Path,
    module_id: str = typer.Option(..., "--module-id"),
    output: Path | None = typer.Option(None, "--output"),
): ...


def graph(filename: str): ...


def subgraph(filename: str, query: str): ...
```

The functions are exposed as the `contexttrack`, `graph`, and `subgraph` CLI
commands through `app`.
