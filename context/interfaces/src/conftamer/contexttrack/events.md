# `src/conftamer/contexttrack/events.py`


## Responsible for
- Defining permissive Pydantic models for supported ContextTrack messages and
  events while preserving unknown upstream fields.
- Validating discriminated ContextTrack event kinds.
- Tracking event sequence and original JSONL input line numbers.
- Reading JSONL while skipping blank lines and continuing past malformed lines
  with warnings.
- Grouping records by `(pid, context_id)` and separating records without a
  context ID.

## Public interface
```python
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
) -> tuple[dict[GroupKey, list[EventRecord]], list[EventRecord]]: ...


def read_events(
    path: str | Path,
) -> tuple[list[EventRecord], list[ParseWarning]]: ...
```
