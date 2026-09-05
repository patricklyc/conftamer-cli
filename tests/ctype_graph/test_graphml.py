import json

import igraph as ig

from conftamer.ctype_graph import CTypeEdge, CTypeGraph, CTypeNode
from conftamer.ctype_graph.graphml import export_graphml, to_igraph


def ctype_graph() -> CTypeGraph:
    child = CTypeNode(id="/child.Type", names=("/child.Type",), methods=(), tags=None)
    isolated = CTypeNode(
        id="/isolated.Type", names=("/isolated.Type",), methods=(), tags={}
    )
    root = CTypeNode(
        id="/root.Type",
        names=("/root.Type", "/alias.Type"),
        methods=("MethodA", "MethodB"),
        tags={"json": 'json:"root"', "yaml": 'yaml:"root"'},
    )
    return CTypeGraph(
        nodes=(child, isolated, root),
        edges=(
            CTypeEdge(
                source=root.id,
                target=child.id,
                ast_paths=((), ("Field:a",), ("Field:z", "Tail")),
            ),
        ),
        name_to_node={
            "/alias.Type": root.id,
            child.id: child.id,
            isolated.id: isolated.id,
            root.id: root.id,
        },
    )


def assert_projection(graph: ig.Graph) -> None:
    assert graph.is_directed()
    assert graph.vs["name"] == [node.id for node in ctype_graph().nodes]
    assert graph.degree(graph.vs.find(name="/isolated.Type").index) == 0
    assert graph.get_edgelist() == [
        (
            graph.vs.find(name="/root.Type").index,
            graph.vs.find(name="/child.Type").index,
        )
    ]

    root = graph.vs.find(name="/root.Type")
    assert root["name"] == "/root.Type"
    assert root["label"] == "/root.Type"
    assert root["aliases"] == "/alias.Type"
    assert root["methods"] == "MethodA\nMethodB"
    assert root["tags"] == 'json: json:"root"\nyaml: yaml:"root"'
    assert root["names_json"] == '["/root.Type","/alias.Type"]'
    assert root["methods_json"] == '["MethodA","MethodB"]'
    assert root["tags_json"] == '{"json":"json:\\"root\\"","yaml":"yaml:\\"root\\""}'
    assert graph.vs.find(name="/child.Type")["tags_json"] == "null"
    assert graph.vs.find(name="/isolated.Type")["tags_json"] == "{}"

    edge = graph.es[0]
    assert edge["ast_paths"] == "(empty path)\nField:a\nField:z → Tail"
    assert edge["ast_paths_json"] == '[[],["Field:a"],["Field:z","Tail"]]'
    assert all(
        isinstance(value, str)
        for vertex in graph.vs
        for value in vertex.attributes().values()
    )
    assert all(isinstance(value, str) for value in edge.attributes().values())


def test_projection_is_readable_lossless_directed_and_keeps_isolates():
    assert_projection(to_igraph(ctype_graph()))


def test_graphml_round_trip_preserves_projection(tmp_path):
    path = tmp_path / "types.graphml"

    export_graphml(ctype_graph(), path)
    loaded = ig.Graph.Read_GraphML(str(path))

    assert_projection(loaded)
    assert json.loads(loaded.es[0]["ast_paths_json"]) == [
        [],
        ["Field:a"],
        ["Field:z", "Tail"],
    ]
