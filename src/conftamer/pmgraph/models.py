from typing import Annotated, Literal

from pydantic import BaseModel, Field


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


Node = Annotated[Parameter | Message, Field(discriminator="kind")]


class PMGraph(BaseModel):
    module_id: str
    nodes: dict[str, Node]
    edges: set[tuple[str, str]]  # (source node ID, target node ID)
