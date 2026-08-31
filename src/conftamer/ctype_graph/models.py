from collections.abc import Mapping
from types import MappingProxyType
from typing import Annotated

from pydantic import Field, field_serializer, field_validator, model_validator

from conftamer.diagnostics import CanonicalModel, NonEmptyString


class CTypeNode(CanonicalModel):
    id: NonEmptyString
    names: Annotated[tuple[NonEmptyString, ...], Field(min_length=1)]
    methods: tuple[NonEmptyString, ...]
    tags: Mapping[str, str] | None

    @field_validator("tags")
    @classmethod
    def freeze_tags(cls, tags: Mapping[str, str] | None) -> Mapping[str, str] | None:
        return None if tags is None else _freeze_mapping(tags)

    @field_serializer("tags")
    def serialize_tags(self, tags: Mapping[str, str] | None) -> dict[str, str] | None:
        return None if tags is None else dict(tags)

    @model_validator(mode="after")
    def validate_node(self) -> "CTypeNode":
        if self.names[0] != self.id:
            raise ValueError("the first node name must equal its ID")
        expected_names = (self.id, *sorted(set(self.names[1:]) - {self.id}))
        if self.names != expected_names:
            raise ValueError("node names must be deduplicated and in canonical order")
        if self.methods != tuple(sorted(set(self.methods))):
            raise ValueError("methods must be in canonical order")
        return self


class CTypeEdge(CanonicalModel):
    source: NonEmptyString
    target: NonEmptyString
    ast_paths: tuple[tuple[str, ...], ...]

    @field_validator("ast_paths")
    @classmethod
    def validate_path_order(
        cls, ast_paths: tuple[tuple[str, ...], ...]
    ) -> tuple[tuple[str, ...], ...]:
        if ast_paths != tuple(sorted(set(ast_paths))):
            raise ValueError("AST paths must be in canonical order")
        return ast_paths


class CTypeGraph(CanonicalModel):
    nodes: tuple[CTypeNode, ...]
    edges: tuple[CTypeEdge, ...]
    name_to_node: Mapping[str, str]

    @field_validator("name_to_node")
    @classmethod
    def freeze_name_mapping(cls, mapping: Mapping[str, str]) -> Mapping[str, str]:
        if any(not key or not value for key, value in mapping.items()):
            raise ValueError("name mappings must contain nonempty strings")
        return _freeze_mapping(mapping)

    @field_serializer("name_to_node")
    def serialize_name_mapping(self, mapping: Mapping[str, str]) -> dict[str, str]:
        return dict(mapping)

    @model_validator(mode="after")
    def validate_graph(self) -> "CTypeGraph":
        node_ids = [node.id for node in self.nodes]
        if len(set(node_ids)) != len(node_ids):
            raise ValueError("vertex IDs must be unique")
        if self.nodes != tuple(sorted(self.nodes, key=lambda node: node.id)):
            raise ValueError("nodes must be in canonical order")

        ids = set(node_ids)
        self._validate_names(ids)
        self._validate_edges(ids)
        return self

    def _validate_names(self, node_ids: set[str]) -> None:
        owners: dict[str, str] = {}
        for node in self.nodes:
            for name in node.names:
                owner = owners.get(name)
                if owner is not None and owner != node.id:
                    raise ValueError(
                        f"represented name {name!r} belongs to multiple nodes"
                    )
                owners[name] = node.id
                mapped = self.name_to_node.get(name)
                if mapped is None:
                    raise ValueError(f"missing mapping for represented name {name!r}")
                if mapped != node.id:
                    raise ValueError(
                        f"mapping for represented name {name!r} must target {node.id!r}"
                    )
        if any(target not in node_ids for target in self.name_to_node.values()):
            raise ValueError("name mappings must target represented vertices")

    def _validate_edges(self, node_ids: set[str]) -> None:
        endpoint_pairs = [(edge.source, edge.target) for edge in self.edges]
        if len(set(endpoint_pairs)) != len(endpoint_pairs):
            raise ValueError("edge endpoint pairs must be unique")
        if self.edges != tuple(
            sorted(self.edges, key=lambda edge: (edge.source, edge.target))
        ):
            raise ValueError("edges must be in canonical order")
        if any(
            edge.source not in node_ids or edge.target not in node_ids
            for edge in self.edges
        ):
            raise ValueError("edge endpoints must reference represented vertices")


def _freeze_mapping(mapping: Mapping[str, str]) -> Mapping[str, str]:
    return MappingProxyType(dict(sorted(mapping.items())))
