import hashlib

import pytest

from conftamer.diagnostics import EvidenceRef, SourceArtifact
from conftamer.pmgraph import (
    BehaviorNode,
    ParameterNode,
    PMEdge,
    PMGraph,
    ReceiveRequestNode,
    ReceiveResponseNode,
    SendRequestNode,
    SendResponseNode,
    make_node_id,
    make_pmgraph,
)


def source_for(module_id: str) -> SourceArtifact:
    digest = hashlib.sha256(module_id.encode()).hexdigest()
    return SourceArtifact(id=f"sha256:{digest}", kind="contexttrack-jsonl")


def evidence_for(module_id: str, line: int = 1, *, response: bool = False):
    source_id = source_for(module_id).id
    refs = [
        EvidenceRef(
            source_id=source_id, records=(f"line:{line}",), derivation="observed"
        )
    ]
    if response:
        refs.append(
            EvidenceRef(
                source_id=source_id,
                records=(f"line:{line}",),
                derivation="response-correlation",
            )
        )
    return tuple(refs)


def parameter(module_id: str, name: str = "timeout", *, line: int = 1) -> ParameterNode:
    fields = {"type": "Parameter", "name": name}
    return ParameterNode(
        id=make_node_id(module_id, fields),
        evidence=evidence_for(module_id, line),
        name=name,
    )


def behavior(module_id: str, name: str = "retry", *, line: int = 1) -> BehaviorNode:
    fields = {"type": "Behavior", "name": name}
    return BehaviorNode(
        id=make_node_id(module_id, fields),
        evidence=evidence_for(module_id, line),
        name=name,
    )


def send_request(
    module_id: str,
    path: str = "/items/1",
    *,
    method: str = "GET",
    host: str = "ignored.example",
    api_id: str | None = None,
    line: int = 1,
) -> SendRequestNode:
    fields = {
        "type": "Send",
        "message": "Request",
        "api_id": api_id,
        "method": method,
        "host": host,
        "path": path,
    }
    return SendRequestNode(
        id=make_node_id(module_id, fields),
        evidence=evidence_for(module_id, line),
        api_id=api_id,
        method=method,
        host=host,
        path=path,
    )


def receive_request(
    module_id: str,
    pattern: str = "/items/{id}",
    *,
    method: str = "GET",
    api_id: str | None = None,
    line: int = 1,
) -> ReceiveRequestNode:
    fields = {
        "type": "Receive",
        "message": "Request",
        "api_id": api_id,
        "method": method,
        "pattern": pattern,
    }
    return ReceiveRequestNode(
        id=make_node_id(module_id, fields),
        evidence=evidence_for(module_id, line),
        api_id=api_id,
        method=method,
        pattern=pattern,
    )


def receive_response(
    module_id: str,
    path: str = "/items/1",
    *,
    method: str = "GET",
    host: str = "ignored.example",
    status: int = 200,
    api_id: str | None = None,
    line: int = 2,
) -> ReceiveResponseNode:
    fields = {
        "type": "Receive",
        "message": "Response",
        "api_id": api_id,
        "method": method,
        "host": host,
        "path": path,
        "status": status,
    }
    return ReceiveResponseNode(
        id=make_node_id(module_id, fields),
        evidence=evidence_for(module_id, line, response=True),
        api_id=api_id,
        method=method,
        host=host,
        path=path,
        status=status,
    )


def send_response(
    module_id: str,
    pattern: str = "/items/{id}",
    *,
    method: str = "GET",
    status: int = 200,
    api_id: str | None = None,
    line: int = 2,
) -> SendResponseNode:
    fields = {
        "type": "Send",
        "message": "Response",
        "api_id": api_id,
        "method": method,
        "pattern": pattern,
        "status": status,
    }
    return SendResponseNode(
        id=make_node_id(module_id, fields),
        evidence=evidence_for(module_id, line, response=True),
        api_id=api_id,
        method=method,
        pattern=pattern,
        status=status,
    )


def pmgraph(module_id: str, nodes, edges: tuple[PMEdge, ...] = ()) -> PMGraph:
    return make_pmgraph(
        module_id=module_id,
        sources=(source_for(module_id),),
        nodes=nodes,
        edges=edges,
    )


@pytest.fixture
def modules():
    return "example.org/client", "example.org/server"
