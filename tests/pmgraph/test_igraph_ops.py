import igraph
import pytest

from conftamer.pmgraph.igraph_ops import to_igraph, write_graphml
from conftamer.pmgraph.models import Message, Parameter, PMGraph


def _rich_graph() -> PMGraph:
    response = Message(
        kind="receive_response",
        api_id=None,
        method="GET",
        host="example.test",
        path="",
        status_code=10**30,
    )
    routed_request = Message(
        kind="receive_request",
        api_id="api<&",
        method="POST",
        pattern="/jobs/{id}",
    )
    return PMGraph(
        module_id="module<&",
        nodes={
            "10": Parameter(key="same<&é"),
            '2<&"': response,
            "routed": routed_request,
            "isolated": Parameter(key="same<&é"),
        },
        edges={("10", '2<&"'), ('2<&"', "10"), ('2<&"', '2<&"')},
    )


def _named_edges(network: igraph.Graph) -> list[tuple[str, str]]:
    return [
        (network.vs[source]["name"], network.vs[target]["name"])
        for source, target in network.get_edgelist()
    ]


def _assert_topology(network: igraph.Graph, graph: PMGraph) -> None:
    assert network.is_directed()
    assert network["module_id"] == graph.module_id
    assert network.vs["name"] == list(graph.nodes)
    assert _named_edges(network) == sorted(graph.edges)


def test_conversion_and_graphml_export_use_flattened_node_attributes(tmp_path):
    graph = _rich_graph()
    original = graph.model_copy(deep=True)

    network = to_igraph(graph)
    _assert_topology(network, graph)
    assert {
        attribute: network.vs[attribute] for attribute in network.vertex_attributes()
    } == {
        "name": ["10", '2<&"', "routed", "isolated"],
        "kind": [
            "parameter",
            "receive_response",
            "receive_request",
            "parameter",
        ],
        "key": ["same<&é", None, None, "same<&é"],
        "api_id": [None, None, "api<&", None],
        "method": [None, "GET", "POST", None],
        "host": [None, "example.test", None, None],
        "path": [None, "", None, None],
        "pattern": [None, None, "/jobs/{id}", None],
        "status_code": [None, 10**30, None, None],
    }
    assert network.degree("isolated", mode="all") == 0

    path = tmp_path / "graph.graphml"
    write_graphml(graph, path)
    exported = igraph.Graph.Read_GraphML(str(path))
    _assert_topology(exported, graph)
    assert exported.vs.find(name="10")["key"] == "same<&é"
    assert graph == original


def test_empty_graph_and_existing_output(tmp_path):
    graph = PMGraph(module_id="empty", nodes={}, edges=set())
    assert to_igraph(graph).vcount() == 0
    path = tmp_path / "empty.graphml"
    write_graphml(graph, path)
    original = path.read_bytes()

    assert igraph.Graph.Read_GraphML(str(path)).vcount() == 0
    with pytest.raises(FileExistsError):
        write_graphml(graph, path)
    assert path.read_bytes() == original


@pytest.mark.parametrize(("module_id", "node_id"), [("m\u0001", "n"), ("m", "n\r")])
def test_write_graphml_rejects_unpreservable_identities(tmp_path, module_id, node_id):
    path = tmp_path / "invalid.graphml"
    graph = PMGraph(
        module_id=module_id, nodes={node_id: Parameter(key="ok")}, edges=set()
    )

    with pytest.raises(ValueError, match="GraphML cannot preserve"):
        write_graphml(graph, path)
    assert not path.exists()


def test_write_graphml_rejects_unpreservable_node_attribute(tmp_path):
    path = tmp_path / "invalid.graphml"
    graph = PMGraph(module_id="m", nodes={"n": Parameter(key="bad\0key")}, edges=set())

    with pytest.raises(ValueError, match="GraphML cannot preserve"):
        write_graphml(graph, path)
    assert not path.exists()


def test_write_graphml_translates_igraph_failures(tmp_path, monkeypatch):
    path = tmp_path / "failed.graphml"

    def fail(*args, **kwargs):
        raise igraph.InternalError("broken writer")

    monkeypatch.setattr(igraph.Graph, "write_graphml", fail)
    with pytest.raises(OSError, match=rf"cannot write GraphML {path}: broken writer"):
        write_graphml(PMGraph(module_id="m", nodes={}, edges=set()), path)
