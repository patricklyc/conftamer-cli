import json
import random
import time
from pathlib import Path

import pytest

from conftamer.pmgraph.models import Parameter, PMGraph
from conftamer.query import query

# Each test writes the paths it got here (git-ignored), replacing the last run's.
OUTPUT_DIR = Path(__file__).parent / "perf-output"


def _write_paths(
    name: str, seed: int, target: str, paths: list[list[list[str]]]
) -> Path:
    """Write ``paths`` as JSON, one path per line so large outputs stay readable."""
    OUTPUT_DIR.mkdir(exist_ok=True)
    output = OUTPUT_DIR / f"{name}.json"
    lines = ",\n".join("    " + json.dumps(path) for path in paths)
    output.write_text(
        f'{{"seed": {seed}, "target": {json.dumps(target)}, "paths": [\n{lines}\n]}}\n',
        encoding="utf-8",
        newline="\n",
    )
    return output


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
    # A new graph every run; the seed is printed so a run can be reproduced.
    seed = random.randrange(2**32)
    graph = _random_dag(n_nodes, edges_per_node=4, seed=seed)
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
        f"\n[query timing] seed={seed} nodes={n_nodes:>4} "
        f"edges={len(graph.edges):>5} "
        f"subgraph_nodes={len(result.subgraph.nodes):>4} "
        f"paths={len(result.paths):>4} "
        f"time={elapsed_ms:.3f} ms"
    )
    output = _write_paths("query_timing", seed, target, result.paths)
    print(f"paths written to {output}")


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
    seed = random.randrange(2**32)
    graph = _random_graph(n_nodes, edges_per_node=4, seed=seed)
    target = str(n_nodes // 2)

    start = time.perf_counter()
    result = query(graph, target)
    elapsed_ms = (time.perf_counter() - start) * 1000

    assert target in result.subgraph.nodes

    print(
        f"\n[cyclic query timing] seed={seed} nodes={n_nodes:>4} "
        f"edges={len(graph.edges):>5} "
        f"subgraph_nodes={len(result.subgraph.nodes):>4} "
        f"paths={len(result.paths):>4} "
        f"time={elapsed_ms:.3f} ms"
    )
    output = _write_paths("query_timing_with_cycles", seed, target, result.paths)
    print(f"paths written to {output}")
