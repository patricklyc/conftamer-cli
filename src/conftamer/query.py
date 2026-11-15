from __future__ import annotations

from dataclasses import dataclass
from itertools import product

import igraph as ig

from conftamer.appgraph.models import Graph
from conftamer.igraph_ops import to_igraph
from conftamer.pmgraph.models import Parameter, PMGraph


@dataclass(frozen=True)
class QueryResult:
    """The result of querying a single node in a graph.

    ``subgraph`` is the induced subgraph over the queried node together with
    every node that can reach it (ancestors) and every node reachable from it
    (descendants); it is the same graph type as the input, with its nodes in
    the input's order, so it can be re-serialized or exported. ``paths`` is the
    list of every root->leaf path that passes through the queried node.

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


def _parameter_module(graph: Graph, node_id: str) -> str | None:
    if isinstance(graph, PMGraph):
        return graph.module_id
    # stitch() namespaces every AppGraph parameter as "module_id::node_id".
    module_id, separator, _ = node_id.partition("::")
    return module_id if separator else None


def find_parameters(graph: Graph, key: str, module: str | None = None) -> list[str]:
    """The sorted IDs of the Parameter nodes in ``graph`` whose ``key`` is ``key``.

    ``module`` narrows the search to one module: a PMGraph's ``module_id``, or in
    an AppGraph the ``module_id::`` prefix that ``stitch`` gives each parameter.
    Keys are only unique within a module, so without ``module`` an AppGraph can
    return several IDs.
    """
    return sorted(
        node_id
        for node_id, node in graph.nodes.items()
        if isinstance(node, Parameter)
        and node.key == key
        and (module is None or _parameter_module(graph, node_id) == module)
    )


def _condense(g: ig.Graph) -> tuple[ig.Graph, list[int]]:
    """Collapse each strongly connected component (SCC) of ``g`` into one vertex.

    Returns the condensed graph, which is acyclic, and each original vertex's
    SCC index in it. SCCs are numbered by their smallest member, so on a graph
    sorted by node ID (as ``query_paths`` builds it) the condensed graph is
    sorted the same way, and on an acyclic graph it is ``g`` itself minus any
    self-loops.
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


def _check_node(graph: Graph, node_id: str) -> None:
    if node_id not in graph.nodes:
        raise ValueError(f"node ID {node_id!r} not in graph")


def query_subgraph(graph: Graph, node_id: str) -> Graph:
    """The part of ``graph`` that can influence ``node_id`` or be influenced by it.

    Returns the node, its ancestors, its descendants, and every edge among them,
    as the same graph type as ``graph`` with nodes in the input's order. This
    only walks reachability and never enumerates paths, so it stays fast on
    graphs with very many paths. Raises ``ValueError`` if ``node_id`` is not a
    node of ``graph``.
    """
    _check_node(graph, node_id)
    g = to_igraph(graph)
    vertex = g.vs.find(name=node_id).index
    reached = set(g.subcomponent(vertex, mode="in")) | set(
        g.subcomponent(vertex, mode="out")
    )
    names: list[str] = g.vs["name"]
    keep = {names[v] for v in reached}
    nodes = {name: node for name, node in graph.nodes.items() if name in keep}
    edges = {
        (source, target)
        for source, target in graph.edges
        if source in keep and target in keep
    }
    return graph.model_copy(update={"nodes": nodes, "edges": edges})


def query_paths(graph: Graph, node_id: str) -> list[list[list[str]]]:
    """Every root->leaf path of ``graph`` that passes through ``node_id``.

    Each cycle is collapsed into a single step (see ``QueryResult``). The number
    of paths can grow exponentially with the size of a branching graph. Raises
    ``ValueError`` if ``node_id`` is not a node of ``graph``.
    """
    _check_node(graph, node_id)
    # The steps below number SCCs and order paths by vertex index, and their
    # results are defined for vertices in sorted node-ID order. ``to_igraph``
    # keeps the graph's own node order, so convert a copy with sorted nodes.
    ordered = graph.model_copy(update={"nodes": dict(sorted(graph.nodes.items()))})
    g = to_igraph(ordered)
    vertex = g.vs.find(name=node_id).index

    # Paths run over the SCCs, so a cycle's members form a single step. Split
    # enumeration: root->node prefixes x node->leaf suffixes.
    dag, component = _condense(g)
    names: list[str] = g.vs["name"]
    steps: list[list[str]] = [[] for _ in range(dag.vcount())]
    for v, c in enumerate(component):
        steps[c].append(names[v])
    ups = _paths_to_ends(dag, component[vertex], "in")  # each is [node, ..., root]
    downs = _paths_to_ends(dag, component[vertex], "out")  # [node, ..., leaf]
    return [
        [list(steps[c]) for c in reversed(up)] + [list(steps[c]) for c in down[1:]]
        for up, down in product(ups, downs)
    ]


def query(graph: Graph, node_id: str) -> QueryResult:
    """Query ``node_id`` in ``graph`` (a PMGraph or AppGraph).

    Returns ``query_subgraph`` and ``query_paths`` together (see
    ``QueryResult``). Raises ``ValueError`` if ``node_id`` is not a node of
    ``graph``.
    """
    return QueryResult(
        subgraph=query_subgraph(graph, node_id), paths=query_paths(graph, node_id)
    )
