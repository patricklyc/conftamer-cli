import typer
from rich import print

from conftamer.csv import read_csv
from conftamer.graph import to_graph

app = typer.Typer()


@app.command()
def main(filename: str):
    edges = read_csv(filename)

    g = to_graph(edges)
    print(g)
    g.write_graphml(f"{filename}.graphml")


if __name__ == "__main__":
    app()
