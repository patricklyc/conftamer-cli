import pytest
from pydantic import ValidationError

from conftamer.contexttrack.events import (
    EVENT_ADAPTER,
    ContextInfo,
    ReceivedResponseMessage,
    RequestID,
    RequestMessage,
    RequestSentEvent,
    ResponseReceivedEvent,
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
