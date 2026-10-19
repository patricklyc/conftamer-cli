from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable

from conftamer.appgraph.models import AppGraph, LinkedMessage
from conftamer.pmgraph.models import Message, Parameter, PMGraph

_SEPARATOR = "::"

# (concrete-path kind, pattern-or-path kind) pairs that can be stitched
# together. The concrete-path side always carries an exact path
#  the pattern-or-path side carries a route pattern where one was resolved, or an exact path otherwise.
_LINK_KIND_PAIRS: tuple[tuple[str, str], ...] = (
    ("send_request", "receive_request"),
    ("receive_response", "send_response"),
)


def _check_no_separator(value: str, description: str) -> None:
    if _SEPARATOR in value:
        raise ValueError(f"{description} {value!r} must not contain {_SEPARATOR!r}")


def _prefixed(module_id: str, node_id: str) -> str:
    return f"{module_id}{_SEPARATOR}{node_id}"


def _module_of(prefixed_id: str) -> str:
    return prefixed_id.split(_SEPARATOR, 1)[0]


def _unprefixed(prefixed_id: str) -> str:
    return prefixed_id.split(_SEPARATOR, 1)[1]


_END_ANCHOR = "{$}"


def _is_go_wildcard(segment: str) -> bool:
    return segment.startswith("{") and segment.endswith("}")


def _is_router_wildcard(segment: str) -> bool:
    return segment.startswith((":", "*"))


def _is_rest_wildcard(segment: str) -> bool:
    return segment.startswith("*") or (
        _is_go_wildcard(segment) and segment.endswith("...}")
    )


def check_pattern(pattern: str) -> None:
    """Raise ``ValueError`` if ``pattern`` uses syntax ``path_matches_pattern``
    does not support."""

    def unsupported(reason: str) -> ValueError:
        return ValueError(f"unsupported route pattern {pattern!r}: {reason}")

    if not pattern.startswith("/"):
        raise unsupported("must start with '/' (no method or host prefix)")
    segments = pattern.split("/")
    for index, segment in enumerate(segments):
        is_last = index == len(segments) - 1
        if _is_go_wildcard(segment):
            name = segment[1:-1].removesuffix("...")
            if segment != _END_ANCHOR and not name:
                raise unsupported(f"wildcard {segment!r} has no name")
        elif "{" in segment or "}" in segment:
            raise unsupported(f"wildcard {segment!r} must be a whole segment")
        elif _is_router_wildcard(segment) and len(segment) == 1:
            raise unsupported(f"wildcard {segment!r} has no name")
        if (_is_rest_wildcard(segment) or segment == _END_ANCHOR) and not is_last:
            raise unsupported(f"{segment!r} must be the last segment")
    if any(map(_is_go_wildcard, segments)) and any(map(_is_router_wildcard, segments)):
        raise unsupported("mixes net/http and httprouter wildcards")


def _segment_matches(path_segment: str, pattern_segment: str) -> bool:
    if pattern_segment == _END_ANCHOR:
        return path_segment == ""
    if _is_go_wildcard(pattern_segment) or pattern_segment.startswith(":"):
        return bool(path_segment)  # a named segment must consume something
    return path_segment == pattern_segment


def path_matches_pattern(path: str, pattern: str) -> bool:
    """Does the concrete URL ``path`` satisfy route ``pattern``?

    Supports net/http 1.22+ patterns (``{name}``, trailing ``{name...}``,
    trailing ``{$}``, and a trailing ``/`` matching the whole subtree) and
    httprouter patterns (``:name``, trailing ``*name``; a trailing ``/`` is
    literal). A trailing rest wildcard consumes the rest of the path, which
    must be nonempty. Raises ``ValueError`` for unsupported syntax, including
    a method or host prefix.
    """
    check_pattern(pattern)
    if path == pattern:
        return True

    path_segments = path.split("/")
    pattern_segments = pattern.split("/")
    is_subtree = pattern_segments[-1] == "" and not any(
        map(_is_router_wildcard, pattern_segments)
    )
    if is_subtree:
        pattern_segments = pattern_segments[:-1]

    for index, segment in enumerate(pattern_segments):
        if _is_rest_wildcard(segment):
            remainder = path_segments[index:]
            is_empty_remainder = remainder == [] or remainder == [""]
            return not is_empty_remainder
        if index >= len(path_segments):
            return False
        if not _segment_matches(path_segments[index], segment):
            return False

    if is_subtree:
        return len(path_segments) > len(pattern_segments)
    return len(path_segments) == len(pattern_segments)


def _messages_match(concrete: Message, pattern_side: Message) -> bool:
    if not concrete.api_id or not pattern_side.api_id:
        return False
    if concrete.api_id != pattern_side.api_id:
        return False
    if concrete.method != pattern_side.method:
        return False
    if concrete.status_code != pattern_side.status_code:
        return False

    # Guaranteed by Message's own validators: concrete-path kinds always
    # have a path, and pattern-or-path kinds always have exactly one of
    # path/pattern.
    assert concrete.path is not None
    if pattern_side.pattern is not None:
        return path_matches_pattern(concrete.path, pattern_side.pattern)
    # A fallback path is literal evidence, not a route expression: wildcard
    # syntax in it (":id", "{id}", "*rest") must not match other paths.
    return concrete.path == pattern_side.path


def _check_unique_module_ids(graphs: list[PMGraph]) -> None:
    seen: set[str] = set()
    for graph in graphs:
        _check_no_separator(graph.module_id, "module_id")
        # A trailing ":" would let the separator start inside the module ID
        # ("a:" + "::" + "cfg" == "a" + "::" + ":cfg"), making prefixed IDs
        # collide and split back to the wrong module.
        if graph.module_id.endswith(":"):
            raise ValueError(f"module_id {graph.module_id!r} must not end with ':'")
        if graph.module_id in seen:
            raise ValueError(f"duplicate module_id {graph.module_id!r}")
        seen.add(graph.module_id)
        for node_id in graph.nodes:
            _check_no_separator(node_id, f"node ID in module {graph.module_id!r}")


def _forward_reachable(seeds: Iterable[str], edges: set[tuple[str, str]]) -> set[str]:
    successors: dict[str, set[str]] = defaultdict(set)
    for source, target in edges:
        successors[source].add(target)

    reached = set(seeds)
    stack = list(reached)
    while stack:
        node = stack.pop()
        for successor in successors[node]:
            if successor not in reached:
                reached.add(successor)
                stack.append(successor)
    return reached


def stitch(graphs: Iterable[PMGraph]) -> AppGraph:
    """Combine per-module PMGraphs into one AppGraph (CompTool).

    Raises ``ValueError`` if two graphs share a ``module_id``, if any
    ``module_id``/node ID contains ``"::"`` (used internally to keep IDs
    globally unique while stitching), if a ``module_id`` ends with ``":"``, or
    if any route pattern uses unsupported syntax (see ``check_pattern``).
    """
    graphs = list(graphs)
    _check_unique_module_ids(graphs)

    prefixed_nodes: dict[str, Parameter | Message] = {}
    prefixed_edges: set[tuple[str, str]] = set()
    for graph in graphs:
        for node_id, node in graph.nodes.items():
            prefixed_nodes[_prefixed(graph.module_id, node_id)] = node
        for source, target in graph.edges:
            prefixed_edges.add(
                (_prefixed(graph.module_id, source), _prefixed(graph.module_id, target))
            )

    for node in prefixed_nodes.values():
        if isinstance(node, Message) and node.pattern is not None:
            check_pattern(node.pattern)

    # prefixed node ID -> the link ID(s) it was merged into. A node can
    # participate in more than one link (e.g. one route pattern matching
    # several distinct senders), in which case every edge touching it is
    # fanned out across all of its links.
    replaces: dict[str, list[str]] = defaultdict(list)
    links: dict[str, LinkedMessage] = {}
    link_counter = 0

    for concrete_kind, pattern_kind in _LINK_KIND_PAIRS:
        concrete_side = sorted(
            (pid, node)
            for pid, node in prefixed_nodes.items()
            if isinstance(node, Message) and node.kind == concrete_kind
        )
        pattern_side = sorted(
            (pid, node)
            for pid, node in prefixed_nodes.items()
            if isinstance(node, Message) and node.kind == pattern_kind
        )

        for concrete_pid, concrete_node in concrete_side:
            for pattern_pid, pattern_node in pattern_side:
                if _module_of(concrete_pid) == _module_of(pattern_pid):
                    continue
                if not _messages_match(concrete_node, pattern_node):
                    continue

                is_request = concrete_kind == "send_request"
                sender_pid, receiver_pid = (
                    (concrete_pid, pattern_pid)
                    if is_request
                    else (pattern_pid, concrete_pid)
                )

                link_id = f"link{link_counter}"
                link_counter += 1
                assert concrete_node.api_id is not None
                pattern = pattern_node.pattern
                if pattern is None:
                    assert pattern_node.path is not None
                    pattern = pattern_node.path

                links[link_id] = LinkedMessage(
                    api_id=concrete_node.api_id,
                    method=concrete_node.method,
                    pattern=pattern,
                    status_code=concrete_node.status_code,
                    sender_module=_module_of(sender_pid),
                    sender_node=_unprefixed(sender_pid),
                    receiver_module=_module_of(receiver_pid),
                    receiver_node=_unprefixed(receiver_pid),
                )
                replaces[concrete_pid].append(link_id)
                replaces[pattern_pid].append(link_id)

    # Pass 1: keep Parameter nodes unconditionally, plus every link.
    # Any Message node that never matched anything (not in `replaces`)
    # is dropped here, simply by not being copied into `final_nodes`.
    final_nodes: dict[str, Parameter | LinkedMessage] = {
        pid: node for pid, node in prefixed_nodes.items() if isinstance(node, Parameter)
    }
    final_nodes.update(links)

    final_edges: set[tuple[str, str]] = set()
    for source, target in prefixed_edges:
        sources = replaces.get(source) or ([source] if source in final_nodes else [])
        targets = replaces.get(target) or ([target] if target in final_nodes else [])
        for new_source in sources:
            for new_target in targets:
                if new_source != new_target:
                    final_edges.add((new_source, new_target))

    # Pass 2: drop anything not forward-reachable from some Parameter.
    parameter_ids = {
        pid for pid, node in final_nodes.items() if isinstance(node, Parameter)
    }
    reachable = _forward_reachable(parameter_ids, final_edges)
    final_nodes = {pid: node for pid, node in final_nodes.items() if pid in reachable}
    final_edges = {
        (source, target)
        for source, target in final_edges
        if source in final_nodes and target in final_nodes
    }

    return AppGraph(nodes=final_nodes, edges=final_edges)
