# `src/conftamer/contexttrack/conversion.py`


## Responsible for
- Orchestrating ContextTrack reading, grouping, route matching, response
  matching, node conversion, and PMGraph assembly.
- Converting supported events into normalized PMGraph message nodes.
- Connecting each converted Receive occurrence to every later converted Send
  occurrence in the same `(pid, context_id)` group.
- Returning usable graph output together with input-line-ordered warnings for
  malformed, ambiguous, unmatched, or unlabelable data.

## Public interface
```python
@dataclass(frozen=True)
class ContextTrackResult:
    graph: PMGraph
    warnings: tuple[ParseWarning, ...]


# Convert one ContextTrack JSONL file into a per-module PMGraph.
def parse_contexttrack(
    path: str | Path,
    *,
    module_id: str,
) -> ContextTrackResult: ...
```

The converter normalizes an empty HTTP path to `/` at the PMGraph boundary and
omits outbound requests that have no host rather than inventing a label.
