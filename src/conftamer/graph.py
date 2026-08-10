import itertools

import igraph as ig

from conftamer.csv import read_csv
from conftamer.models import BaseNode


def to_vertices(edges: list[tuple]) -> set[BaseNode]:
    vs = set(itertools.chain.from_iterable(edges))
    return vs


def to_ig_edges(edges: list[tuple]):
    ig_edges = [(str(a), str(b)) for a, b in edges]
    return ig_edges


def to_graph(edges: list[tuple[BaseNode, BaseNode]]) -> ig.Graph:
    vs = list(set(itertools.chain.from_iterable(edges)))
    ig_edges = [(vs.index(a), vs.index(b)) for a, b in edges]
    vattrs = [v.model_dump() for v in vs]
    g = ig.Graph(len(vs), ig_edges, directed=True)
    for i in range(len(vs)):
        g.vs[i].update_attributes(vattrs[i])
    return g


if __name__ == "__main__":
    edges = read_csv("test_log.csv")

    g = to_graph(edges)
    print(g)
    g.write_graphml("test_log.graphml")
