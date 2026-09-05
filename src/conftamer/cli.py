from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated, Never

import typer
from pydantic import ValidationError

from conftamer.ctype_graph import export_graphml, load_ctype_graph

app = typer.Typer()


@app.callback()
def main() -> None:
    """Validate a gopls CType artifact and export visualization GraphML."""


@app.command("export")
def export_command(
    input_path: Annotated[Path, typer.Argument()],
    output: Annotated[Path, typer.Option("--output")],
) -> None:
    with _user_errors():
        graph = load_ctype_graph(input_path)
        export_graphml(graph, output)
    _echo_summary(len(graph.nodes), len(graph.edges), output)


def _echo_summary(vertices: int, edges: int, output: Path) -> None:
    vertex_label = "vertex" if vertices == 1 else "vertices"
    edge_label = "edge" if edges == 1 else "edges"
    typer.echo(
        f"Wrote GraphML with {vertices} {vertex_label} and "
        f"{edges} {edge_label} to {output}"
    )


@contextmanager
def _user_errors() -> Iterator[None]:
    try:
        yield
    except (OSError, UnicodeError, ValueError) as error:
        _exit_with_error(_error_message(error))


def _error_message(error: OSError | UnicodeError | ValueError) -> str:
    if isinstance(error, ValidationError):
        detail = error.errors(include_url=False, include_context=False)[0]
        return f"invalid CType input: {detail['msg']}"
    return str(error)


def _exit_with_error(message: str) -> Never:
    typer.echo(f"error: {message}", err=True)
    raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
