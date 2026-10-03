from __future__ import annotations

from dataclasses import dataclass
from itertools import islice, product

import igraph as ig

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


def to_igraph(graph: Graph) -> ig.Graph:
    """Convert a PMGraph or AppGraph into a directed ``igraph.Graph``.

    Each vertex's ``name`` attribute is its node ID. Vertices are added in sorted
    node-ID order, so igraph's index-ordered traversals visit neighbors in sorted
    ID order and results are deterministic. Raises ``ValueError`` if an edge
    references a node ID that is not in ``graph.nodes``.
    """
    names = sorted(graph.nodes)
    index = {name: i for i, name in enumerate(names)}
    edges: list[tuple[int, int]] = []
    for source, target in sorted(graph.edges):
        if source not in index or target not in index:
            raise ValueError(f"edge {(source, target)!r} has a missing endpoint")
        edges.append((index[source], index[target]))
    return ig.Graph(
        n=len(names), edges=edges, directed=True, vertex_attrs={"name": names}
    )


def _paths_to_ends(
    g: ig.Graph, vertex: int, mode: str, limit: int | None
) -> list[list[int]]:
    """Every simple path from ``vertex`` to a structural end, as vertex indices
    starting at ``vertex``: roots (in-degree 0) when ``mode="in"``, leaves
    (out-degree 0) when ``mode="out"``. At most ``limit`` paths (None = all)."""
    degree = g.indegree if mode == "in" else g.outdegree
    if degree(vertex) == 0:
        # igraph never returns the zero-length path from a vertex to itself.
        return [[vertex]] if limit != 0 else []
    ends = [v for v, d in enumerate(degree()) if d == 0]
    return g.get_all_simple_paths(vertex, to=ends, mode=mode, max_results=limit)


def query(graph: Graph, node_id: str, path_limit: int = -1) -> QueryResult:
    """Query ``node_id`` in ``graph`` (a PMGraph or AppGraph).

    Returns the induced subgraph over the node's ancestors and descendants, plus
    the root->leaf paths that pass through it. ``path_limit`` caps the number of
    paths returned; ``-1`` means no limit. Raises ``ValueError`` if ``node_id``
    is not a node of ``graph``.
    """
    if node_id not in graph.nodes:
        raise ValueError(f"node ID {node_id!r} not in graph")

    g = to_igraph(graph)
    vertex = g.vs.find(name=node_id).index

    keep = set(g.subcomponent(vertex, mode="in")) | set(
        g.subcomponent(vertex, mode="out")
    )
    sub = g.induced_subgraph(sorted(keep))
    sub_names: list[str] = sub.vs["name"]
    sub_nodes = {name: graph.nodes[name] for name in sub_names}
    sub_edges = {(sub_names[s], sub_names[t]) for s, t in sub.get_edgelist()}
    subgraph = graph.model_copy(update={"nodes": sub_nodes, "edges": sub_edges})

    # Split enumeration: root->node prefixes x node->leaf suffixes. Pulling one
    # extra past the cap tells a full result from a truncated one; the first
    # path_limit + 1 cross-product items never need more than that many of either.
    cap = None if path_limit < 0 else path_limit + 1
    ups = _paths_to_ends(g, vertex, "in", cap)  # each is [node, ..., root]
    downs = _paths_to_ends(g, vertex, "out", cap)  # each is [node, ..., leaf]
    names: list[str] = g.vs["name"]
    paths_iter = (
        [names[v] for v in reversed(up)] + [names[v] for v in down[1:]]
        for up, down in product(ups, downs)
    )
    if cap is None:
        paths = list(paths_iter)
        truncated = False
    else:
        paths = list(islice(paths_iter, cap))
        truncated = len(paths) > path_limit
        paths = paths[:path_limit]

    return QueryResult(subgraph=subgraph, paths=paths, truncated=truncated)
