import json
import warnings

import pytest
from contexttrack import EventFileError, iter_events

import conftamer.contexttrack as consumer
from conftamer.contexttrack import load_contexttrack
from conftamer.pmgraph.models import Message


def event(kind="receive_request", *, path="/", pattern="/route", **fields):
    message = {"method": "gEt", "path": path}

    if kind == "send_request":
        message["host"] = "Höst:80"
    if kind == "request_routed":
        message["pattern"] = pattern
    if kind in ("send_response", "receive_response"):
        message["status_code"] = 200

    return {
        "schema_version": 1,
        "kind": kind,
        "pid": 1,
        "context": {"context_id": "c"},
        "message": message,
        "api_id": " API\n",
    } | fields


def write_capture(tmp_path, *records):
    path = tmp_path / "events.jsonl"
    path.write_text(
        "\n".join(json.dumps(record, ensure_ascii=False) for record in records),
        encoding="utf-8",
    )
    return path


def load(tmp_path, *records, warn=False):
    path = write_capture(tmp_path, *records)
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


def test_normalized_sent_request(tmp_path):
    graph = load(
        tmp_path,
        {
            "schema_version": 1,
            "kind": "send_request",
            "pid": 1,
            "context": {"context_id": "c"},
            "api_id": " API\n",
            "message": {
                "method": "gEt",
                "host": "Höst:80",
                "path": "/",
                "raw_query": "",
            },
        },
    )

    assert graph.nodes == {
        "n0": Message(
            kind="send_request", api_id=" API\n", method="gEt", host="Höst:80", path="/"
        )
    }
    assert graph.edges == set()


@pytest.mark.parametrize(
    "record",
    [
        "{",
        None,
        {"kind": "Request received", "pid": 1, "context": {}, "message": {}},
        event(schema_version=2),
        event(kind="unknown"),
        event(extra=False),
        event(message={"method": 3}),
        event(message={"path": ""}),
        event("send_response", message={"status_code": "200"}),
        b"\xff",
    ],
)
def test_normalized_input_diagnostics(tmp_path, record):
    path = tmp_path / "bad.jsonl"
    if isinstance(record, bytes):
        data = record
    else:
        text = (
            record
            if isinstance(record, str)
            else json.dumps(record, ensure_ascii=False)
        )
        data = text.encode("utf-8")
    path.write_bytes(json.dumps(event()).encode("utf-8") + b"\n \t\n" + data)

    with pytest.raises(EventFileError) as caught:
        load_contexttrack(path, module_id="module")

    error = caught.value
    assert error.path == path and error.line == 3
    assert error.reason and str(error).startswith(f"{path}:3:")
    assert error.__cause__ is not None
    assert not isinstance(error.__cause__, EventFileError)


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
        (["/", "/"], "/route-1"),
        (["/", "/rewritten"], None),
        (["/rewritten", "/"], None),
    ],
)
@pytest.mark.parametrize("copies", [1, 2])
def test_routing_fallback_and_last_pattern(tmp_path, paths, pattern, copies):
    routes = [
        event("request_routed", path=p, pattern=f"/route-{i}")
        for i, p in enumerate(paths)
    ]

    graph = load(
        tmp_path,
        *([event()] * copies),
        *routes,
        event("send_response"),
        warn=copies == 2 or "/rewritten" in paths,
    )

    assert len(graph.nodes) == (2 if copies == 1 else 1)
    for node in graph.nodes.values():
        assert (node.pattern, node.path, node.host) == (
            (pattern, None, None) if pattern and copies == 1 else (None, "/", None)
        )


@pytest.mark.parametrize("direction", ["send", "receive"])
@pytest.mark.parametrize(
    "copies, api_id", [(0, None), (2, None), (1, None), (1, " API\n"), (1, "conflict")]
)
def test_response_matching(tmp_path, direction, copies, api_id):
    request = event(f"{direction}_request")
    response_kind = "receive_response" if direction == "send" else "send_response"
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


@pytest.mark.parametrize("field", ["method", "path"])
def test_missing_response_labels_never_use_partial_matches(tmp_path, field):
    response = event("send_response")
    del response["message"][field]

    graph = load(tmp_path, event(), response, warn=True)

    assert len(graph.nodes) == 1


@pytest.mark.parametrize(
    "context, fields, repeats",
    [
        ({}, {}, 2),
        ({"context_id": None}, {}, 2),
        ({"context_id": ""}, {}, 2),
        ({"context_id": "c"}, {}, 0),
        ({"context_id": "c"}, {}, 2),
        ({"context_id": "c"}, {"pid": 2}, 2),
        ({"context_id": "c"}, {"context": {"context_id": "other"}}, 2),
        ({"context_id": "c"}, {"context": {"context_id": " c "}}, 2),
    ],
)
def test_context_scoped_occurrence_influence(tmp_path, context, fields, repeats):
    received = event(context=context)
    sent = event("send_request", context=context) | fields
    sent["message"]["raw_query"] = "unconsumed=false"
    reply = event("send_response", context=context) | fields
    connected = context == {"context_id": "c"} and not fields

    graph = load(
        tmp_path, sent, received, *([sent] * repeats), reply, warn=not connected
    )

    assert len(graph.nodes) == (3 if connected else 2)

    expected = {("n1", "n2")} if connected else set()
    if connected and repeats:
        expected.add(("n1", "n0"))

    assert graph.edges == expected


@pytest.mark.parametrize(
    "kind, message",
    [
        ("receive_request", {}),
        ("receive_request", {"method": "", "path": "/"}),
        ("receive_request", {"method": "gEt", "path": None}),
        ("send_request", {"method": "gEt", "path": "/", "host": None}),
        ("send_request", {"method": "gEt", "path": "/", "host": ""}),
        ("request_routed", {"method": "gEt", "path": "/", "pattern": None}),
        ("request_routed", {"method": "gEt", "path": "/", "pattern": ""}),
        ("send_response", {"method": "gEt", "path": "/", "status_code": None}),
    ],
)
def test_incomplete_normalized_evidence_warns(tmp_path, kind, message):
    graph = load(tmp_path, event(), event(kind, message=message), warn=True)

    assert graph.nodes == {
        "n0": Message(kind="receive_request", api_id=" API\n", method="gEt", path="/")
    }
    assert graph.edges == set()


@pytest.mark.parametrize("status_code", [0, 999])
def test_status_codes_have_no_http_range_limit(tmp_path, status_code):
    response = event("send_response")
    response["message"]["status_code"] = status_code

    graph = load(tmp_path, event(), response)

    assert graph.nodes["n1"].status_code == status_code
    assert graph.edges == {("n0", "n1")}


def test_nonsemantic_metadata_does_not_change_graph(tmp_path):
    records = [
        event(kind, path="/Raw%2f//", context={"context_id": " \t"})
        for kind in (
            "receive_request",
            "request_routed",
            "send_request",
            "send_response",
            "receive_response",
        )
    ]
    baseline = load(tmp_path, *records)
    for index, record in enumerate(records):
        record.update(
            handler=f"handler-{index}",
            file="debug.go",
            line=999,
            goroutine_id=index,
            thread_id=-index,
        )
        record["context"].update(
            source="source", type="context.Context", error="diagnostic"
        )
        if record["kind"] in ("receive_request", "send_request"):
            record["message"]["raw_query"] = f"query={index}%2F"

    graph = load(tmp_path, *records)

    assert graph == baseline
    assert graph.edges == {("n0", "n1"), ("n0", "n2")}
    assert graph.nodes["n1"] == Message(
        kind="send_request",
        api_id=" API\n",
        method="gEt",
        host="Höst:80",
        path="/Raw%2f//",
    )


def test_warning_uses_physical_not_debug_location(tmp_path):
    path = tmp_path / "events.jsonl"
    path.write_text(
        "\n\n" + json.dumps(event(message={}, file="debug.go", line=999)),
        encoding="utf-8",
    )

    with pytest.warns(UserWarning, match=rf"{path}:3: incomplete request label"):
        assert load_contexttrack(path, module_id="module").nodes == {}


def test_association_does_not_mutate_wire_events(tmp_path, monkeypatch):
    path = write_capture(
        tmp_path,
        event(),
        event("request_routed", pattern="GET /items/{id}"),
        event("send_request"),
        event("send_response", api_id=None),
        event("receive_response", api_id=None),
    )
    records = list(iter_events(path))
    original = [record.event.model_dump_json() for record in records]
    monkeypatch.setattr(consumer, "iter_events", lambda _source: iter(records))

    graph = load_contexttrack(path, module_id="module")

    assert [record.event.model_dump_json() for record in records] == original
    assert graph.nodes["n2"] == Message(
        kind="send_response",
        api_id=" API\n",
        method="gEt",
        pattern="GET /items/{id}",
        status_code=200,
    )
    assert graph.nodes["n3"] == Message(
        kind="receive_response",
        api_id=" API\n",
        method="gEt",
        host="Höst:80",
        path="/",
        status_code=200,
    )
    assert graph.edges == {("n0", "n1"), ("n0", "n2")}


def test_conflicting_duplicate_hook_preserves_usable_response(tmp_path):
    response = event("receive_response", api_id=None)
    response["message"]["status_code"] = 202
    path = write_capture(
        tmp_path, event("send_request"), response, response | {"api_id": "conflict"}
    )

    with pytest.warns(UserWarning) as notices:
        graph = load_contexttrack(path, module_id="module")

    assert len(notices) == 1
    assert (
        str(notices[0].message) == f"{path}:3: conflicting response and request API IDs"
    )
    assert list(graph.nodes) == ["n0", "n1"]
    assert graph.nodes["n0"].kind == "send_request"
    assert graph.nodes["n1"] == Message(
        kind="receive_response",
        api_id=" API\n",
        method="gEt",
        host="Höst:80",
        path="/",
        status_code=202,
    )
    assert graph.edges == set()


def test_scrape_capture(normalized_scrape_capture):
    records = list(iter_events(normalized_scrape_capture))
    assert len(records) == 20
    assert sum(record.event.kind == "receive_response" for record in records) == 8

    with warnings.catch_warnings(record=True) as notices:
        warnings.simplefilter("always")
        graph = load_contexttrack(normalized_scrape_capture, module_id="scraper")
    assert notices == []
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
