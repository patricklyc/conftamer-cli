from collections.abc import Sequence

from conftamer.contexttrack.events import (
    EventGroups,
    EventRecord,
    ParseWarning,
    RequestReceivedEvent,
    RequestRoutedEvent,
)


def match_routes(
    groups: EventGroups,
) -> tuple[dict[int, str], list[ParseWarning]]:
    routes = {}
    warnings = []

    for records in groups.values():
        ordered = sorted(records, key=lambda item: item.sequence)
        requests = [
            record
            for record in ordered
            if isinstance(record.event, RequestReceivedEvent)
        ]
        chains: dict[tuple[str, str], list[EventRecord]] = {}

        for record in ordered:
            if not isinstance(record.event, RequestRoutedEvent):
                continue

            method = record.event.message.method.upper()
            path = record.event.message.path
            candidates = [
                key
                for key in chains
                if method == key[0]
                and path != _route_event(chains[key][-1]).message.path
                and _route_event(chains[key][-1]).message.path.endswith(path)
            ]
            if len(candidates) > 1:
                warnings.append(
                    ParseWarning(record.input_line, "ambiguous route chain")
                )
                continue
            if candidates:
                chains[candidates[0]].append(record)
                continue

            key = (method, path)
            chains.setdefault(key, []).append(record)

        for key, chain in chains.items():
            candidates = [request for request in requests if _endpoint(request) == key]
            if not candidates:
                warnings.append(
                    ParseWarning(chain[0].input_line, "route has no request match")
                )
                continue

            pattern = _full_pattern(chain)
            routes.update((candidate.sequence, pattern) for candidate in candidates)

    return routes, warnings


def _route_event(record: EventRecord) -> RequestRoutedEvent:
    event = record.event
    if not isinstance(event, RequestRoutedEvent):
        raise TypeError("route chain contains a non-route event")
    return event


def _endpoint(record: EventRecord) -> tuple[str, str] | None:
    message = record.event.message
    if message.method is None or message.path is None:
        return None
    return message.method.upper(), message.path


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
