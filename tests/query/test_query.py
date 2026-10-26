from collections.abc import Iterable

import pytest

from conftamer.appgraph.models import AppGraph
from conftamer.pmgraph.models import Message, Parameter, PMGraph
from conftamer.query import find_parameters, query, to_igraph


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


def _flat(paths: list[list[list[str]]]) -> list[list[str]]:
    """Paths on an acyclic graph, where every step is a single node, as plain
    lists of node IDs."""
    assert all(len(step) == 1 for path in paths for step in path)
    return [[node for (node,) in path] for path in paths]


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
        # Both graph models reject dangling edges, so bypass validation.
        graph = PMGraph.model_construct(
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
    assert _flat(result.paths) == [["a", "m", "l"]]


def test_isolated_node_returns_itself() -> None:
    graph = _pmgraph(set(), extra_nodes={"solo"})
    result = query(graph, "solo")

    assert set(result.subgraph.nodes) == {"solo"}
    assert result.subgraph.edges == set()
    assert _flat(result.paths) == [["solo"]]


def test_paths_through_node_diamond() -> None:
    # r -> a -> m, then m fans out to two leaves via b1 and b2.
    graph = _pmgraph(
        {("r", "a"), ("a", "m"), ("m", "b1"), ("m", "b2"), ("b1", "l"), ("b2", "l")}
    )
    result = query(graph, "m")

    # Deterministic (neighbors visited in sorted order).
    assert _flat(result.paths) == [
        ["r", "a", "m", "b1", "l"],
        ["r", "a", "m", "b2", "l"],
    ]


def test_paths_cross_multiple_roots_and_leaves() -> None:
    # Two roots feed m and m feeds two leaves: 2 prefixes x 2 suffixes, ordered
    # by prefix first, then suffix (both in sorted node-ID order).
    graph = _pmgraph({("r1", "m"), ("r2", "m"), ("m", "l1"), ("m", "l2")})

    assert _flat(query(graph, "m").paths) == [
        ["r1", "m", "l1"],
        ["r1", "m", "l2"],
        ["r2", "m", "l1"],
        ["r2", "m", "l2"],
    ]


def test_node_as_root_and_as_leaf() -> None:
    graph = _pmgraph({("m", "a"), ("a", "l")})

    # m is a root: single path from m down to the leaf.
    assert _flat(query(graph, "m").paths) == [["m", "a", "l"]]
    # l is a leaf: single path from the root down to l.
    assert _flat(query(graph, "l").paths) == [["m", "a", "l"]]


class TestCyclicPaths:
    """Each SCC is one step of a path, so roots and leaves generalize to source
    and sink SCCs and a cycle never multiplies the number of paths."""

    def test_cycle_between_a_root_and_a_leaf(self) -> None:
        graph = _pmgraph({("r", "a"), ("a", "b"), ("b", "a"), ("b", "l")})

        # Starts only at the real root r, not inside the a <-> b loop.
        assert query(graph, "a").paths == [[["r"], ["a", "b"], ["l"]]]

    def test_cycle_with_no_leaf_ends_in_it(self) -> None:
        # Downstream of r there is no leaf, only the a <-> b sink cycle.
        graph = _pmgraph({("r", "a"), ("a", "b"), ("b", "a")})

        assert query(graph, "a").paths == [[["r"], ["a", "b"]]]
        assert query(graph, "r").paths == [[["r"], ["a", "b"]]]

    def test_cycle_with_no_root_starts_in_it(self) -> None:
        # Upstream of m there is no root, only the x <-> y source cycle.
        graph = _pmgraph({("x", "y"), ("y", "x"), ("x", "m"), ("m", "l")})

        assert query(graph, "m").paths == [[["x", "y"], ["m"], ["l"]]]

    def test_pure_cycle(self) -> None:
        graph = _pmgraph({("a", "b"), ("b", "c"), ("c", "a")})

        # The whole graph is one SCC, both the source and the sink.
        assert query(graph, "a").paths == [[["a", "b", "c"]]]

    def test_node_reachable_only_by_revisiting_another(self) -> None:
        # Every r -> l route through a goes b -> a -> b; grouping the a <-> b
        # loop still gives a its path.
        graph = _pmgraph({("r", "b"), ("b", "a"), ("a", "b"), ("b", "l")})

        assert query(graph, "a").paths == [[["r"], ["a", "b"], ["l"]]]

    def test_self_loop(self) -> None:
        graph = _pmgraph({("r", "a"), ("a", "a"), ("a", "l")})

        assert query(graph, "a").paths == [[["r"], ["a"], ["l"]]]

    def test_self_loop_as_the_only_way_out(self) -> None:
        # a's only successor is itself, so a is a leaf.
        graph = _pmgraph({("r", "a"), ("a", "a")})

        assert query(graph, "a").paths == [[["r"], ["a"]]]

    def test_multiple_roots_into_a_sink_cycle(self) -> None:
        # Two roots into the sink cycle a <-> b: 2 prefixes x 1 suffix.
        graph = _pmgraph({("r1", "a"), ("r2", "a"), ("a", "b"), ("b", "a")})

        assert query(graph, "a").paths == [
            [["r1"], ["a", "b"]],
            [["r2"], ["a", "b"]],
        ]

    def test_routes_inside_a_cycle_are_one_path(self) -> None:
        # a -> b -> c -> a plus a -> c has two routes around the cycle; both
        # are the same SCC step, and the routes themselves stay in the subgraph.
        graph = _pmgraph({("r", "a"), ("a", "b"), ("b", "c"), ("c", "a"), ("a", "c")})
        result = query(graph, "a")

        assert result.paths == [[["r"], ["a", "b", "c"]]]
        assert result.subgraph.edges == graph.edges

    def test_dense_cycle_does_not_multiply_paths(self) -> None:
        # Every node of the cluster points at every other: thousands of simple
        # routes through it, but one SCC step.
        cluster = [f"c{i}" for i in range(8)]
        edges = {(a, b) for a in cluster for b in cluster if a != b}
        graph = _pmgraph(edges | {("r", "c0"), ("c7", "l")})

        assert query(graph, "c3").paths == [[["r"], sorted(cluster), ["l"]]]

    def test_branches_around_and_between_cycles(self) -> None:
        # r feeds the a <-> b cycle directly and through m; the cycle feeds
        # the x <-> y cycle, which feeds two leaves.
        graph = _pmgraph(
            {
                ("r", "a"),
                ("r", "m"),
                ("m", "b"),
                ("a", "b"),
                ("b", "a"),
                ("b", "x"),
                ("x", "y"),
                ("y", "x"),
                ("x", "l1"),
                ("y", "l2"),
            }
        )

        assert query(graph, "y").paths == [
            [["r"], ["m"], ["a", "b"], ["x", "y"], ["l1"]],
            [["r"], ["m"], ["a", "b"], ["x", "y"], ["l2"]],
            [["r"], ["a", "b"], ["x", "y"], ["l1"]],
            [["r"], ["a", "b"], ["x", "y"], ["l2"]],
        ]

    def test_steps_are_independent_lists(self) -> None:
        graph = _pmgraph({("r1", "a"), ("r2", "a"), ("a", "b"), ("b", "a")})
        paths = query(graph, "a").paths

        paths[0][1].append("mutated")
        assert paths[1][1] == ["a", "b"]


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
    assert _flat(result.paths) == [["a", "m", "b"]]


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
    assert result.paths == [[["cfg"], ["call"]]]

    [root_id], [leaf_id] = result.paths[0]

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


class TestFindParameters:
    @staticmethod
    def _appgraph() -> AppGraph:
        # Shaped like stitch() output: parameters are "module_id::node_id".
        return AppGraph(
            nodes={
                "frontend::p-timeout": Parameter(key="timeout"),
                "orders::p-timeout": Parameter(key="timeout"),
                "orders::p-retries": Parameter(key="max_retries"),
                "unprefixed": Parameter(key="timeout"),
            },
            edges=set(),
        )

    def test_pmgraph_by_key(self) -> None:
        graph = PMGraph(
            module_id="orders",
            nodes={
                "p1": Parameter(key="max_retries"),
                "p2": Parameter(key="timeout"),
                "send": Message(
                    kind="send_request",
                    api_id="a",
                    method="GET",
                    host="h",
                    path="/max_retries",
                ),
            },
            edges=set(),
        )

        assert find_parameters(graph, "max_retries") == ["p1"]
        assert find_parameters(graph, "max_retries", module="orders") == ["p1"]
        assert find_parameters(graph, "max_retries", module="frontend") == []

    def test_appgraph_key_in_several_modules(self) -> None:
        assert find_parameters(self._appgraph(), "timeout") == [
            "frontend::p-timeout",
            "orders::p-timeout",
            "unprefixed",
        ]

    def test_appgraph_module_comes_from_the_id_prefix(self) -> None:
        graph = self._appgraph()

        assert find_parameters(graph, "timeout", module="orders") == [
            "orders::p-timeout"
        ]
        # A parameter without a "module::" prefix belongs to no module.
        assert find_parameters(graph, "timeout", module="unprefixed") == []

    def test_key_must_match_exactly(self) -> None:
        graph = self._appgraph()

        assert find_parameters(graph, "time") == []
        assert find_parameters(graph, "Timeout") == []
        assert find_parameters(graph, "p-timeout") == []  # a node ID, not a key
