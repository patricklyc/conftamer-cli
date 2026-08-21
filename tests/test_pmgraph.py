import json

import pytest
from pydantic import ValidationError

from conftamer.pmgraph import (
    ParameterNode,
    PMEdge,
    PMGraph,
    ReceiveRequestNode,
    ReceiveResponseNode,
    SendRequestNode,
    SendResponseNode,
    make_node_id,
    make_pmgraph,
    write_pmgraph,
)


@pytest.mark.parametrize(
    "node",
    [
        ParameterNode(id="parameter", name="request_timeout"),
        ReceiveRequestNode(
            id="receive-request",
            api_id="example.org/service",
            method="GET",
            pattern="/items/{id}",
        ),
        SendRequestNode(
            id="send-request",
            api_id=None,
            method="POST",
            host="inventory:8080",
            path="/reserve",
        ),
        ReceiveResponseNode(
            id="receive-response",
            api_id=None,
            method="POST",
            host="inventory:8080",
            path="/reserve",
            status=200,
        ),
        SendResponseNode(
            id="send-response",
            api_id="example.org/service",
            method="GET",
            pattern="/items/{id}",
            status=201,
        ),
    ],
)
def test_node_shapes_round_trip(node):
    assert type(node).model_validate_json(node.model_dump_json()) == node


def test_graph_rejects_invalid_edge_direction():
    receive = ReceiveRequestNode(
        id="receive",
        api_id=None,
        method="GET",
        pattern="/items",
    )
    parameter = ParameterNode(id="parameter", name="request_timeout")

    with pytest.raises(ValidationError, match="target must be a Send node"):
        make_pmgraph(
            "example.org/service",
            [receive, parameter],
            [PMEdge(source=receive.id, target=parameter.id)],
        )


def test_ids_and_graph_output_are_deterministic(tmp_path):
    fields = {
        "type": "Send",
        "message": "Request",
        "api_id": None,
        "method": "POST",
        "host": "inventory:8080",
        "path": "/reserve",
    }
    reversed_fields = dict(reversed(list(fields.items())))

    assert make_node_id("example.org/service", fields) == make_node_id(
        "example.org/service", reversed_fields
    )

    receive = ReceiveRequestNode(
        id="z-receive",
        api_id=None,
        method="GET",
        pattern="/items",
    )
    send = SendRequestNode(
        id="a-send",
        api_id=None,
        method="POST",
        host="inventory:8080",
        path="/reserve",
    )
    graph = make_pmgraph(
        "example.org/service",
        [receive, send, receive],
        [
            PMEdge(source=receive.id, target=send.id),
            PMEdge(source=receive.id, target=send.id),
        ],
    )

    assert [node.id for node in graph.nodes] == ["a-send", "z-receive"]
    assert graph.edges == (PMEdge(source="z-receive", target="a-send"),)

    output = tmp_path / "graph.json"
    write_pmgraph(graph, output)
    text = output.read_text()
    assert json.loads(text) == graph.model_dump(mode="json")
    assert PMGraph.model_validate_json(text) == graph
    assert text.endswith("\n")
