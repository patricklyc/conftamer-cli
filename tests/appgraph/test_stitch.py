import json

import pytest
from pydantic import ValidationError

from conftamer.appgraph import (
    AppGraph,
    load_appgraph,
    prune_unmatched,
    stitch_pmgraph_files,
    stitch_pmgraphs,
    write_appgraph,
)
from conftamer.diagnostics import SourceArtifact
from conftamer.pmgraph import PMEdge, write_pmgraph

from conftest import (
    evidence_for,
    parameter,
    pmgraph,
    receive_request,
    send_request,
    send_response,
)


def test_stitch_rejects_too_few_graphs_and_duplicate_modules():
    graph = pmgraph("a", ())
    with pytest.raises(ValueError, match="at least two"):
        stitch_pmgraphs([])
    with pytest.raises(ValueError, match="at least two"):
        stitch_pmgraphs([graph])
    with pytest.raises(ValueError, match="module IDs.*unique"):
        stitch_pmgraphs([graph, graph])


def test_stitch_rejects_conflicting_source_entries():
    first = pmgraph("a", ())
    conflicting = pmgraph("b", ()).model_copy(
        update={
            "sources": (SourceArtifact(id=first.sources[0].id, kind="ctype-graph"),)
        }
    )

    with pytest.raises(ValueError, match="conflicting source"):
        stitch_pmgraphs([first, conflicting])


def graph_with_edge():
    client, server = "example.org/client", "example.org/server"
    receive = receive_request(server)
    response = send_response(server)
    edge = PMEdge(
        source=receive.id,
        target=response.id,
        evidence=evidence_for(server),
    )
    return stitch_pmgraphs(
        [
            pmgraph(client, (send_request(client),)),
            pmgraph(server, (receive, response), (edge,)),
        ]
    ).graph


def test_pm_edges_are_remapped_with_evidence_bearing_origins():
    graph = graph_with_edge()

    assert len(graph.edges) == 1
    edge = graph.edges[0]
    assert edge.source != edge.target
    assert edge.origins[0].module_id == "example.org/server"
    assert (edge.origins[0].source, edge.origins[0].target) == (
        next(
            member.node.id
            for node in graph.nodes
            for member in node.members
            if member.module_id == "example.org/server"
            and member.node.message == "Request"
        ),
        next(
            member.node.id
            for node in graph.nodes
            for member in node.members
            if member.module_id == "example.org/server"
            and member.node.message == "Response"
        ),
    )
    assert edge.origins[0].evidence == evidence_for("example.org/server")


def test_appgraph_rejects_origins_that_do_not_remap_to_the_edge():
    document = graph_with_edge().model_dump()
    document["edges"][0]["source"], document["edges"][0]["target"] = (
        document["edges"][0]["target"],
        document["edges"][0]["source"],
    )

    with pytest.raises(ValidationError, match="origin"):
        AppGraph.model_validate(document)


def test_appgraph_rejects_duplicate_qualified_edge_origins():
    document = graph_with_edge().model_dump()
    origin = document["edges"][0]["origins"][0]
    document["edges"][0]["origins"] = (origin, origin)

    with pytest.raises(ValidationError, match="origins.*unique"):
        AppGraph.model_validate(document)


def test_appgraph_rejects_dangling_origin_evidence():
    document = graph_with_edge().model_dump()
    document["edges"][0]["origins"][0]["evidence"][0]["source_id"] = (
        f"sha256:{'f' * 64}"
    )

    with pytest.raises(ValidationError, match="evidence source"):
        AppGraph.model_validate(document)


def test_three_modules_can_form_two_independent_contractions():
    graph = stitch_pmgraphs(
        [
            pmgraph("a", (send_request("a", "/to-b"),)),
            pmgraph(
                "b",
                (
                    receive_request("b", "/to-b"),
                    send_request("b", "/to-c"),
                ),
            ),
            pmgraph("c", (receive_request("c", "/to-c"),)),
        ]
    ).graph

    assert len(graph.nodes) == 2
    assert [node.match.status for node in graph.nodes] == ["matched", "matched"]
    assert sorted(
        tuple(member.module_id for member in node.members) for node in graph.nodes
    ) == [("a", "b"), ("b", "c")]


def test_stitch_diagnostics_cover_heuristic_and_ambiguous_associations(modules):
    client, server = modules
    matched = stitch_pmgraphs(
        [
            pmgraph(client, (send_request(client),)),
            pmgraph(server, (receive_request(server),)),
        ]
    )
    assert [item.code for item in matched.diagnostics] == ["appgraph.heuristic_match"]
    assert "does not prove network delivery" in matched.diagnostics[0].message

    ambiguous = stitch_pmgraphs(
        [
            pmgraph("a", (send_request("a"),)),
            pmgraph("b", (receive_request("b"),)),
            pmgraph("c", (receive_request("c"),)),
        ]
    )
    assert [item.code for item in ambiguous.diagnostics] == ["appgraph.ambiguous_match"]


def test_pruning_removes_only_unmatched_messages_and_incident_edges(modules):
    client, server = modules
    setting = parameter(client)
    unmatched = send_request(client, "/unmatched")
    edge = PMEdge(
        source=setting.id,
        target=unmatched.id,
        evidence=evidence_for(client),
    )
    stitched = stitch_pmgraphs(
        [
            pmgraph(client, (setting, unmatched, send_request(client)), (edge,)),
            pmgraph(server, (receive_request(server),)),
        ]
    ).graph

    pruned = prune_unmatched(stitched)

    assert len(pruned.nodes) == 2
    assert {node.match.status for node in pruned.nodes} == {
        "matched",
        "not_applicable",
    }
    assert pruned.edges == ()


def test_appgraph_file_stitching_and_io_are_canonical_and_order_independent(
    tmp_path, modules
):
    client, server = modules
    first = tmp_path / "first.pmgraph.json"
    second = tmp_path / "second.pmgraph.json"
    write_pmgraph(pmgraph(client, (send_request(client), parameter(client))), first)
    write_pmgraph(pmgraph(server, (receive_request(server),)), second)

    forward = stitch_pmgraph_files([first, second]).graph
    reverse = stitch_pmgraph_files([second, first]).graph
    forward_path = tmp_path / "forward.appgraph.json"
    reverse_path = tmp_path / "reverse.appgraph.json"
    write_appgraph(forward, forward_path)
    write_appgraph(reverse, reverse_path)

    assert forward_path.read_bytes() == reverse_path.read_bytes()
    assert forward_path.read_bytes().endswith(b"\n")
    assert load_appgraph(forward_path) == forward

    document = json.loads(forward_path.read_text())
    document["nodes"].reverse()
    forward_path.write_text(json.dumps(document))
    with pytest.raises(ValidationError, match="nodes.*canonical"):
        load_appgraph(forward_path)
