import hashlib
import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

NonEmptyString = Annotated[str, StringConstraints(min_length=1)]
StatusCode = Annotated[int, Field(ge=100, le=999)]


class PMGraphModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ParameterNode(PMGraphModel):
    id: NonEmptyString
    type: Literal["Parameter"] = "Parameter"
    name: NonEmptyString


class MessageNode(PMGraphModel):
    id: NonEmptyString
    api_id: NonEmptyString | None
    method: NonEmptyString

    @field_validator("method")
    @classmethod
    def uppercase_method(cls, method: str) -> str:
        return method.upper()


class ReceiveRequestNode(MessageNode):
    type: Literal["Receive"] = "Receive"
    message: Literal["Request"] = "Request"
    pattern: NonEmptyString


class SendRequestNode(MessageNode):
    type: Literal["Send"] = "Send"
    message: Literal["Request"] = "Request"
    host: NonEmptyString
    path: NonEmptyString


class ReceiveResponseNode(MessageNode):
    type: Literal["Receive"] = "Receive"
    message: Literal["Response"] = "Response"
    host: NonEmptyString
    path: NonEmptyString
    status: StatusCode


class SendResponseNode(MessageNode):
    type: Literal["Send"] = "Send"
    message: Literal["Response"] = "Response"
    pattern: NonEmptyString
    status: StatusCode


PMNode = (
    ParameterNode
    | ReceiveRequestNode
    | SendRequestNode
    | ReceiveResponseNode
    | SendResponseNode
)


class PMEdge(PMGraphModel):
    source: NonEmptyString
    target: NonEmptyString


class PMGraph(PMGraphModel):
    format: Literal["conftamer.pmgraph"] = "conftamer.pmgraph"
    version: Literal[1] = 1
    module_id: NonEmptyString
    nodes: tuple[PMNode, ...]
    edges: tuple[PMEdge, ...]

    @model_validator(mode="after")
    def validate_edges(self) -> "PMGraph":
        nodes_by_id = {node.id: node for node in self.nodes}
        if len(nodes_by_id) != len(self.nodes):
            raise ValueError("node IDs must be unique")

        for edge in self.edges:
            source = nodes_by_id.get(edge.source)
            target = nodes_by_id.get(edge.target)

            if source is None or target is None:
                raise ValueError("edge endpoints must reference existing nodes")
            if source.id == target.id:
                raise ValueError("self-edges are not allowed")
            if source.type not in {"Receive", "Parameter"}:
                raise ValueError("source must be a Receive or Parameter node")
            if target.type != "Send":
                raise ValueError("target must be a Send node")

        return self


def make_node_id(module_id: str, fields: Mapping[str, object]) -> str:
    identity = {"module_id": module_id, **fields}
    encoded = json.dumps(
        identity,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return f"n:{hashlib.sha256(encoded).hexdigest()}"


def make_pmgraph(
    module_id: str,
    nodes: Iterable[PMNode],
    edges: Iterable[PMEdge],
) -> PMGraph:
    unique_nodes = sorted(set(nodes), key=lambda node: node.id)
    unique_edges = sorted(set(edges), key=lambda edge: (edge.source, edge.target))

    return PMGraph(
        module_id=module_id,
        nodes=tuple(unique_nodes),
        edges=tuple(unique_edges),
    )


def write_pmgraph(graph: PMGraph, path: str | Path) -> None:
    Path(path).write_text(graph.model_dump_json(indent=2) + "\n")
