from pathlib import Path

import igraph

from conftamer.pmgraph.models import Message, Parameter, PMGraph


def to_igraph(graph: PMGraph) -> igraph.Graph:
    node_ids = list(graph.nodes)
    indices = {node_id: index for index, node_id in enumerate(node_ids)}
    edges = [(indices[a], indices[b]) for a, b in sorted(graph.edges)]
    network = igraph.Graph(n=len(node_ids), edges=edges, directed=True)
    network["module_id"] = graph.module_id
    network.vs["name"] = node_ids
    for attribute in Parameter.model_fields | Message.model_fields:
        network.vs[attribute] = [
            getattr(node, attribute, None) for node in graph.nodes.values()
        ]
    return network


def _check_graphml_text(value: str, location: str) -> None:
    for character in value:
        code = ord(character)
        if character == "\r" or not (
            code in (9, 10)
            or 0x20 <= code <= 0xD7FF
            or 0xE000 <= code <= 0xFFFD
            or 0x10000 <= code <= 0x10FFFF
        ):
            raise ValueError(f"GraphML cannot preserve {location} {value!r}")


def write_graphml(graph: PMGraph, path: str | Path) -> None:
    _check_graphml_text(graph.module_id, "module ID")
    for node_id, node in graph.nodes.items():
        _check_graphml_text(node_id, "node ID")
        for attribute, value in node.model_dump().items():
            if isinstance(value, str):
                _check_graphml_text(value, f"node {node_id!r} attribute {attribute}")

    network = to_igraph(graph)
    with Path(path).open("xb") as output:
        try:
            network.write_graphml(output, prefixattr=True)
        except igraph.InternalError as error:
            raise OSError(f"cannot write GraphML {path}: {error}") from error
