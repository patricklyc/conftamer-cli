import hashlib
import json
from collections.abc import Iterable, Mapping
from typing import Annotated, Literal

from pydantic import Field, model_validator

from conftamer.appgraph.matching import MatchStatus, NodeKey, plan_matches
from conftamer.diagnostics import (
    CanonicalModel,
    EvidenceRef,
    NodeID,
    NonEmptyString,
    SourceArtifact,
)
from conftamer.pmgraph import (
    BehaviorNode,
    ParameterNode,
    PMEdge,
    PMNode,
    ReceiveRequestNode,
    ReceiveResponseNode,
    SendRequestNode,
    SendResponseNode,
    make_pmgraph,
)

AppNodeID = Annotated[str, Field(pattern=r"^a:[0-9a-f]{64}$")]


class QualifiedNodeRef(CanonicalModel):
    module_id: NonEmptyString
    node_id: NodeID


class MatchInfo(CanonicalModel):
    status: MatchStatus
    basis: Literal["unique-http-labels"] | None
    candidates: tuple[QualifiedNodeRef, ...]

    @model_validator(mode="after")
    def validate_combination(self) -> "MatchInfo":
        candidate_keys = tuple(
            (candidate.module_id, candidate.node_id) for candidate in self.candidates
        )
        valid = candidate_keys == tuple(sorted(set(candidate_keys)))
        if self.status == "matched":
            valid &= self.basis == "unique-http-labels" and not self.candidates
        elif self.status == "ambiguous":
            valid &= self.basis is None and bool(self.candidates)
        else:
            valid &= self.basis is None and not self.candidates
        if not valid:
            raise ValueError("invalid match status, basis, and candidates combination")
        return self


class QualifiedPMNode(CanonicalModel):
    module_id: NonEmptyString
    node: PMNode


class AppNode(CanonicalModel):
    id: AppNodeID
    members: Annotated[tuple[QualifiedPMNode, ...], Field(min_length=1)]
    match: MatchInfo

    @model_validator(mode="after")
    def validate_member_shape(self) -> "AppNode":
        if self.match.status == "matched":
            if len(self.members) != 2:
                raise ValueError("matched AppNode requires exactly two members")
            first, second = self.members
            if not _complementary(first, second):
                raise ValueError("matched AppNode members must be complementary")
            return self
        if len(self.members) != 1:
            raise ValueError("unmatched AppNode requires exactly one member")
        node = self.members[0].node
        special = isinstance(node, (ParameterNode, BehaviorNode))
        if (self.match.status == "not_applicable") != special:
            raise ValueError(
                "not_applicable is required only for Parameter or Behavior"
            )
        if self.match.status == "unsupported_pattern" and not isinstance(
            node, ReceiveRequestNode
        ):
            raise ValueError("unsupported_pattern requires a Receive Request")
        if self.match.status == "missing_request_match" and not isinstance(
            node, (ReceiveResponseNode, SendResponseNode)
        ):
            raise ValueError("missing_request_match requires a Response")
        return self


class QualifiedEdgeRef(CanonicalModel):
    module_id: NonEmptyString
    source: NodeID
    target: NodeID
    evidence: Annotated[tuple[EvidenceRef, ...], Field(min_length=1)]


class AppEdge(CanonicalModel):
    source: AppNodeID
    target: AppNodeID
    origins: Annotated[tuple[QualifiedEdgeRef, ...], Field(min_length=1)]


class AppGraph(CanonicalModel):
    format: Literal["conftamer.appgraph"]
    version: Literal[1]
    module_ids: Annotated[tuple[NonEmptyString, ...], Field(min_length=2)]
    sources: Annotated[tuple[SourceArtifact, ...], Field(min_length=1)]
    nodes: tuple[AppNode, ...]
    edges: tuple[AppEdge, ...]

    @model_validator(mode="after")
    def validate_document(self) -> "AppGraph":
        self._validate_collection_order()
        qualified, containers = self._validate_nodes()
        module_edges = self._validate_edges(containers)
        self._validate_embedded_pmgraphs(qualified, module_edges)
        return self

    def _validate_collection_order(self) -> None:
        if self.module_ids != tuple(sorted(set(self.module_ids))):
            raise ValueError("module IDs must be unique and in canonical order")
        source_keys = tuple((source.kind, source.id) for source in self.sources)
        unique_source_ids = {source.id for source in self.sources}
        if source_keys != tuple(sorted(source_keys)) or len(unique_source_ids) != len(
            self.sources
        ):
            raise ValueError("sources must be unique and in canonical order")
        node_ids = tuple(node.id for node in self.nodes)
        if node_ids != tuple(sorted(set(node_ids))):
            raise ValueError("nodes must have unique IDs and be in canonical order")
        endpoints = tuple((edge.source, edge.target) for edge in self.edges)
        if endpoints != tuple(sorted(set(endpoints))):
            raise ValueError("AppEdge endpoints must be unique and in canonical order")

    def _validate_nodes(
        self,
    ) -> tuple[dict[NodeKey, PMNode], dict[NodeKey, str]]:
        qualified: dict[NodeKey, PMNode] = {}
        containers: dict[NodeKey, str] = {}
        actual_matches = {}
        for app_node in self.nodes:
            member_keys = tuple(_member_key(member) for member in app_node.members)
            if member_keys != tuple(sorted(member_keys)):
                raise ValueError("members must be in canonical order")
            if app_node.id != _make_app_node_id(app_node.members):
                raise ValueError("AppNode ID does not match its members")
            if any(module not in self.module_ids for module, _ in member_keys):
                raise ValueError("member module is not in module_ids")
            for key, member in zip(member_keys, app_node.members, strict=True):
                if key in qualified:
                    raise ValueError("qualified member occurs in more than one AppNode")
                qualified[key] = member.node
                containers[key] = app_node.id
            actual_matches[member_keys] = _match_claim(app_node.match)

        expected_matches = {
            plan.members: (plan.status, plan.basis, plan.candidates)
            for plan in plan_matches(qualified)
        }
        if actual_matches != expected_matches:
            raise ValueError("stored match state does not match recomputed candidates")
        return qualified, containers

    def _validate_edges(
        self, containers: Mapping[NodeKey, str]
    ) -> dict[str, list[PMEdge]]:
        app_node_ids = {node.id for node in self.nodes}
        origin_endpoints: set[tuple[str, str, str]] = set()
        module_edges: dict[str, list[PMEdge]] = {}
        for edge in self.edges:
            if (
                edge.source == edge.target
                or not {
                    edge.source,
                    edge.target,
                }
                <= app_node_ids
            ):
                raise ValueError("AppEdge endpoints must exist and not be self-edges")
            keys = tuple(_origin_key(origin) for origin in edge.origins)
            endpoints = {key[:3] for key in keys}
            if (
                keys != tuple(sorted(keys))
                or len(endpoints) != len(keys)
                or origin_endpoints & endpoints
            ):
                raise ValueError("origins must be unique and in canonical order")
            origin_endpoints.update(endpoints)
            for origin in edge.origins:
                source = containers.get((origin.module_id, origin.source))
                target = containers.get((origin.module_id, origin.target))
                if (source, target) != (edge.source, edge.target):
                    raise ValueError("origin does not remap to its AppEdge")
                module_edges.setdefault(origin.module_id, []).append(
                    PMEdge(
                        source=origin.source,
                        target=origin.target,
                        evidence=origin.evidence,
                    )
                )
        return module_edges

    def _validate_embedded_pmgraphs(
        self,
        qualified: Mapping[NodeKey, PMNode],
        module_edges: Mapping[str, list[PMEdge]],
    ) -> None:
        for module_id in self.module_ids:
            nodes = (
                node for (module, _), node in qualified.items() if module == module_id
            )
            make_pmgraph(
                module_id=module_id,
                sources=self.sources,
                nodes=nodes,
                edges=module_edges.get(module_id, ()),
            )


def _complementary(first: QualifiedPMNode, second: QualifiedPMNode) -> bool:
    message_types = (
        ReceiveRequestNode,
        ReceiveResponseNode,
        SendRequestNode,
        SendResponseNode,
    )
    if not isinstance(first.node, message_types) or not isinstance(
        second.node, message_types
    ):
        return False
    return (
        first.module_id != second.module_id
        and first.node.type != second.node.type
        and first.node.message == second.node.message
    )


def _member_key(member: QualifiedPMNode) -> NodeKey:
    return member.module_id, member.node.id


def _match_claim(match: MatchInfo) -> tuple:
    candidates = tuple(
        (candidate.module_id, candidate.node_id) for candidate in match.candidates
    )
    if candidates != tuple(sorted(set(candidates))):
        raise ValueError("candidates must be unique and in canonical order")
    return match.status, match.basis, candidates


def _origin_key(origin: QualifiedEdgeRef) -> tuple:
    evidence = tuple(
        (item.source_id, item.derivation, item.records) for item in origin.evidence
    )
    return origin.module_id, origin.source, origin.target, evidence


def _make_app_node_id(members: Iterable[QualifiedPMNode]) -> str:
    values = sorted(
        (
            {"module_id": member.module_id, "node_id": member.node.id}
            for member in members
        ),
        key=lambda item: (item["module_id"], item["node_id"]),
    )
    encoded = json.dumps(
        {"members": values}, sort_keys=True, separators=(",", ":")
    ).encode()
    return f"a:{hashlib.sha256(encoded).hexdigest()}"
