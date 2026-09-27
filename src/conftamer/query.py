from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterator
from dataclasses import dataclass
from itertools import islice

from conftamer.appgraph.models import AppGraph
from conftamer.pmgraph.models import PMGraph

Graph = PMGraph | AppGraph


@dataclass(frozen=True)
class QueryResult:
    """The result of querying a single node in a graph.

    ``subgraph`` is the induced subgraph over the queried node together with
    every node that can reach it (ancestors) and every node reachable from it
    (descendants); it is the same graph type as the input, so it can be
    re-serialized or exported. ``paths`` is the list of root->leaf paths (each a
    list of node IDs) that pass through the queried node, capped at the requested
    limit. ``truncated`` is True when that cap dropped one or more paths.
    """

    subgraph: Graph
    paths: list[list[str]]
    truncated: bool


def _adjacency(
    edges: set[tuple[str, str]],
) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    """Build forward (successor) and reverse (predecessor) adjacency maps."""
    successors: dict[str, set[str]] = defaultdict(set)
    predecessors: dict[str, set[str]] = defaultdict(set)
    for source, target in edges:
        successors[source].add(target)
        predecessors[target].add(source)
    return successors, predecessors


def _reachable(start: str, adjacency: dict[str, set[str]]) -> set[str]:
    """Every node reachable from ``start`` by following ``adjacency`` (excludes
    ``start`` itself, given the no-cycles assumption)."""
    reached: set[str] = set()
    stack = list(adjacency.get(start, ()))
    while stack:
        node = stack.pop()
        if node in reached:
            continue
        reached.add(node)
        stack.extend(adjacency.get(node, ()))
    return reached


def _paths_to_ends(
    start: str, adjacency: dict[str, set[str]], on_path: set[str]
) -> Iterator[list[str]]:
    """Yield every simple path from ``start`` to a node with no outgoing edge in
    ``adjacency`` (a root when walking predecessors, a leaf when walking
    successors). Each yielded path begins with ``start``. ``on_path`` guards
    against revisiting a node so a stray cycle cannot loop forever."""
    neighbors = adjacency.get(start)
    if not neighbors:
        yield [start]
        return
    for neighbor in sorted(neighbors):
        if neighbor in on_path:
            continue
        on_path.add(neighbor)
        for tail in _paths_to_ends(neighbor, adjacency, on_path):
            yield [start, *tail]
        on_path.discard(neighbor)


def _through_paths(
    node_id: str,
    successors: dict[str, set[str]],
    predecessors: dict[str, set[str]],
) -> Iterator[list[str]]:
    """Yield every root->leaf path passing through ``node_id``.

    Splits the work: walk predecessors to enumerate root->node prefixes and
    successors to enumerate node->leaf suffixes, then cross-product them. Suffixes
    are cached as they are pulled so each is computed once, while prefixes stay
    lazy -- so with a downstream cap only as many suffixes as needed are built.
    """
    up_paths = (
        list(reversed(path))  # yielded as [node, ..., root]; want [root, ..., node]
        for path in _paths_to_ends(node_id, predecessors, {node_id})
    )
    down_gen = _paths_to_ends(node_id, successors, {node_id})

    down_cache: list[list[str]] = []
    down_exhausted = False
    for up in up_paths:
        index = 0
        while True:
            if index < len(down_cache):
                down = down_cache[index]
            elif down_exhausted:
                break
            else:
                nxt = next(down_gen, None)
                if nxt is None:
                    down_exhausted = True
                    break
                down_cache.append(nxt)
                down = nxt
            # up ends with node_id and down starts with it; drop the duplicate.
            yield [*up[:-1], *down]
            index += 1


def query(graph: Graph, node_id: str, path_limit: int = -1) -> QueryResult:
    """Query ``node_id`` in ``graph`` (a PMGraph or AppGraph).

    Returns the induced subgraph over the node's ancestors and descendants, plus
    the root->leaf paths that pass through it. ``path_limit`` caps the number of
    paths returned; ``-1`` means no limit. Raises ``ValueError`` if ``node_id``
    is not a node of ``graph``.
    """
    if node_id not in graph.nodes:
        raise ValueError(f"node ID {node_id!r} not in graph")

    successors, predecessors = _adjacency(graph.edges)

    keep = (
        {node_id} | _reachable(node_id, predecessors) | _reachable(node_id, successors)
    )
    sub_nodes = {nid: node for nid, node in graph.nodes.items() if nid in keep}
    sub_edges = {
        (source, target)
        for source, target in graph.edges
        if source in keep and target in keep
    }
    subgraph = graph.model_copy(update={"nodes": sub_nodes, "edges": sub_edges})

    paths_iter = _through_paths(node_id, successors, predecessors)
    if path_limit < 0:
        paths = list(paths_iter)
        truncated = False
    else:
        # Pull one extra to tell a full result from a truncated one.
        paths = list(islice(paths_iter, path_limit + 1))
        truncated = len(paths) > path_limit
        paths = paths[:path_limit]

    return QueryResult(subgraph=subgraph, paths=paths, truncated=truncated)
