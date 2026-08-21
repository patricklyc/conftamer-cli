import itertools

import igraph as ig

from conftamer.models import BaseNode


def to_graph(edges: list[tuple[BaseNode, BaseNode]]) -> ig.Graph:
    nodes = itertools.chain.from_iterable(edges)
    vs = list(dict.fromkeys(nodes))

    vertex_ids = {vertex: index for index, vertex in enumerate(vs)}
    ig_edges = [
        (vertex_ids[source], vertex_ids[target]) for source, target in edges
    ]
    vattrs: list[dict[str, str]] = [v.model_dump() for v in vs]
    for v in vattrs:
        v["label"] = (
            f"{v.get('module_id')} {(v.get('param_name') or v.get('request_id') or v.get('request_pattern'))}"
        )

    g = ig.Graph(len(vs), ig_edges, directed=True)
    for i in range(len(vs)):
        g.vs[i].update_attributes(vattrs[i])
    return g


def to_subgraph(graph: ig.Graph, node_id: int) -> ig.Graph:
    v = []
    v.extend(graph.subcomponent(node_id, mode="in"))
    v.extend(graph.subcomponent(node_id, mode="out"))
    print(v)
    sg: ig.Graph = graph.subgraph(v)
    print(sg)
    return sg
