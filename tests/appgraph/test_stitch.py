import pytest

from conftamer.appgraph.models import LinkedMessage
from conftamer.appgraph.stitch import path_matches_pattern, stitch
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
        ],
    )
    def test_does_not_match(self, path: str, pattern: str) -> None:
        assert not path_matches_pattern(path, pattern)


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
