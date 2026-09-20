import pytest
from pydantic import ValidationError

from conftamer.appgraph.models import AppGraph, LinkedMessage
from conftamer.pmgraph.models import Parameter


def _linked_message(**overrides: object) -> dict:
    fields = {
        "kind": "linked_message",
        "api_id": "orgB",
        "method": "GET",
        "pattern": "/items/{id}",
        "status_code": None,
        "sender_module": "frontend",
        "sender_node": "send-1",
        "receiver_module": "backend",
        "receiver_node": "recv-1",
    }
    fields.update(overrides)
    return fields


def test_linked_message_round_trips() -> None:
    link = LinkedMessage.model_validate(_linked_message())

    assert link.kind == "linked_message"
    assert link.sender_module == "frontend"
    assert link.receiver_module == "backend"


@pytest.mark.parametrize(
    "overrides",
    [
        {"api_id": ""},
        {"method": ""},
        {"pattern": ""},
        {"sender_module": ""},
        {"receiver_module": ""},
        {"sender_node": ""},
        {"receiver_node": ""},
        {"sender_module": "frontend", "receiver_module": "frontend"},
    ],
)
def test_linked_message_rejects_invalid_fields(overrides: dict) -> None:
    with pytest.raises(ValidationError):
        LinkedMessage.model_validate(_linked_message(**overrides))


def test_appgraph_builds_typed_nodes() -> None:
    graph = AppGraph.model_validate(
        {
            "nodes": {
                "param": {"kind": "parameter", "key": "timeout"},
                "link0": _linked_message(),
            },
            "edges": [["param", "link0"]],
        }
    )

    assert graph.nodes["param"] == Parameter(key="timeout")
    assert graph.edges == {("param", "link0")}


@pytest.mark.parametrize(
    "fields",
    [
        {"nodes": {"": Parameter(key="timeout")}},
        {"edges": [("param", "missing")]},
        {"edges": [("missing", "param")]},
    ],
)
def test_appgraph_rejects_invalid_payloads(fields: dict) -> None:
    with pytest.raises(ValidationError):
        AppGraph.model_validate(
            {"nodes": {"param": Parameter(key="timeout")}, "edges": []} | fields
        )
