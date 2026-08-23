from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from conftamer.contexttrack.events import (
    EventGroups,
    EventRecord,
    ParseWarning,
    RequestReceivedEvent,
    RequestSentEvent,
    ResponseReceivedEvent,
    ResponseSentEvent,
)


@dataclass(frozen=True)
class ResponseMatches:
    sent: dict[int, EventRecord]
    received: dict[int, EventRecord]


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
    if _is_duplicate(response, previous, matches):
        return response

    message = response.event.message
    if message.method is None or message.path is None:
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
        reason = "ambiguous" if len(candidates) > 1 else "missing"
        warnings.append(ParseWarning(response.input_line, f"{reason} request match"))
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


def _endpoint(record: EventRecord) -> tuple[str, str] | None:
    message = record.event.message
    if message.method is None or message.path is None:
        return None
    return message.method.upper(), message.path


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

    message = event.message
    previous_message = previous_event.message
    return message.status == previous_message.status and (
        message.method is None
        or previous_message.method is None
        or message.method.upper() == previous_message.method.upper()
    )
