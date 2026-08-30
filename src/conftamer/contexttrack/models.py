from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, TypeAdapter


def _parse_status(value: object) -> int:
    if isinstance(value, bool):
        raise ValueError(  # noqa: TRY004 - Pydantic converts ValueError to validation
            "status must be a decimal string or integer"
        )
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdecimal() and value.isascii():
        return int(value)
    raise ValueError("status must be a decimal string or integer")


RawStatus = Annotated[int, BeforeValidator(_parse_status)]


class ContextTrackModel(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="allow",
        strict=True,
        validate_by_name=True,
        validate_by_alias=True,
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


class RouteMessage(ContextTrackModel):
    method: str = Field(alias="req.Method")
    path: str = Field(alias="req.URL.Path")
    pattern: str


class SentResponseMessage(ContextTrackModel):
    method: str = Field(alias="req.Method")
    path: str = Field(alias="req.URL.Path")
    status: RawStatus = Field(alias="code")


class ReceivedResponseMessage(ContextTrackModel):
    method: str | None = Field(default=None, alias="req.Method")
    path: str | None = Field(default=None, alias="req.URL.Path")
    status: RawStatus = Field(alias="resp.StatusCode")


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


class RouteEvent(EventBase):
    kind: Literal["Request routed"]
    message: RouteMessage


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
    | RouteEvent
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


GroupKey = tuple[int, str]
EventGroups = Mapping[GroupKey, Sequence[EventRecord]]


def group_events(
    records: Iterable[EventRecord],
) -> tuple[dict[GroupKey, list[EventRecord]], list[EventRecord]]:
    groups: dict[GroupKey, list[EventRecord]] = {}
    ungrouped = []
    for record in records:
        context_id = record.event.context.context_id
        if not context_id:
            ungrouped.append(record)
            continue
        groups.setdefault((record.event.pid, context_id), []).append(record)
    return groups, ungrouped
