from __future__ import annotations

from dataclasses import dataclass
from itertools import product

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
    re-serialized or exported. ``paths`` is the list of every root->leaf path
    that passes through the queried node.

    Each path is a list of steps, and each step is a sorted list of node IDs:
    one strongly connected component (SCC) of the graph. On an acyclic graph
    every step is a single node, so a path is the plain root->leaf path. On a
    cyclic graph every member of a cycle influences every other, so the whole
    cycle is one step instead of one path per route around it, and roots and
    leaves generalize to source and sink SCCs. Every node with ancestors or
    descendants gets at least one path, and the routes inside a cycle remain
    in ``subgraph``.
    """

    subgraph: Graph
    paths: list[list[list[str]]]


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


def _condense(g: ig.Graph) -> tuple[ig.Graph, list[int]]:
    """Collapse each strongly connected component (SCC) of ``g`` into one vertex.

    Returns the condensed graph, which is acyclic, and each original vertex's
    SCC index in it. SCCs are numbered by their smallest member, so on a graph
    sorted by node ID (see ``to_igraph``) the condensed graph is sorted the same
    way, and on an acyclic graph it is ``g`` itself minus any self-loops.
    """
    membership = g.connected_components(mode="strong").membership
    first: dict[int, int] = {}
    for v, scc in enumerate(membership):
        first.setdefault(scc, v)
    rank = {scc: i for i, scc in enumerate(sorted(first, key=first.__getitem__))}
    component = [rank[scc] for scc in membership]
    edges = sorted(
        {(component[s], component[t]) for s, t in g.get_edgelist()}
        - {(c, c) for c in range(len(rank))}
    )
    return ig.Graph(n=len(rank), edges=edges, directed=True), component


def _paths_to_ends(dag: ig.Graph, vertex: int, mode: str) -> list[list[int]]:
    """Every path in the acyclic ``dag`` from ``vertex`` to a root (``mode="in"``)
    or a leaf (``mode="out"``), as vertex indices starting at ``vertex``."""
    if not dag.degree(vertex, mode=mode):
        # igraph never returns the zero-length path from a vertex to itself.
        return [[vertex]]
    ends = [v for v, d in enumerate(dag.degree(mode=mode)) if not d]
    return dag.get_all_simple_paths(vertex, to=ends, mode=mode)


def query(graph: Graph, node_id: str) -> QueryResult:
    """Query ``node_id`` in ``graph`` (a PMGraph or AppGraph).

    Returns the induced subgraph over the node's ancestors and descendants, plus
    every root->leaf path that passes through it, with each cycle collapsed into
    a single step (see ``QueryResult``). Raises ``ValueError`` if
    ``node_id`` is not a node of ``graph``.
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

    # Paths run over the SCCs, so a cycle's members form a single step. Split
    # enumeration: root->node prefixes x node->leaf suffixes.
    dag, component = _condense(g)
    names: list[str] = g.vs["name"]
    steps: list[list[str]] = [[] for _ in range(dag.vcount())]
    for v, c in enumerate(component):
        steps[c].append(names[v])
    ups = _paths_to_ends(dag, component[vertex], "in")  # each is [node, ..., root]
    downs = _paths_to_ends(dag, component[vertex], "out")  # [node, ..., leaf]
    paths = [
        [list(steps[c]) for c in reversed(up)] + [list(steps[c]) for c in down[1:]]
        for up, down in product(ups, downs)
    ]

    return QueryResult(subgraph=subgraph, paths=paths)
