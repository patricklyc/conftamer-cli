import pytest
from pydantic import ValidationError

from conftamer.appgraph import (
    AppGraph,
    AppNode,
    MatchInfo,
    QualifiedNodeRef,
    QualifiedPMNode,
    stitch_pmgraphs,
)

from conftest import (
    behavior,
    evidence_for,
    parameter,
    pmgraph,
    receive_request,
    send_request,
)


def matched_graph(modules):
    client, server = modules
    return stitch_pmgraphs(
        [
            pmgraph(client, (send_request(client),)),
            pmgraph(server, (receive_request(server),)),
        ]
    ).graph


def ambiguous_graph():
    return stitch_pmgraphs(
        [
            pmgraph("a", (send_request("a"),)),
            pmgraph("b", (receive_request("b"),)),
            pmgraph("c", (receive_request("c"),)),
        ]
    ).graph


def test_match_info_rejects_invalid_status_basis_candidate_combinations():
    candidate = QualifiedNodeRef(module_id="other", node_id=f"n:{'0' * 64}")
    invalid = (
        {"status": "matched", "basis": None, "candidates": ()},
        {
            "status": "matched",
            "basis": "unique-http-labels",
            "candidates": (candidate,),
        },
        {"status": "ambiguous", "basis": None, "candidates": ()},
        {
            "status": "no_candidate",
            "basis": None,
            "candidates": (candidate,),
        },
        {
            "status": "not_applicable",
            "basis": "unique-http-labels",
            "candidates": (),
        },
    )

    for values in invalid:
        with pytest.raises(ValidationError, match="match status"):
            MatchInfo.model_validate(values)


def test_app_node_rejects_invalid_local_member_shapes(modules):
    client, server = modules
    send = QualifiedPMNode(module_id=client, node=send_request(client))
    other_send = QualifiedPMNode(module_id=server, node=send_request(server))
    matched = MatchInfo(status="matched", basis="unique-http-labels", candidates=())

    with pytest.raises(ValidationError, match="matched AppNode"):
        AppNode(id=f"a:{'0' * 64}", members=(send,), match=matched)
    with pytest.raises(ValidationError, match="complementary"):
        AppNode(id=f"a:{'0' * 64}", members=(send, other_send), match=matched)

    not_applicable = MatchInfo(status="not_applicable", basis=None, candidates=())
    with pytest.raises(ValidationError, match="not_applicable"):
        AppNode(id=f"a:{'0' * 64}", members=(send,), match=not_applicable)

    unsupported = MatchInfo(status="unsupported_pattern", basis=None, candidates=())
    with pytest.raises(ValidationError, match="unsupported_pattern"):
        AppNode(id=f"a:{'0' * 64}", members=(send,), match=unsupported)

    missing_request = MatchInfo(
        status="missing_request_match", basis=None, candidates=()
    )
    receive = QualifiedPMNode(module_id=server, node=receive_request(server))
    with pytest.raises(ValidationError, match="missing_request_match"):
        AppNode(id=f"a:{'0' * 64}", members=(receive,), match=missing_request)


def test_app_node_id_has_a_fixed_contract_vector_and_excludes_evidence(modules):
    graph = matched_graph(modules)
    client, server = modules
    changed_send = send_request(client).model_copy(
        update={"evidence": evidence_for(client, 9)}
    )
    changed_evidence = stitch_pmgraphs(
        [
            pmgraph(client, (changed_send,)),
            pmgraph(server, (receive_request(server),)),
        ]
    ).graph

    assert graph.nodes[0].id == (
        "a:3ea043059672920e40d3490e672bc40ea3530b56c4740ffdeaebf0f1523f4fce"
    )
    assert changed_evidence.nodes[0].id == graph.nodes[0].id


def test_appgraph_recomputes_match_state_instead_of_trusting_claims(modules):
    document = matched_graph(modules).model_dump()
    document["nodes"][0]["match"].update(status="no_candidate", basis=None)

    with pytest.raises(ValidationError, match="match"):
        AppGraph.model_validate(document)


def test_ambiguous_candidates_must_be_complete_and_reciprocal():
    document = ambiguous_graph().model_dump()
    ambiguous = next(node for node in document["nodes"] if node["match"]["candidates"])
    ambiguous["match"]["candidates"] = ()

    with pytest.raises(ValidationError, match="match"):
        AppGraph.model_validate(document)


def test_appgraph_rejects_invalid_app_and_embedded_semantic_ids(modules):
    document = matched_graph(modules).model_dump()
    document["nodes"][0]["id"] = f"a:{'0' * 64}"
    with pytest.raises(ValidationError, match="AppNode ID"):
        AppGraph.model_validate(document)

    document = matched_graph(modules).model_dump()
    send = next(
        member["node"]
        for member in document["nodes"][0]["members"]
        if member["node"]["type"] == "Send"
    )
    send["host"] = "changed.invalid"
    with pytest.raises(ValidationError, match="semantic ID"):
        AppGraph.model_validate(document)


def test_appgraph_rejects_noncanonical_collections(modules):
    document = matched_graph(modules).model_dump()
    document["sources"] = tuple(reversed(document["sources"]))
    with pytest.raises(ValidationError, match="sources.*canonical"):
        AppGraph.model_validate(document)

    document = matched_graph(modules).model_dump()
    document["nodes"][0]["members"] = tuple(reversed(document["nodes"][0]["members"]))
    with pytest.raises(ValidationError, match="members.*canonical"):
        AppGraph.model_validate(document)


def test_appgraph_rejects_dangling_member_evidence(modules):
    document = matched_graph(modules).model_dump()
    document["nodes"][0]["members"][0]["node"]["evidence"][0]["source_id"] = (
        f"sha256:{'f' * 64}"
    )

    with pytest.raises(ValidationError, match="evidence source"):
        AppGraph.model_validate(document)


def test_parameter_and_behavior_are_singleton_not_applicable_nodes(modules):
    client, server = modules
    graph = stitch_pmgraphs(
        [
            pmgraph(client, (parameter(client), behavior(client))),
            pmgraph(server, ()),
        ]
    ).graph

    assert len(graph.nodes) == 2
    assert {node.match.status for node in graph.nodes} == {"not_applicable"}
    assert all(len(node.members) == 1 for node in graph.nodes)
