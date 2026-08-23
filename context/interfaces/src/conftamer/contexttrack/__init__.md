# `src/conftamer/contexttrack/__init__.py`


## Responsible for
- Exposing the supported ContextTrack event and conversion interface.
- Keeping callers independent of the internal module layout.

## Public interface
```python
from conftamer.contexttrack.conversion import (
    ContextTrackResult,
    parse_contexttrack,
)
from conftamer.contexttrack.events import EVENT_ADAPTER, ContextTrackEvent

__all__ = [
    "EVENT_ADAPTER",
    "ContextTrackEvent",
    "ContextTrackResult",
    "parse_contexttrack",
]
```
