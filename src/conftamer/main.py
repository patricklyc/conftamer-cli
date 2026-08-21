import sys
from pathlib import Path

import igraph as ig
import typer
from rich import print

from conftamer.contexttrack import parse_contexttrack
from conftamer.csv import read_csv
from conftamer.graph import to_graph
from conftamer.pmgraph import write_pmgraph

app = typer.Typer()


@app.command()
def contexttrack(
    input_path: Path,
    module_id: str = typer.Option(..., "--module-id"),
    output: Path | None = typer.Option(None, "--output"),
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
    edges = read_csv(filename)

    g: ig.Graph = to_graph(edges)
    v = []
    v.extend(g.subcomponent(node_id, mode="in"))
    v.extend(g.subcomponent(node_id, mode="out"))
    print(v)
    sg: ig.Graph = g.subgraph(v)
    print(sg)
    sg.write_graphml(f"{filename}.graphml")


if __name__ == "__main__":
    app()
