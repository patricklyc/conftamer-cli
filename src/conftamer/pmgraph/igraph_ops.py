from pathlib import Path

import igraph

from conftamer.pmgraph.models import PMGraph


def to_igraph(graph: PMGraph) -> igraph.Graph:
    node_ids = list(graph.nodes)
    indices = {node_id: index for index, node_id in enumerate(node_ids)}
    edges = [(indices[a], indices[b]) for a, b in sorted(graph.edges)]
    network = igraph.Graph(n=len(node_ids), edges=edges, directed=True)
    network["module_id"] = graph.module_id
    network.vs["name"] = node_ids
    network.vs["kind"] = [node.kind for node in graph.nodes.values()]
    network.vs["node_json"] = [
        node.model_dump_json(ensure_ascii=True) for node in graph.nodes.values()
    ]
    return network


def _check_graphml_identity(value: str) -> None:
    for character in value:
        code = ord(character)
        if character == "\r" or not (
            code in (9, 10)
            or 0x20 <= code <= 0xD7FF
            or 0xE000 <= code <= 0xFFFD
            or 0x10000 <= code <= 0x10FFFF
        ):
            raise ValueError(f"GraphML cannot preserve identity {value!r}")


def write_graphml(graph: PMGraph, path: str | Path) -> None:
    network = to_igraph(graph)
    for value in [graph.module_id, *graph.nodes]:
        _check_graphml_identity(value)
    with Path(path).open("xb") as output:
        try:
            network.write_graphml(output, prefixattr=True)
        except igraph.InternalError as error:
            raise OSError(f"cannot write GraphML {path}: {error}") from error
