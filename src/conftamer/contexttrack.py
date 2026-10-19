"""Import one ContextTrack capture as a message-only per-module influence graph."""

import json
import warnings
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from conftamer.pmgraph.models import Message, PMGraph

_KINDS = {
    "Request sent": "send_request",
    "Request received": "receive_request",
    "Response sent": "send_response",
    "Response received": "receive_response",
}
_REQUEST_KIND_BY_EVENT = {
    "Request routed": "Request received",
    "Response sent": "Request received",
    "Response received": "Request sent",
}


@dataclass
class _Event:
    kind: str
    context_key: tuple[int, str] | None
    method: str | None
    path: str | None
    host: str | None
    api_id: str | None
    location: str
    pattern: str | None = None
    status_code: int | None = None
    matched_request: _Event | None = None
    routing_ambiguous: bool = False

    def warn(self, reason: str) -> None:
        warnings.warn(f"{self.location}: {reason}", stacklevel=2)


def _object(record: dict, name: str) -> dict:
    value = record.get(name)

    if value is None:
        return {}

    if not isinstance(value, dict):
        raise TypeError(f"{name} must be an object")

    return value


def _string(record: dict, name: str, *, nullable: bool = False) -> str | None:
    value = record.get(name)

    if value is None and (name not in record or nullable):
        return None

    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")

    return value


def _normalized_path(path: str | None) -> str | None:
    return "/" if path == "" else path


def _reject_constant(value: str) -> None:
    raise ValueError(f"invalid JSON constant {value}")


def _read_events(path: Path) -> Iterator[_Event]:
    with path.open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, 1):
            if not line.strip():
                continue

            location = f"{path}:{line_number}"

            try:
                record = json.loads(line, parse_constant=_reject_constant)

                if not isinstance(record, dict):
                    raise TypeError("record must be an object")

                kind = record.get("kind")
                pid = record.get("pid")
                message = record.get("message")

                if not isinstance(kind, str):
                    raise TypeError("kind must be a string")
                if type(pid) is not int:
                    raise TypeError("pid must be an integer, not a boolean")
                if not isinstance(message, dict):
                    raise TypeError("message must be an object")

                context_id = _string(
                    _object(record, "context"), "context_id", nullable=True
                )
                request_id = _object(record, "request_id")
                api_id = _string(record, "api_id", nullable=True)

                if kind not in _KINDS and kind != "Request routed":
                    warnings.warn(
                        f"{location}: unknown event kind {kind!r}", stacklevel=2
                    )
                    continue

                if kind == "Request sent":
                    method = _string(request_id, "method")
                    concrete_path = _string(request_id, "path")
                    host = _string(request_id, "host")
                else:
                    method = _string(message, "req.Method")
                    concrete_path = _string(message, "req.URL.Path")
                    host = None

                pattern = (
                    _string(message, "pattern") if kind == "Request routed" else None
                )

                status_key = "code" if kind == "Response sent" else "resp.StatusCode"
                status = None

                if kind.startswith("Response"):
                    status = _string(message, status_key)

                if status is not None and not status.isdecimal():
                    raise ValueError(f"{status_key} must be a decimal status string")

                yield _Event(
                    kind=kind,
                    context_key=(pid, context_id) if context_id else None,
                    method=method,
                    path=_normalized_path(concrete_path),
                    host=host,
                    api_id=api_id,
                    location=location,
                    pattern=pattern,
                    status_code=int(status) if status is not None else None,
                )
            except TypeError as error:
                raise TypeError(f"{location}: {error}") from error
            except ValueError as error:
                raise ValueError(f"{location}: {error}") from error


def _correlate(events: Iterator[_Event]) -> list[_Event]:
    """Attach routes and responses to preceding request occurrences.

    Requests are retained by reference so later routes can update their labels
    before occurrences are normalized and interned.
    """
    requests: dict[tuple[int, str], list[_Event]] = {}
    occurrences = []

    for event in events:
        if event.kind in ("Request sent", "Request received"):
            if event.context_key is not None:
                requests.setdefault(event.context_key, []).append(event)

            occurrences.append(event)
            continue

        routed = event.kind == "Request routed"
        missing_match_key = (
            event.context_key is None or not event.method or event.path is None
        )
        missing_metadata = not event.pattern if routed else event.status_code is None

        if missing_match_key or missing_metadata:
            event.warn(
                "incomplete association: context, method, path or pattern/status missing"
            )
            continue

        request_kind = _REQUEST_KIND_BY_EVENT[event.kind]
        candidates = [
            request
            for request in requests.get(event.context_key, [])
            if request.kind == request_kind and request.method == event.method
        ]
        matches = [request for request in candidates if request.path == event.path]

        if len(matches) != 1:
            if routed:
                # Invalidate possible routing chains, without inventing a rewritten-path match.
                for request in matches or candidates:
                    request.pattern = None
                    request.routing_ambiguous = True

            event.warn(
                "ambiguous routing or path rewriting; using concrete path"
                if routed
                else f"expected one preceding request, found {len(matches)}"
            )
            continue

        request = matches[0]

        if routed:
            if not request.routing_ambiguous:
                request.pattern = event.pattern
            continue

        if (
            event.api_id is not None
            and request.api_id is not None
            and event.api_id != request.api_id
        ):
            event.warn("conflicting response and request API IDs")
            continue

        event.api_id = request.api_id if event.api_id is None else event.api_id
        event.matched_request = request
        occurrences.append(event)

    return occurrences


def load_contexttrack(path: str | Path, *, module_id: str) -> PMGraph:
    """Load one UTF-8 JSONL capture; module identity is supplied by the caller."""
    if not isinstance(module_id, str):
        raise TypeError("module_id must be a string")
    if not module_id:
        raise ValueError("module_id must be nonempty")

    nodes: dict[str, Message] = {}
    edges: set[tuple[str, str]] = set()
    interned: dict[tuple, str] = {}
    prior_receives: dict[tuple[int, str], set[str]] = {}

    # Routes may arrive after receipt; resolve all labels before interning occurrences.
    for event in _correlate(_read_events(Path(path))):
        request = event.matched_request or event

        if (
            not request.method
            or request.path is None
            or (request.kind == "Request sent" and not request.host)
        ):
            event.warn("incomplete request label: method, path or client host missing")
            continue

        message = Message.model_validate(
            {
                "kind": _KINDS[event.kind],
                "api_id": event.api_id,
                "method": request.method,
                "host": request.host,
                "path": None if request.pattern else request.path,
                "pattern": request.pattern,
                "status_code": event.status_code,
            }
        )

        identity = tuple(message.model_dump().items())
        node_id = interned.setdefault(identity, f"n{len(interned)}")
        nodes[node_id] = message

        if event.context_key is not None:
            received = prior_receives.setdefault(event.context_key, set())

            if message.kind in ("receive_request", "receive_response"):
                received.add(node_id)
            else:
                edges.update((source_id, node_id) for source_id in received)

    return PMGraph(module_id=module_id, nodes=nodes, edges=edges)
