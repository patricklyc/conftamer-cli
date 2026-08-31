import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from conftamer.contexttrack.matching import (
    ResponseMatches,
    RouteMatch,
    match_responses,
    match_routes,
)
from conftamer.contexttrack.models import (
    EVENT_ADAPTER,
    EventRecord,
    GroupKey,
    RequestReceivedEvent,
    RequestSentEvent,
    ResponseReceivedEvent,
    ResponseSentEvent,
    group_events,
)
from conftamer.diagnostics import (
    Diagnostic,
    EvidenceDerivation,
    EvidenceRef,
    SourceArtifact,
    merge_evidence,
    sort_diagnostics,
)
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
class ContextTrackResult:
    graph: PMGraph
    diagnostics: tuple[Diagnostic, ...]


@dataclass(frozen=True)
class Occurrence:
    group: GroupKey | None
    sequence: int
    input_line: int
    node: PMNode


class NodeConversionError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


def import_contexttrack(
    path: str | Path,
    *,
    module_id: str,
) -> ContextTrackResult:
    source_path = Path(path)
    source_name = str(path)
    data = source_path.read_bytes()
    source = SourceArtifact(
        id=f"sha256:{hashlib.sha256(data).hexdigest()}",
        kind="contexttrack-jsonl",
    )
    records, diagnostics = _read_records(data, source_name)
    groups, ungrouped = group_events(records)
    routes, route_issues = match_routes(groups)
    responses, response_issues = match_responses(groups)
    diagnostics.extend(
        Diagnostic(
            source=source_name,
            line=issue.input_line,
            code=issue.code,
            message=issue.message,
        )
        for issue in [*route_issues, *response_issues]
    )
    diagnostics.extend(
        Diagnostic(
            source=source_name,
            line=record.input_line,
            code="contexttrack.missing_context_id",
            message="event has no usable context ID",
        )
        for record in ungrouped
    )

    occurrences = _project_records(
        records, module_id, source.id, source_name, routes, responses, diagnostics
    )
    graph = make_pmgraph(
        module_id=module_id,
        sources=[source],
        nodes=[occurrence.node for occurrence in occurrences],
        edges=_context_edges(occurrences, source.id),
    )
    return ContextTrackResult(graph, sort_diagnostics(diagnostics))


def _read_records(
    data: bytes, source: str
) -> tuple[list[EventRecord], list[Diagnostic]]:
    records = []
    diagnostics = []
    for input_line, line in enumerate(data.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            event = EVENT_ADAPTER.validate_json(line)
        except ValidationError as error:
            diagnostics.append(
                Diagnostic(
                    source=source,
                    line=input_line,
                    code="contexttrack.invalid_event",
                    message=str(error),
                )
            )
            continue
        records.append(EventRecord(len(records), input_line, event))
    return records, diagnostics


def _project_records(
    records: list[EventRecord],
    module_id: str,
    source_id: str,
    source_name: str,
    routes: Mapping[int, RouteMatch],
    responses: ResponseMatches,
    diagnostics: list[Diagnostic],
) -> list[Occurrence]:
    occurrences = []
    for record in records:
        try:
            node = _to_node(record, module_id, source_id, routes, responses)
        except NodeConversionError as error:
            diagnostics.append(
                Diagnostic(
                    source=source_name,
                    line=record.input_line,
                    code=error.code,
                    message=str(error),
                )
            )
            continue
        except ValidationError as error:
            diagnostics.append(
                Diagnostic(
                    source=source_name,
                    line=record.input_line,
                    code="contexttrack.invalid_semantics",
                    message=str(error),
                )
            )
            continue
        if node is not None:
            occurrences.append(
                Occurrence(_group_key(record), record.sequence, record.input_line, node)
            )
    return occurrences


def _to_node(
    record: EventRecord,
    module_id: str,
    source_id: str,
    routes: Mapping[int, RouteMatch],
    responses: ResponseMatches,
) -> PMNode | None:
    match record.event:
        case RequestReceivedEvent():
            return _receive_request(record, module_id, source_id, routes)
        case RequestSentEvent():
            return _send_request(record, module_id, source_id)
        case ResponseReceivedEvent() as event:
            request = responses.received.get(record.sequence)
            if request is None or not isinstance(request.event, RequestSentEvent):
                return None
            method, host, path = _outbound_labels(request.event)
            if not host:
                return None
            fields = {
                "type": "Receive",
                "message": "Response",
                "api_id": request.event.api_id,
                "method": method,
                "host": host,
                "path": path,
                "status": event.message.status,
            }
            return ReceiveResponseNode(
                id=make_node_id(module_id, fields),
                evidence=_response_evidence(record, request, source_id),
                api_id=request.event.api_id,
                method=method,
                host=host,
                path=path,
                status=event.message.status,
            )
        case ResponseSentEvent() as event:
            request = responses.sent.get(record.sequence)
            if request is None or not isinstance(request.event, RequestReceivedEvent):
                return None
            api_id, method, pattern = _inbound_labels(request, routes)
            fields = {
                "type": "Send",
                "message": "Response",
                "api_id": api_id,
                "method": method,
                "pattern": pattern,
                "status": event.message.status,
            }
            return SendResponseNode(
                id=make_node_id(module_id, fields),
                evidence=_send_response_evidence(
                    record, request, source_id, routes.get(request.sequence)
                ),
                api_id=api_id,
                method=method,
                pattern=pattern,
                status=event.message.status,
            )
        case _:
            return None


def _receive_request(
    record: EventRecord,
    module_id: str,
    source_id: str,
    routes: Mapping[int, RouteMatch],
) -> ReceiveRequestNode:
    event = record.event
    if not isinstance(event, RequestReceivedEvent):
        raise TypeError("expected a received request")
    api_id, method, pattern = _inbound_labels(record, routes)
    fields = {
        "type": "Receive",
        "message": "Request",
        "api_id": api_id,
        "method": method,
        "pattern": pattern,
    }
    evidence = [_evidence(source_id, "observed", record.input_line)]
    route = routes.get(record.sequence)
    if route is not None:
        evidence.append(
            _evidence(
                source_id,
                "route-inference",
                record.input_line,
                *(item.input_line for item in route.records),
            )
        )
    return ReceiveRequestNode(
        id=make_node_id(module_id, fields),
        evidence=merge_evidence(evidence),
        api_id=api_id,
        method=method,
        pattern=pattern,
    )


def _send_request(
    record: EventRecord, module_id: str, source_id: str
) -> SendRequestNode:
    event = record.event
    if not isinstance(event, RequestSentEvent):
        raise TypeError("expected a sent request")
    method, host, path = _outbound_labels(event)
    if not host:
        raise NodeConversionError(
            "contexttrack.request_without_host",
            "sent request has no host",
        )
    fields = {
        "type": "Send",
        "message": "Request",
        "api_id": event.api_id,
        "method": method,
        "host": host,
        "path": path,
    }
    return SendRequestNode(
        id=make_node_id(module_id, fields),
        evidence=(_evidence(source_id, "observed", record.input_line),),
        api_id=event.api_id,
        method=method,
        host=host,
        path=path,
    )


def _inbound_labels(
    record: EventRecord, routes: Mapping[int, RouteMatch]
) -> tuple[str | None, str, str]:
    event = record.event
    if not isinstance(event, RequestReceivedEvent):
        raise TypeError("expected a received request")
    route = routes.get(record.sequence)
    pattern = route.pattern if route is not None else _http_path(event.message.path)
    return event.api_id, event.message.method.upper(), pattern


def _outbound_labels(event: RequestSentEvent) -> tuple[str, str, str]:
    request = event.request_id or event.message
    return request.method.upper(), request.host or "", _http_path(request.path)


def _response_evidence(
    response: EventRecord, request: EventRecord, source_id: str
) -> tuple[EvidenceRef, ...]:
    return merge_evidence(
        [
            _evidence(source_id, "observed", response.input_line),
            _evidence(
                source_id,
                "response-correlation",
                request.input_line,
                response.input_line,
            ),
        ]
    )


def _send_response_evidence(
    response: EventRecord,
    request: EventRecord,
    source_id: str,
    route: RouteMatch | None,
) -> tuple[EvidenceRef, ...]:
    evidence = list(_response_evidence(response, request, source_id))
    if route is not None:
        evidence.append(
            _evidence(
                source_id,
                "route-inference",
                response.input_line,
                *(item.input_line for item in route.records),
            )
        )
    return merge_evidence(evidence)


def _context_edges(occurrences: list[Occurrence], source_id: str) -> list[PMEdge]:
    groups: dict[GroupKey, list[Occurrence]] = {}
    for occurrence in occurrences:
        if occurrence.group is not None:
            groups.setdefault(occurrence.group, []).append(occurrence)
    edges = []
    for group in groups.values():
        group.sort(key=lambda item: item.sequence)
        for index, source in enumerate(group):
            if source.node.type != "Receive":
                continue
            edges.extend(
                PMEdge(
                    source=source.node.id,
                    target=target.node.id,
                    evidence=(
                        _evidence(
                            source_id,
                            "context-order",
                            source.input_line,
                            target.input_line,
                        ),
                    ),
                )
                for target in group[index + 1 :]
                if target.node.type == "Send"
            )
    return edges


def _evidence(
    source_id: str, derivation: EvidenceDerivation, *lines: int
) -> EvidenceRef:
    return EvidenceRef(
        source_id=source_id,
        derivation=derivation,
        records=tuple(f"line:{line}" for line in sorted(set(lines))),
    )


def _http_path(path: str) -> str:
    return path or "/"


def _group_key(record: EventRecord) -> GroupKey | None:
    context_id = record.event.context.context_id
    return (record.event.pid, context_id) if context_id else None
