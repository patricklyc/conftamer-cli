import json
import warnings
from pathlib import Path

import pytest

from conftamer.contexttrack import load_contexttrack
from conftamer.pmgraph.models import Message


def event(kind="Request received", *, path="", pattern="/route", **fields):
    message = {"req.Method": "gEt", "req.URL.Path": path}

    if kind == "Request routed":
        message["pattern"] = pattern

    if kind in ("Response sent", "Response received"):
        message["code" if kind == "Response sent" else "resp.StatusCode"] = "0200"

    record = {
        "kind": kind,
        "pid": 1,
        "context": {"context_id": "c"},
        "message": message,
        "api_id": " API\n",
    }

    if kind == "Request sent":
        record["request_id"] = {"method": "gEt", "host": "H\u00f6st:80", "path": path}

    return record | fields


def load(tmp_path, *records, warn=False):
    path = tmp_path / "events.jsonl"
    path.write_text(
        "\n".join(json.dumps(record, ensure_ascii=False) for record in records),
        encoding="utf-8",
    )

    with warnings.catch_warnings(record=True) as notices:
        warnings.simplefilter("always")
        graph = load_contexttrack(path, module_id="module")

    assert bool(notices) == warn
    return graph


@pytest.mark.parametrize("text", ["", "\n \t\n"])
def test_blank_capture(tmp_path, text):
    path = tmp_path / "empty.jsonl"
    path.write_text(text, encoding="utf-8")

    graph = load_contexttrack(str(path), module_id="module")

    assert (graph.module_id, graph.nodes, graph.edges) == ("module", {}, set())


def test_literal_utf8_input_is_preserved(tmp_path):
    graph = load(tmp_path, event("Request sent"))

    [message] = graph.nodes.values()
    assert message.host == "Höst:80"


@pytest.mark.parametrize(
    "record, expected_error",
    [
        ("{", ValueError),
        (None, TypeError),
        (event(kind=3), TypeError),
        (event(pid=True), TypeError),
        (event(message=None), TypeError),
        (event(context=[]), TypeError),
        (event(request_id=3), TypeError),
        (event(context={"context_id": 3}), TypeError),
        (event(api_id=[]), TypeError),
        (event(message={"req.Method": 3}), TypeError),
        (event(message={"req.URL.Path": None}), TypeError),
        (event("Request sent", request_id={"host": False}), TypeError),
        (event("Response sent", message={"code": "bad"}), ValueError),
        (event(extra=float("nan")), ValueError),
        (event("unknown", message={"req.Method": False}), None),
        (event(message={"req.Method": "gEt"}), None),
        (event("Request sent", request_id=None), None),
    ],
)
def test_bad_input_diagnostics(tmp_path, record, expected_error):
    path = tmp_path / "bad.jsonl"
    text = record if isinstance(record, str) else json.dumps(record, ensure_ascii=False)
    path.write_text("\n \n" + text, encoding="utf-8")

    with (
        pytest.raises(expected_error, match=rf"{path}:3: .+")
        if expected_error
        else pytest.warns(UserWarning, match=rf"{path}:3: .+")
    ):
        assert load_contexttrack(path, module_id="module").nodes == {}


@pytest.mark.parametrize(
    "module_id, expected_error", [("", ValueError), (None, TypeError), (1, TypeError)]
)
def test_module_id_must_be_a_nonempty_string(tmp_path, module_id, expected_error):
    with pytest.raises(expected_error, match="module_id"):
        load_contexttrack(tmp_path / "absent.jsonl", module_id=module_id)


@pytest.mark.parametrize(
    "paths, pattern",
    [
        ([], None),
        (["", "/"], "/route-1"),
        (["", "/rewritten"], None),
        (["/rewritten", ""], None),
    ],
)
@pytest.mark.parametrize("copies", [1, 2])
def test_routing_fallback_and_last_pattern(tmp_path, paths, pattern, copies):
    routes = [
        event("Request routed", path=p, pattern=f"/route-{i}")
        for i, p in enumerate(paths)
    ]

    graph = load(
        tmp_path,
        *([event()] * copies),
        *routes,
        event("Response sent"),
        warn=copies == 2 or "/rewritten" in paths,
    )

    assert len(graph.nodes) == (2 if copies == 1 else 1)
    for node in graph.nodes.values():
        assert (node.pattern, node.path, node.host) == (
            (pattern, None, None) if pattern and copies == 1 else (None, "/", None)
        )


@pytest.mark.parametrize("direction", ["sent", "received"])
@pytest.mark.parametrize("copies", [0, 1, 2])
@pytest.mark.parametrize("api_id", [None, " API\n", "conflict"])
def test_response_matching(tmp_path, direction, copies, api_id):
    request = event(f"Request {direction}")
    response_kind = "Response received" if direction == "sent" else "Response sent"
    response = event(response_kind, api_id=api_id)
    records = [request] * copies + [response, response]

    if copies == 0:
        records.append(request)

    matched = copies == 1 and api_id != "conflict"
    graph = load(tmp_path, *records, warn=not matched)

    assert len(graph.nodes) == (2 if matched else 1)

    if matched:
        request_node, response_node = graph.nodes.values()
        assert response_node.api_id == " API\n"
        assert response_node.status_code == 200
        assert request_node.model_dump(
            exclude={"kind", "status_code"}
        ) == response_node.model_dump(exclude={"kind", "status_code"})


@pytest.mark.parametrize("field", ["req.Method", "req.URL.Path", "code"])
def test_missing_response_labels_never_use_partial_matches(tmp_path, field):
    response = event("Response sent")
    del response["message"][field]

    graph = load(tmp_path, event(), response, warn=True)

    assert len(graph.nodes) == 1


@pytest.mark.parametrize(
    "context", [None, {}, {"context_id": None}, {"context_id": ""}, {"context_id": "c"}]
)
@pytest.mark.parametrize(
    "fields", [{}, {"pid": 2}, {"context": {"context_id": "other"}}]
)
@pytest.mark.parametrize("repeats", [0, 1, 2])
def test_context_scoped_occurrence_influence(tmp_path, context, fields, repeats):
    received = event(context=context)
    sent = event("Request sent", context=context) | fields
    sent["message"] = {"unconsumed": False}
    reply = event("Response sent", context=context) | fields
    connected = context == {"context_id": "c"} and not fields

    graph = load(
        tmp_path, sent, received, *([sent] * repeats), reply, warn=not connected
    )

    assert len(graph.nodes) == (3 if connected else 2)

    expected = {("n1", "n2")} if connected else set()
    if connected and repeats:
        expected.add(("n1", "n0"))

    assert graph.edges == expected


def test_scrape_capture():
    captures = Path(__file__).parents[1] / "examples/contexttrack/prometheus"
    graph = load_contexttrack(captures / "scrape-ok.jsonl", module_id="scraper")
    host = "127.0.0.1:38151"

    assert list(graph.nodes) == ["n0", "n1", "n2", "n3"]

    messages = [m for m in graph.nodes.values() if isinstance(m, Message)]
    assert [(m.kind, m.host, m.status_code) for m in messages] == [
        ("send_request", host, None),
        ("receive_request", None, None),
        ("send_response", None, 200),
        ("receive_response", host, 200),
    ]
    assert {(m.api_id, m.method, m.path, m.pattern) for m in messages} == {
        ("github.com/prometheus", "GET", "/", None)
    }
    assert graph.edges == {("n1", "n2")}
