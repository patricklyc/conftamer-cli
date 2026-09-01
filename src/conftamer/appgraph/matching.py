import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Literal

from conftamer.pmgraph import (
    BehaviorNode,
    ParameterNode,
    PMNode,
    ReceiveRequestNode,
    ReceiveResponseNode,
    SendRequestNode,
    SendResponseNode,
)

NodeKey = tuple[str, str]
MatchStatus = Literal[
    "matched",
    "no_candidate",
    "ambiguous",
    "unsupported_pattern",
    "missing_request_match",
    "not_applicable",
]
Adjacency = dict[NodeKey, set[NodeKey]]


@dataclass(frozen=True)
class MatchPlan:
    members: tuple[NodeKey, ...]
    status: MatchStatus
    basis: Literal["unique-http-labels"] | None = None
    candidates: tuple[NodeKey, ...] = ()


def plan_matches(nodes: Mapping[NodeKey, PMNode]) -> tuple[MatchPlan, ...]:
    request_adjacency = _request_adjacency(nodes)
    request_plans, accepted_requests = _partition(
        request_adjacency,
        lambda key: _unmatched_request_status(key, nodes),
    )
    response_adjacency, evaluable = _response_adjacency(nodes, accepted_requests)
    response_plans, _ = _partition(
        response_adjacency,
        lambda key: "no_candidate" if key in evaluable else "missing_request_match",
    )

    plans = [*request_plans, *response_plans]
    planned = {key for plan in plans for key in plan.members}
    for key, node in nodes.items():
        if key in planned:
            continue
        status: MatchStatus = (
            "not_applicable"
            if isinstance(node, (ParameterNode, BehaviorNode))
            else "missing_request_match"
        )
        plans.append(MatchPlan((key,), status))
    return tuple(sorted(plans, key=lambda item: item.members))


def _request_adjacency(nodes: Mapping[NodeKey, PMNode]) -> Adjacency:
    sends = {
        key: node for key, node in nodes.items() if isinstance(node, SendRequestNode)
    }
    receives = {
        key: node for key, node in nodes.items() if isinstance(node, ReceiveRequestNode)
    }
    adjacency: Adjacency = {key: set() for key in sends | receives}
    for send_key, send in sends.items():
        for receive_key, receive in receives.items():
            matches = (
                send.method == receive.method
                and _path_matches(send.path, receive.pattern)[0]
            )
            if send_key[0] != receive_key[0] and matches:
                adjacency[send_key].add(receive_key)
                adjacency[receive_key].add(send_key)
    return adjacency


def _unmatched_request_status(
    key: NodeKey, nodes: Mapping[NodeKey, PMNode]
) -> MatchStatus:
    node = nodes[key]
    if isinstance(node, ReceiveRequestNode) and not _path_matches("", node.pattern)[1]:
        return "unsupported_pattern"
    return "no_candidate"


def _response_adjacency(
    nodes: Mapping[NodeKey, PMNode],
    accepted_requests: set[tuple[NodeKey, ...]],
) -> tuple[Adjacency, set[NodeKey]]:
    responses = {
        key: node
        for key, node in nodes.items()
        if isinstance(node, (ReceiveResponseNode, SendResponseNode))
    }
    adjacency: Adjacency = {key: set() for key in responses}
    evaluable: set[NodeKey] = set()
    for pair in accepted_requests:
        send_key = next(key for key in pair if isinstance(nodes[key], SendRequestNode))
        receive_key = next(
            key for key in pair if isinstance(nodes[key], ReceiveRequestNode)
        )
        send = nodes[send_key]
        receive = nodes[receive_key]
        assert isinstance(send, SendRequestNode)
        assert isinstance(receive, ReceiveRequestNode)
        clients, servers = _eligible_responses(
            responses, send_key, receive_key, send, receive
        )
        evaluable.update(clients | servers)
        for client_key, client in clients.items():
            for server_key, server in servers.items():
                if client.status == server.status:
                    adjacency[client_key].add(server_key)
                    adjacency[server_key].add(client_key)
    return adjacency, evaluable


def _eligible_responses(
    responses: Mapping[NodeKey, ReceiveResponseNode | SendResponseNode],
    send_key: NodeKey,
    receive_key: NodeKey,
    send: SendRequestNode,
    receive: ReceiveRequestNode,
) -> tuple[dict[NodeKey, ReceiveResponseNode], dict[NodeKey, SendResponseNode]]:
    clients = {
        key: node
        for key, node in responses.items()
        if isinstance(node, ReceiveResponseNode)
        and key[0] == send_key[0]
        and (node.method, node.host, node.path) == (send.method, send.host, send.path)
    }
    servers = {
        key: node
        for key, node in responses.items()
        if isinstance(node, SendResponseNode)
        and key[0] == receive_key[0]
        and (node.method, node.pattern) == (receive.method, receive.pattern)
    }
    return clients, servers


def _partition(
    adjacency: Adjacency,
    empty_status: Callable[[NodeKey], MatchStatus],
) -> tuple[list[MatchPlan], set[tuple[NodeKey, ...]]]:
    accepted = {
        tuple(sorted((key, next(iter(candidates)))))
        for key, candidates in adjacency.items()
        if len(candidates) == 1 and len(adjacency[next(iter(candidates))]) == 1
    }
    matched = {key for pair in accepted for key in pair}
    plans = [MatchPlan(pair, "matched", "unique-http-labels") for pair in accepted]
    for key, values in adjacency.items():
        if key in matched:
            continue
        candidates = tuple(sorted(values))
        status: MatchStatus = "ambiguous" if candidates else empty_status(key)
        plans.append(MatchPlan((key,), status, candidates=candidates))
    return plans, accepted


def _path_matches(path: str, pattern: str) -> tuple[bool, bool]:
    if path == pattern:
        return True, True
    expression = _pattern_regex(pattern)
    return bool(expression and re.fullmatch(expression, path)), expression is not None


def _pattern_regex(pattern: str) -> str | None:
    if not pattern.startswith("/") or " " in pattern:
        return None
    subtree = pattern.endswith("/")
    parts = pattern[1:].split("/")
    if subtree:
        parts.pop()

    grammar: set[str] = set()
    expressions = []
    for index, part in enumerate(parts):
        go_wildcard = re.fullmatch(r"\{([^{}./$:* ]+)\}", part)
        if go_wildcard and _valid_router_name(go_wildcard.group(1)):
            grammar.add("go")
            expressions.append(r"[^/]+")
        elif part.startswith(":") and _valid_router_name(part[1:]):
            grammar.add("router")
            expressions.append(r"[^/]+")
        elif (
            part.startswith("*")
            and _valid_router_name(part[1:])
            and index == len(parts) - 1
        ):
            grammar.add("router")
            expressions.append(r".+")
        elif any(character in part for character in "{}") or part.startswith(
            (":", "*")
        ):
            return None
        else:
            expressions.append(re.escape(part))
    if len(grammar) > 1:
        return None

    expression = "/" + "/".join(expressions)
    if subtree and not expressions:
        return r"/.*"
    return expression + (r"/.*" if subtree else "")


def _valid_router_name(name: str) -> bool:
    return bool(name) and not any(
        character.isspace() or character in "{}:*" for character in name
    )
