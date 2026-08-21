from collections.abc import Iterable

from conftamer.contexttrack.events import EventRecord

GroupKey = tuple[int, str]


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
