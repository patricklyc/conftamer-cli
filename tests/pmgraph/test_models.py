import json

import pytest
from pydantic import ValidationError

from conftamer.diagnostics import (
    Diagnostic,
    EvidenceDerivation,
    EvidenceRef,
    SourceArtifact,
    merge_evidence,
    sort_diagnostics,
)
from conftamer.pmgraph import (
    BehaviorNode,
    ParameterNode,
    PMEdge,
    PMGraph,
    PMNodeBase,
    ReceiveRequestNode,
    ReceiveResponseNode,
    SendRequestNode,
    SendResponseNode,
    make_node_id,
    make_pmgraph,
)

MODULE = "example.org/service"
SOURCE_ID = f"sha256:{'a' * 64}"
SOURCE = SourceArtifact(id=SOURCE_ID, kind="contexttrack-jsonl")


def evidence(*lines: int, derivation: EvidenceDerivation = "observed") -> EvidenceRef:
    return EvidenceRef(
        source_id=SOURCE_ID,
        records=tuple(f"line:{line}" for line in lines),
        derivation=derivation,
    )


def validate_document(document: dict) -> PMGraph:
    return PMGraph.model_validate_json(json.dumps(document))


def parameter(name: str = "request_timeout", *refs: EvidenceRef) -> ParameterNode:
    fields = {"type": "Parameter", "name": name}
    return ParameterNode(
        id=make_node_id(MODULE, fields),
        evidence=refs or (evidence(1),),
        name=name,
    )


def behavior(name: str = "retry", *refs: EvidenceRef) -> BehaviorNode:
    fields = {"type": "Behavior", "name": name}
    return BehaviorNode(
        id=make_node_id(MODULE, fields),
        evidence=refs or (evidence(1),),
        name=name,
    )


def receive_request(*refs: EvidenceRef) -> ReceiveRequestNode:
    fields = {
        "type": "Receive",
        "message": "Request",
        "api_id": None,
        "method": "GET",
        "pattern": "/items/{id}",
    }
    return ReceiveRequestNode(
        id=make_node_id(MODULE, fields),
        evidence=refs or (evidence(1),),
        api_id=None,
        method="GET",
        pattern="/items/{id}",
    )


def send_request(*refs: EvidenceRef) -> SendRequestNode:
    fields = {
        "type": "Send",
        "message": "Request",
        "api_id": None,
        "method": "POST",
        "host": "inventory:8080",
        "path": "/reserve",
    }
    return SendRequestNode(
        id=make_node_id(MODULE, fields),
        evidence=refs or (evidence(2),),
        api_id=None,
        method="post",
        host="inventory:8080",
        path="/reserve",
    )


def receive_response(*refs: EvidenceRef) -> ReceiveResponseNode:
    fields = {
        "type": "Receive",
        "message": "Response",
        "api_id": None,
        "method": "POST",
        "host": "inventory:8080",
        "path": "/reserve",
        "status": 200,
    }
    return ReceiveResponseNode(
        id=make_node_id(MODULE, fields),
        evidence=refs
        or (
            evidence(3),
            evidence(2, 3, derivation="response-correlation"),
        ),
        api_id=None,
        method="POST",
        host="inventory:8080",
        path="/reserve",
        status=200,
    )


def send_response(*refs: EvidenceRef) -> SendResponseNode:
    fields = {
        "type": "Send",
        "message": "Response",
        "api_id": "example.org/api",
        "method": "GET",
        "pattern": "/items/{id}",
        "status": 201,
    }
    return SendResponseNode(
        id=make_node_id(MODULE, fields),
        evidence=refs
        or (
            evidence(4),
            evidence(1, 4, derivation="response-correlation"),
        ),
        api_id="example.org/api",
        method="GET",
        pattern="/items/{id}",
        status=201,
    )


@pytest.mark.parametrize(
    "node",
    [
        parameter(),
        behavior(),
        receive_request(),
        send_request(),
        receive_response(),
        send_response(),
    ],
)
def test_complete_node_shapes_round_trip(node):
    assert type(node).model_validate_json(node.model_dump_json()) == node


def test_node_union_rejects_missing_or_unknown_discriminators():
    graph = make_pmgraph(
        module_id=MODULE,
        sources=[SOURCE],
        nodes=[send_request()],
        edges=[],
    )
    document = graph.model_dump(mode="json")

    del document["nodes"][0]["message"]
    with pytest.raises(ValidationError):
        validate_document(document)

    document["nodes"][0]["message"] = "Unknown"
    with pytest.raises(ValidationError):
        validate_document(document)


def test_models_are_strict_frozen_and_reject_unknown_fields():
    with pytest.raises(ValidationError):
        Diagnostic(
            source=None,
            line=None,
            code="test.code",
            message="message",
            unknown=True,  # ty: ignore[unknown-argument]
        )
    with pytest.raises(ValidationError):
        ReceiveResponseNode(
            id=f"n:{'0' * 64}",
            evidence=(evidence(1),),
            api_id=None,
            method="GET",
            host="example.org",
            path="/",
            status=True,
        )

    item = parameter()
    with pytest.raises(ValidationError):
        item.name = "changed"  # ty: ignore[invalid-assignment]


def test_diagnostic_requires_source_for_line_and_sorts_canonically():
    with pytest.raises(ValidationError, match="line requires a source"):
        Diagnostic(source=None, line=1, code="test.code", message="message")

    diagnostics = [
        Diagnostic(source="b", line=2, code="b", message="second"),
        Diagnostic(source=None, line=None, code="z", message="build"),
        Diagnostic(source="a", line=None, code="a", message="source"),
        Diagnostic(source="b", line=1, code="a", message="first"),
    ]
    assert sort_diagnostics(diagnostics) == (
        diagnostics[1],
        diagnostics[2],
        diagnostics[3],
        diagnostics[0],
    )


def test_evidence_merges_records_and_has_canonical_order():
    other_source = f"sha256:{'b' * 64}"
    merged = merge_evidence(
        [
            evidence(10),
            EvidenceRef(
                source_id=other_source,
                records=("line:3",),
                derivation="observed",
            ),
            evidence(2, 10),
            evidence(4, derivation="context-order"),
        ]
    )

    assert merged == (
        EvidenceRef(
            source_id=SOURCE_ID,
            records=("line:4",),
            derivation="context-order",
        ),
        EvidenceRef(
            source_id=SOURCE_ID,
            records=("line:2", "line:10"),
            derivation="observed",
        ),
        EvidenceRef(
            source_id=other_source,
            records=("line:3",),
            derivation="observed",
        ),
    )


@pytest.mark.parametrize(
    "records",
    [("line:2", "line:1"), ("line:1", "line:1")],
)
def test_evidence_rejects_noncanonical_records(records):
    with pytest.raises(ValidationError, match="canonical order"):
        EvidenceRef(
            source_id=SOURCE_ID,
            records=records,
            derivation="observed",
        )


def test_fixed_node_id_vectors_preserve_v1_hash_algorithm():
    assert (
        make_node_id(
            "example.org/frontend",
            {
                "type": "Send",
                "message": "Request",
                "api_id": None,
                "method": "POST",
                "host": "inventory:8080",
                "path": "/reserve",
            },
        )
        == "n:2b9e9ccb13ca1f22d8e69e27bf46cb6a28a0e7482bd13228154925b49ed186fd"
    )
    assert (
        make_node_id(
            "módulo/例",
            {"type": "Behavior", "name": "café/例"},
        )
        == "n:6c734bf7af9830db8716d99e2db89f9681d2edab51b42e403df24946a123ca64"
    )


def test_builder_rejects_incomplete_base_nodes_cleanly():
    incomplete = PMNodeBase(id=f"n:{'0' * 64}", evidence=(evidence(1),))
    with pytest.raises(ValidationError, match="Unable to extract tag"):
        make_pmgraph(
            module_id=MODULE,
            sources=[SOURCE],
            nodes=[incomplete],  # ty: ignore[invalid-argument-type]
            edges=[],
        )


def test_node_id_excludes_evidence_but_graph_recomputes_semantics():
    first = parameter("request_timeout", evidence(1))
    second = parameter("request_timeout", evidence(2))
    assert first.id == second.id

    invalid = first.model_copy(update={"id": f"n:{'0' * 64}"})
    with pytest.raises(ValidationError, match="semantic ID"):
        make_pmgraph(
            module_id=MODULE,
            sources=[SOURCE],
            nodes=[invalid],
            edges=[],
        )


def test_message_normalization_and_status_bounds():
    node = SendRequestNode(
        id=make_node_id(
            MODULE,
            {
                "type": "Send",
                "message": "Request",
                "api_id": None,
                "method": "GET",
                "host": "example.org",
                "path": "/",
            },
        ),
        evidence=(evidence(1),),
        api_id=None,
        method="get",
        host="example.org",
        path="",
    )
    assert (node.method, node.path) == ("GET", "/")

    for status in (99, 1000):
        with pytest.raises(ValidationError):
            ReceiveResponseNode(
                id=f"n:{'0' * 64}",
                evidence=(evidence(1),),
                api_id=None,
                method="GET",
                host="example.org",
                path="/",
                status=status,
            )


def test_builder_accepts_parameter_and_receive_to_send_edges():
    param_source_id = f"sha256:{'b' * 64}"
    param_source = SourceArtifact(id=param_source_id, kind="paramtrack-csv")
    param_evidence = EvidenceRef(
        source_id=param_source_id,
        records=("line:2",),
        derivation="observed",
    )
    parameter_node = parameter("request_timeout", param_evidence)
    receive_node = receive_request()
    request_node = send_request()
    response_node = send_response()
    edges = [
        PMEdge(
            source=parameter_node.id,
            target=request_node.id,
            evidence=(
                EvidenceRef(
                    source_id=param_source_id,
                    records=("line:2",),
                    derivation="paramtrack-unique-method-path",
                ),
            ),
        ),
        PMEdge(
            source=receive_node.id,
            target=response_node.id,
            evidence=(evidence(1, 4, derivation="context-order"),),
        ),
    ]

    graph = make_pmgraph(
        module_id=MODULE,
        sources=[SOURCE, param_source],
        nodes=[response_node, request_node, receive_node, parameter_node],
        edges=reversed(edges),
    )
    assert graph.version == 2
    assert graph.nodes == tuple(sorted(graph.nodes, key=lambda item: item.id))
    assert graph.edges == tuple(
        sorted(graph.edges, key=lambda item: (item.source, item.target))
    )


@pytest.mark.parametrize(
    ("source_factory", "target_factory", "message"),
    [
        (send_request, send_response, "source must be"),
        (receive_request, parameter, "target must be"),
    ],
)
def test_graph_rejects_invalid_edge_directions(source_factory, target_factory, message):
    source = source_factory()
    target = target_factory()
    with pytest.raises(ValidationError, match=message):
        make_pmgraph(
            module_id=MODULE,
            sources=[SOURCE],
            nodes=[source, target],
            edges=[
                PMEdge(
                    source=source.id,
                    target=target.id,
                    evidence=(evidence(1),),
                )
            ],
        )


def test_graph_rejects_invalid_evidence_attachments():
    invalid_node = parameter("request_timeout", evidence(1, derivation="context-order"))
    with pytest.raises(ValidationError, match="context-order.*edge"):
        make_pmgraph(
            module_id=MODULE,
            sources=[SOURCE],
            nodes=[invalid_node],
            edges=[],
        )

    response_without_correlation = receive_response(evidence(3))
    with pytest.raises(ValidationError, match="response-correlation"):
        make_pmgraph(
            module_id=MODULE,
            sources=[SOURCE],
            nodes=[response_without_correlation],
            edges=[],
        )

    receive = receive_request()
    send = send_request()
    invalid_edge = PMEdge(
        source=receive.id,
        target=send.id,
        evidence=(evidence(1, derivation="route-inference"),),
    )
    with pytest.raises(ValidationError, match="route-inference.*node"):
        make_pmgraph(
            module_id=MODULE,
            sources=[SOURCE],
            nodes=[receive, send],
            edges=[invalid_edge],
        )


def test_graph_rejects_endpoints_self_edges_and_dangling_evidence():
    receive = receive_request()
    send = send_request()

    with pytest.raises(ValidationError, match="existing nodes"):
        make_pmgraph(
            module_id=MODULE,
            sources=[SOURCE],
            nodes=[receive],
            edges=[
                PMEdge(
                    source=receive.id,
                    target=send.id,
                    evidence=(evidence(1),),
                )
            ],
        )
    with pytest.raises(ValidationError, match="self-edges"):
        make_pmgraph(
            module_id=MODULE,
            sources=[SOURCE],
            nodes=[receive],
            edges=[
                PMEdge(
                    source=receive.id,
                    target=receive.id,
                    evidence=(evidence(1),),
                )
            ],
        )

    dangling = receive.model_copy(
        update={
            "evidence": (
                EvidenceRef(
                    source_id=f"sha256:{'f' * 64}",
                    records=("line:1",),
                    derivation="observed",
                ),
            )
        }
    )
    with pytest.raises(ValidationError, match="evidence source"):
        make_pmgraph(
            module_id=MODULE,
            sources=[SOURCE],
            nodes=[dangling],
            edges=[],
        )

    dangling_edge = PMEdge(
        source=receive.id,
        target=send.id,
        evidence=(
            EvidenceRef(
                source_id=f"sha256:{'f' * 64}",
                records=("line:1",),
                derivation="observed",
            ),
        ),
    )
    with pytest.raises(ValidationError, match="evidence source"):
        make_pmgraph(
            module_id=MODULE,
            sources=[SOURCE],
            nodes=[receive, send],
            edges=[dangling_edge],
        )


def test_canonical_document_rejects_duplicates_and_unsorted_collections():
    receive = receive_request()
    send = send_request()
    behavior_node = behavior()
    edge = PMEdge(
        source=receive.id,
        target=send.id,
        evidence=(evidence(1, 2, derivation="context-order"),),
    )
    behavior_edge = PMEdge(
        source=receive.id,
        target=behavior_node.id,
        evidence=(evidence(1),),
    )
    graph = make_pmgraph(
        module_id=MODULE,
        sources=[SOURCE],
        nodes=[receive, send, behavior_node],
        edges=[edge, behavior_edge],
    )
    document = graph.model_dump(mode="json")

    duplicate_nodes = {**document, "nodes": [*document["nodes"], document["nodes"][0]]}
    with pytest.raises(ValidationError, match="node IDs must be unique"):
        validate_document(duplicate_nodes)

    duplicate_edges = {**document, "edges": [*document["edges"], document["edges"][0]]}
    with pytest.raises(ValidationError, match="edge endpoint pairs must be unique"):
        validate_document(duplicate_edges)

    unsorted_nodes = {**document, "nodes": list(reversed(document["nodes"]))}
    with pytest.raises(ValidationError, match="nodes must be in canonical order"):
        validate_document(unsorted_nodes)

    unsorted_edges = {**document, "edges": list(reversed(document["edges"]))}
    with pytest.raises(ValidationError, match="edges must be in canonical order"):
        validate_document(unsorted_edges)

    duplicate_sources = {
        **document,
        "sources": [*document["sources"], document["sources"][0]],
    }
    with pytest.raises(ValidationError, match="source IDs must be unique"):
        validate_document(duplicate_sources)

    second_source = SourceArtifact(
        id=f"sha256:{'b' * 64}",
        kind="ctype-graph",
    )
    two_sources = make_pmgraph(
        module_id=MODULE,
        sources=[second_source, SOURCE],
        nodes=[receive, send, behavior_node],
        edges=[edge, behavior_edge],
    ).model_dump(mode="json")
    two_sources["sources"].reverse()
    with pytest.raises(ValidationError, match="sources must be in canonical order"):
        validate_document(two_sources)


def test_builder_rejects_empty_and_conflicting_sources():
    with pytest.raises(ValidationError):
        make_pmgraph(module_id=MODULE, sources=[], nodes=[], edges=[])

    conflicting = SourceArtifact(id=SOURCE_ID, kind="ctype-graph")
    with pytest.raises(ValueError, match="conflicting source artifact"):
        make_pmgraph(
            module_id=MODULE,
            sources=[SOURCE, conflicting],
            nodes=[],
            edges=[],
        )


def test_builder_merges_duplicate_node_and_edge_evidence():
    receive_first = receive_request(evidence(1))
    receive_second = receive_request(evidence(3))
    send_first = send_request(evidence(2))
    send_second = send_request(evidence(4))
    first_edge = PMEdge(
        source=receive_first.id,
        target=send_first.id,
        evidence=(evidence(1, 2, derivation="context-order"),),
    )
    second_edge = PMEdge(
        source=receive_second.id,
        target=send_second.id,
        evidence=(evidence(3, 4, derivation="context-order"),),
    )

    graph = make_pmgraph(
        module_id=MODULE,
        sources=[SOURCE, SOURCE],
        nodes=[send_second, receive_second, send_first, receive_first],
        edges=[second_edge, first_edge],
    )

    assert len(graph.nodes) == 2
    assert len(graph.edges) == 1
    receive = next(node for node in graph.nodes if node.type == "Receive")
    send = next(node for node in graph.nodes if node.type == "Send")
    assert receive.evidence == (evidence(1, 3),)
    assert send.evidence == (evidence(2, 4),)
    assert graph.edges[0].evidence == (
        evidence(1, 2, 3, 4, derivation="context-order"),
    )


def test_canonical_json_shape_requires_exact_format_and_version():
    graph = make_pmgraph(
        module_id=MODULE,
        sources=[SOURCE],
        nodes=[],
        edges=[],
    )
    document = json.loads(graph.model_dump_json())

    document["version"] = 1
    with pytest.raises(ValidationError):
        validate_document(document)
