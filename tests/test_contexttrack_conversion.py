import json

from conftamer.contexttrack.conversion import parse_contexttrack
from conftamer.contexttrack.events import (
    EVENT_ADAPTER,
    EventRecord,
    group_events,
)
from conftamer.contexttrack.responses import match_responses
from conftamer.contexttrack.routes import match_routes
from conftamer.pmgraph import (
    ReceiveRequestNode,
    ReceiveResponseNode,
    SendRequestNode,
    SendResponseNode,
)


def record(sequence: int, event: dict) -> EventRecord:
    return EventRecord(
        sequence=sequence,
        input_line=sequence + 1,
        event=EVENT_ADAPTER.validate_python(event),
    )


def test_matches_routes_and_responses(tmp_path):
    context = {"context_id": "id:1"}
    records = [
        record(
            0,
            {
                "kind": "Request received",
                "pid": 10,
                "goroutine_id": 5,
                "message": {
                    "req.Method": "GET",
                    "req.URL.Path": "/items/1",
                },
                "context": context,
            },
        ),
        record(
            1,
            {
                "kind": "Request routed",
                "pid": 10,
                "message": {
                    "req.Method": "GET",
                    "req.URL.Path": "/items/1",
                    "pattern": "/items/{id}",
                },
                "context": context,
            },
        ),
        record(
            2,
            {
                "kind": "Request sent",
                "pid": 10,
                "goroutine_id": 7,
                "message": {
                    "req.Method": "POST",
                    "req.URL.Host": "inventory:8080",
                    "req.URL.Path": "/reserve",
                },
                "context": context,
            },
        ),
        record(
            3,
            {
                "kind": "Response received",
                "pid": 10,
                "goroutine_id": 7,
                "message": {
                    "resp.StatusCode": "200",
                    "req.Method": "POST",
                    "req.URL.Path": "/reserve",
                },
                "context": context,
            },
        ),
        record(
            4,
            {
                "kind": "Response sent",
                "pid": 10,
                "goroutine_id": 5,
                "message": {
                    "code": "201",
                    "req.Method": "GET",
                    "req.URL.Path": "/items/1",
                },
                "context": context,
            },
        ),
    ]
    groups, _ = group_events(records)

    routes, route_warnings = match_routes(groups)
    responses, response_warnings = match_responses(groups)

    assert routes == {0: "/items/{id}"}
    assert responses.received == {3: records[2]}
    assert responses.sent == {4: records[0]}
    assert route_warnings == []
    assert response_warnings == []

    event_file = tmp_path / "events.jsonl"
    event_file.write_text(
        "\n".join(
            json.dumps(item.event.model_dump(by_alias=True, exclude_none=True))
            for item in records
        )
    )
    graph = parse_contexttrack(
        event_file, module_id="example.org/service"
    ).graph
    nodes = {
        (node.type, getattr(node, "message", None)): node
        for node in graph.nodes
    }
    receive_request = nodes[("Receive", "Request")]
    send_request = nodes[("Send", "Request")]
    receive_response = nodes[("Receive", "Response")]
    send_response = nodes[("Send", "Response")]
    assert len(graph.nodes) == 4
    assert {(edge.source, edge.target) for edge in graph.edges} == {
        (receive_request.id, send_request.id),
        (receive_request.id, send_response.id),
        (receive_response.id, send_response.id),
    }


def test_preserves_outbound_api_id_and_normalizes_empty_http_path(tmp_path):
    context = {"context_id": "id:1"}
    events = [
        {
            "kind": "Request received",
            "pid": 10,
            "message": {"req.Method": "GET", "req.URL.Path": ""},
            "context": {"context_id": "id:2"},
            "api_id": "example.org/api",
        },
        {
            "kind": "Response sent",
            "pid": 10,
            "message": {
                "code": "204",
                "req.Method": "GET",
                "req.URL.Path": "",
            },
            "context": {"context_id": "id:2"},
        },
        {
            "kind": "Request sent",
            "pid": 10,
            "message": {
                "req.Method": "GET",
                "req.URL.Host": "example.org",
                "req.URL.Path": "",
            },
            "context": context,
            "request_id": {
                "method": "GET",
                "host": "example.org",
                "path": "",
            },
            "api_id": "example.org/api",
        },
        {
            "kind": "Response received",
            "pid": 10,
            "message": {
                "resp.StatusCode": "200",
                "req.Method": "GET",
                "req.URL.Path": "",
            },
            "context": context,
        },
        {
            "kind": "Response received",
            "pid": 10,
            "message": {
                "resp.StatusCode": "200",
                "req.Method": "GET",
                "req.URL.Path": "",
            },
            "context": context,
            "api_id": "example.org/api",
        },
    ]
    event_file = tmp_path / "events.jsonl"
    event_file.write_text("\n".join(json.dumps(event) for event in events))

    result = parse_contexttrack(event_file, module_id="example.org/service")

    sent = next(
        node
        for node in result.graph.nodes
        if isinstance(node, SendRequestNode)
    )
    received = next(
        node
        for node in result.graph.nodes
        if isinstance(node, ReceiveResponseNode)
    )
    receive_request = next(
        node
        for node in result.graph.nodes
        if isinstance(node, ReceiveRequestNode)
    )
    send_response = next(
        node
        for node in result.graph.nodes
        if isinstance(node, SendResponseNode)
    )
    assert sent.api_id == "example.org/api"
    assert sent.path == "/"
    assert received.api_id == "example.org/api"
    assert received.path == "/"
    assert receive_request.pattern == "/"
    assert send_response.pattern == "/"
    assert result.warnings == ()


def test_reports_request_without_host_as_unlabelable(tmp_path):
    event_file = tmp_path / "events.jsonl"
    event_file.write_text(
        json.dumps(
            {
                "kind": "Request sent",
                "pid": 10,
                "message": {
                    "req.Method": "GET",
                    "req.URL.Host": "",
                    "req.URL.Path": "",
                },
                "context": {"context_id": "id:1"},
                "request_id": {"method": "GET", "host": "", "path": ""},
                "api_id": "go.opentelemetry.io",
            }
        )
    )

    result = parse_contexttrack(event_file, module_id="example.org/service")

    assert result.graph.nodes == ()
    assert len(result.warnings) == 1
    assert result.warnings[0].message == "request endpoint has no host"
