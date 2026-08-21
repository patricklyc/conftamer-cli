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
        for index, route_record in enumerate(records):
            route = route_record.event
            if not isinstance(route, RequestRoutedEvent):
                continue

            candidates = [
                record
                for record in records[:index]
                if isinstance(record.event, RequestReceivedEvent)
                and record.event.message.method == route.message.method
                and record.event.message.path == route.message.path
            ]
            if len(candidates) != 1:
                warnings.append(
                    ParseWarning(
                        route_record.input_line,
                        "route has no unambiguous request match",
                    )
                )
                continue

            routes[candidates[0].sequence] = route.message.pattern

    return routes, warnings


def match_responses(
    groups: EventGroups,
) -> tuple[ResponseMatches, list[ParseWarning]]:
    sent = {}
    received = {}
    warnings = []

    for records in groups.values():
        for index, response_record in enumerate(records):
            response = response_record.event

            if isinstance(response, ResponseSentEvent):
                request_type = RequestReceivedEvent
                matches = sent
            elif isinstance(response, ResponseReceivedEvent):
                request_type = RequestSentEvent
                matches = received
            else:
                continue

            method = response.message.method
            path = response.message.path
            candidates = [
                record
                for record in records[:index]
                if isinstance(record.event, request_type)
                and record.event.message.method == method
                and record.event.message.path == path
            ]
            request = _choose_request(candidates, response_record)
            if request is None:
                reason = "ambiguous" if len(candidates) > 1 else "missing"
                warnings.append(
                    ParseWarning(
                        response_record.input_line,
                        f"{reason} request match for response",
                    )
                )
                continue

            matches[response_record.sequence] = request

    return ResponseMatches(sent=sent, received=received), warnings


def _choose_request(
    candidates: Sequence[EventRecord],
    response: EventRecord,
) -> EventRecord | None:
    if len(candidates) == 1:
        return candidates[0]
    if response.event.goroutine_id is None:
        return None

    same_goroutine = [
        candidate
        for candidate in candidates
        if candidate.event.goroutine_id == response.event.goroutine_id
    ]
    if len(same_goroutine) == 1:
        return same_goroutine[0]
    return None
