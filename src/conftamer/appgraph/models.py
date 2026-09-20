from typing import Annotated, Literal, Self

from pydantic import BaseModel, Field, model_validator

from conftamer.pmgraph.models import Parameter


class LinkedMessage(BaseModel):
    kind: Literal["linked_message"] = "linked_message"
    api_id: str
    method: str
    pattern: str
    status_code: int | None = None
    sender_module: str
    sender_node: str
    receiver_module: str
    receiver_node: str

    @model_validator(mode="after")
    def validate_linked_message(self) -> Self:
        if not self.api_id:
            raise ValueError("api_id must be nonempty")
        if not self.method:
            raise ValueError("method must be nonempty")
        if not self.pattern:
            raise ValueError("pattern must be nonempty")
        if not self.sender_module or not self.receiver_module:
            raise ValueError("sender_module and receiver_module must be nonempty")
        if not self.sender_node or not self.receiver_node:
            raise ValueError("sender_node and receiver_node must be nonempty")
        if self.sender_module == self.receiver_module:
            raise ValueError("sender_module and receiver_module must differ")
        return self


AppGraphNode = Annotated[Parameter | LinkedMessage, Field(discriminator="kind")]


class AppGraph(BaseModel):
    nodes: dict[str, AppGraphNode]
    edges: set[tuple[str, str]]  # (source node ID, target node ID)

    @model_validator(mode="after")
    def validate_graph(self) -> Self:
        if "" in self.nodes:
            raise ValueError("node ID '' must be nonempty")
        for source, target in self.edges:
            if source not in self.nodes or target not in self.nodes:
                raise ValueError(f"edge {(source, target)!r} has a missing endpoint")
        return self
