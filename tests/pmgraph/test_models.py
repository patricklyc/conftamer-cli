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


def test_pmgraph_rejects_an_unknown_node_kind() -> None:
    with pytest.raises(ValidationError):
        PMGraph.model_validate(
            {
                "module_id": "frontend",
                "nodes": {"unknown-1": {"kind": "unknown"}},
                "edges": [],
            }
        )


def test_pmgraph_deduplicates_edges() -> None:
    graph = PMGraph.model_validate(
        {
            "module_id": "frontend",
            "nodes": {},
            "edges": [["input", "output"], ["input", "output"]],
        }
    )

    assert graph.edges == {("input", "output")}
