# `src/conftamer/contexttrack/routes.py`


## Responsible for
- Matching routed records to inbound requests within context groups.
- Reconstructing full patterns across nested and prefix-stripping routers.
- Reporting unmatched or ambiguous route chains without guessing.

## Public interface
```python
# Return inbound request sequence-to-pattern matches and route warnings.
#
# Methods compare case-insensitively and paths compare exactly. A route hop
# that could continue more than one active chain is omitted as ambiguous.
def match_routes(
    groups: EventGroups,
) -> tuple[dict[int, str], list[ParseWarning]]: ...
```
