from pathlib import Path

from conftamer.io import load_pmgraph_json, write_graph_json
from conftamer.pmgraph.models import PMGraph

__all__ = ["load_pmgraph_json", "write_pmgraph_json"]


def write_pmgraph_json(graph: PMGraph, path: str | Path) -> None:
    write_graph_json(graph, path)
