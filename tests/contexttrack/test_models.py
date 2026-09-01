import pytest
from pydantic import ValidationError

from conftamer.contexttrack.models import (
    EVENT_ADAPTER,
    EventRecord,
    RequestReceivedEvent,
    RequestSentEvent,
    ResponseReceivedEvent,
    ResponseSentEvent,
    RouteEvent,
    group_events,
)


def event(kind: str, message: dict[str, object], **extra: object) -> dict[str, object]:
    return {
        "kind": kind,
        "pid": 42,
        "goroutine_id": 7,
        "thread_id": 0,
        "file": "/go/src/net/http/transport.go",
        "line": 599,
        "message": message,
        "context": {
            "source": "req.Context()",
            "type": "context.Context",
            "context_id": "id:3",
            "future_context_field": "kept",
        },
        **extra,
    }


@pytest.mark.parametrize(
    ("payload", "expected_type"),
    [
        (
            event(
                "Request sent",
                {
                    "req.Method": "POST",
                    "req.URL.Host": "inventory:8080",
                    "req.URL.Path": "/reserve",
                    "req.URL.RawQuery": "dry_run=true",
                },
                request_id={
                    "method": "POST",
                    "host": "inventory:8080",
                    "path": "/reserve",
                },
                api_id="example.org/frontend",
            ),
            RequestSentEvent,
        ),
        (
            event(
                "Request received",
                {
                    "req.Method": "GET",
                    "req.URL.Path": "/items/1",
                    "req.URL.RawQuery": "view=full",
                },
                api_id="example.org/api",
                handler="example.org/service.Handler",
            ),
            RequestReceivedEvent,
        ),
        (
            event(
                "Request routed",
                {
                    "req.Method": "GET",
                    "req.URL.Path": "/items/1",
                    "pattern": "/items/{id}",
                },
            ),
            RouteEvent,
        ),
        (
            event(
                "Response sent",
                {"code": "201", "req.Method": "GET", "req.URL.Path": "/items/1"},
            ),
            ResponseSentEvent,
        ),
        (
            event(
                "Response received",
                {
                    "resp.StatusCode": 200,
                    "req.Method": "POST",
                    "req.URL.Path": "/reserve",
                },
                api_id="example.org/frontend",
            ),
            ResponseReceivedEvent,
        ),
    ],
)
def test_models_accept_observed_nested_event_shapes(payload, expected_type):
    parsed = EVENT_ADAPTER.validate_python(payload)

    assert isinstance(parsed, expected_type)
    assert parsed.pid == 42


def test_models_preserve_unknown_envelope_and_nested_fields():
    payload = event(
        "Request sent",
        {
            "req.Method": "POST",
            "req.URL.Host": "inventory:8080",
            "req.URL.Path": "/reserve",
            "future_message_field": "kept",
        },
        request_id={
            "method": "POST",
            "host": "inventory:8080",
            "path": "/reserve",
            "future_request_field": "kept",
        },
        future_event_field="kept",
    )

    parsed = EVENT_ADAPTER.validate_python(payload)
    dumped = parsed.model_dump(by_alias=True)

    assert dumped["future_event_field"] == "kept"
    assert dumped["message"]["future_message_field"] == "kept"
    assert dumped["context"]["future_context_field"] == "kept"
    assert dumped["request_id"]["future_request_field"] == "kept"


@pytest.mark.parametrize("value", ["100", "999", 100, 999])
def test_status_accepts_decimal_strings_and_json_integers(value):
    parsed = EVENT_ADAPTER.validate_python(
        event("Response received", {"resp.StatusCode": value})
    )

    assert isinstance(parsed, ResponseReceivedEvent)
    assert parsed.message.status == int(value)


@pytest.mark.parametrize("value", [True, 200.0, "20.5", "0xC8", ""])
def test_status_rejects_non_decimal_or_non_integer_values(value):
    with pytest.raises(ValidationError):
        EVENT_ADAPTER.validate_python(
            event(
                "Response sent",
                {"code": value, "req.Method": "GET", "req.URL.Path": "/"},
            )
        )


@pytest.mark.parametrize(
    "change",
    [
        {"kind": "Unsupported"},
        {"pid": True},
        {"message": []},
        {"context": []},
    ],
)
def test_models_reject_invalid_envelopes(change):
    payload = event(
        "Request sent",
        {"req.Method": "GET", "req.URL.Host": "example.org", "req.URL.Path": "/"},
    )
    payload.update(change)

    with pytest.raises(ValidationError):
        EVENT_ADAPTER.validate_python(payload)


def test_group_events_uses_pid_and_only_nonempty_context_ids():
    payloads = [
        event(
            "Request sent",
            {"req.Method": "GET", "req.URL.Host": "a", "req.URL.Path": "/"},
        ),
        event(
            "Request sent",
            {"req.Method": "GET", "req.URL.Host": "b", "req.URL.Path": "/"},
        ),
        event(
            "Request sent",
            {"req.Method": "GET", "req.URL.Host": "c", "req.URL.Path": "/"},
        ),
        event(
            "Request sent",
            {"req.Method": "GET", "req.URL.Host": "d", "req.URL.Path": "/"},
        ),
    ]
    payloads[1]["pid"] = 99
    payloads[2]["context"] = {}
    payloads[3]["context"] = {"context_id": ""}
    records = [
        EventRecord(index, index + 1, EVENT_ADAPTER.validate_python(payload))
        for index, payload in enumerate(payloads)
    ]

    groups, ungrouped = group_events(records)

    assert list(groups) == [(42, "id:3"), (99, "id:3")]
    assert ungrouped == [records[2], records[3]]
