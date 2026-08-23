from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError


class ContextTrackModel(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="allow",
        populate_by_name=True,
    )


class ContextInfo(ContextTrackModel):
    source: str | None = None
    type: str | None = None
    context_id: str | None = None
    error: str | None = None


class RequestID(ContextTrackModel):
    method: str
    host: str
    path: str


class RequestMessage(ContextTrackModel):
    method: str = Field(alias="req.Method")
    host: str | None = Field(default=None, alias="req.URL.Host")
    path: str = Field(alias="req.URL.Path")
    raw_query: str | None = Field(default=None, alias="req.URL.RawQuery")


class RoutedMessage(ContextTrackModel):
    method: str = Field(alias="req.Method")
    path: str = Field(alias="req.URL.Path")
    pattern: str


class SentResponseMessage(ContextTrackModel):
    method: str = Field(alias="req.Method")
    path: str = Field(alias="req.URL.Path")
    status: int = Field(alias="code")


class ReceivedResponseMessage(ContextTrackModel):
    method: str | None = Field(default=None, alias="req.Method")
    path: str | None = Field(default=None, alias="req.URL.Path")
    status: int = Field(alias="resp.StatusCode")


class EventBase(ContextTrackModel):
    pid: int
    goroutine_id: int | None = None
    thread_id: int | None = None
    file: str | None = None
    line: int | None = None
    context: ContextInfo


class RequestSentEvent(EventBase):
    kind: Literal["Request sent"]
    message: RequestMessage
    request_id: RequestID | None = None
    api_id: str | None = None


class RequestReceivedEvent(EventBase):
    kind: Literal["Request received"]
    message: RequestMessage
    api_id: str | None = None
    handler: str | None = None


class RequestRoutedEvent(EventBase):
    kind: Literal["Request routed"]
    message: RoutedMessage


class ResponseSentEvent(EventBase):
    kind: Literal["Response sent"]
    message: SentResponseMessage


class ResponseReceivedEvent(EventBase):
    kind: Literal["Response received"]
    message: ReceivedResponseMessage
    api_id: str | None = None


ContextTrackEvent = Annotated[
    RequestSentEvent
    | RequestReceivedEvent
    | RequestRoutedEvent
    | ResponseSentEvent
    | ResponseReceivedEvent,
    Field(discriminator="kind"),
]

EVENT_ADAPTER = TypeAdapter(ContextTrackEvent)


@dataclass(frozen=True)
class EventRecord:
    sequence: int
    input_line: int
    event: ContextTrackEvent


@dataclass(frozen=True)
class ParseWarning:
    input_line: int
    message: str


GroupKey = tuple[int, str]
EventGroups = Mapping[GroupKey, Sequence[EventRecord]]


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


def read_events(
    path: str | Path,
) -> tuple[list[EventRecord], list[ParseWarning]]:
    records = []
    warnings = []

    with Path(path).open() as event_file:
        for input_line, line in enumerate(event_file, start=1):
            if not line.strip():
                continue

            try:
                event = EVENT_ADAPTER.validate_json(line)
            except ValidationError as error:
                warnings.append(ParseWarning(input_line, str(error)))
                continue

            records.append(EventRecord(len(records), input_line, event))

    return records, warnings
