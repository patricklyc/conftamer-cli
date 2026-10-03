from collections.abc import Iterable

import pytest

from conftamer.appgraph.models import AppGraph
from conftamer.pmgraph.models import Message, Parameter, PMGraph
from conftamer.query import query, to_igraph


def _pmgraph(edges: set[tuple[str, str]], extra_nodes: Iterable[str] = ()) -> PMGraph:
    """A PMGraph whose nodes are inferred from ``edges`` (plus any isolated
    ``extra_nodes``). Node kind is irrelevant to querying, so every node is a
    Parameter."""
    node_ids = {n for edge in edges for n in edge} | set(extra_nodes)
    return PMGraph(
        module_id="m",
        nodes={nid: Parameter(key=nid) for nid in node_ids},
        edges=edges,
    )


def _named_edges(graph: PMGraph | AppGraph) -> set[tuple[str, str]]:
    g = to_igraph(graph)
    return {(g.vs[s]["name"], g.vs[t]["name"]) for s, t in g.get_edgelist()}


class TestToIgraph:
    def test_vertices_are_named_by_node_id_in_sorted_order(self) -> None:
        g = to_igraph(_pmgraph({("b", "a"), ("c", "b")}))

        assert g.is_directed()
        assert g.vs["name"] == ["a", "b", "c"]

    def test_edges_round_trip(self) -> None:
        edges = {("r", "a"), ("a", "m"), ("m", "b1"), ("m", "b2"), ("a", "l")}
        graph = _pmgraph(edges)

        assert to_igraph(graph).ecount() == len(edges)
        assert _named_edges(graph) == edges

    def test_isolated_nodes_become_vertices(self) -> None:
        g = to_igraph(_pmgraph({("a", "b")}, extra_nodes={"solo"}))

        assert set(g.vs["name"]) == {"a", "b", "solo"}
        assert g.vs.find(name="solo").degree() == 0

    def test_empty_graph(self) -> None:
        g = to_igraph(PMGraph(module_id="m", nodes={}, edges=set()))

        assert g.vcount() == 0
        assert g.ecount() == 0

    def test_appgraph(self) -> None:
        graph = AppGraph(
            nodes={nid: Parameter(key=nid) for nid in ("a", "m", "b")},
            edges={("a", "m"), ("m", "b")},
        )

        assert to_igraph(graph).vs["name"] == ["a", "b", "m"]
        assert _named_edges(graph) == {("a", "m"), ("m", "b")}

    def test_dangling_edge_raises(self) -> None:
        # PMGraph does not itself validate edge endpoints; conversion does.
        graph = PMGraph(
            module_id="m", nodes={"a": Parameter(key="a")}, edges={("a", "ghost")}
        )

        with pytest.raises(ValueError, match="missing endpoint"):
            to_igraph(graph)


def test_unknown_node_raises() -> None:
    with pytest.raises(ValueError):
        query(_pmgraph({("a", "b")}), "missing")


def test_subgraph_is_ancestors_and_descendants() -> None:
    # r -> a -> m -> b -> l, and a sibling s hanging off a (a -> s).
    graph = _pmgraph({("r", "a"), ("a", "m"), ("m", "b"), ("b", "l"), ("a", "s")})
    result = query(graph, "m")

    # m keeps r, a (ancestors) and b, l (descendants); the sibling s is excluded.
    assert set(result.subgraph.nodes) == {"r", "a", "m", "b", "l"}
    assert "s" not in result.subgraph.nodes
    assert ("a", "s") not in result.subgraph.edges
    assert result.subgraph.edges == {("r", "a"), ("a", "m"), ("m", "b"), ("b", "l")}


def test_subgraph_includes_bypass_edges_induced() -> None:
    # a is an ancestor of m, l a descendant; the edge a -> l bypasses m entirely.
    # A fully induced subgraph still keeps it (both endpoints are in the set).
    graph = _pmgraph({("a", "m"), ("m", "l"), ("a", "l")})
    result = query(graph, "m")

    assert ("a", "l") in result.subgraph.edges
    # ...but a bypass path is never enumerated as a path "through" m.
    assert result.paths == [["a", "m", "l"]]


def test_isolated_node_returns_itself() -> None:
    graph = _pmgraph(set(), extra_nodes={"solo"})
    result = query(graph, "solo")

    assert set(result.subgraph.nodes) == {"solo"}
    assert result.subgraph.edges == set()
    assert result.paths == [["solo"]]
    assert result.truncated is False


def test_paths_through_node_diamond() -> None:
    # r -> a -> m, then m fans out to two leaves via b1 and b2.
    graph = _pmgraph(
        {("r", "a"), ("a", "m"), ("m", "b1"), ("m", "b2"), ("b1", "l"), ("b2", "l")}
    )
    result = query(graph, "m")

    # Deterministic (neighbors visited in sorted order).
    assert result.paths == [
        ["r", "a", "m", "b1", "l"],
        ["r", "a", "m", "b2", "l"],
    ]
    assert result.truncated is False


def test_path_limit_caps_and_flags_truncation() -> None:
    graph = _pmgraph(
        {("r", "a"), ("a", "m"), ("m", "b1"), ("m", "b2"), ("b1", "l"), ("b2", "l")}
    )

    capped = query(graph, "m", path_limit=1)
    assert capped.paths == [["r", "a", "m", "b1", "l"]]
    assert capped.truncated is True

    exact = query(graph, "m", path_limit=2)
    assert len(exact.paths) == 2
    assert exact.truncated is False

    generous = query(graph, "m", path_limit=99)
    assert len(generous.paths) == 2
    assert generous.truncated is False

    unlimited = query(graph, "m", path_limit=-1)
    assert len(unlimited.paths) == 2
    assert unlimited.truncated is False


def test_paths_cross_multiple_roots_and_leaves() -> None:
    # Two roots feed m and m feeds two leaves: 2 prefixes x 2 suffixes, ordered
    # by prefix first, then suffix (both in sorted node-ID order).
    graph = _pmgraph({("r1", "m"), ("r2", "m"), ("m", "l1"), ("m", "l2")})

    assert query(graph, "m").paths == [
        ["r1", "m", "l1"],
        ["r1", "m", "l2"],
        ["r2", "m", "l1"],
        ["r2", "m", "l2"],
    ]

    capped = query(graph, "m", path_limit=3)
    assert capped.paths == [["r1", "m", "l1"], ["r1", "m", "l2"], ["r2", "m", "l1"]]
    assert capped.truncated is True


def test_path_limit_zero_returns_none_but_flags_truncation() -> None:
    graph = _pmgraph({("a", "m"), ("m", "b")})
    result = query(graph, "m", path_limit=0)

    assert result.paths == []
    assert result.truncated is True


def test_node_as_root_and_as_leaf() -> None:
    graph = _pmgraph({("m", "a"), ("a", "l")})

    # m is a root: single path from m down to the leaf.
    assert query(graph, "m").paths == [["m", "a", "l"]]
    # l is a leaf: single path from the root down to l.
    assert query(graph, "l").paths == [["m", "a", "l"]]


def test_returns_same_graph_type_pmgraph() -> None:
    graph = _pmgraph({("a", "m")})
    result = query(graph, "m")

    assert isinstance(result.subgraph, PMGraph)
    assert result.subgraph.module_id == "m"  # preserved by model_copy


def test_returns_same_graph_type_appgraph() -> None:
    graph = AppGraph(
        nodes={nid: Parameter(key=nid) for nid in ("a", "m", "b")},
        edges={("a", "m"), ("m", "b")},
    )
    result = query(graph, "m")

    assert isinstance(result.subgraph, AppGraph)
    assert set(result.subgraph.nodes) == {"a", "m", "b"}
    assert result.paths == [["a", "m", "b"]]


def test_path_ids_resolve_back_to_the_right_nodes() -> None:
    # A path returns bare node IDs; the design is that they resolve against
    # result.subgraph.nodes. This exercises that round trip end to end.
    graph = PMGraph(
        module_id="frontend",
        nodes={
            "cfg": Parameter(key="db_timeout"),
            "call": Message(
                kind="send_request",
                api_id="jobs-api",
                method="POST",
                host="backend:8080",
                path="/jobs",
            ),
        },
        edges={("cfg", "call")},
    )

    result = query(graph, "cfg")
    assert result.paths == [["cfg", "call"]]

    root_id, leaf_id = result.paths[0]

    # Resolve each ID back to its node via the returned subgraph...
    root = result.subgraph.nodes[root_id]
    leaf = result.subgraph.nodes[leaf_id]

    # ...and confirm we got the correct, fully-populated nodes.
    assert isinstance(root, Parameter)
    assert root.key == "db_timeout"

    assert isinstance(leaf, Message)
    assert leaf.kind == "send_request"
    assert leaf.method == "POST"
    assert leaf.path == "/jobs"

    # The resolved nodes are the same objects as in the original graph.
    assert root == graph.nodes["cfg"]
    assert leaf == graph.nodes["call"]
