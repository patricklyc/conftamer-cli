import json
from pathlib import Path

import igraph as ig

from conftamer.ctype_graph.models import CTypeEdge, CTypeGraph, CTypeNode


def to_igraph(document: CTypeGraph) -> ig.Graph:
    graph = ig.Graph(n=len(document.nodes), directed=True)
    for index, node in enumerate(document.nodes):
        graph.vs[index].update_attributes(_node_attributes(node))

    indices = {node.id: index for index, node in enumerate(document.nodes)}
    graph.add_edges(
        (indices[edge.source], indices[edge.target]) for edge in document.edges
    )
    for projected, edge in zip(graph.es, document.edges, strict=True):
        projected.update_attributes(_edge_attributes(edge))
    return graph


def export_graphml(document: CTypeGraph, path: str | Path) -> None:
    to_igraph(document).write_graphml(str(path))


def _node_attributes(node: CTypeNode) -> dict[str, str]:
    tags = {} if node.tags is None else node.tags
    return {
        "name": node.id,
        "label": node.id,
        "aliases": "\n".join(node.names[1:]),
        "methods": "\n".join(node.methods),
        "tags": "\n".join(f"{key}: {value}" for key, value in tags.items()),
        "names_json": _compact_json(node.names),
        "methods_json": _compact_json(node.methods),
        "tags_json": _compact_json(None if node.tags is None else dict(node.tags)),
    }


def _edge_attributes(edge: CTypeEdge) -> dict[str, str]:
    return {
        "ast_paths": "\n".join(_readable_path(path) for path in edge.ast_paths),
        "ast_paths_json": _compact_json(edge.ast_paths),
    }


def _readable_path(path: tuple[str, ...]) -> str:
    return " → ".join(path) if path else "(empty path)"


def _compact_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
