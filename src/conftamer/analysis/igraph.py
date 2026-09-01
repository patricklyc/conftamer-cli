import json
from collections.abc import Iterable
from pathlib import Path
from typing import Literal

import igraph as ig

from conftamer.appgraph import AppGraph, AppNode
from conftamer.ctype_graph import CTypeGraph
from conftamer.paramtrack import ParamTrackRecord
from conftamer.pmgraph import (
    BehaviorNode,
    ParameterNode,
    PMGraph,
    PMNode,
    ReceiveRequestNode,
    ReceiveResponseNode,
    SendResponseNode,
)

_PM_ATTRIBUTES = (
    "name",
    "canonical_id",
    "label",
    "node_type",
    "module_ids",
    "match_status",
    "message",
    "api_id",
    "method",
    "host",
    "path",
    "pattern",
    "status",
    "members_json",
)


GraphDocument = PMGraph | AppGraph


def to_igraph(document: GraphDocument) -> ig.Graph:
    graph = ig.Graph(n=len(document.nodes), directed=True)
    if isinstance(document, AppGraph):
        for index, node in enumerate(document.nodes):
            graph.vs[index].update_attributes(_app_attributes(node))
    else:
        for index, node in enumerate(document.nodes):
            graph.vs[index].update_attributes(_pm_attributes(document.module_id, node))
    indices = {node.id: index for index, node in enumerate(document.nodes)}
    graph.add_edges(
        (indices[edge.source], indices[edge.target]) for edge in document.edges
    )
    return graph


def ctype_to_igraph(document: CTypeGraph) -> ig.Graph:
    graph = ig.Graph(n=len(document.nodes), directed=True)
    for index, node in enumerate(document.nodes):
        graph.vs[index].update_attributes(
            {
                "name": node.id,
                "label": node.id,
                "names_json": _canonical_json(node.names),
                "methods_json": _canonical_json(node.methods),
                "tags_json": ""
                if node.tags is None
                else _canonical_json(dict(node.tags)),
            }
        )
    indices = {node.id: index for index, node in enumerate(document.nodes)}
    graph.add_edges(
        (indices[edge.source], indices[edge.target]) for edge in document.edges
    )
    for projected, edge in zip(graph.es, document.edges, strict=True):
        projected["ast_paths_json"] = _canonical_json(edge.ast_paths)
    return graph


def paramtrack_to_igraph(records: Iterable[ParamTrackRecord]) -> ig.Graph:
    ordered = tuple(sorted(records, key=lambda record: record.input_line))
    ctypes = sorted({record.ctype for record in ordered if record.ctype})
    parameters = sorted({key for record in ordered for key in record.keys if key})
    vertices = [
        {
            "name": f"row:{record.input_line}",
            "label": f"line {record.input_line}: {record.verb} {record.resource}",
            "node_type": "Row",
            "source_line": str(record.input_line),
            "api": record.api,
            "verb": record.verb,
            "resource": record.resource,
            "ctype": record.ctype,
            "parameter_key": "",
        }
        for record in ordered
    ]
    vertices.extend(_association_attributes("CType", value) for value in ctypes)
    vertices.extend(_association_attributes("Parameter", value) for value in parameters)

    graph = ig.Graph(n=len(vertices), directed=False)
    for vertex, attributes in zip(graph.vs, vertices, strict=True):
        vertex.update_attributes(attributes)
    indices = {vertex["name"]: vertex.index for vertex in graph.vs}
    edges = []
    relations = []
    for record in ordered:
        row = indices[f"row:{record.input_line}"]
        if record.ctype:
            edges.append((row, indices[f"ctype:{record.ctype}"]))
            relations.append("ctype")
        for key in sorted({key for key in record.keys if key}):
            edges.append((row, indices[f"parameter:{key}"]))
            relations.append("parameter")
    graph.add_edges(edges)
    graph.es["relation"] = relations
    return graph


def _association_attributes(node_type: str, value: str) -> dict[str, str]:
    prefix = node_type.lower()
    attributes = {
        "name": f"{prefix}:{value}",
        "label": value,
        "node_type": node_type,
        "source_line": "",
        "api": "",
        "verb": "",
        "resource": "",
        "ctype": "",
        "parameter_key": "",
    }
    attributes["ctype" if node_type == "CType" else "parameter_key"] = value
    return attributes


def find_vertices(graph: ig.Graph, query: str) -> tuple[int, ...]:
    if not query:
        raise ValueError("search query must not be empty")

    exact = _exact_names(graph, query)
    if exact:
        return exact

    search = query.strip()
    if not search:
        raise ValueError("search query must not be empty")
    exact = _exact_names(graph, search)
    if exact:
        return exact

    folded = search.casefold()
    return tuple(
        vertex.index
        for vertex in graph.vs
        if any(
            folded in str(value).casefold()
            for value in vertex.attributes().values()
            if value is not None
        )
    )


def _exact_names(graph: ig.Graph, query: str) -> tuple[int, ...]:
    return tuple(
        vertex.index for vertex in graph.vs if vertex.attributes().get("name") == query
    )


def influence_subgraph(
    graph: ig.Graph,
    vertices: Iterable[int],
    *,
    direction: Literal["ancestors", "descendants", "both"],
) -> ig.Graph:
    if direction not in {"ancestors", "descendants", "both"}:
        raise ValueError(f"unknown influence direction {direction!r}")

    selected = set(vertices)
    reached = set(selected)
    modes = {
        "ancestors": ("in",),
        "descendants": ("out",),
        "both": ("in", "out"),
    }
    for vertex in selected:
        for mode in modes[direction]:
            reached.update(graph.subcomponent(vertex, mode=mode))
    return graph.induced_subgraph(sorted(reached))


def write_graphml(graph: ig.Graph, path: str | Path) -> None:
    _validate_graphml_strings(graph)
    graph.write_graphml(str(path))


def _validate_graphml_strings(graph: ig.Graph) -> None:
    for name in graph.attributes():
        _validate_xml_string(graph[name], f"graph attribute {name!r}")
    for kind, elements in (("vertex", graph.vs), ("edge", graph.es)):
        for element in elements:
            for name, value in element.attributes().items():
                _validate_xml_string(value, f"{kind} attribute {name!r}")


def _validate_xml_string(value: object, location: str) -> None:
    if not isinstance(value, str):
        return
    for character in value:
        codepoint = ord(character)
        allowed = (
            codepoint in {0x09, 0x0A, 0x0D}
            or 0x20 <= codepoint <= 0xD7FF
            or 0xE000 <= codepoint <= 0xFFFD
            or 0x10000 <= codepoint <= 0x10FFFF
        )
        if not allowed:
            raise ValueError(
                f"{location} contains XML 1.0-forbidden character U+{codepoint:04X}"
            )


def _app_attributes(node: AppNode) -> dict[str, str]:
    attributes = dict.fromkeys(_PM_ATTRIBUTES, "")
    members = node.members
    attributes.update(
        name=node.id,
        canonical_id=node.id,
        label=" ↔ ".join(_pm_label(member.node) for member in members),
        node_type="/".join(sorted({member.node.type for member in members})),
        module_ids=_canonical_json(sorted({member.module_id for member in members})),
        match_status=node.match.status,
        members_json=_canonical_json(
            [member.model_dump(mode="json") for member in members]
        ),
    )
    for name in ("message", "api_id", "method", "host", "path", "pattern", "status"):
        values = {
            str(value)
            for member in members
            if (value := member.node.model_dump().get(name)) is not None
        }
        attributes[name] = values.pop() if len(values) == 1 else ""
    return attributes


def _pm_attributes(module_id: str, node: PMNode) -> dict[str, str]:
    attributes = dict.fromkeys(_PM_ATTRIBUTES, "")
    attributes.update(
        name=node.id,
        canonical_id=node.id,
        label=_pm_label(node),
        node_type=node.type,
        module_ids=_canonical_json([module_id]),
    )
    fields = node.model_dump()
    for name in ("message", "api_id", "method", "host", "path", "pattern", "status"):
        value = fields.get(name)
        attributes[name] = "" if value is None else str(value)
    return attributes


def _pm_label(node: PMNode) -> str:
    if isinstance(node, (ParameterNode, BehaviorNode)):
        return f"{node.type}: {node.name}"
    if isinstance(node, (ReceiveRequestNode, SendResponseNode)):
        location = node.pattern
    else:
        location = node.path
    label = f"{node.type} {node.message}: {node.method} {location}"
    if isinstance(node, (ReceiveResponseNode, SendResponseNode)):
        return f"{label} {node.status}"
    return label


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
