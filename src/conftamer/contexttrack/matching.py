from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from conftamer.contexttrack.models import (
    EventGroups,
    EventRecord,
    RequestReceivedEvent,
    RequestSentEvent,
    ResponseReceivedEvent,
    ResponseSentEvent,
    RouteEvent,
)


@dataclass(frozen=True)
class MatchIssue:
    input_line: int
    code: str
    message: str


@dataclass(frozen=True)
class RouteMatch:
    pattern: str
    records: tuple[EventRecord, ...]


@dataclass(frozen=True)
class ResponseMatches:
    sent: dict[int, EventRecord]
    received: dict[int, EventRecord]


def match_routes(
    groups: EventGroups,
) -> tuple[dict[int, RouteMatch], list[MatchIssue]]:
    matches: dict[int, RouteMatch] = {}
    issues = []
    for records in groups.values():
        ordered = sorted(records, key=lambda item: item.sequence)
        requests = [
            record
            for record in ordered
            if isinstance(record.event, RequestReceivedEvent)
        ]
        chains: dict[tuple[str, str], list[EventRecord]] = {}
        unresolved: set[tuple[str, str]] = set()
        for record in ordered:
            if not isinstance(record.event, RouteEvent):
                continue
            if not record.event.message.pattern:
                issues.append(
                    MatchIssue(
                        record.input_line,
                        "contexttrack.invalid_route_pattern",
                        "route pattern is empty",
                    )
                )
                continue
            _extend_route_chains(record, chains, unresolved, issues)
        _match_route_chains(requests, chains, unresolved, matches, issues)
    return matches, issues


def _extend_route_chains(
    record: EventRecord,
    chains: dict[tuple[str, str], list[EventRecord]],
    unresolved: set[tuple[str, str]],
    issues: list[MatchIssue],
) -> None:
    event = _route_event(record)
    method = event.message.method.upper()
    path = event.message.path
    candidates = [
        key
        for key, chain in chains.items()
        if method == key[0] and _route_event(chain[-1]).message.path.endswith(path)
    ]
    if len(candidates) > 1:
        unresolved.update(candidates)
        issues.append(
            MatchIssue(
                record.input_line,
                "contexttrack.ambiguous_route",
                "route has several suffix-compatible chains",
            )
        )
    elif candidates:
        chains[candidates[0]].append(record)
    else:
        chains.setdefault((method, path), [record])


def _match_route_chains(
    requests: Sequence[EventRecord],
    chains: Mapping[tuple[str, str], list[EventRecord]],
    unresolved: set[tuple[str, str]],
    matches: dict[int, RouteMatch],
    issues: list[MatchIssue],
) -> None:
    for endpoint, chain in chains.items():
        if endpoint in unresolved:
            continue
        candidates = [request for request in requests if _endpoint(request) == endpoint]
        if not candidates:
            issues.append(
                MatchIssue(
                    chain[0].input_line,
                    "contexttrack.route_without_request",
                    "route has no matching received request",
                )
            )
            continue
        match = RouteMatch(_full_pattern(chain), tuple(chain))
        matches.update((request.sequence, match) for request in candidates)


def match_responses(
    groups: EventGroups,
) -> tuple[ResponseMatches, list[MatchIssue]]:
    sent: dict[int, EventRecord] = {}
    received: dict[int, EventRecord] = {}
    issues = []
    for records in groups.values():
        inbound: list[EventRecord] = []
        outbound: list[EventRecord] = []
        previous_sent = None
        previous_received = None
        for record in sorted(records, key=lambda item: item.sequence):
            match record.event:
                case RequestReceivedEvent():
                    inbound.append(record)
                case RequestSentEvent():
                    outbound.append(record)
                case ResponseSentEvent():
                    previous_sent = _match_response(
                        record, inbound, sent, issues, previous_sent
                    )
                case ResponseReceivedEvent():
                    previous_received = _match_response(
                        record, outbound, received, issues, previous_received
                    )
                case _:
                    continue
    return ResponseMatches(sent, received), issues


def _match_response(
    response: EventRecord,
    requests: list[EventRecord],
    matches: dict[int, EventRecord],
    issues: list[MatchIssue],
    previous: EventRecord | None,
) -> EventRecord:
    if _is_duplicate(response, previous, matches):
        return response
    if _endpoint(response) is None:
        return response

    candidates = [request for request in requests if _same_endpoint(request, response)]
    if not candidates and isinstance(response.event, ResponseReceivedEvent):
        candidates = [
            request
            for request in requests
            if _same_method_and_goroutine(request, response)
        ]
    request = _choose_request(candidates, response)
    if request is None:
        code = (
            "contexttrack.ambiguous_response"
            if len(candidates) > 1
            else "contexttrack.unmatched_response"
        )
        message = (
            "response has several request candidates"
            if len(candidates) > 1
            else "response has no request candidate"
        )
        issues.append(MatchIssue(response.input_line, code, message))
        return response

    requests.remove(request)
    matches[response.sequence] = request
    return response


def _choose_request(
    candidates: Sequence[EventRecord], response: EventRecord
) -> EventRecord | None:
    if len(candidates) == 1:
        return candidates[0]
    same_goroutine = [
        candidate
        for candidate in candidates
        if response.event.goroutine_id is not None
        and candidate.event.goroutine_id == response.event.goroutine_id
    ]
    return same_goroutine[0] if len(same_goroutine) == 1 else None


def _endpoint(record: EventRecord) -> tuple[str, str] | None:
    event = record.event
    if isinstance(event, RequestSentEvent) and event.request_id is not None:
        return event.request_id.method.upper(), event.request_id.path
    message = event.message
    method = getattr(message, "method", None)
    path = getattr(message, "path", None)
    if method is None or path is None:
        return None
    return method.upper(), path


def _same_endpoint(first: EventRecord, second: EventRecord) -> bool:
    first_endpoint = _endpoint(first)
    return first_endpoint is not None and first_endpoint == _endpoint(second)


def _same_method_and_goroutine(request: EventRecord, response: EventRecord) -> bool:
    request_endpoint = _endpoint(request)
    response_endpoint = _endpoint(response)
    return (
        request_endpoint is not None
        and response_endpoint is not None
        and request_endpoint[0] == response_endpoint[0]
        and response.event.goroutine_id is not None
        and request.event.goroutine_id == response.event.goroutine_id
    )


def _is_duplicate(
    response: EventRecord,
    previous: EventRecord | None,
    matches: Mapping[int, EventRecord],
) -> bool:
    if previous is None or previous.sequence not in matches:
        return False
    event = response.event
    previous_event = previous.event
    if not isinstance(event, ResponseReceivedEvent) or not isinstance(
        previous_event, ResponseReceivedEvent
    ):
        return False
    if previous_event.api_id is not None or event.api_id is None:
        return False
    endpoint = _endpoint(response)
    previous_endpoint = _endpoint(matches[previous.sequence])
    if (
        endpoint is not None
        and previous_endpoint is not None
        and endpoint != previous_endpoint
    ):
        return False
    return event.message.status == previous_event.message.status and (
        event.message.method is None
        or previous_event.message.method is None
        or event.message.method.upper() == previous_event.message.method.upper()
    )


def _route_event(record: EventRecord) -> RouteEvent:
    event = record.event
    if not isinstance(event, RouteEvent):
        raise TypeError("route chain contains a non-route event")
    return event


def _full_pattern(chain: Sequence[EventRecord]) -> str:
    original_path = _route_event(chain[0]).message.path
    last_message = _route_event(chain[-1]).message
    if last_message.path == original_path:
        return last_message.pattern
    prefix = original_path[: len(original_path) - len(last_message.path)]
    path_start = last_message.pattern.find("/")
    if path_start < 0:
        return last_message.pattern
    return (
        last_message.pattern[:path_start] + prefix + last_message.pattern[path_start:]
    )
