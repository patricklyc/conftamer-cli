import sys
from pathlib import Path
from typing import Annotated

import typer
from rich import print

from conftamer.contexttrack import parse_contexttrack
from conftamer.csv_graph import read_csv, to_graph, to_subgraph
from conftamer.pmgraph import write_pmgraph

app = typer.Typer()


@app.command()
def contexttrack(
    input_path: Path,
    module_id: Annotated[str, typer.Option("--module-id")],
    output: Annotated[Path | None, typer.Option("--output")] = None,
):
    result = parse_contexttrack(input_path, module_id=module_id)
    output_path = output or Path(f"{input_path}.pmgraph.json")
    write_pmgraph(result.graph, output_path)

    for warning in result.warnings:
        print(
            f"warning: line {warning.input_line}: {warning.message}",
            file=sys.stderr,
        )


@app.command()
def graph(filename: str):
    edges = read_csv(filename)

    g = to_graph(edges)
    print(g)
    g.write_graphml(f"{filename}.graphml")


@app.command()
def subgraph(filename: str, node_id: int):
    graph = to_graph(read_csv(filename))
    to_subgraph(graph, node_id).write_graphml(f"{filename}.graphml")


if __name__ == "__main__":
    app()
