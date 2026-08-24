from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from conftamer.contexttrack.events import (
    EventRecord,
    GroupKey,
    ParseWarning,
    RequestReceivedEvent,
    RequestSentEvent,
    ResponseReceivedEvent,
    ResponseSentEvent,
    group_events,
    read_events,
)
from conftamer.contexttrack.responses import ResponseMatches, match_responses
from conftamer.contexttrack.routes import match_routes
from conftamer.pmgraph import (
    PMEdge,
    PMGraph,
    PMNode,
    ReceiveRequestNode,
    ReceiveResponseNode,
    SendRequestNode,
    SendResponseNode,
    make_node_id,
    make_pmgraph,
)


@dataclass(frozen=True)
class Occurrence:
    group: GroupKey | None
    sequence: int
    node: PMNode


class NodeConversionError(ValueError):
    pass


@dataclass(frozen=True)
class ContextTrackResult:
    graph: PMGraph
    warnings: tuple[ParseWarning, ...]


def parse_contexttrack(
    path: str | Path, *, module_id: str
) -> ContextTrackResult:
    records, warnings = read_events(path)
    groups, ungrouped = group_events(records)
    routes, route_warnings = match_routes(groups)
    responses, response_warnings = match_responses(groups)
    occurrences = []

    for record in records:
        try:
            node = _to_node(record, module_id, routes, responses)
        except NodeConversionError as error:
            warnings.append(ParseWarning(record.input_line, str(error)))
            continue
        except ValidationError as error:
            warnings.append(ParseWarning(record.input_line, str(error)))
            continue
        if node is not None:
            occurrences.append(
                Occurrence(_group_key(record), record.sequence, node)
            )

    warnings.extend(
        ParseWarning(record.input_line, "event has no context ID")
        for record in ungrouped
    )
    warnings.extend(route_warnings)
    warnings.extend(response_warnings)

    return ContextTrackResult(
        graph=_to_graph(module_id, occurrences),
        warnings=tuple(
            sorted(warnings, key=lambda warning: warning.input_line)
        ),
    )


def _to_node(
    record: EventRecord,
    module_id: str,
    routes: dict[int, str],
    responses: ResponseMatches,
) -> PMNode | None:
    event = record.event

    if isinstance(event, RequestReceivedEvent):
        api_id = event.api_id
        method = event.message.method.upper()
        pattern = routes.get(record.sequence, _http_path(event.message.path))
        fields = {"api_id": api_id, "method": method, "pattern": pattern}
        return ReceiveRequestNode(
            id=_id(module_id, "Receive", "Request", fields),
            api_id=api_id,
            method=method,
            pattern=pattern,
        )

    if isinstance(event, RequestSentEvent):
        return _send_request(event, module_id)

    if isinstance(event, ResponseReceivedEvent):
        request = responses.received.get(record.sequence)
        if request is None or not isinstance(request.event, RequestSentEvent):
            return None
        sent = _send_request(request.event, module_id)
        status = event.message.status
        fields = {
            "api_id": sent.api_id,
            "method": sent.method,
            "host": sent.host,
            "path": sent.path,
            "status": status,
        }
        return ReceiveResponseNode(
            id=_id(module_id, "Receive", "Response", fields),
            api_id=sent.api_id,
            method=sent.method,
            host=sent.host,
            path=sent.path,
            status=status,
        )

    if isinstance(event, ResponseSentEvent):
        request = responses.sent.get(record.sequence)
        if request is None:
            return None
        received = _to_node(request, module_id, routes, responses)
        if not isinstance(received, ReceiveRequestNode):
            return None
        status = event.message.status
        fields = {
            "api_id": received.api_id,
            "method": received.method,
            "pattern": received.pattern,
            "status": status,
        }
        return SendResponseNode(
            id=_id(module_id, "Send", "Response", fields),
            api_id=received.api_id,
            method=received.method,
            pattern=received.pattern,
            status=status,
        )

    return None


def _send_request(event: RequestSentEvent, module_id: str) -> SendRequestNode:
    request = event.request_id or event.message
    if not request.host:
        raise NodeConversionError("request endpoint has no host")

    api_id = event.api_id
    method = request.method.upper()
    host = request.host
    path = _http_path(request.path)
    fields = {"api_id": api_id, "method": method, "host": host, "path": path}
    return SendRequestNode(
        id=_id(module_id, "Send", "Request", fields),
        api_id=api_id,
        method=method,
        host=host,
        path=path,
    )


def _http_path(path: str) -> str:
    return path or "/"


def _id(
    module_id: str,
    node_type: str,
    message: str,
    fields: Mapping[str, object],
) -> str:
    return make_node_id(
        module_id,
        {"type": node_type, "message": message, **fields},
    )


def _to_graph(module_id: str, occurrences: list[Occurrence]) -> PMGraph:
    groups = {}
    edges = []
    for occurrence in occurrences:
        if occurrence.group is not None:
            groups.setdefault(occurrence.group, []).append(occurrence)

    for group in groups.values():
        group.sort(key=lambda item: item.sequence)
        for index, source in enumerate(group):
            if source.node.type == "Receive":
                edges.extend(
                    PMEdge(source=source.node.id, target=target.node.id)
                    for target in group[index + 1 :]
                    if target.node.type == "Send"
                )

    return make_pmgraph(module_id, [item.node for item in occurrences], edges)


def _group_key(record: EventRecord) -> GroupKey | None:
    context_id = record.event.context.context_id
    return None if context_id is None else (record.event.pid, context_id)
