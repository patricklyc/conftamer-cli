from enum import Enum
from typing import Literal

from pydantic import BaseModel


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


class ReceiveNode(BaseNode):
    node_type: Literal[NodeType.RECEIVE] = NodeType.RECEIVE
    module_id: str
    api_id: str
    request_pattern: str
    respond_code: int


class SendNode(BaseNode):
    node_type: Literal[NodeType.SEND] = NodeType.SEND
    module_id: str
    api_id: str
    request_id: str
    respond_code: int
