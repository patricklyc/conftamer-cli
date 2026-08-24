from conftamer.contexttrack.events import (
    EVENT_ADAPTER,
    EventRecord,
    group_events,
)
from conftamer.contexttrack.responses import match_responses


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


def record(sequence: int, event: dict) -> EventRecord:
    return EventRecord(
        sequence=sequence,
        input_line=sequence + 1,
        event=EVENT_ADAPTER.validate_python(event),
    )


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
            "api_id": "example.org/api",
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


def test_duplicate_response_does_not_consume_newer_request():
    first_request = record(0, request_sent(10, "id:1"))
    wire_response = record(
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
    newer_request = record(2, request_sent(10, "id:1"))
    client_response = record(
        3,
        {
            "kind": "Response received",
            "pid": 10,
            "message": {
                "resp.StatusCode": "200",
                "req.Method": "GET",
                "req.URL.Path": "/items",
            },
            "context": {"context_id": "id:1"},
            "api_id": "example.org/api",
        },
    )
    groups, _ = group_events(
        [first_request, wire_response, newer_request, client_response]
    )

    matches, warnings = match_responses(groups)

    assert matches.received == {wire_response.sequence: first_request}
    assert warnings == []


def test_matches_client_response_after_redirect():
    context = {"context_id": "id:1"}
    events = [
        {
            "kind": "Request sent",
            "pid": 10,
            "goroutine_id": 7,
            "message": {
                "req.Method": "GET",
                "req.URL.Host": "example.org",
                "req.URL.Path": "/items",
            },
            "context": context,
        },
        {
            "kind": "Response received",
            "pid": 10,
            "goroutine_id": 7,
            "message": {
                "resp.StatusCode": "302",
                "req.Method": "GET",
                "req.URL.Path": "/items",
            },
            "context": context,
        },
        {
            "kind": "Request sent",
            "pid": 10,
            "goroutine_id": 7,
            "message": {
                "req.Method": "GET",
                "req.URL.Host": "example.org",
                "req.URL.Path": "/redirected",
            },
            "context": context,
        },
        {
            "kind": "Response received",
            "pid": 10,
            "message": {"resp.StatusCode": "500"},
            "context": context,
        },
        {
            "kind": "Response received",
            "pid": 10,
            "goroutine_id": 7,
            "message": {
                "resp.StatusCode": "500",
                "req.Method": "GET",
                "req.URL.Path": "/original",
            },
            "context": context,
            "api_id": "example.org/api",
        },
    ]
    records = [
        record(sequence, event) for sequence, event in enumerate(events)
    ]
    groups, _ = group_events(records)

    matches, warnings = match_responses(groups)

    assert matches.received == {1: records[0], 4: records[2]}
    assert warnings == []
