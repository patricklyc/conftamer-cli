import xml.etree.ElementTree as ET
from pathlib import Path
 
from conftamer.pmgraph.pm_to_graphml import (
    GRAPHML_NS,
    graphml_to_pmgraph,
    pmgraph_to_graphml,
    pmgraph_to_graphml_element,
    write_graphml,
)
from conftamer.pmgraph.models import Message, Parameter, PMGraph



def _sample_graph() -> PMGraph:
    return PMGraph(
        module_id="frontend",
        nodes={
            "parameter-1": Parameter(key="timeout"),
            "message-1": Message(
                kind="send_request",
                api_id=None,
                method="POST",
                host="backend:8080",
                path="/jobs",
            ),
            "message-2": Message(
                kind="receive_response",
                api_id="orgB",
                method="POST",
                status_code=200,
            ),
        },
        edges={("parameter-1", "message-1"), ("message-1", "message-2")},
    )


def test_round_trip_preserves_graph() -> None:
    graph = _sample_graph()

    xml_text = pmgraph_to_graphml(graph)
    restored = graphml_to_pmgraph(xml_text)

    assert restored == graph

def test_write_graphml_round_trips_through_a_file(tmp_path: Path) -> None:
    graph = _sample_graph()
    path = tmp_path / "sample.graphml"
 
    write_graphml(graph, str(path))
    restored = graphml_to_pmgraph(path.read_text(encoding="utf-8"))
 
    assert restored == graph



def test_node_ids_are_prefixed_with_module_id() -> None:
    graph = _sample_graph()

    xml_text = pmgraph_to_graphml(graph)

    assert 'id="frontend::parameter-1"' in xml_text
    assert 'id="frontend::message-1"' in xml_text


def test_none_fields_are_omitted_not_written_empty() -> None:
    # api_id/host/path/pattern/status_code are all None here and should not
    # appear as <data> elements on this node at all (the <key> schema
    # declarations up top still list every attribute name regardless, since
    # GraphML declares the full schema once per document).
    graph = PMGraph(
        module_id="frontend",
        nodes={
            "message-1": Message(
                kind="send_request",
                api_id=None,
                method="GET",
            ),
        },
        edges=set(),
    )

    root = pmgraph_to_graphml_element(graph)
    ns = {"g": GRAPHML_NS}
    node_el = root.find(f".//g:node[@id='frontend::message-1']", ns)
    assert node_el is not None

    data_keys_used = {
        data_el.attrib["key"] for data_el in node_el.findall("g:data", ns)
    }
    key_names_used = {
        key_el.attrib["attr.name"]
        for key_el in root.findall("g:key", ns)
        if key_el.attrib["id"] in data_keys_used
    }

    assert key_names_used == {"kind", "method"}


def test_status_code_round_trips_as_int() -> None:
    graph = PMGraph(
        module_id="backend",
        nodes={
            "message-1": Message(
                kind="send_response",
                api_id="orgA",
                method="POST",
                status_code=404,
            ),
        },
        edges=set(),
    )

    restored = graphml_to_pmgraph(pmgraph_to_graphml(graph))

    restored_node = restored.nodes["message-1"]
    assert isinstance(restored_node, Message)
    assert restored_node.status_code == 404
    assert isinstance(restored_node.status_code, int)


def test_module_id_recorded_at_graph_level() -> None:
    graph = _sample_graph()

    xml_text = pmgraph_to_graphml(graph)
    restored = graphml_to_pmgraph(xml_text)

    assert 'for="graph"' in xml_text
    assert 'attr.name="module_id"' in xml_text
    assert restored.module_id == "frontend"


def test_edges_round_trip_without_module_prefix_leaking() -> None:
    graph = _sample_graph()

    restored = graphml_to_pmgraph(pmgraph_to_graphml(graph))

    assert restored.edges == graph.edges
    for source, target in restored.edges:
        assert "::" not in source
        assert "::" not in target


def test_empty_graph_round_trips() -> None:
    graph = PMGraph(module_id="empty-module", nodes={}, edges=set())

    restored = graphml_to_pmgraph(pmgraph_to_graphml(graph))

    assert restored == graph