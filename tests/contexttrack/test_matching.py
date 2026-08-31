from conftamer.contexttrack.matching import match_responses, match_routes
from conftamer.contexttrack.models import EVENT_ADAPTER, EventRecord, group_events


def record(sequence: int, payload: dict[str, object]) -> EventRecord:
    return EventRecord(
        sequence=sequence,
        input_line=sequence + 1,
        event=EVENT_ADAPTER.validate_python(payload),
    )


def base(kind: str, message: dict[str, object], **extra: object) -> dict[str, object]:
    return {
        "kind": kind,
        "pid": 10,
        "message": message,
        "context": {"context_id": "id:1"},
        **extra,
    }


def sent_request(
    sequence: int,
    *,
    path: str = "/items",
    goroutine_id: int | None = None,
    api_id: str | None = None,
) -> EventRecord:
    return record(
        sequence,
        base(
            "Request sent",
            {
                "req.Method": "GET",
                "req.URL.Host": "example.org",
                "req.URL.Path": path,
            },
            goroutine_id=goroutine_id,
            api_id=api_id,
        ),
    )


def received_response(
    sequence: int,
    *,
    path: str | None = "/items",
    status: int = 200,
    goroutine_id: int | None = None,
    api_id: str | None = None,
) -> EventRecord:
    message: dict[str, object] = {"resp.StatusCode": status}
    if path is not None:
        message.update({"req.Method": "GET", "req.URL.Path": path})
    return record(
        sequence,
        base(
            "Response received",
            message,
            goroutine_id=goroutine_id,
            api_id=api_id,
        ),
    )


def test_routes_reconstruct_suffix_chain_and_retain_supporting_records():
    request = record(
        0,
        base(
            "Request received",
            {"req.Method": "GET", "req.URL.Path": "/api/v1/status/config"},
        ),
    )
    outer = record(
        1,
        base(
            "Request routed",
            {
                "req.Method": "GET",
                "req.URL.Path": "/api/v1/status/config",
                "pattern": "/api/v1/",
            },
        ),
    )
    inner = record(
        2,
        base(
            "Request routed",
            {
                "req.Method": "GET",
                "req.URL.Path": "/status/config",
                "pattern": "/status/config",
            },
        ),
    )
    groups, _ = group_events([request, outer, inner])

    matches, issues = match_routes(groups)

    assert matches[request.sequence].pattern == "/api/v1/status/config"
    assert matches[request.sequence].records == (outer, inner)
    assert issues == []


def test_routes_keep_the_innermost_pattern_for_equal_observed_paths():
    request = record(
        0,
        base("Request received", {"req.Method": "GET", "req.URL.Path": "/-/ready"}),
    )
    broad = record(
        1,
        base(
            "Request routed",
            {"req.Method": "GET", "req.URL.Path": "/-/ready", "pattern": "/"},
        ),
    )
    specific = record(
        2,
        base(
            "Request routed",
            {
                "req.Method": "GET",
                "req.URL.Path": "/-/ready",
                "pattern": "/-/ready",
            },
        ),
    )
    groups, _ = group_events([request, broad, specific])

    matches, issues = match_routes(groups)

    assert matches[request.sequence].pattern == "/-/ready"
    assert matches[request.sequence].records == (broad, specific)
    assert issues == []


def test_routes_do_not_cross_associate_repeated_request_endpoints():
    first_request = record(
        0,
        base("Request received", {"req.Method": "GET", "req.URL.Path": "/same"}),
    )
    first_route = record(
        1,
        base(
            "Request routed",
            {"req.Method": "GET", "req.URL.Path": "/same", "pattern": "/first"},
        ),
    )
    second_request = record(
        2,
        base("Request received", {"req.Method": "GET", "req.URL.Path": "/same"}),
    )
    second_route = record(
        3,
        base(
            "Request routed",
            {"req.Method": "GET", "req.URL.Path": "/same", "pattern": "/second"},
        ),
    )
    groups, _ = group_events([first_request, first_route, second_request, second_route])

    matches, issues = match_routes(groups)

    assert matches == {}
    assert [issue.code for issue in issues] == ["contexttrack.ambiguous_route_request"]


def test_routes_do_not_match_a_request_observed_after_the_route():
    route = record(
        0,
        base(
            "Request routed",
            {"req.Method": "GET", "req.URL.Path": "/items", "pattern": "/items"},
        ),
    )
    request = record(
        1,
        base("Request received", {"req.Method": "GET", "req.URL.Path": "/items"}),
    )
    groups, _ = group_events([route, request])

    matches, issues = match_routes(groups)

    assert matches == {}
    assert [issue.code for issue in issues] == ["contexttrack.route_without_request"]


def test_route_chains_do_not_cross_another_received_request():
    request = record(
        0,
        base(
            "Request received",
            {"req.Method": "GET", "req.URL.Path": "/api/items"},
        ),
    )
    outer = record(
        1,
        base(
            "Request routed",
            {"req.Method": "GET", "req.URL.Path": "/api/items", "pattern": "/api/"},
        ),
    )
    other_request = record(
        2,
        base("Request received", {"req.Method": "GET", "req.URL.Path": "/other"}),
    )
    inner = record(
        3,
        base(
            "Request routed",
            {"req.Method": "GET", "req.URL.Path": "/items", "pattern": "/items"},
        ),
    )
    groups, _ = group_events([request, outer, other_request, inner])

    matches, issues = match_routes(groups)

    assert matches == {}
    assert [issue.code for issue in issues] == ["contexttrack.ambiguous_route_request"]


def test_routes_do_not_use_chains_with_an_ambiguous_suffix_continuation():
    first_request = record(
        0,
        base(
            "Request received",
            {"req.Method": "GET", "req.URL.Path": "/one/items"},
        ),
    )
    second_request = record(
        1,
        base(
            "Request received",
            {"req.Method": "GET", "req.URL.Path": "/two/items"},
        ),
    )
    routes = [
        record(
            sequence + 2,
            base(
                "Request routed",
                {"req.Method": "GET", "req.URL.Path": path, "pattern": path},
            ),
        )
        for sequence, path in enumerate(["/one/items", "/two/items", "/items"])
    ]
    groups, _ = group_events([first_request, second_request, *routes])

    matches, issues = match_routes(groups)

    assert matches == {}
    assert any(issue.code == "contexttrack.ambiguous_route" for issue in issues)


def test_empty_route_pattern_is_diagnosed_and_ignored():
    request = record(
        0,
        base("Request received", {"req.Method": "GET", "req.URL.Path": "/items"}),
    )
    route = record(
        1,
        base(
            "Request routed",
            {"req.Method": "GET", "req.URL.Path": "/items", "pattern": ""},
        ),
    )
    groups, _ = group_events([request, route])

    matches, issues = match_routes(groups)

    assert matches == {}
    assert [issue.code for issue in issues] == ["contexttrack.invalid_route_pattern"]


def test_response_matching_uses_preferred_request_id_labels():
    request = record(
        0,
        base(
            "Request sent",
            {
                "req.Method": "POST",
                "req.URL.Host": "old.example",
                "req.URL.Path": "/old",
            },
            request_id={"method": "GET", "host": "example.org", "path": "/items"},
        ),
    )
    response = received_response(1)
    groups, _ = group_events([request, response])

    matches, issues = match_responses(groups)

    assert matches.received == {response.sequence: request}
    assert issues == []


def test_ambiguous_response_is_not_matched_without_unique_goroutine():
    requests = [sent_request(0), sent_request(1)]
    response = received_response(2)
    groups, _ = group_events([*requests, response])

    matches, issues = match_responses(groups)

    assert matches.received == {}
    assert [issue.code for issue in issues] == ["contexttrack.ambiguous_response"]


def test_goroutine_selects_one_of_several_endpoint_candidates():
    first = sent_request(0, goroutine_id=5)
    second = sent_request(1, goroutine_id=7)
    response = received_response(2, goroutine_id=7)
    groups, _ = group_events([first, second, response])

    matches, issues = match_responses(groups)

    assert matches.received == {response.sequence: second}
    assert issues == []


def test_duplicate_client_hook_does_not_consume_a_newer_request():
    first = sent_request(0)
    wire = received_response(1)
    newer = sent_request(2)
    client = received_response(3, api_id="example.org/api")
    groups, _ = group_events([first, wire, newer, client])

    matches, issues = match_responses(groups)

    assert matches.received == {wire.sequence: first}
    assert issues == []


def test_api_hook_for_a_different_path_is_not_suppressed_as_a_duplicate():
    first = sent_request(0, path="/a")
    second = sent_request(1, path="/b")
    wire = received_response(2, path="/a")
    client = received_response(3, path="/b", api_id="example.org/api")
    groups, _ = group_events([first, second, wire, client])

    matches, issues = match_responses(groups)

    assert matches.received == {wire.sequence: first, client.sequence: second}
    assert issues == []


def test_endpointless_hook_is_silent_and_redirect_fallback_uses_goroutine():
    request = sent_request(0, path="/redirected", goroutine_id=7)
    endpointless = received_response(1, path=None)
    client = received_response(2, path="/original", goroutine_id=7, api_id="api")
    groups, _ = group_events([request, endpointless, client])

    matches, issues = match_responses(groups)

    assert matches.received == {client.sequence: request}
    assert issues == []


def test_unmatched_usable_response_is_diagnosed():
    response = received_response(0, path="/missing")
    groups, _ = group_events([response])

    matches, issues = match_responses(groups)

    assert matches.received == {}
    assert [issue.code for issue in issues] == ["contexttrack.unmatched_response"]
