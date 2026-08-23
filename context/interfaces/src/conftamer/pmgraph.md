# `src/conftamer/pmgraph.py`


## Responsible for
- Defining the serialized PMGraph node, edge, and graph schema.
- Validating node identity and directed edge constraints.
- Generating deterministic node IDs from semantic fields.
- Deduplicating and ordering graph contents built by this package.
- Serializing validated PMGraph JSON.

## Public interface
```python
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


def make_node_id(module_id: str, fields: Mapping[str, object]) -> str: ...


def make_pmgraph(
    module_id: str,
    nodes: Iterable[PMNode],
    edges: Iterable[PMEdge],
) -> PMGraph: ...


def write_pmgraph(graph: PMGraph, path: str | Path) -> None: ...
```

`PMGraph` validation requires unique node IDs, existing edge endpoints, no
self-edges, a Receive or Parameter source, and a Send target. `make_pmgraph()`
additionally deduplicates and sorts nodes and edges; direct model validation
does not normalize ordering or reject duplicate edges.
