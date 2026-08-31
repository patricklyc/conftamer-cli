import hashlib
import json
from collections.abc import Sequence
from pathlib import Path

import conftamer.contexttrack as contexttrack
from conftamer.contexttrack import import_contexttrack
from conftamer.pmgraph import (
    ReceiveRequestNode,
    ReceiveResponseNode,
    SendRequestNode,
    SendResponseNode,
)

MODULE = "example.org/service"
EXAMPLES = Path("examples/contexttrack/prometheus")


def write_events(tmp_path: Path, events: Sequence[dict[str, object] | str]) -> Path:
    path = tmp_path / "events.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [item if isinstance(item, str) else json.dumps(item) for item in events]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def event(
    kind: str,
    message: dict[str, object],
    *,
    context_id: str | None = "id:1",
    **extra: object,
) -> dict[str, object]:
    context = {} if context_id is None else {"context_id": context_id}
    return {
        "kind": kind,
        "pid": 10,
        "message": message,
        "context": context,
        **extra,
    }


def request_received(
    *, path: str = "/items/1", context_id: str | None = "id:1"
) -> dict[str, object]:
    return event(
        "Request received",
        {"req.Method": "GET", "req.URL.Path": path, "req.URL.RawQuery": "view=full"},
        context_id=context_id,
        api_id="example.org/api",
        handler="example.org/service.Handler",
    )


def request_sent(
    *, path: str = "/reserve", context_id: str | None = "id:1"
) -> dict[str, object]:
    return event(
        "Request sent",
        {
            "req.Method": "POST",
            "req.URL.Host": "inventory:8080",
            "req.URL.Path": path,
            "req.URL.RawQuery": "dry_run=true",
        },
        context_id=context_id,
        request_id={"method": "POST", "host": "inventory:8080", "path": path},
        api_id="example.org/client",
    )


def by_type(graph, node_type):
    return next(node for node in graph.nodes if isinstance(node, node_type))


def evidence_records(node, derivation: str) -> tuple[str, ...]:
    return next(
        reference.records
        for reference in node.evidence
        if reference.derivation == derivation
    )


def test_reader_continues_after_bad_lines_and_hashes_exact_bytes(tmp_path):
    path = write_events(
        tmp_path,
        [
            request_sent(),
            "{bad json",
            "",
            event("Unsupported", {}),
        ],
    )

    result = import_contexttrack(path, module_id=MODULE)

    assert len(result.graph.nodes) == 1
    assert [(item.line, item.code) for item in result.diagnostics] == [
        (2, "contexttrack.invalid_event"),
        (4, "contexttrack.invalid_event"),
    ]
    assert all(item.source == str(path) for item in result.diagnostics)
    assert result.graph.sources[0].kind == "contexttrack-jsonl"
    assert result.graph.sources[0].id == (
        f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"
    )


def test_importer_projects_nodes_edges_and_all_inference_evidence(tmp_path):
    events = [
        request_received(),
        event(
            "Request routed",
            {
                "req.Method": "GET",
                "req.URL.Path": "/items/1",
                "pattern": "/items/{id}",
            },
        ),
        request_sent(),
        event(
            "Response received",
            {
                "resp.StatusCode": "200",
                "req.Method": "POST",
                "req.URL.Path": "/reserve",
            },
            api_id="different-response-hook-api",
        ),
        event(
            "Response sent",
            {"code": "201", "req.Method": "GET", "req.URL.Path": "/items/1"},
        ),
    ]
    result = import_contexttrack(write_events(tmp_path, events), module_id=MODULE)
    graph = result.graph

    receive_request = by_type(graph, ReceiveRequestNode)
    send_request = by_type(graph, SendRequestNode)
    receive_response = by_type(graph, ReceiveResponseNode)
    send_response = by_type(graph, SendResponseNode)

    assert result.diagnostics == ()
    assert len(graph.nodes) == 4
    assert receive_request.pattern == "/items/{id}"
    assert send_request.path == "/reserve"
    assert receive_response.api_id == "example.org/client"
    assert send_response.api_id == "example.org/api"
    assert evidence_records(receive_request, "observed") == ("line:1",)
    assert evidence_records(receive_request, "route-inference") == (
        "line:1",
        "line:2",
    )
    assert evidence_records(receive_response, "observed") == ("line:4",)
    assert evidence_records(receive_response, "response-correlation") == (
        "line:3",
        "line:4",
    )
    assert evidence_records(send_response, "response-correlation") == (
        "line:1",
        "line:5",
    )
    assert evidence_records(send_response, "route-inference") == (
        "line:2",
        "line:5",
    )
    assert {(edge.source, edge.target) for edge in graph.edges} == {
        (receive_request.id, send_request.id),
        (receive_request.id, send_response.id),
        (receive_response.id, send_response.id),
    }
    assert all(edge.evidence[0].derivation == "context-order" for edge in graph.edges)


def test_query_and_handler_do_not_change_semantic_identity(tmp_path):
    first = request_received()
    second = request_received()
    second["message"] = {
        "req.Method": "GET",
        "req.URL.Path": "/items/1",
        "req.URL.RawQuery": "different=true",
    }
    second["handler"] = "example.org/service.OtherHandler"

    first_result = import_contexttrack(
        write_events(tmp_path / "first", [first]), module_id=MODULE
    )
    second_result = import_contexttrack(
        write_events(tmp_path / "second", [second]), module_id=MODULE
    )

    assert first_result.graph.nodes[0].id == second_result.graph.nodes[0].id


def test_events_without_context_ids_create_nodes_but_no_edges(tmp_path):
    path = write_events(
        tmp_path,
        [
            request_received(context_id=None),
            request_sent(context_id=None),
        ],
    )

    result = import_contexttrack(path, module_id=MODULE)

    assert len(result.graph.nodes) == 2
    assert result.graph.edges == ()
    assert [item.code for item in result.diagnostics] == [
        "contexttrack.missing_context_id",
        "contexttrack.missing_context_id",
    ]


def test_hostless_send_is_diagnosed_and_omitted(tmp_path):
    payload = request_sent()
    payload["request_id"] = {"method": "POST", "host": "", "path": "/reserve"}
    path = write_events(tmp_path, [payload])

    result = import_contexttrack(path, module_id=MODULE)

    assert result.graph.nodes == ()
    assert [item.code for item in result.diagnostics] == [
        "contexttrack.request_without_host"
    ]


def test_unresolved_response_hooks_follow_endpoint_diagnostic_policy(tmp_path):
    path = write_events(
        tmp_path,
        [
            event("Response received", {"resp.StatusCode": "200"}),
            event(
                "Response received",
                {
                    "resp.StatusCode": "404",
                    "req.Method": "GET",
                    "req.URL.Path": "/missing",
                },
            ),
        ],
    )

    result = import_contexttrack(path, module_id=MODULE)

    assert result.graph.nodes == ()
    assert [(item.line, item.code) for item in result.diagnostics] == [
        (2, "contexttrack.unmatched_response")
    ]


def test_semantically_invalid_completed_hook_is_diagnosed(tmp_path):
    path = write_events(
        tmp_path,
        [
            request_received(path="/"),
            event(
                "Response sent",
                {"code": "99", "req.Method": "GET", "req.URL.Path": "/"},
            ),
        ],
    )

    result = import_contexttrack(path, module_id=MODULE)

    assert len(result.graph.nodes) == 1
    assert [item.code for item in result.diagnostics] == [
        "contexttrack.invalid_semantics"
    ]


def test_parse_contexttrack_is_not_exported():
    assert not hasattr(contexttrack, "parse_contexttrack")


def test_scrape_ok_real_trace_imports_to_four_nodes_and_one_edge():
    result = import_contexttrack(EXAMPLES / "scrape-ok.jsonl", module_id=MODULE)

    assert len(result.graph.nodes) == 4
    assert len(result.graph.edges) == 1
    assert result.diagnostics == ()


def test_all_tests_real_trace_has_documented_hostless_send_count():
    result = import_contexttrack(EXAMPLES / "all-tests.jsonl", module_id=MODULE)

    assert (
        sum(
            item.code == "contexttrack.request_without_host"
            for item in result.diagnostics
        )
        == 5_820
    )
