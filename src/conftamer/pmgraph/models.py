from typing import Annotated, Literal, Self

from pydantic import BaseModel, Field, model_validator


class Parameter(BaseModel):
    kind: Literal["parameter"] = "parameter"
    key: str


class Message(BaseModel):
    kind: Literal[
        "send_request",
        "receive_request",
        "send_response",
        "receive_response",
    ]
    api_id: str | None
    method: str
    host: str | None = None
    path: str | None = None
    pattern: str | None = None
    status_code: int | None = None

    @model_validator(mode="after")
    def validate_message(self) -> Self:
        if not self.method:
            raise ValueError("method must be nonempty")
        if (self.path is None) == (self.pattern is None):
            raise ValueError("exactly one of path and pattern must be present")
        if self.pattern == "":
            raise ValueError("pattern must be nonempty")
        is_response = self.kind in ("send_response", "receive_response")
        if is_response != (self.status_code is not None):
            raise ValueError("responses require status_code; requests forbid it")
        if self.kind in ("send_request", "receive_response"):
            if not self.host or self.path is None:
                raise ValueError("client messages require a nonempty host and a path")
        elif self.host is not None:
            raise ValueError("server messages must have host=None")
        return self


Node = Annotated[Parameter | Message, Field(discriminator="kind")]


class PMGraph(BaseModel):
    module_id: str
    nodes: dict[str, Node]
    edges: set[tuple[str, str]]  # (source node ID, target node ID)

    @model_validator(mode="after")
    def validate_graph(self) -> Self:
        if not self.module_id:
            raise ValueError(f"module_id must be nonempty, got {self.module_id!r}")
        if "" in self.nodes:
            raise ValueError("node ID '' must be nonempty")
        for source, target in self.edges:
            if source not in self.nodes or target not in self.nodes:
                raise ValueError(f"edge {(source, target)!r} has a missing endpoint")
        return self
