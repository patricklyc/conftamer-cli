import csv
import itertools
from enum import Enum
from typing import Literal

import igraph as ig
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
    response_code: int


class SendNode(BaseNode):
    node_type: Literal[NodeType.SEND] = NodeType.SEND
    module_id: str
    api_id: str
    request_id: str
    response_code: int


def read_csv(file_path: str) -> list[tuple[BaseNode, BaseNode]]:
    edges = []

    with open(file_path) as csvfile:
        reader = csv.reader(csvfile)
        for row in reader:
            match row:
                case [
                    "Parameter",
                    module_id,
                    param_name,
                    "Send",
                    _module_id,
                    api_id,
                    request_id,
                    response_code,
                ]:
                    edges.append(
                        (
                            ParameterNode(
                                node_type=NodeType.PARAMETER,
                                module_id=module_id,
                                param_name=param_name,
                            ),
                            SendNode(
                                node_type=NodeType.SEND,
                                module_id=_module_id,
                                api_id=api_id,
                                request_id=request_id,
                                response_code=response_code,
                            ),
                        )
                    )
                case [
                    "Receive",
                    module_id,
                    api_id,
                    request_pattern,
                    response_code,
                    "Send",
                    _module_id,
                    _api_id,
                    request_id,
                    _response_code,
                ]:
                    edges.append(
                        (
                            ReceiveNode(
                                node_type=NodeType.RECEIVE,
                                module_id=module_id,
                                api_id=api_id,
                                request_pattern=request_pattern,
                                response_code=response_code,
                            ),
                            SendNode(
                                node_type=NodeType.SEND,
                                module_id=_module_id,
                                api_id=_api_id,
                                request_id=request_id,
                                response_code=_response_code,
                            ),
                        )
                    )
                case _:
                    raise ValueError("parsing error")

    return edges


def to_graph(edges: list[tuple[BaseNode, BaseNode]]) -> ig.Graph:
    nodes = itertools.chain.from_iterable(edges)
    vertices = list(dict.fromkeys(nodes))

    vertex_ids = {vertex: index for index, vertex in enumerate(vertices)}
    graph_edges = [(vertex_ids[source], vertex_ids[target]) for source, target in edges]
    attributes: list[dict[str, str]] = [vertex.model_dump() for vertex in vertices]
    for attribute in attributes:
        attribute["label"] = (
            f"{attribute.get('module_id')} "
            f"{attribute.get('param_name') or attribute.get('request_id') or attribute.get('request_pattern')}"
        )

    graph = ig.Graph(len(vertices), graph_edges, directed=True)
    for index, attribute in enumerate(attributes):
        graph.vs[index].update_attributes(attribute)
    return graph


def find_nodes(graph: ig.Graph, query: str) -> list[int]:
    normalized_query = query.strip().casefold()
    if not normalized_query:
        raise ValueError("search query must not be empty")

    return [
        vertex.index
        for vertex in graph.vs
        if any(
            normalized_query in str(value).casefold()
            for value in vertex.attributes().values()
            if value is not None
        )
    ]


def to_subgraph(graph: ig.Graph, node_id: int) -> ig.Graph:
    vertices = []
    vertices.extend(graph.subcomponent(node_id, mode="in"))
    vertices.extend(graph.subcomponent(node_id, mode="out"))
    subgraph: ig.Graph = graph.subgraph(vertices)
    return subgraph
