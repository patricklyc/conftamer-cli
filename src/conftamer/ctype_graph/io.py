from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from conftamer.diagnostics import NonEmptyString
from conftamer.ctype_graph.models import CTypeEdge, CTypeGraph, CTypeNode


class _RawModel(BaseModel):
    model_config = ConfigDict(extra="allow", strict=True)


class _RawVertex(_RawModel):
    names: Annotated[tuple[NonEmptyString, ...], Field(alias="Names", min_length=1)]
    methods: tuple[NonEmptyString, ...] = Field(alias="Methods")
    tags: dict[str, str] | None = Field(alias="Tags")


class _RawProperties(_RawModel):
    data: tuple[tuple[str, ...] | None, ...] | None = Field(alias="Data")


class _RawEdge(_RawModel):
    source: NonEmptyString = Field(alias="Source")
    target: NonEmptyString = Field(alias="Target")
    properties: _RawProperties = Field(alias="Properties")


class _RawDocument(_RawModel):
    edges: tuple[_RawEdge, ...] = Field(alias="Edges")
    vertices: tuple[_RawVertex, ...] = Field(alias="Vertices")
    name_mapping: dict[str, str] = Field(alias="List")


def load_ctype_graph(path: str | Path) -> CTypeGraph:
    input_path = Path(path)
    text = input_path.read_text(encoding="utf-8")
    _validate_transport(input_path, text)
    raw = _RawDocument.model_validate_json(text)
    return _normalize(raw)


def _validate_transport(path: Path, text: str) -> None:
    suffix = path.suffix.lower()
    content = text.lstrip().lower()
    if suffix == ".gv" or content.startswith(
        ("digraph", "graph", "strict digraph", "strict graph")
    ):
        raise ValueError("Graphviz CType input is not supported")
    if suffix == ".graphml" or content.startswith("<"):
        raise ValueError("GraphML CType input is not supported")
    if suffix != ".text" and not content.startswith("{"):
        raise ValueError("unsupported CType graph format")


def _normalize(raw: _RawDocument) -> CTypeGraph:
    vertex_ids = [vertex.names[0] for vertex in raw.vertices]
    if len(set(vertex_ids)) != len(vertex_ids):
        raise ValueError("vertex IDs must be unique")
    node_ids = set(vertex_ids)

    _validate_name_mapping(raw)
    _validate_edges(raw, node_ids)

    nodes = [_normalize_node(vertex) for vertex in raw.vertices]
    edges = [_normalize_edge(edge) for edge in raw.edges]
    name_to_node = {
        name: target for name, target in raw.name_mapping.items() if target in node_ids
    }
    return CTypeGraph(
        nodes=tuple(sorted(nodes, key=lambda node: node.id)),
        edges=tuple(sorted(edges, key=lambda edge: (edge.source, edge.target))),
        name_to_node=name_to_node,
    )


def _validate_name_mapping(raw: _RawDocument) -> None:
    if any(not name or not target for name, target in raw.name_mapping.items()):
        raise ValueError("List mappings must contain nonempty strings")

    owners: dict[str, str] = {}
    for vertex in raw.vertices:
        vertex_id = vertex.names[0]
        for name in vertex.names:
            owner = owners.get(name)
            if owner is not None and owner != vertex_id:
                raise ValueError(
                    f"represented name {name!r} belongs to multiple vertices"
                )
            owners[name] = vertex_id
            mapped = raw.name_mapping.get(name)
            if mapped is None:
                raise ValueError(f"missing mapping for represented name {name!r}")
            if mapped != vertex_id:
                raise ValueError(
                    f"mapping for represented name {name!r} must target {vertex_id!r}"
                )


def _validate_edges(raw: _RawDocument, node_ids: set[str]) -> None:
    pairs = [(edge.source, edge.target) for edge in raw.edges]
    if len(set(pairs)) != len(pairs):
        raise ValueError("edge endpoint pairs must be unique")
    if any(
        source not in node_ids or target not in node_ids for source, target in pairs
    ):
        raise ValueError("edge endpoints must reference represented vertices")


def _normalize_node(vertex: _RawVertex) -> CTypeNode:
    vertex_id = vertex.names[0]
    aliases = sorted(set(vertex.names[1:]) - {vertex_id})
    return CTypeNode(
        id=vertex_id,
        names=(vertex_id, *aliases),
        methods=tuple(sorted(set(vertex.methods))),
        tags=vertex.tags,
    )


def _normalize_edge(edge: _RawEdge) -> CTypeEdge:
    raw_paths = edge.properties.data or ()
    paths = {() if path is None else tuple(path) for path in raw_paths}
    return CTypeEdge(
        source=edge.source,
        target=edge.target,
        ast_paths=tuple(sorted(paths)),
    )
