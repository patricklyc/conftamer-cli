import json

from conftamer.contexttrack.conversion import parse_contexttrack
from conftamer.contexttrack.events import (
    EVENT_ADAPTER,
    EventRecord,
    group_events,
)
from conftamer.contexttrack.routes import match_routes


def record(sequence: int, event: dict) -> EventRecord:
    return EventRecord(
        sequence=sequence,
        input_line=sequence + 1,
        event=EVENT_ADAPTER.validate_python(event),
    )


def test_reconstructs_nested_route_after_prefix_stripping(tmp_path):
    context = {"context_id": "id:1"}
    events = [
        {
            "kind": "Request received",
            "pid": 10,
            "message": {
                "req.Method": "GET",
                "req.URL.Path": "/api/v1/status/config",
            },
            "context": context,
            "api_id": "example.org/api",
        },
        {
            "kind": "Request routed",
            "pid": 10,
            "message": {
                "req.Method": "GET",
                "req.URL.Path": "/api/v1/status/config",
                "pattern": "/api/v1/",
            },
            "context": context,
        },
        {
            "kind": "Request routed",
            "pid": 10,
            "message": {
                "req.Method": "GET",
                "req.URL.Path": "/status/config",
                "pattern": "/status/config",
            },
            "context": context,
        },
        {
            "kind": "Response sent",
            "pid": 10,
            "message": {
                "code": "200",
                "req.Method": "GET",
                "req.URL.Path": "/api/v1/status/config",
            },
            "context": context,
        },
    ]
    event_file = tmp_path / "events.jsonl"
    event_file.write_text("\n".join(json.dumps(event) for event in events))

    result = parse_contexttrack(event_file, module_id="example.org/service")

    patterns = {node.pattern for node in result.graph.nodes if hasattr(node, "pattern")}
    assert patterns == {"/api/v1/status/config"}
    assert result.warnings == ()


def test_does_not_guess_ambiguous_nested_route_chain():
    context = {"context_id": "id:1"}
    routes = [
        record(
            sequence,
            {
                "kind": "Request routed",
                "pid": 10,
                "message": {
                    "req.Method": "GET",
                    "req.URL.Path": path,
                    "pattern": path,
                },
                "context": context,
            },
        )
        for sequence, path in enumerate(["/one/items", "/two/items", "/items"])
    ]
    groups, _ = group_events(routes)

    matches, warnings = match_routes(groups)

    assert matches == {}
    assert any(warning.message == "ambiguous route chain" for warning in warnings)
