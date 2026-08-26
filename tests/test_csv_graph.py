import pytest

from conftamer import csv_graph
from conftamer.csv_graph import ParameterNode, ReceiveNode, SendNode, to_graph


def example_graph():
    return to_graph(
        [
            (
                ParameterNode(module_id="service", param_name="timeout"),
                SendNode(
                    module_id="service",
                    api_id="inventory",
                    request_id="GET /items",
                    response_code=201,
                ),
            ),
            (
                ReceiveNode(
                    module_id="gateway",
                    api_id="public",
                    request_pattern="/Orders/{id}",
                    response_code=202,
                ),
                SendNode(
                    module_id="gateway",
                    api_id="billing",
                    request_id="POST /charge",
                    response_code=503,
                ),
            ),
        ]
    )


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("parameter", [0]),
        ("SERVICE", [0, 1]),
        ("inventory", [1]),
        ("get /ITEMS", [1]),
        ("receive", [2]),
        ("PUBLIC", [2]),
        ("/orders/{ID}", [2]),
        ("202", [2]),
        ("billing", [3]),
        ("503", [3]),
    ],
)
def test_find_nodes_matches_case_insensitive_attribute_substrings(query, expected):
    assert csv_graph.find_nodes(example_graph(), query) == expected


def test_find_nodes_strips_query_and_returns_each_vertex_once():
    assert csv_graph.find_nodes(example_graph(), "  SERVICE  ") == [0, 1]


def test_find_nodes_returns_no_match():
    assert csv_graph.find_nodes(example_graph(), "missing") == []


def test_find_nodes_rejects_blank_query():
    with pytest.raises(ValueError, match="search query must not be empty"):
        csv_graph.find_nodes(example_graph(), "   ")
