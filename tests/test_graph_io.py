import json
import re

import igraph
import pytest

import conftamer.igraph_ops
import conftamer.io
import conftamer.pmgraph.igraph_ops
from conftamer.appgraph.models import AppGraph, DroppedMessage, LinkedMessage
from conftamer.appgraph.stitch import stitch
from conftamer.io import (
    load_appgraph_json,
    load_graph_json,
    write_dropped_json,
    write_graph_json,
    write_graphml,
)
from conftamer.pmgraph.models import Message, Parameter, PMGraph


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


@pytest.mark.parametrize(
    "data",
    [
        b"{",
        b"\xff",
        b"null",
        b"[]",
        b'{"nodes":{}}',
        pytest.param(b"[" * 200000, id="nested-too-deeply"),
    ],
)
def test_load_graph_json_rejects_invalid_input_with_path(tmp_path, data):
    path = tmp_path / "invalid.json"
    path.write_bytes(data)
    with pytest.raises(ValueError, match=rf"{re.escape(str(path))}: .+"):
        load_graph_json(path)


@pytest.mark.parametrize(
    "data, reason",
    [
        (b'{"nodes":{},"edges":[],"extra":true}', "type=extra_forbidden"),
        (
            b'{"nodes":{"l":{"kind":"linked_message","api_id":"a","method":"GET",'
            b'"pattern":"/x","status_code":"200","sender_module":"a",'
            b'"sender_node":"s","receiver_module":"b","receiver_node":"r"}},'
            b'"edges":[]}',
            "type=int_type",
        ),
        (b'{"nodes":{},"edges":[]}\xff', "invalid start byte"),
    ],
)
def test_load_appgraph_rejects_invalid_input_with_path(tmp_path, data, reason):
    path = tmp_path / "invalid[app].json"
    path.write_bytes(data)
    with pytest.raises(ValueError, match=rf"{re.escape(str(path))}: .+") as caught:
        load_appgraph_json(path)
    assert reason in str(caught.value)


def _named_edges(network: igraph.Graph) -> set[tuple[str, str]]:
    return {
        (network.vs[source]["name"], network.vs[target]["name"])
        for source, target in network.get_edgelist()
    }


def test_graphml_exports_an_appgraph_with_flattened_attributes(tmp_path):
    graph = _appgraph()
    path = tmp_path / "app.graphml"
    write_graphml(graph, path)

    network = igraph.Graph.Read_GraphML(str(path))
    assert "module_id" not in network.attributes()
    assert network.vs["name"] == ["client::cfg", "link0"]
    assert set(network.vertex_attributes()) - {"id"} == {
        "name",
        "kind",
        "key",
        "api_id",
        "method",
        "pattern",
        "status_code",
        "sender_module",
        "sender_node",
        "receiver_module",
        "receiver_node",
    }
    assert network.vs.find(name="client::cfg")["key"] == "timeout"
    link = network.vs.find(name="link0")
    assert link["kind"] == "linked_message"
    assert (link["sender_module"], link["sender_node"]) == ("client", "send")
    assert (link["receiver_module"], link["receiver_node"]) == ("backend", "recv")
    assert link["pattern"] == "/items/{id}"
    assert _named_edges(network) == graph.edges


LINK = LinkedMessage(
    api_id="api",
    method="GET",
    pattern="/x",
    sender_module="a",
    sender_node="s",
    receiver_module="b",
    receiver_node="r",
)


@pytest.mark.parametrize(
    "nodes",
    [
        {"p": Parameter(key="bad\0key")},
        {"l": LINK.model_copy(update={"sender_node": "bad\0"})},
        {"n\r": Parameter(key="ok")},
    ],
)
def test_graphml_rejects_unpreservable_appgraph_text(tmp_path, nodes):
    path = tmp_path / "invalid.graphml"
    graph = AppGraph(nodes=nodes, edges=set())

    with pytest.raises(ValueError, match="GraphML cannot preserve"):
        write_graphml(graph, path)
    assert not path.exists()


def test_graphml_writers_are_one_function():
    assert conftamer.io.write_graphml is conftamer.igraph_ops.write_graphml
    assert conftamer.pmgraph.igraph_ops.write_graphml is conftamer.io.write_graphml


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
