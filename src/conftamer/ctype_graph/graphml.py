import json
from itertools import chain
from pathlib import Path
from tempfile import NamedTemporaryFile

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
    graph = to_igraph(document)
    _validate_xml_attributes(graph)
    output = Path(path)
    with NamedTemporaryFile(dir=output.parent, delete=False) as temporary:
        temporary_path = Path(temporary.name)
    try:
        try:
            graph.write_graphml(str(temporary_path))
        except ig.InternalError as error:
            raise ValueError(f"could not write GraphML: {error}") from error
        temporary_path.replace(output)
    finally:
        temporary_path.unlink(missing_ok=True)


def _validate_xml_attributes(graph: ig.Graph) -> None:
    for element in chain(graph.vs, graph.es):
        for value in element.attributes().values():
            if any(not _is_xml_character(character) for character in value):
                raise ValueError("GraphML attributes must use valid XML 1.0 characters")


def _is_xml_character(character: str) -> bool:
    codepoint = ord(character)
    return (
        codepoint in {0x9, 0xA, 0xD}
        or 0x20 <= codepoint <= 0xD7FF
        or 0xE000 <= codepoint <= 0xFFFD
        or 0x10000 <= codepoint <= 0x10FFFF
    )


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
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
