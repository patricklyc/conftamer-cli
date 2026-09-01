import pytest

from conftamer.appgraph import AppNode, stitch_pmgraphs
from conftamer.pmgraph import (
    ReceiveRequestNode,
    ReceiveResponseNode,
    SendRequestNode,
    SendResponseNode,
)

from conftest import (
    pmgraph,
    receive_request,
    receive_response,
    send_request,
    send_response,
)


def message(app_node: AppNode) -> str:
    node = app_node.members[0].node
    assert isinstance(
        node,
        (ReceiveRequestNode, ReceiveResponseNode, SendRequestNode, SendResponseNode),
    )
    return node.message


@pytest.mark.parametrize(
    ("path", "pattern"),
    [
        ("/exact", "/exact"),
        ("/api/v1/items", "/api/v1/"),
        ("/items", "/"),
        ("/users/42", "/users/{id}"),
        ("/users/42", "/users/:id"),
        ("/files/a/b", "/files/*path"),
    ],
)
def test_supported_http_patterns_create_unique_request_matches(modules, path, pattern):
    client, server = modules

    result = stitch_pmgraphs(
        [
            pmgraph(client, (send_request(client, path),)),
            pmgraph(server, (receive_request(server, pattern),)),
        ]
    )

    assert len(result.graph.nodes) == 1
    assert result.graph.nodes[0].match.status == "matched"
    assert result.graph.nodes[0].match.basis == "unique-http-labels"
    assert {member.module_id for member in result.graph.nodes[0].members} == {
        client,
        server,
    }


@pytest.mark.parametrize(
    "pattern",
    [
        "GET /items/{id}",
        "/items/a}b",
        "/items/{id...}",
        "/items/:id:other",
        "/items/:id\tother",
        "/items/{id\nother}",
        "/items/*path*other",
        "/items/{$}",
        "/{id}/:part",
        "/files/*path/more",
    ],
)
def test_unsupported_patterns_are_not_interpreted(pattern, modules):
    client, server = modules

    graph = stitch_pmgraphs(
        [
            pmgraph(client, (send_request(client, "/items/value"),)),
            pmgraph(server, (receive_request(server, pattern),)),
        ]
    ).graph

    states = {
        member.node.type: node.match.status
        for node in graph.nodes
        for member in node.members
    }
    assert states == {"Send": "no_candidate", "Receive": "unsupported_pattern"}


def test_unsupported_syntax_can_still_match_as_an_exact_literal(modules):
    client, server = modules
    literal = "/items/{id...}"

    graph = stitch_pmgraphs(
        [
            pmgraph(client, (send_request(client, literal),)),
            pmgraph(server, (receive_request(server, literal),)),
        ]
    ).graph

    assert [node.match.status for node in graph.nodes] == ["matched"]


@pytest.mark.parametrize(
    ("send_modules", "receive_modules", "candidate_counts"),
    [
        (("a",), ("b", "c"), (1, 1, 2)),
        (("a", "c"), ("b",), (1, 1, 2)),
        (("a", "c"), ("b", "d"), (2, 2, 2, 2)),
    ],
)
def test_non_mutually_unique_request_candidates_remain_ambiguous(
    send_modules, receive_modules, candidate_counts
):
    documents = [
        pmgraph(module, (send_request(module, "/items/1"),)) for module in send_modules
    ] + [
        pmgraph(module, (receive_request(module, "/items/{id}"),))
        for module in receive_modules
    ]

    graph = stitch_pmgraphs(documents).graph

    assert [node.match.status for node in graph.nodes] == ["ambiguous"] * len(
        graph.nodes
    )
    assert sorted(len(node.match.candidates) for node in graph.nodes) == list(
        candidate_counts
    )


def test_same_module_requests_are_never_candidates():
    module = "example.org/combined"

    graph = stitch_pmgraphs(
        [
            pmgraph(
                module,
                (send_request(module), receive_request(module)),
            ),
            pmgraph("example.org/other", ()),
        ]
    ).graph

    assert [node.match.status for node in graph.nodes] == [
        "no_candidate",
        "no_candidate",
    ]


def test_host_and_api_id_do_not_select_or_exclude_a_receiver(modules):
    client, server = modules

    graph = stitch_pmgraphs(
        [
            pmgraph(
                client,
                (
                    send_request(
                        client,
                        host="unrelated.invalid",
                        api_id="client-api",
                    ),
                ),
            ),
            pmgraph(server, (receive_request(server, api_id="different-api"),)),
        ]
    ).graph

    assert [node.match.status for node in graph.nodes] == ["matched"]


def test_responses_match_only_inside_an_accepted_request_pair(modules):
    client, server = modules

    graph = stitch_pmgraphs(
        [
            pmgraph(
                client,
                (
                    send_request(client),
                    receive_response(client, api_id="client-response"),
                ),
            ),
            pmgraph(
                server,
                (
                    receive_request(server),
                    send_response(server, api_id="server-response"),
                ),
            ),
        ]
    ).graph

    assert sorted((message(node), node.match.status) for node in graph.nodes) == [
        ("Request", "matched"),
        ("Response", "matched"),
    ]


def test_responses_without_an_accepted_request_match_are_not_compared(modules):
    client, server = modules

    graph = stitch_pmgraphs(
        [
            pmgraph(client, (receive_response(client),)),
            pmgraph(server, (send_response(server),)),
        ]
    ).graph

    assert [node.match.status for node in graph.nodes] == [
        "missing_request_match",
        "missing_request_match",
    ]


def test_response_status_mismatch_has_no_candidate_within_request_pair(modules):
    client, server = modules

    graph = stitch_pmgraphs(
        [
            pmgraph(
                client, (send_request(client), receive_response(client, status=404))
            ),
            pmgraph(
                server, (receive_request(server), send_response(server, status=200))
            ),
        ]
    ).graph

    response_states = [
        node.match.status for node in graph.nodes if message(node) == "Response"
    ]
    assert response_states == ["no_candidate", "no_candidate"]


def test_response_candidates_also_require_mutual_uniqueness(modules):
    client, server = modules

    graph = stitch_pmgraphs(
        [
            pmgraph(
                client,
                (
                    send_request(client),
                    receive_response(client, api_id="first"),
                    receive_response(client, api_id="second", line=3),
                ),
            ),
            pmgraph(server, (receive_request(server), send_response(server))),
        ]
    ).graph

    response_nodes = [node for node in graph.nodes if message(node) == "Response"]
    assert [node.match.status for node in response_nodes] == ["ambiguous"] * 3
    assert sorted(len(node.match.candidates) for node in response_nodes) == [1, 1, 2]
