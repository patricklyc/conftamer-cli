from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class NodeType(str, Enum):
    PARAMETER = "Parameter"
    RECEIVE = "Receive"
    SEND = "Send"
    BEHAVIOR = "Behavior"


class ParameterNode(BaseModel):
    node_type: Literal[NodeType.PARAMETER] = NodeType.PARAMETER
    module_id: str = Field(
        description="Organization or module identifier (e.g., 'orgA/A')",
    )
    name: str = Field(
        description="Name of configuration parameter",
    )


class ReceiveNode(BaseModel):
    node_type: Literal[NodeType.RECEIVE] = NodeType.RECEIVE
    module_id: str
    api_id: str
    request_pattern: str
    respond_code: int


class SendNode(BaseModel):
    node_type: Literal[NodeType.SEND] = NodeType.SEND
    module_id: str
    api_id: str
    request_id: str
    respond_code: int
