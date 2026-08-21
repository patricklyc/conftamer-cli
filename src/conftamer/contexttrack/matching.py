from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from conftamer.contexttrack.events import (
    EventRecord,
    ParseWarning,
    RequestReceivedEvent,
    RequestRoutedEvent,
    RequestSentEvent,
    ResponseReceivedEvent,
    ResponseSentEvent,
)

GroupKey = tuple[int, str]
EventGroups = Mapping[GroupKey, Sequence[EventRecord]]


@dataclass(frozen=True)
class ResponseMatches:
    sent: dict[int, EventRecord]
    received: dict[int, EventRecord]


def group_events(
    records: Iterable[EventRecord],
) -> tuple[dict[GroupKey, list[EventRecord]], list[EventRecord]]:
    groups: dict[GroupKey, list[EventRecord]] = {}
    ungrouped = []

    for record in records:
        context_id = record.event.context.context_id
        if context_id is None:
            ungrouped.append(record)
            continue

        key = (record.event.pid, context_id)
        groups.setdefault(key, []).append(record)

    return groups, ungrouped


def match_routes(
    groups: EventGroups,
) -> tuple[dict[int, str], list[ParseWarning]]:
    routes = {}
    warnings = []

    for records in groups.values():
        requests = []
        for record in sorted(records, key=lambda item: item.sequence):
            event = record.event
            if isinstance(event, RequestReceivedEvent):
                requests.append(record)
            elif isinstance(event, RequestRoutedEvent):
                candidates = [
                    request for request in requests if _same_endpoint(request, record)
                ]
                if candidates:
                    routes[candidates[-1].sequence] = event.message.pattern
                else:
                    warnings.append(
                        ParseWarning(record.input_line, "route has no request match")
                    )

    return routes, warnings


def match_responses(
    groups: EventGroups,
) -> tuple[ResponseMatches, list[ParseWarning]]:
    sent = {}
    received = {}
    warnings = []

    for records in groups.values():
        inbound = []
        outbound = []
        previous_sent = None
        previous_received = None
        for record in sorted(records, key=lambda item: item.sequence):
            event = record.event
            if isinstance(event, RequestReceivedEvent):
                inbound.append(record)
            elif isinstance(event, RequestSentEvent):
                outbound.append(record)
            elif isinstance(event, ResponseSentEvent):
                previous_sent = _match_response(
                    record, inbound, sent, warnings, previous_sent
                )
            elif isinstance(event, ResponseReceivedEvent):
                previous_received = _match_response(
                    record, outbound, received, warnings, previous_received
                )

    return ResponseMatches(sent=sent, received=received), warnings


def _match_response(
    response: EventRecord,
    requests: list[EventRecord],
    matches: dict[int, EventRecord],
    warnings: list[ParseWarning],
    previous: EventRecord | None,
) -> EventRecord:
    message = response.event.message
    if message.method is None or message.path is None:
        if not _is_duplicate(response, previous):
            warnings.append(
                ParseWarning(response.input_line, "response has no endpoint")
            )
        return response

    candidates = [request for request in requests if _same_endpoint(request, response)]
    request = _choose_request(candidates, response)
    if request is None:
        if not _is_duplicate(response, previous):
            reason = "ambiguous" if len(candidates) > 1 else "missing"
            warnings.append(
                ParseWarning(response.input_line, f"{reason} request match")
            )
        return response

    requests.remove(request)
    matches[response.sequence] = request
    return response


def _choose_request(
    candidates: Sequence[EventRecord], event: EventRecord
) -> EventRecord | None:
    if len(candidates) == 1:
        return candidates[0]
    same_goroutine = [
        candidate
        for candidate in candidates
        if event.event.goroutine_id is not None
        and candidate.event.goroutine_id == event.event.goroutine_id
    ]
    return same_goroutine[0] if len(same_goroutine) == 1 else None


def _same_endpoint(first: EventRecord, second: EventRecord) -> bool:
    first_message = first.event.message
    second_message = second.event.message
    return (
        first_message.method.upper() == second_message.method.upper()
        and first_message.path == second_message.path
    )


def _is_duplicate(response: EventRecord, previous: EventRecord | None) -> bool:
    return (
        previous is not None
        and response.sequence == previous.sequence + 1
        and response.event.message.status == previous.event.message.status
    )
