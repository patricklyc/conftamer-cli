"""End-to-end tour of what ConfTamer can do today, using the example PMGraphs.

Run from the repository root:

    uv run python examples/walkthrough.py
"""

from pathlib import Path

from conftamer.appgraph.models import Graph, LinkedMessage
from conftamer.appgraph.stitch import stitch_with_dropped
from conftamer.io import load_pmgraph_json
from conftamer.pmgraph.models import Message, Parameter, PMGraph
from conftamer.query import query_paths, query_subgraph

PMGRAPH_DIR = Path(__file__).parent / "pmgraphs"


def load_pmgraphs() -> list[PMGraph]:
    return [
        load_pmgraph_json(path) for path in sorted(PMGRAPH_DIR.glob("*.pmgraph.json"))
    ]


def describe(node: Parameter | Message | LinkedMessage) -> str:
    if isinstance(node, Parameter):
        return f"parameter {node.key}"
    if isinstance(node, LinkedMessage):
        status = f" -> {node.status_code}" if node.status_code is not None else ""
        return (
            f"{node.method} {node.pattern}{status}  "
            f"[{node.sender_module}::{node.sender_node} => "
            f"{node.receiver_module}::{node.receiver_node}]"
        )
    target = node.path if node.path is not None else node.pattern
    status = f" -> {node.status_code}" if node.status_code is not None else ""
    return f"{node.kind} {node.method} {target}{status}"


def print_graph(graph: Graph) -> None:
    # Nodes in the graph's own order and edges sorted, as graph JSON is written.
    print("  nodes:")
    for node_id, node in graph.nodes.items():
        print(f"    {node_id:<34} {describe(node)}")
    print("  edges:")
    for source, target in sorted(graph.edges):
        print(f"    {source} -> {target}")


def print_query(graph: Graph, node_id: str) -> None:
    # `conftamer query GRAPH --node ID` prints this subgraph as graph JSON.
    print("subgraph:")
    print_graph(query_subgraph(graph, node_id))
    # `--paths` adds every root-to-leaf path through the node. Listing them can
    # be very slow on large or densely connected graphs, so it is opt-in.
    print("paths (--paths):")
    for path in query_paths(graph, node_id):
        # A step with several nodes is a cycle; print it as [a, b].
        steps = (s[0] if len(s) == 1 else "[" + ", ".join(s) + "]" for s in path)
        print("    " + " -> ".join(steps))


def main() -> None:
    pmgraphs = load_pmgraphs()

    print("== 1. Loaded PMGraphs ==")
    for graph in pmgraphs:
        print(f"[{graph.module_id}]")
        print_graph(graph)

    # `conftamer stitch` writes the AppGraph and this dropped-message report.
    print("\n== 2. Stitch all PMGraphs into an AppGraph ==")
    stitched = stitch_with_dropped(pmgraphs)
    appgraph = stitched.appgraph
    print_graph(appgraph)
    print("  dropped:")
    for dropped in stitched.dropped:
        node_id = f"{dropped.module_id}::{dropped.node_id}"
        print(f"    {node_id:<34} {dropped.reason}")

    # Which configuration parameters, in any module, can influence the
    # checkout response the frontend receives?
    checkout_response = next(
        node_id
        for node_id, node in appgraph.nodes.items()
        if isinstance(node, LinkedMessage)
        and node.receiver_module == "frontend"
        and node.receiver_node == "recv-checkout-201"
    )
    print(f"\n== 3. Query the AppGraph: {checkout_response} (checkout response) ==")
    print_query(appgraph, checkout_response)

    # What could orders' inventory.max_retries setting affect, anywhere in
    # the application?
    print("\n== 4. Query the AppGraph: orders::param-max-retries ==")
    print_query(appgraph, "orders::param-max-retries")


if __name__ == "__main__":
    main()
