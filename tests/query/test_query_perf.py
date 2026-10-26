import random
import time

import pytest

from conftamer.pmgraph.models import Parameter, PMGraph
from conftamer.query import query


def _random_dag(n_nodes: int, edges_per_node: int, seed: int) -> PMGraph:
    """A random DAG with ``n_nodes`` nodes. Edges only ever point from a lower to
    a higher index, which guarantees acyclicity."""
    rng = random.Random(seed)
    nodes = {str(i): Parameter(key=str(i)) for i in range(n_nodes)}
    edges: set[tuple[str, str]] = set()
    for i in range(n_nodes):
        if i + 1 >= n_nodes:
            break
        for _ in range(edges_per_node):
            j = rng.randint(i + 1, n_nodes - 1)
            edges.add((str(i), str(j)))
    return PMGraph(module_id="bench", nodes=nodes, edges=edges)


# query enumerates *every* path. A random DAG can have exponentially many
# root->leaf paths (millions at these sizes), so raising n_nodes or
# edges_per_node can make this run very slow.
@pytest.mark.parametrize("n_nodes", [100])
def test_query_timing(n_nodes: int) -> None:
    graph = _random_dag(n_nodes, edges_per_node=4, seed=n_nodes)
    # A node in the middle, so it has both ancestors and descendants.
    target = str(n_nodes // 2)

    start = time.perf_counter()
    result = query(graph, target)
    elapsed_ms = (time.perf_counter() - start) * 1000

    # sanity: the query ran and the queried node is in its own subgraph
    assert target in result.subgraph.nodes

    # Printed timing (run with `-s` to see it):
    #   uv run pytest tests/query/test_query_perf.py -s
    print(
        f"\n[query timing] nodes={n_nodes:>4} "
        f"edges={len(graph.edges):>5} "
        f"subgraph_nodes={len(result.subgraph.nodes):>4} "
        f"paths={len(result.paths):>4} "
        f"time={elapsed_ms:.3f} ms"
    )


def _random_graph(n_nodes: int, edges_per_node: int, seed: int) -> PMGraph:
    """A random directed graph that allows cycles."""
    rng = random.Random(seed)
    nodes = {str(i): Parameter(key=str(i)) for i in range(n_nodes)}
    edges: set[tuple[str, str]] = set()

    for i in range(n_nodes):
        for _ in range(edges_per_node):
            j = rng.randint(0, n_nodes - 1)
            edges.add((str(i), str(j)))

    return PMGraph(module_id="bench", nodes=nodes, edges=edges)


@pytest.mark.parametrize("n_nodes", [100])
def test_query_timing_with_cycles(n_nodes: int) -> None:
    graph = _random_graph(n_nodes, edges_per_node=4, seed=n_nodes)
    target = str(n_nodes // 2)

    start = time.perf_counter()
    result = query(graph, target)
    elapsed_ms = (time.perf_counter() - start) * 1000

    assert target in result.subgraph.nodes

    print(
        f"\n[cyclic query timing] nodes={n_nodes:>4} "
        f"edges={len(graph.edges):>5} "
        f"subgraph_nodes={len(result.subgraph.nodes):>4} "
        f"paths={len(result.paths):>4} "
        f"time={elapsed_ms:.3f} ms"
    )


def _show(graph: PMGraph, target: str) -> None:
    """Print a graph's edges and the result of querying ``target`` in it."""
    result = query(graph, target)
    print(f"\n=== query {target!r} ===")
    print("edges:")
    for source, dest in sorted(graph.edges):
        print(f"    {source} -> {dest}")
    print(f"paths ({len(result.paths)}):")
    for path in result.paths:
        # A step with several nodes is a cycle; print it as [a, b].
        steps = (s[0] if len(s) == 1 else "[" + ", ".join(s) + "]" for s in path)
        print("    " + " -> ".join(steps))


# Prints the edges and paths for a small random cyclic graph (run with `-s`):
#   uv run pytest tests/query/test_query_perf.py -s -k show
@pytest.mark.parametrize("n_nodes,seed", [(6, 1), (8, 2), (10, 3)])
def test_show_cyclic_query(n_nodes: int, seed: int) -> None:
    graph = _random_graph(n_nodes, edges_per_node=2, seed=seed)
    _show(graph, str(n_nodes // 2))
