import json

import pytest
from pydantic import ValidationError

from conftamer.contexttrack.events import (
    EVENT_ADAPTER,
    ContextInfo,
    EventRecord,
    ReceivedResponseMessage,
    RequestID,
    RequestMessage,
    RequestSentEvent,
    ResponseReceivedEvent,
    read_events,
)
from conftamer.contexttrack.matching import (
    group_events,
    match_responses,
    match_routes,
)
from conftamer.contexttrack.parser import parse_contexttrack


def test_request_sent_preserves_nested_input():
    event = EVENT_ADAPTER.validate_python(
        {
            "kind": "Request sent",
            "pid": 42,
            "goroutine_id": 7,
            "file": "/go/src/net/http/transport.go",
            "line": 599,
            "message": {
                "req.Method": "POST",
                "req.URL.Host": "inventory:8080",
                "req.URL.Path": "/reserve",
                "req.URL.RawQuery": "",
                "future_message_field": "kept",
            },
            "context": {
                "source": "req.Context()",
                "type": "context.Context",
                "context_id": "id:3",
                "future_context_field": "kept",
            },
            "request_id": {
                "method": "POST",
                "host": "inventory:8080",
                "path": "/reserve",
            },
            "api_id": "example.org/frontend",
        }
    )

    assert isinstance(event, RequestSentEvent)
    assert isinstance(event.message, RequestMessage)
    assert isinstance(event.context, ContextInfo)
    assert isinstance(event.request_id, RequestID)
    assert event.message.method == "POST"
    assert event.context.context_id == "id:3"
    assert event.request_id.host == "inventory:8080"

    dumped = event.model_dump(by_alias=True)
    assert dumped["message"]["req.Method"] == "POST"
    assert dumped["message"]["future_message_field"] == "kept"
    assert dumped["context"]["future_context_field"] == "kept"


def test_response_status_is_parsed_as_integer():
    event = EVENT_ADAPTER.validate_python(
        {
            "kind": "Response received",
            "pid": 42,
            "message": {
                "resp.StatusCode": "201",
                "req.Method": "POST",
                "req.URL.Path": "/reserve",
            },
            "context": {"context_id": "id:3"},
        }
    )

    assert isinstance(event, ResponseReceivedEvent)
    assert isinstance(event.message, ReceivedResponseMessage)
    assert event.message.status == 201


def test_unknown_event_kind_is_rejected():
    with pytest.raises(ValidationError):
        EVENT_ADAPTER.validate_python(
            {
                "kind": "Unknown",
                "pid": 42,
                "message": {},
                "context": {"context_id": "id:3"},
            }
        )


def request_sent(pid: int, context_id: str | None) -> dict:
    return {
        "kind": "Request sent",
        "pid": pid,
        "message": {
            "req.Method": "GET",
            "req.URL.Host": "example.org",
            "req.URL.Path": "/items",
        },
        "context": {"context_id": context_id},
    }


def test_read_events_warns_and_continues_after_bad_line(tmp_path):
    event_file = tmp_path / "events.jsonl"
    event_file.write_text(
        "\n".join(
            [
                json.dumps(request_sent(10, "id:1")),
                "{bad json",
                "",
                json.dumps(request_sent(10, "id:2")),
            ]
        )
    )

    records, warnings = read_events(event_file)

    assert [record.input_line for record in records] == [1, 4]
    assert [record.sequence for record in records] == [0, 1]
    assert len(warnings) == 1
    assert warnings[0].input_line == 2


def test_group_events_separates_processes_and_missing_context():
    events = [
        EVENT_ADAPTER.validate_python(request_sent(10, "id:1")),
        EVENT_ADAPTER.validate_python(request_sent(20, "id:1")),
        EVENT_ADAPTER.validate_python(request_sent(10, None)),
    ]
    records = [
        EventRecord(sequence=index, input_line=index + 1, event=event)
        for index, event in enumerate(events)
    ]

    groups, ungrouped = group_events(records)

    assert list(groups) == [(10, "id:1"), (20, "id:1")]
    assert ungrouped == [records[2]]


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
    graph = parse_contexttrack(event_file, module_id="example.org/service").graph
    nodes = {(node.type, getattr(node, "message", None)): node for node in graph.nodes}
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


def test_ambiguous_response_is_not_matched():
    requests = [
        record(0, request_sent(10, "id:1")),
        record(1, request_sent(10, "id:1")),
    ]
    response = record(
        2,
        {
            "kind": "Response received",
            "pid": 10,
            "message": {
                "resp.StatusCode": "200",
                "req.Method": "GET",
                "req.URL.Path": "/items",
            },
            "context": {"context_id": "id:1"},
        },
    )
    groups, _ = group_events([*requests, response])

    matches, warnings = match_responses(groups)

    assert matches.received == {}
    assert len(warnings) == 1
    assert warnings[0].input_line == response.input_line
    assert "ambiguous" in warnings[0].message


def test_matches_sequential_requests_and_duplicate_hook():
    first = record(0, request_sent(10, "id:1"))
    first_response = record(
        1,
        {
            "kind": "Response received",
            "pid": 10,
            "message": {
                "resp.StatusCode": "200",
                "req.Method": "GET",
                "req.URL.Path": "/items",
            },
            "context": {"context_id": "id:1"},
        },
    )
    duplicate = record(
        2,
        {
            "kind": "Response received",
            "pid": 10,
            "message": {"resp.StatusCode": "200"},
            "context": {"context_id": "id:1"},
        },
    )
    second = record(3, request_sent(10, "id:1"))
    second_response = record(
        4,
        {
            "kind": "Response received",
            "pid": 10,
            "message": {
                "resp.StatusCode": "201",
                "req.Method": "get",
                "req.URL.Path": "/items",
            },
            "context": {"context_id": "id:1"},
        },
    )
    groups, _ = group_events(
        [second_response, duplicate, first, second, first_response]
    )

    matches, warnings = match_responses(groups)

    assert matches.received == {1: first, 4: second}
    assert warnings == []
