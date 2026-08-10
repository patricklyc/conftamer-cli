import itertools

import igraph as ig

from conftamer.csv import read_csv


def to_vertices(edges: list[tuple]):
    vs = set(itertools.chain.from_iterable(edges))
    return vs


def to_ig_edges(edges: list[tuple]):
    ig_edges = []
    for a, b in edges:
        # ig_edges.append((a.model_dump()["name"], b.model_dump()["name"]))
        ig_edges.append((str(a), str(b)))
    return ig_edges


if __name__ == "__main__":
    nodes = read_csv("test_log.csv")
    edges = to_ig_edges(nodes)

    g = ig.Graph.TupleList(edges, directed=True)
    print(g)
    g.write_gml("test_log.gml")
