import json
from pathlib import Path

import igraph as ig
import pytest

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


@pytest.mark.parametrize(
    ("field", "bad_character"),
    [
        ("id", "\x00"),
        ("method", "\x01"),
        ("tag", "\x01"),
        ("path", "\x01"),
    ],
)
def test_export_rejects_xml_forbidden_attribute_characters(
    tmp_path, field, bad_character
):
    node_id = f"/Type{bad_character}" if field == "id" else "/Type"
    node = CTypeNode(
        id=node_id,
        names=(node_id,),
        methods=(f"Method{bad_character}",) if field == "method" else (),
        tags={"json": f"value{bad_character}"} if field == "tag" else None,
    )
    graph = CTypeGraph(
        nodes=(node,),
        edges=(
            CTypeEdge(
                source=node_id,
                target=node_id,
                ast_paths=((f"Field{bad_character}",),) if field == "path" else (),
            ),
        ),
        name_to_node={node_id: node_id},
    )
    output = tmp_path / "invalid.graphml"

    with pytest.raises(ValueError, match="XML 1.0"):
        export_graphml(graph, output)

    assert not output.exists()


def test_export_preserves_destination_and_cleans_temp_after_igraph_failure(
    tmp_path, monkeypatch
):
    output = tmp_path / "failed.graphml"
    output.write_bytes(b"original")
    writer_paths = []

    def fail_after_write(_graph, path):
        writer_paths.append(Path(path))
        Path(path).write_text("partial", encoding="utf-8")
        raise ig.InternalError("serialization failed")

    monkeypatch.setattr(ig.Graph, "write_graphml", fail_after_write)

    with pytest.raises(ValueError, match="could not write GraphML"):
        export_graphml(ctype_graph(), output)

    assert len(writer_paths) == 1
    assert writer_paths[0] != output
    assert writer_paths[0].parent == output.parent
    assert output.read_bytes() == b"original"
    assert set(tmp_path.iterdir()) == {output}


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
