import json
import re

import igraph
import pytest

from conftamer.appgraph.models import AppGraph, DroppedMessage
from conftamer.appgraph.stitch import stitch
from conftamer.io import (
    load_appgraph_json,
    load_graph_json,
    load_pmgraph_json,
    write_dropped_json,
    write_graph_json,
    write_graphml,
)
from conftamer.pmgraph.models import Message, Parameter, PMGraph


def test_json_round_trip_is_deterministic_utf8(tmp_path):
    source = tmp_path / "source.json"
    source.write_text(
        r"""{"module_id":"mödule","nodes":{
          "z":{"kind":"parameter","key":"\u00f6\u0000"},
          "a":{"kind":"send_request","api_id":null,"method":"gEt",
               "host":"Höst","path":"/"},
          "isolate":{"kind":"parameter","key":""}},
          "edges":[["z","a"],["a","z"],["z","a"]]}""",
        encoding="utf-8",
    )
    graph = load_pmgraph_json(str(source))
    first, second = tmp_path / "first.json", tmp_path / "second.json"
    write_graph_json(graph, first)
    write_graph_json(graph, str(second))
    raw = first.read_bytes()
    assert raw == second.read_bytes()
    assert load_pmgraph_json(first) == graph
    payload = json.loads(raw)
    assert list(payload["nodes"]) == ["z", "a", "isolate"]
    assert payload["nodes"]["z"]["key"] == "ö\0"
    message = payload["nodes"]["a"]
    assert message["api_id"] is message["pattern"] is message["status_code"] is None
    assert message["path"] == "/"
    assert payload["edges"] == [["a", "z"], ["z", "a"]]
    assert raw.startswith('{\n  "module_id": "mödule",\n'.encode())
    assert raw.endswith(b"}\n") and b"\\u00f6" not in raw


@pytest.mark.parametrize(
    "data",
    [
        b"{",
        b"\xff",
        b'{"module_id":"m","nodes":{},"edges":[],"extra":true}',
        b'{"module_id":"m","nodes":{},"edges":[["absent","absent"]]}',
        b'{"module_id":"m","nodes":{"p":{"kind":"parameter","key":"",'
        b'"extra":true}},"edges":[]}',
        b'{"module_id":"m","nodes":{"r":{"kind":"send_response","api_id":null,'
        b'"method":"GET","path":"/","status_code":"200"}},"edges":[]}',
    ],
)
def test_load_rejects_invalid_input_with_path(tmp_path, data):
    path = tmp_path / "invalid.json"
    path.write_bytes(data)
    with pytest.raises(ValueError, match=rf"{re.escape(str(path))}: .+"):
        load_pmgraph_json(path)


def test_empty_graph_and_filesystem_errors(tmp_path):
    graph = PMGraph(module_id="m", nodes={}, edges=set())
    path = tmp_path / "graph.json"
    write_graph_json(graph, path)
    assert load_pmgraph_json(path) == graph
    with pytest.raises(FileExistsError):
        write_graph_json(graph, path)
    assert load_pmgraph_json(path) == graph
    missing = tmp_path / "absent" / "graph.json"
    with pytest.raises(FileNotFoundError):
        load_pmgraph_json(missing)
    with pytest.raises(FileNotFoundError):
        write_graph_json(graph, missing)
    assert not missing.parent.exists()


def _appgraph() -> AppGraph:
    client = PMGraph(
        module_id="client",
        nodes={
            "cfg": Parameter(key="timeout"),
            "send": Message(
                kind="send_request",
                api_id="api",
                method="GET",
                host="backend",
                path="/items/42",
            ),
        },
        edges={("cfg", "send")},
    )
    backend = PMGraph(
        module_id="backend",
        nodes={
            "recv": Message(
                kind="receive_request",
                api_id="api",
                method="GET",
                pattern="/items/{id}",
            )
        },
        edges=set(),
    )
    return stitch([client, backend])


def test_appgraph_json_round_trip(tmp_path):
    graph = _appgraph()
    path = tmp_path / "app.json"
    write_graph_json(graph, path)

    assert load_appgraph_json(path) == graph
    assert json.loads(path.read_text(encoding="utf-8"))["edges"] == [
        ["client::cfg", "link0"]
    ]


def test_load_graph_json_detects_the_graph_type(tmp_path):
    pm_path, app_path = tmp_path / "pm.json", tmp_path / "app.json"
    pmgraph = PMGraph(module_id="m", nodes={"p": Parameter(key="k")}, edges=set())
    write_graph_json(pmgraph, pm_path)
    write_graph_json(_appgraph(), app_path)

    assert load_graph_json(pm_path) == pmgraph
    assert isinstance(load_graph_json(app_path), AppGraph)


@pytest.mark.parametrize("data", [b"{", b"\xff", b"null", b"[]", b'{"nodes":{}}'])
def test_load_graph_json_rejects_invalid_input_with_path(tmp_path, data):
    path = tmp_path / "invalid.json"
    path.write_bytes(data)
    with pytest.raises(ValueError, match=rf"{re.escape(str(path))}: .+"):
        load_graph_json(path)


def _named_edges(network: igraph.Graph) -> set[tuple[str, str]]:
    return {
        (network.vs[source]["name"], network.vs[target]["name"])
        for source, target in network.get_edgelist()
    }


def test_graphml_round_trip_preserves_a_pmgraph(tmp_path):
    graph = PMGraph(
        module_id="module<&",
        nodes={
            "10": Parameter(key="same\0<&é"),
            '2<&"': Message(
                kind="receive_response",
                api_id=None,
                method="GET",
                host="example.test",
                path="/",
                status_code=10**30,
            ),
            "isolated": Parameter(key="same\0<&é"),
        },
        edges={("10", '2<&"'), ('2<&"', "10"), ('2<&"', '2<&"')},
    )
    path = tmp_path / "graph.graphml"
    write_graphml(graph, path)

    network = igraph.Graph.Read_GraphML(str(path))
    assert network.is_directed()
    assert network["module_id"] == graph.module_id
    assert network.vs["name"] == sorted(graph.nodes)
    assert _named_edges(network) == graph.edges
    assert {
        name: json.loads(node_json)
        for name, node_json in zip(network.vs["name"], network.vs["node_json"])
    } == {name: node.model_dump(mode="json") for name, node in graph.nodes.items()}
    assert network.degree("isolated", mode="all") == 0


def test_graphml_exports_an_appgraph(tmp_path):
    graph = _appgraph()
    path = tmp_path / "app.graphml"
    write_graphml(graph, path)

    network = igraph.Graph.Read_GraphML(str(path))
    assert "module_id" not in network.attributes()
    assert network.vs["kind"] == ["parameter", "linked_message"]
    assert _named_edges(network) == graph.edges


def test_graphml_never_overwrites(tmp_path):
    graph = PMGraph(module_id="empty", nodes={}, edges=set())
    path = tmp_path / "empty.graphml"
    write_graphml(graph, path)
    original = path.read_bytes()

    assert igraph.Graph.Read_GraphML(str(path)).vcount() == 0
    with pytest.raises(FileExistsError):
        write_graphml(graph, path)
    assert path.read_bytes() == original


@pytest.mark.parametrize(("module_id", "node_id"), [("m\u0001", "n"), ("m", "n\r")])
def test_graphml_rejects_unpreservable_identities(tmp_path, module_id, node_id):
    path = tmp_path / "invalid.graphml"
    graph = PMGraph(
        module_id=module_id, nodes={node_id: Parameter(key="ok")}, edges=set()
    )

    with pytest.raises(ValueError, match="GraphML cannot preserve identity"):
        write_graphml(graph, path)
    assert not path.exists()


def test_graphml_translates_igraph_failures(tmp_path, monkeypatch):
    path = tmp_path / "failed.graphml"

    def fail(*args, **kwargs):
        raise igraph.InternalError("broken writer")

    monkeypatch.setattr(igraph.Graph, "write_graphml", fail)
    with pytest.raises(OSError, match="cannot write GraphML .*: broken writer"):
        write_graphml(PMGraph(module_id="m", nodes={}, edges=set()), path)


def test_write_dropped_json(tmp_path):
    message = Message(
        kind="send_request", api_id="a", method="GET", host="höst", path="/x"
    )
    dropped = [
        DroppedMessage(module_id="m", node_id="n", reason="unmatched", message=message)
    ]
    path = tmp_path / "dropped.json"

    write_dropped_json(dropped, path)

    raw = path.read_bytes()
    assert raw.endswith(b"]\n") and b"\r" not in raw
    text = raw.decode("utf-8")
    assert "höst" in text
    assert [DroppedMessage.model_validate(d) for d in json.loads(text)] == dropped


def test_write_dropped_json_empty_and_never_overwrites(tmp_path):
    path = tmp_path / "dropped.json"
    write_dropped_json([], path)
    assert json.loads(path.read_text(encoding="utf-8")) == []

    with pytest.raises(FileExistsError):
        write_dropped_json([], path)
    assert path.read_bytes() == b"[]\n"
