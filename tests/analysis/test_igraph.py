import json

import igraph as ig
import pytest
from pydantic import TypeAdapter

from conftamer.analysis import (
    ctype_to_igraph,
    find_vertices,
    influence_subgraph,
    to_igraph,
    write_graphml,
)
from conftamer.ctype_graph import CTypeEdge, CTypeGraph, CTypeNode
from conftamer.diagnostics import EvidenceRef, SourceArtifact
from conftamer.pmgraph import (
    BehaviorNode,
    ParameterNode,
    PMEdge,
    PMNode,
    SendRequestNode,
    make_node_id,
    make_pmgraph,
)

MODULE = "example.org/service"
SOURCE_ID = f"sha256:{'a' * 64}"
SOURCE = SourceArtifact(id=SOURCE_ID, kind="contexttrack-jsonl")
EVIDENCE = (
    EvidenceRef(source_id=SOURCE_ID, records=("line:1",), derivation="observed"),
)
NODE_ADAPTER = TypeAdapter(PMNode)


def pmgraph():
    parameter_fields = {"type": "Parameter", "name": "timeout"}
    parameter = ParameterNode(
        id=make_node_id(MODULE, parameter_fields),
        evidence=EVIDENCE,
        name="timeout",
    )
    behavior_fields = {"type": "Behavior", "name": "retry"}
    behavior = BehaviorNode(
        id=make_node_id(MODULE, behavior_fields),
        evidence=EVIDENCE,
        name="retry",
    )
    send_fields = {
        "type": "Send",
        "message": "Request",
        "api_id": None,
        "method": "GET",
        "host": "backend:8080",
        "path": "/items",
    }
    send = SendRequestNode(
        id=make_node_id(MODULE, send_fields),
        evidence=EVIDENCE,
        api_id=None,
        method="GET",
        host="backend:8080",
        path="/items",
    )
    return make_pmgraph(
        module_id=MODULE,
        sources=(SOURCE,),
        nodes=(parameter, behavior, send),
        edges=(PMEdge(source=parameter.id, target=send.id, evidence=EVIDENCE),),
    )


def all_pm_nodes_graph():
    definitions = (
        {"type": "Parameter", "name": "timeout"},
        {"type": "Behavior", "name": "retry"},
        {
            "type": "Receive",
            "message": "Request",
            "api_id": "public",
            "method": "GET",
            "pattern": "/items/{id}",
        },
        {
            "type": "Send",
            "message": "Request",
            "api_id": None,
            "method": "GET",
            "host": "backend:8080",
            "path": "/items",
        },
        {
            "type": "Receive",
            "message": "Response",
            "api_id": None,
            "method": "GET",
            "host": "backend:8080",
            "path": "/items",
            "status": 200,
        },
        {
            "type": "Send",
            "message": "Response",
            "api_id": "public",
            "method": "GET",
            "pattern": "/items/{id}",
            "status": 201,
        },
    )
    response_evidence = (
        *EVIDENCE,
        EvidenceRef(
            source_id=SOURCE_ID,
            records=("line:1",),
            derivation="response-correlation",
        ),
    )
    nodes = tuple(
        NODE_ADAPTER.validate_python(
            {
                "id": make_node_id(MODULE, fields),
                "evidence": response_evidence
                if fields.get("message") == "Response"
                else EVIDENCE,
                **fields,
            }
        )
        for fields in definitions
    )
    return make_pmgraph(
        module_id=MODULE,
        sources=(SOURCE,),
        nodes=nodes,
        edges=(),
    )


def test_pmgraph_projection_preserves_canonical_vertices_isolates_and_direction():
    document = pmgraph()

    graph = to_igraph(document)

    assert graph.is_directed()
    assert graph.vs["name"] == [node.id for node in document.nodes]
    assert graph.vcount() == 3
    assert graph.ecount() == 1
    parameter = next(node for node in document.nodes if node.type == "Parameter")
    send = next(node for node in document.nodes if node.type == "Send")
    assert graph.get_edgelist() == [
        (graph.vs.find(name=parameter.id).index, graph.vs.find(name=send.id).index)
    ]
    assert (
        graph.degree(
            graph.vs.find(
                name=next(node.id for node in document.nodes if node.type == "Behavior")
            ).index
        )
        == 0
    )


def test_pmgraph_projection_exposes_sanitized_semantic_attributes():
    document = pmgraph()

    graph = to_igraph(document)

    parameter_node = next(node for node in document.nodes if node.type == "Parameter")
    parameter = graph.vs.find(name=parameter_node.id).attributes()
    assert parameter == {
        "name": parameter_node.id,
        "canonical_id": parameter_node.id,
        "label": "Parameter: timeout",
        "node_type": "Parameter",
        "module_ids": json.dumps([MODULE], separators=(",", ":")),
        "match_status": "",
        "message": "",
        "api_id": "",
        "method": "",
        "host": "",
        "path": "",
        "pattern": "",
        "status": "",
        "members_json": "",
    }

    send_node = next(node for node in document.nodes if node.type == "Send")
    send = graph.vs.find(name=send_node.id).attributes()
    assert send["label"] == "Send Request: GET /items"
    assert send["node_type"] == "Send"
    assert send["message"] == "Request"
    assert send["api_id"] == ""
    assert send["method"] == "GET"
    assert send["host"] == "backend:8080"
    assert send["path"] == "/items"
    assert send["pattern"] == send["status"] == ""


@pytest.mark.parametrize(
    ("node_key", "label", "attributes"),
    [
        (("Parameter", ""), "Parameter: timeout", {"status": ""}),
        (("Behavior", ""), "Behavior: retry", {"status": ""}),
        (
            ("Receive", "Request"),
            "Receive Request: GET /items/{id}",
            {"api_id": "public", "pattern": "/items/{id}", "status": ""},
        ),
        (
            ("Send", "Request"),
            "Send Request: GET /items",
            {"host": "backend:8080", "path": "/items", "status": ""},
        ),
        (
            ("Receive", "Response"),
            "Receive Response: GET /items 200",
            {"host": "backend:8080", "path": "/items", "status": "200"},
        ),
        (
            ("Send", "Response"),
            "Send Response: GET /items/{id} 201",
            {"api_id": "public", "pattern": "/items/{id}", "status": "201"},
        ),
    ],
)
def test_pmgraph_projection_covers_every_node_shape(node_key, label, attributes):
    graph = to_igraph(all_pm_nodes_graph())
    vertex = next(
        vertex
        for vertex in graph.vs
        if (vertex["node_type"], vertex["message"]) == node_key
    )

    assert vertex["label"] == label
    assert all(isinstance(value, str) for value in vertex.attributes().values())
    for name, expected in attributes.items():
        assert vertex[name] == expected


def ctype_graph():
    child = CTypeNode(
        id="/child.Type",
        names=("/child.Type",),
        methods=(),
        tags=None,
    )
    isolated = CTypeNode(
        id="/isolated.Type",
        names=("/isolated.Type",),
        methods=(),
        tags={},
    )
    root = CTypeNode(
        id="/root.Type",
        names=("/root.Type", "/alias.Type"),
        methods=("Method",),
        tags={"json": "root"},
    )
    return CTypeGraph(
        nodes=(child, isolated, root),
        edges=(
            CTypeEdge(
                source=root.id,
                target=child.id,
                ast_paths=(("Field:a",), ("Field:z", "Tail")),
            ),
        ),
        name_to_node={
            "/alias.Type": root.id,
            child.id: child.id,
            isolated.id: isolated.id,
            root.id: root.id,
        },
    )


def test_ctype_projection_preserves_canonical_vertices_isolates_and_direction():
    document = ctype_graph()

    graph = ctype_to_igraph(document)

    assert graph.is_directed()
    assert graph.vs["name"] == [node.id for node in document.nodes]
    assert graph.degree(graph.vs.find(name="/isolated.Type").index) == 0
    assert graph.get_edgelist() == [
        (
            graph.vs.find(name="/root.Type").index,
            graph.vs.find(name="/child.Type").index,
        )
    ]


def test_ctype_projection_preserves_nested_semantics_and_grouped_ast_paths():
    graph = ctype_to_igraph(ctype_graph())

    root = graph.vs.find(name="/root.Type").attributes()
    assert root == {
        "name": "/root.Type",
        "label": "/root.Type",
        "names_json": '["/root.Type","/alias.Type"]',
        "methods_json": '["Method"]',
        "tags_json": '{"json":"root"}',
    }
    assert graph.vs.find(name="/child.Type")["tags_json"] == ""
    assert graph.vs.find(name="/isolated.Type")["tags_json"] == "{}"
    assert graph.es[0]["ast_paths_json"] == ('[["Field:a"],["Field:z","Tail"]]')


def test_find_vertices_prefers_exact_canonical_names():
    graph = to_igraph(pmgraph())
    parameter = next(
        vertex for vertex in graph.vs if vertex["node_type"] == "Parameter"
    )
    other = next(vertex for vertex in graph.vs if vertex.index != parameter.index)
    other["label"] = f"related to {parameter['name']}"

    assert find_vertices(graph, f"  {parameter['name']}  ") == (parameter.index,)


def test_find_vertices_matches_case_insensitive_substrings_and_reports_ambiguity():
    graph = to_igraph(pmgraph())

    parameter = next(
        vertex for vertex in graph.vs if vertex["node_type"] == "Parameter"
    )
    assert find_vertices(graph, "  TIME  ") == (parameter.index,)
    assert find_vertices(graph, "EXAMPLE.ORG/SERVICE") == tuple(range(graph.vcount()))
    assert find_vertices(graph, "missing") == ()


def test_find_vertices_rejects_blank_queries():
    with pytest.raises(ValueError, match="search query must not be empty"):
        find_vertices(to_igraph(pmgraph()), "   ")


@pytest.mark.parametrize(
    ("direction", "names"),
    [
        ("ancestors", ["a", "b"]),
        ("descendants", ["b", "c"]),
        ("both", ["a", "b", "c"]),
    ],
)
def test_influence_subgraph_selects_requested_transitive_reachability(direction, names):
    graph = ig.Graph(n=4, edges=((0, 1), (1, 2), (0, 3)), directed=True)
    graph.vs["name"] = ["a", "b", "c", "sibling"]
    graph.vs["label"] = ["A", "B", "C", "Sibling"]

    result = influence_subgraph(graph, [1, 1], direction=direction)

    assert result.is_directed()
    assert result.vs["name"] == names
    assert result.vs["label"] == [name.upper() for name in names]


def test_influence_subgraph_rejects_unknown_direction():
    graph = ig.Graph(n=1, directed=True)

    with pytest.raises(ValueError, match="direction"):
        influence_subgraph(
            graph,
            [0],
            direction="sideways",  # ty: ignore[invalid-argument-type]
        )


def test_pmgraph_graphml_round_trip(tmp_path):
    path = tmp_path / "pmgraph.graphml"
    projected = to_igraph(all_pm_nodes_graph())

    write_graphml(projected, path)
    loaded = ig.Graph.Read_GraphML(str(path))

    assert loaded.is_directed()
    assert loaded.vs["name"] == projected.vs["name"]
    assert loaded.vs["module_ids"] == projected.vs["module_ids"]
    assert loaded.vs["status"] == projected.vs["status"]
    assert loaded.get_edgelist() == projected.get_edgelist()


def test_ctype_graphml_round_trip_preserves_grouped_ast_paths(tmp_path):
    path = tmp_path / "ctype.graphml"
    projected = ctype_to_igraph(ctype_graph())

    write_graphml(projected, path)
    loaded = ig.Graph.Read_GraphML(str(path))

    assert loaded.is_directed()
    assert loaded.vs["name"] == projected.vs["name"]
    assert loaded.vs["tags_json"] == projected.vs["tags_json"]
    assert loaded.es["ast_paths_json"] == projected.es["ast_paths_json"]
    assert json.loads(loaded.es[0]["ast_paths_json"]) == [
        ["Field:a"],
        ["Field:z", "Tail"],
    ]
