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
    group_events,
    read_events,
)


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
