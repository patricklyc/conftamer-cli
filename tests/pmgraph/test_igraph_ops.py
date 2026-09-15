import json

import igraph
import pytest

from conftamer.pmgraph.igraph_ops import query_node, to_igraph, write_graphml
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
    return PMGraph(
        module_id="module<&",
        nodes={
            "10": Parameter(key="same\0<&é"),
            '2<&"': response,
            "isolated": Parameter(key="same\0<&é"),
        },
        edges={("10", '2<&"'), ('2<&"', "10"), ('2<&"', '2<&"')},
    )


def _named_edges(network: igraph.Graph) -> list[tuple[str, str]]:
    return [
        (network.vs[source]["name"], network.vs[target]["name"])
        for source, target in network.get_edgelist()
    ]


def _assert_preserved(network: igraph.Graph, graph: PMGraph) -> None:
    assert network.is_directed()
    assert network["module_id"] == graph.module_id
    assert network.vs["name"] == list(graph.nodes)
    assert network.vs["kind"] == [node.kind for node in graph.nodes.values()]
    assert _named_edges(network) == sorted(graph.edges)
    assert [json.loads(value) for value in network.vs["node_json"]] == [
        node.model_dump(mode="json") for node in graph.nodes.values()
    ]


def test_conversion_and_graphml_round_trip_preserve_the_complete_graph(tmp_path):
    graph = _rich_graph()
    original = graph.model_copy(deep=True)

    network = to_igraph(graph)
    _assert_preserved(network, graph)
    assert network.degree("isolated", mode="all") == 0
    assert "\\u0000" in network.vs["node_json"][0]

    path = tmp_path / "graph.graphml"
    write_graphml(graph, path)
    _assert_preserved(igraph.Graph.Read_GraphML(str(path)), graph)
    assert graph == original


def test_query_node_returns_directed_reachability_in_node_order():
    graph = PMGraph(
        module_id="m",
        nodes={
            name: Parameter(key=name)
            for name in (
                "descendant-2",
                "ancestor-2",
                "seed",
                "ancestor-1",
                "descendant-1",
                "isolate",
            )
        },
        edges={
            ("ancestor-2", "ancestor-1"),
            ("ancestor-1", "seed"),
            ("seed", "descendant-1"),
            ("descendant-1", "descendant-2"),
            ("seed", "descendant-2"),
        },
    )
    original = graph.model_copy(deep=True)

    assert query_node(graph, "seed") == {
        "ancestors": ["ancestor-2", "ancestor-1"],
        "descendants": ["descendant-2", "descendant-1"],
    }
    assert query_node(graph, "isolate") == {"ancestors": [], "descendants": []}
    assert graph == original


def test_query_node_excludes_seed_from_cycles_and_uses_exact_ids():
    graph = _rich_graph()

    assert query_node(graph, "10") == {
        "ancestors": ['2<&"'],
        "descendants": ['2<&"'],
    }


def test_query_node_rejects_unknown_id():
    graph = PMGraph(module_id="m", nodes={"known": Parameter(key="x")}, edges=set())

    with pytest.raises(ValueError, match="unknown node ID 'missing'"):
        query_node(graph, "missing")


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

    with pytest.raises(ValueError, match="GraphML cannot preserve identity"):
        write_graphml(graph, path)
    assert not path.exists()


def test_write_graphml_translates_igraph_failures(tmp_path, monkeypatch):
    path = tmp_path / "failed.graphml"

    def fail(*args, **kwargs):
        raise igraph.InternalError("broken writer")

    monkeypatch.setattr(igraph.Graph, "write_graphml", fail)
    with pytest.raises(OSError, match=rf"cannot write GraphML {path}: broken writer"):
        write_graphml(PMGraph(module_id="m", nodes={}, edges=set()), path)
