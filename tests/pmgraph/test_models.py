import pytest
from pydantic import ValidationError

from conftamer.pmgraph.models import Message, Parameter, PMGraph


def test_pmgraph_builds_typed_nodes_from_payloads() -> None:
    graph = PMGraph.model_validate(
        {
            "module_id": "frontend",
            "nodes": {
                "parameter-1": {"kind": "parameter", "key": "timeout"},
                "message-1": {
                    "kind": "send_request",
                    "api_id": None,
                    "method": "POST",
                    "host": "backend:8080",
                    "path": "/jobs",
                },
            },
            "edges": [["parameter-1", "message-1"]],
        }
    )

    assert graph.module_id == "frontend"
    assert graph.nodes["parameter-1"] == Parameter(key="timeout")
    assert graph.nodes["message-1"] == Message(
        kind="send_request",
        api_id=None,
        method="POST",
        host="backend:8080",
        path="/jobs",
    )
    assert graph.edges == {("parameter-1", "message-1")}


@pytest.mark.parametrize(
    "fields",
    [
        {"module_id": ""},
        {"nodes": {"": Parameter(key="timeout")}},
        {"edges": [("input", "missing")]},
        {"edges": [("missing", "input")]},
        {"nodes": {"unknown-1": {"kind": "unknown"}}},
    ],
)
def test_pmgraph_rejects_invalid_payloads(fields) -> None:
    with pytest.raises(ValidationError):
        PMGraph.model_validate(
            {
                "module_id": "frontend",
                "nodes": {"input": Parameter(key="timeout")},
                "edges": [],
            }
            | fields
        )


def test_pmgraph_deduplicates_edges() -> None:
    graph = PMGraph.model_validate(
        {
            "module_id": "frontend",
            "nodes": {
                "input": {"kind": "parameter", "key": "timeout"},
                "output": {"kind": "parameter", "key": "retries"},
            },
            "edges": [["input", "output"], ["input", "output"]],
        }
    )

    assert graph.edges == {("input", "output")}


@pytest.mark.parametrize(
    "fields",
    [
        {"method": ""},
        {"path": None},
        {"pattern": "/route"},
        {"path": None, "pattern": ""},
        {"status_code": 0},
        {"kind": "receive_response"},
        {"host": None},
        {"host": ""},
        {"path": None, "pattern": "/route"},
        {"kind": "receive_request"},
        {"kind": "receive_request", "host": ""},
        {"kind": "receive_request", "host": None, "status_code": 0},
        {"kind": "send_response", "host": None},
        {"kind": "send_response", "status_code": 0},
    ],
)
def test_message_rejects_invalid_fields(fields) -> None:
    with pytest.raises(ValidationError):
        Message.model_validate(
            {
                "kind": "send_request",
                "api_id": None,
                "method": "GET",
                "host": "h",
                "path": "",
            }
            | fields
        )
