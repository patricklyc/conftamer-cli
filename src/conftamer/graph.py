import itertools

import igraph as ig

from conftamer.csv import read_csv
from conftamer.models import BaseNode


def to_graph(edges: list[tuple[BaseNode, BaseNode]]) -> ig.Graph:
    vs = list(set(itertools.chain.from_iterable(edges)))
    ig_edges = [(vs.index(a), vs.index(b)) for a, b in edges]
    vattrs: list[dict[str, str]] = [v.model_dump() for v in vs]
    for v in vattrs:
        v["label"] = (
            f"{v.get('module_id')} {(v.get('param_name') or v.get('request_id') or v.get('request_pattern'))}"
        )

    g = ig.Graph(len(vs), ig_edges, directed=True)
    for i in range(len(vs)):
        g.vs[i].update_attributes(vattrs[i])
    return g


if __name__ == "__main__":
    edges = read_csv("test_gen.csv")

    g = to_graph(edges)
    print(g)
    g.write_graphml("test_gen.graphml")
