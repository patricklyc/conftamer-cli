import igraph as ig
import typer
from rich import print

from conftamer.csv import read_csv
from conftamer.graph import to_graph

app = typer.Typer()


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
