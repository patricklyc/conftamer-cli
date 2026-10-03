import random
import time

import pytest

from conftamer.pmgraph.models import Parameter, PMGraph
from conftamer.query import query


def _random_dag(n_nodes: int, edges_per_node: int, seed: int) -> PMGraph:
    """A random DAG with ``n_nodes`` nodes. Edges only ever point from a lower to
    a higher index, which guarantees acyclicity (matching query's assumption)."""
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


# path_limit caps enumeration: a dense random DAG can have exponentially many
# root->leaf paths, so an uncapped query would not terminate in reasonable time.
_PATH_LIMIT = -1


@pytest.mark.parametrize("n_nodes", [100, 500, 1000])
def test_query_timing(n_nodes: int) -> None:
    graph = _random_dag(n_nodes, edges_per_node=4, seed=n_nodes)
    # A node in the middle, so it has both ancestors and descendants.
    target = str(n_nodes // 2)

    start = time.perf_counter()
    result = query(graph, target, path_limit=_PATH_LIMIT)
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
        f"truncated={result.truncated!s:>5} "
        f"time={elapsed_ms:.3f} ms"
    )
