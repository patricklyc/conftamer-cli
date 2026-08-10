from enum import Enum
from typing import Literal, Self

from pydantic import BaseModel, model_validator


class NodeType(str, Enum):
    PARAMETER = "Parameter"
    RECEIVE = "Receive"
    SEND = "Send"


class BaseNode(BaseModel, frozen=True):
    pass


class ParameterNode(BaseNode):
    node_type: Literal[NodeType.PARAMETER] = NodeType.PARAMETER
    module_id: str
    param_name: str

    # @model_validator(mode="after")
    # def write_igraph_vertex_name(self) -> Self:
    #     self.name = str(self)
    #     return self


class ReceiveNode(BaseNode):
    node_type: Literal[NodeType.RECEIVE] = NodeType.RECEIVE
    module_id: str
    api_id: str
    request_pattern: str
    respond_code: int

    # @model_validator(mode="after")
    # def write_igraph_vertex_name(self) -> Self:
    #     self.name = str(self)
    #     return self


class SendNode(BaseNode):
    node_type: Literal[NodeType.SEND] = NodeType.SEND
    module_id: str
    api_id: str
    request_id: str
    respond_code: int

    # @model_validator(mode="after")
    # def write_igraph_vertex_name(self) -> Self:
    #     self.name = str(self)
    #     return self
