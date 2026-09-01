import json

import pytest
from pydantic import ValidationError

from conftamer.diagnostics import EvidenceDerivation, EvidenceRef, SourceArtifact
from conftamer.pmgraph import (
    BehaviorNode,
    PMEdge,
    ReceiveRequestNode,
    SendRequestNode,
    load_pmgraph,
    make_node_id,
    make_pmgraph,
    write_pmgraph,
)

MODULE = "example.org/módulo"
SOURCE_ID = f"sha256:{'a' * 64}"
SOURCE = SourceArtifact(id=SOURCE_ID, kind="contexttrack-jsonl")
SECOND_SOURCE = SourceArtifact(id=f"sha256:{'b' * 64}", kind="ctype-graph")


def evidence(*lines: int, derivation: EvidenceDerivation = "observed") -> EvidenceRef:
    return EvidenceRef(
        source_id=SOURCE_ID,
        records=tuple(f"line:{line}" for line in lines),
        derivation=derivation,
    )


def nodes():
    receive_fields = {
        "type": "Receive",
        "message": "Request",
        "api_id": None,
        "method": "GET",
        "pattern": "/café/{id}",
    }
    send_fields = {
        "type": "Send",
        "message": "Request",
        "api_id": None,
        "method": "GET",
        "host": "example.org",
        "path": "/café/1",
    }
    receive = ReceiveRequestNode(
        id=make_node_id(MODULE, receive_fields),
        evidence=(evidence(1),),
        api_id=None,
        method="GET",
        pattern="/café/{id}",
    )
    send = SendRequestNode(
        id=make_node_id(MODULE, send_fields),
        evidence=(evidence(2),),
        api_id=None,
        method="GET",
        host="example.org",
        path="/café/1",
    )
    behavior_fields = {"type": "Behavior", "name": "réessayer"}
    behavior = BehaviorNode(
        id=make_node_id(MODULE, behavior_fields),
        evidence=(evidence(5),),
        name="réessayer",
    )
    return receive, send, behavior


def graph(reverse: bool = False):
    receive, send, behavior = nodes()
    node_values = [
        receive,
        send,
        behavior,
        receive.model_copy(update={"evidence": (evidence(3),)}),
        send.model_copy(update={"evidence": (evidence(4),)}),
    ]
    edge_values = [
        PMEdge(
            source=receive.id,
            target=send.id,
            evidence=(evidence(1, 2, derivation="context-order"),),
        ),
        PMEdge(
            source=receive.id,
            target=send.id,
            evidence=(evidence(3, 4, derivation="context-order"),),
        ),
        PMEdge(
            source=receive.id,
            target=behavior.id,
            evidence=(evidence(5),),
        ),
    ]
    source_values = [SECOND_SOURCE, SOURCE]
    if reverse:
        node_values.reverse()
        edge_values.reverse()
        source_values.reverse()
    return make_pmgraph(
        module_id=MODULE,
        sources=source_values,
        nodes=node_values,
        edges=edge_values,
    )


def test_write_and_load_canonical_utf8_json(tmp_path):
    path = tmp_path / "graph.json"
    expected = graph()

    write_pmgraph(expected, path)

    data = path.read_bytes()
    assert data.endswith(b"\n")
    assert not data.endswith(b"\n\n")
    assert "módulo".encode() in data
    assert "café".encode() in data
    assert json.loads(data) == expected.model_dump(mode="json")
    assert load_pmgraph(path) == expected


def test_shuffled_semantic_inputs_write_byte_identically(tmp_path):
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"

    write_pmgraph(graph(), first)
    write_pmgraph(graph(reverse=True), second)

    assert first.read_bytes() == second.read_bytes()


def test_loader_rejects_noncanonical_collection_order(tmp_path):
    path = tmp_path / "graph.json"
    document = graph().model_dump(mode="json")
    document["nodes"].reverse()
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ValidationError, match="nodes must be in canonical order"):
        load_pmgraph(path)


@pytest.mark.parametrize(("field", "value"), [("method", "get"), ("path", "")])
def test_loader_rejects_noncanonical_scalar_normalization(tmp_path, field, value):
    path = tmp_path / "graph.json"
    document = graph().model_dump(mode="json")
    send = next(node for node in document["nodes"] if node["type"] == "Send")
    send[field] = value
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ValueError):
        load_pmgraph(path)
