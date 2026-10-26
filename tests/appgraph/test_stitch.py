import pytest

from conftamer.appgraph.models import DroppedMessage, LinkedMessage
from conftamer.appgraph.stitch import path_matches_pattern, stitch, stitch_with_dropped
from conftamer.pmgraph.models import Message, Parameter, PMGraph


def _pmgraph(module_id: str, nodes: dict, edges: set[tuple[str, str]]) -> PMGraph:
    return PMGraph(module_id=module_id, nodes=nodes, edges=edges)


def _send_request(**overrides: object) -> Message:
    fields = {
        "kind": "send_request",
        "api_id": "orgB",
        "method": "GET",
        "host": "backend:8080",
        "path": "/items/42",
    }
    fields.update(overrides)
    return Message.model_validate(fields)


def _receive_request(**overrides: object) -> Message:
    fields = {
        "kind": "receive_request",
        "api_id": "orgB",
        "method": "GET",
        "pattern": "/items/{id}",
    }
    fields.update(overrides)
    return Message.model_validate(fields)


def _send_response(**overrides: object) -> Message:
    fields = {
        "kind": "send_response",
        "api_id": "orgB",
        "method": "GET",
        "pattern": "/items/{id}",
        "status_code": 200,
    }
    fields.update(overrides)
    return Message.model_validate(fields)


def _receive_response(**overrides: object) -> Message:
    fields = {
        "kind": "receive_response",
        "api_id": "orgB",
        "method": "GET",
        "host": "backend:8080",
        "path": "/items/42",
        "status_code": 200,
    }
    fields.update(overrides)
    return Message.model_validate(fields)


class TestPathMatchesPattern:
    @pytest.mark.parametrize(
        ("path", "pattern"),
        [
            ("/items", "/items"),
            ("/items/42", "/items/{id}"),
            ("/items/42", "/items/:id"),
            ("/items/42/reviews/7", "/items/{id}/reviews/{review_id}"),
            ("/static/css/site.css", "/static/{rest...}"),
            ("/static/css/site.css", "/static/*rest"),
            ("/static/x", "/static/*rest"),
            ("/api/v1/items", "/api/v1/"),
            ("/api/v1/items/7", "/api/v1/"),
            ("/api/v1/", "/api/v1/"),
            ("/items", "/"),
            ("/users/42/posts", "/users/{id}/"),
            ("/items/", "/items/{$}"),
            ("/", "/{$}"),
            ("/items/42/", "/items/:id/"),
        ],
    )
    def test_matches(self, path: str, pattern: str) -> None:
        assert path_matches_pattern(path, pattern)

    @pytest.mark.parametrize(
        ("path", "pattern"),
        [
            ("/items/42", "/items/42/reviews"),
            ("/items", "/items/{id}"),
            ("/items/42/reviews", "/items/{id}"),
            ("/other/42", "/items/{id}"),
            ("/static/", "/static/{rest...}"),  # wildcard segment must be nonempty
            ("/static", "/static/*rest"),
            ("/api/v1", "/api/v1/"),
            ("/api/v2/items", "/api/v1/"),
            ("/items/wrong", "/items/{$}"),
            ("/items", "/items/{$}"),
            ("/items", "/{$}"),
            ("/items/42/x", "/items/:id/"),  # httprouter: trailing slash is literal
        ],
    )
    def test_does_not_match(self, path: str, pattern: str) -> None:
        assert not path_matches_pattern(path, pattern)

    @pytest.mark.parametrize(
        "pattern",
        [
            "GET /items",
            "example.com/items",
            "/items/{id...}/more",
            "/items/*rest/more",
            "/items/{$}/more",
            "/items/{}",
            "/items/{...}",
            "/items/:",
            "/items/x{id}",
            "/items/{id}/:sub",
        ],
    )
    def test_unsupported_pattern_raises(self, pattern: str) -> None:
        with pytest.raises(ValueError, match="unsupported route pattern"):
            path_matches_pattern("/items/42", pattern)


class TestStitch:
    def test_links_a_request_and_its_response_across_two_modules(self) -> None:
        client = _pmgraph(
            "frontend",
            {
                "param": Parameter(key="timeout"),
                "send": _send_request(),
                "recv-resp": _receive_response(),
            },
            {("param", "send")},
        )
        server = _pmgraph(
            "backend",
            {
                "recv": _receive_request(),
                "send-resp": _send_response(),
            },
            {("recv", "send-resp")},
        )

        app = stitch([client, server])

        # param -> request link -> response link
        assert len(app.nodes) == 3
        param_id = next(pid for pid, n in app.nodes.items() if isinstance(n, Parameter))
        links = {pid: n for pid, n in app.nodes.items() if isinstance(n, LinkedMessage)}
        assert len(links) == 2

        request_link_id = next(
            pid for pid, link in links.items() if link.status_code is None
        )
        response_link_id = next(
            pid for pid, link in links.items() if link.status_code is not None
        )

        request_link = links[request_link_id]
        assert request_link.sender_module == "frontend"
        assert request_link.sender_node == "send"
        assert request_link.receiver_module == "backend"
        assert request_link.receiver_node == "recv"
        assert request_link.pattern == "/items/{id}"

        response_link = links[response_link_id]
        assert response_link.sender_module == "backend"
        assert response_link.sender_node == "send-resp"
        assert response_link.receiver_module == "frontend"
        assert response_link.receiver_node == "recv-resp"
        assert response_link.status_code == 200

        assert app.edges == {
            (param_id, request_link_id),
            (request_link_id, response_link_id),
        }

    def test_prunes_unmatched_message_and_edges_to_it(self) -> None:
        client = _pmgraph(
            "frontend",
            {
                "param": Parameter(key="timeout"),
                "send": _send_request(api_id="no-such-api"),
            },
            {("param", "send")},
        )

        app = stitch([client])

        assert list(app.nodes) == ["frontend::param"]
        assert app.edges == set()

    def test_no_api_id_never_matches(self) -> None:
        client = _pmgraph("frontend", {"send": _send_request(api_id=None)}, set())
        server = _pmgraph("backend", {"recv": _receive_request(api_id=None)}, set())

        app = stitch([client, server])

        assert app.nodes == {}

    @pytest.mark.parametrize(
        "server_path", ["/items/:id", "/items/{id}", "/items/*rest", "/items/{id...}"]
    )
    def test_fallback_path_is_literal_not_a_pattern(self, server_path: str) -> None:
        client = _pmgraph(
            "frontend",
            {"param": Parameter(key="timeout"), "send": _send_request()},
            {("param", "send")},
        )
        server = _pmgraph(
            "backend",
            {"recv": _receive_request(pattern=None, path=server_path)},
            set(),
        )

        app = stitch([client, server])

        assert list(app.nodes) == ["frontend::param"]

    def test_fallback_path_matches_identical_path(self) -> None:
        client = _pmgraph(
            "frontend",
            {"param": Parameter(key="timeout"), "send": _send_request()},
            {("param", "send")},
        )
        server = _pmgraph(
            "backend",
            {"recv": _receive_request(pattern=None, path="/items/42")},
            set(),
        )

        app = stitch([client, server])

        link = app.nodes["link0"]
        assert isinstance(link, LinkedMessage)
        assert link.pattern == "/items/42"

    def test_status_code_mismatch_blocks_response_link_but_not_request_link(
        self,
    ) -> None:
        client = _pmgraph(
            "frontend",
            {
                "param": Parameter(key="timeout"),
                "send": _send_request(),
                "recv-resp": _receive_response(status_code=200),
            },
            {("param", "send")},
        )
        server = _pmgraph(
            "backend",
            {
                "recv": _receive_request(),
                "send-resp": _send_response(status_code=500),
            },
            {("recv", "send-resp")},
        )

        app = stitch([client, server])

        links = [n for n in app.nodes.values() if isinstance(n, LinkedMessage)]
        assert len(links) == 1
        assert links[0].status_code is None  # the request link, not a response link

    def test_same_module_is_never_stitched(self) -> None:
        graph = _pmgraph(
            "solo",
            {"send": _send_request(), "recv": _receive_request()},
            set(),
        )

        app = stitch([graph])

        assert app.nodes == {}

    def test_unsupported_pattern_raises_even_without_a_candidate(self) -> None:
        server = _pmgraph(
            "backend", {"recv": _receive_request(pattern="GET /items/{id}")}, set()
        )

        with pytest.raises(ValueError, match="unsupported route pattern"):
            stitch([server])

    def test_one_pattern_matches_many_senders(self) -> None:
        client_a = _pmgraph(
            "client-a",
            {
                "param": Parameter(key="target"),
                "send": _send_request(path="/items/1"),
            },
            {("param", "send")},
        )
        client_b = _pmgraph(
            "client-b",
            {
                "param": Parameter(key="target"),
                "send": _send_request(path="/items/2"),
            },
            {("param", "send")},
        )
        server = _pmgraph("backend", {"recv": _receive_request()}, set())

        app = stitch([client_a, client_b, server])

        links = [n for n in app.nodes.values() if isinstance(n, LinkedMessage)]
        assert len(links) == 2
        assert {link.sender_module for link in links} == {"client-a", "client-b"}
        assert all(link.receiver_module == "backend" for link in links)

    def test_duplicate_module_id_rejected(self) -> None:
        a = _pmgraph("shared", {}, set())
        b = _pmgraph("shared", {}, set())

        with pytest.raises(ValueError, match="duplicate module_id"):
            stitch([a, b])

    def test_module_id_with_separator_rejected(self) -> None:
        graph = _pmgraph("front::end", {}, set())

        with pytest.raises(ValueError, match="::"):
            stitch([graph])

    def test_node_id_with_separator_rejected(self) -> None:
        graph = _pmgraph("frontend", {"bad::id": Parameter(key="timeout")}, set())

        with pytest.raises(ValueError, match="::"):
            stitch([graph])

    def test_module_id_with_trailing_colon_rejected(self) -> None:
        # "a:" + "::" + "cfg" would collide with "a" + "::" + ":cfg".
        a = _pmgraph("a", {":cfg": Parameter(key="one")}, set())
        b = _pmgraph("a:", {"cfg": Parameter(key="two")}, set())

        with pytest.raises(ValueError, match="must not end with ':'"):
            stitch([a, b])

    def test_node_id_with_leading_colon_keeps_its_provenance(self) -> None:
        client = _pmgraph(
            "client",
            {"cfg": Parameter(key="k"), ":send": _send_request()},
            {("cfg", ":send")},
        )
        backend = _pmgraph("backend", {"recv": _receive_request()}, set())

        app = stitch([client, backend])

        link = app.nodes["link0"]
        assert isinstance(link, LinkedMessage)
        assert (link.sender_module, link.sender_node) == ("client", ":send")
        assert set(app.nodes) == {"client::cfg", "link0"}

    def test_parameter_with_no_influence_is_still_kept(self) -> None:
        graph = _pmgraph("frontend", {"param": Parameter(key="unused")}, set())

        app = stitch([graph])

        assert list(app.nodes) == ["frontend::param"]

    def test_influence_chains_through_an_intermediate_module(self) -> None:
        # web --> orders --> payments, over two distinct APIs. A config param
        # in web must reach payments two hops away, even though web never
        # references payments: the link is forged only because `orders` records
        # (Propagator (4)) that handling its inbound call triggered its
        # outbound call, and stitching rewrites that internal edge across the
        # two merged boundary nodes.
        web = _pmgraph(
            "web",
            {
                "cfg": Parameter(key="orders.currency"),
                "call_orders": Message(
                    kind="send_request",
                    api_id="orders-api",
                    method="POST",
                    host="orders:80",
                    path="/checkout/abc",
                ),
            },
            {("cfg", "call_orders")},
        )
        orders = _pmgraph(
            "orders",
            {
                "got_called": Message(
                    kind="receive_request",
                    api_id="orders-api",
                    method="POST",
                    pattern="/checkout/{cart}",
                ),
                "call_payments": Message(
                    kind="send_request",
                    api_id="pay-api",
                    method="POST",
                    host="payments:80",
                    path="/charge/abc",
                ),
            },
            {("got_called", "call_payments")},
        )
        payments = _pmgraph(
            "payments",
            {
                "got_called": Message(
                    kind="receive_request",
                    api_id="pay-api",
                    method="POST",
                    pattern="/charge/{cart}",
                ),
            },
            set(),
        )

        app = stitch([web, orders, payments])

        param_id = next(pid for pid, n in app.nodes.items() if isinstance(n, Parameter))
        links = {pid: n for pid, n in app.nodes.items() if isinstance(n, LinkedMessage)}
        assert len(links) == 2

        web_orders_id = next(
            pid
            for pid, link in links.items()
            if link.sender_module == "web" and link.receiver_module == "orders"
        )
        orders_pay_id = next(
            pid
            for pid, link in links.items()
            if link.sender_module == "orders" and link.receiver_module == "payments"
        )

        # The two hops chain together: cfg -> (web->orders) -> (orders->payments).
        assert app.edges == {
            (param_id, web_orders_id),
            (web_orders_id, orders_pay_id),
        }
        assert links[web_orders_id].pattern == "/checkout/{cart}"
        assert links[orders_pay_id].pattern == "/charge/{cart}"
        assert links[orders_pay_id].receiver_node == "got_called"


class TestDropped:
    def test_reports_nothing_when_every_message_survives(self) -> None:
        client = _pmgraph(
            "frontend",
            {"param": Parameter(key="timeout"), "send": _send_request()},
            {("param", "send")},
        )
        server = _pmgraph("backend", {"recv": _receive_request()}, set())

        result = stitch_with_dropped([client, server])

        assert result.dropped == []
        assert result.appgraph == stitch([client, server])

    def test_unmatched_message(self) -> None:
        send = _send_request(api_id="no-such-api")
        client = _pmgraph(
            "frontend",
            {"param": Parameter(key="timeout"), "send": send},
            {("param", "send")},
        )

        assert stitch_with_dropped([client]).dropped == [
            DroppedMessage(
                module_id="frontend", node_id="send", reason="unmatched", message=send
            )
        ]

    def test_matched_but_unreachable_from_a_parameter(self) -> None:
        # The two sides match, but no Parameter influences the link, so it is
        # pruned and both of its messages are reported.
        send, recv = _send_request(), _receive_request()
        client = _pmgraph("frontend", {"send": send}, set())
        server = _pmgraph("backend", {"recv": recv}, set())

        result = stitch_with_dropped([client, server])

        assert result.appgraph.nodes == {}
        assert result.dropped == [
            DroppedMessage(
                module_id="backend", node_id="recv", reason="unreachable", message=recv
            ),
            DroppedMessage(
                module_id="frontend",
                node_id="send",
                reason="unreachable",
                message=send,
            ),
        ]

    def test_message_kept_if_any_of_its_links_survives(self) -> None:
        # One receiver matches two senders; only a's link is reachable from a
        # Parameter. The receiver survives through it, b's sender does not.
        a = _pmgraph(
            "a",
            {"param": Parameter(key="k"), "send": _send_request()},
            {("param", "send")},
        )
        b = _pmgraph("b", {"send": _send_request(path="/items/7")}, set())
        server = _pmgraph("server", {"recv": _receive_request()}, set())

        dropped = stitch_with_dropped([a, b, server]).dropped

        assert [(d.module_id, d.node_id, d.reason) for d in dropped] == [
            ("b", "send", "unreachable")
        ]

    def test_parameters_are_never_reported(self) -> None:
        graph = _pmgraph("m", {"param": Parameter(key="k")}, set())

        assert stitch_with_dropped([graph]).dropped == []

    def test_sorted_by_module_then_node(self) -> None:
        # "a" sorts before "a-b" as a module ID even though "a::" > "a-b::".
        graphs = [
            _pmgraph("a-b", {"x": _send_request(api_id=None)}, set()),
            _pmgraph(
                "a",
                {
                    "y": _send_request(api_id=None),
                    "x": _send_request(api_id=None),
                },
                set(),
            ),
        ]

        dropped = stitch_with_dropped(graphs).dropped

        assert [(d.module_id, d.node_id) for d in dropped] == [
            ("a", "x"),
            ("a", "y"),
            ("a-b", "x"),
        ]
