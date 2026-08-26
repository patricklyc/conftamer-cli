# `src/conftamer/csv_graph.py`


## Responsible for
- Defining the node representation used by the legacy CSV workflow.
- Parsing the two supported headerless CSV edge shapes.
- Constructing directed `igraph` graphs with stable first-seen vertex order.
- Finding vertices with case-insensitive attribute substring searches.
- Selecting the incoming and outgoing component around one graph vertex.

This module is separate from the PMGraph schema and exists for compatibility
with the original CSV-to-GraphML workflow.

## Public interface
```python
class NodeType(str, Enum):
    PARAMETER = "Parameter"
    RECEIVE = "Receive"
    SEND = "Send"


class BaseNode(BaseModel, frozen=True): ...


class ParameterNode(BaseNode):
    node_type: Literal[NodeType.PARAMETER] = NodeType.PARAMETER
    module_id: str
    param_name: str


class ReceiveNode(BaseNode):
    node_type: Literal[NodeType.RECEIVE] = NodeType.RECEIVE
    module_id: str
    api_id: str
    request_pattern: str
    response_code: int


class SendNode(BaseNode):
    node_type: Literal[NodeType.SEND] = NodeType.SEND
    module_id: str
    api_id: str
    request_id: str
    response_code: int


def read_csv(file_path: str) -> list[tuple[BaseNode, BaseNode]]: ...


def to_graph(edges: list[tuple[BaseNode, BaseNode]]) -> ig.Graph: ...


def find_nodes(graph: ig.Graph, query: str) -> list[int]: ...


def to_subgraph(graph: ig.Graph, node_id: int) -> ig.Graph: ...
```
