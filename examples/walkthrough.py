"""End-to-end tour of what ConfTamer can do today, using the example PMGraphs.

Run from the repository root:

    uv run python examples/walkthrough.py
"""

from pathlib import Path

from conftamer.appgraph.models import AppGraph, LinkedMessage
from conftamer.appgraph.stitch import stitch
from conftamer.pmgraph.models import Message, Parameter, PMGraph
from conftamer.query import QueryResult, query

PMGRAPH_DIR = Path(__file__).parent / "pmgraphs"


def load_pmgraphs() -> list[PMGraph]:
    return [
        PMGraph.model_validate_json(path.read_text())
        for path in sorted(PMGRAPH_DIR.glob("*.pmgraph.json"))
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


def print_graph(graph: PMGraph | AppGraph) -> None:
    print("  nodes:")
    for node_id in sorted(graph.nodes):
        print(f"    {node_id:<34} {describe(graph.nodes[node_id])}")
    print("  edges:")
    for source, target in sorted(graph.edges):
        print(f"    {source} -> {target}")


def print_result(result: QueryResult, show_subgraph: bool = True) -> None:
    if show_subgraph:
        print("subgraph:")
        print_graph(result.subgraph)
    print(f"paths (truncated={result.truncated}):")
    for path in result.paths:
        print("    " + " -> ".join(path))


def main() -> None:
    pmgraphs = load_pmgraphs()

    print("== 1. Loaded PMGraphs ==")
    for graph in pmgraphs:
        print(f"[{graph.module_id}]")
        print_graph(graph)

    print("\n== 2. Stitch all PMGraphs into an AppGraph ==")
    appgraph = stitch(pmgraphs)
    print_graph(appgraph)

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
    print_result(query(appgraph, checkout_response))

    # What could orders' inventory.max_retries setting affect, anywhere in
    # the application?
    print("\n== 4. Query the AppGraph: orders::param-max-retries ==")
    print_result(query(appgraph, "orders::param-max-retries"))

    print(f"\n== 5. Query {checkout_response} again with path_limit=2 ==")
    print_result(query(appgraph, checkout_response, path_limit=2), show_subgraph=False)


if __name__ == "__main__":
    main()
