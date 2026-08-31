import json
from collections.abc import Iterable
from pathlib import Path
from typing import Literal

import igraph as ig

from conftamer.appgraph import AppGraph, AppNode
from conftamer.ctype_graph import CTypeGraph
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


def find_vertices(graph: ig.Graph, query: str) -> tuple[int, ...]:
    search = query.strip()
    if not search:
        raise ValueError("search query must not be empty")

    exact = tuple(
        vertex.index for vertex in graph.vs if vertex.attributes().get("name") == search
    )
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
    graph.write_graphml(str(path))


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
