# `src/conftamer/contexttrack/responses.py`


## Responsible for
- Correlating sent responses with inbound requests and received responses with
  outbound requests.
- Consuming matched requests so one request is not assigned repeatedly.
- Using unique goroutine evidence to disambiguate candidates and to support the
  method-only fallback used by changed-path response hooks.
- Suppressing compatible duplicate client hooks only after a wire hook was
  matched successfully.
- Reporting missing and ambiguous matches when usable endpoint data exists.

## Public interface
```python
@dataclass(frozen=True)
class ResponseMatches:
    sent: dict[int, EventRecord]
    received: dict[int, EventRecord]


# Return response sequence-to-request matches and correlation warnings.
def match_responses(
    groups: EventGroups,
) -> tuple[ResponseMatches, list[ParseWarning]]: ...
```

Response hooks without method or path are not matched independently and do not
produce a missing-match warning.
