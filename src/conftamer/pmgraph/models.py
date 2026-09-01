import hashlib
import json
from collections.abc import Iterable, Mapping
from typing import Annotated, Literal

from pydantic import Discriminator, Field, Tag, field_validator, model_validator

from conftamer.diagnostics import (
    CanonicalModel,
    EvidenceRef,
    NodeID,
    NonEmptyString,
    SourceArtifact,
    merge_evidence,
)

StatusCode = Annotated[int, Field(ge=100, le=999)]


class PMNodeBase(CanonicalModel):
    id: NodeID
    evidence: Annotated[tuple[EvidenceRef, ...], Field(min_length=1)]

    @field_validator("evidence")
    @classmethod
    def validate_evidence_order(
        cls, evidence: tuple[EvidenceRef, ...]
    ) -> tuple[EvidenceRef, ...]:
        if evidence != merge_evidence(evidence):
            raise ValueError("evidence must be merged and in canonical order")
        return evidence


class MessageNode(PMNodeBase):
    api_id: NonEmptyString | None
    method: NonEmptyString

    @field_validator("method")
    @classmethod
    def uppercase_method(cls, method: str) -> str:
        return method.upper()


class ParameterNode(PMNodeBase):
    type: Literal["Parameter"] = "Parameter"
    name: NonEmptyString


class BehaviorNode(PMNodeBase):
    type: Literal["Behavior"] = "Behavior"
    name: NonEmptyString


class ReceiveRequestNode(MessageNode):
    type: Literal["Receive"] = "Receive"
    message: Literal["Request"] = "Request"
    pattern: NonEmptyString


class SendRequestNode(MessageNode):
    type: Literal["Send"] = "Send"
    message: Literal["Request"] = "Request"
    host: NonEmptyString
    path: NonEmptyString

    @field_validator("path", mode="before")
    @classmethod
    def normalize_path(cls, path: object) -> object:
        return "/" if path == "" else path


class ReceiveResponseNode(MessageNode):
    type: Literal["Receive"] = "Receive"
    message: Literal["Response"] = "Response"
    host: NonEmptyString
    path: NonEmptyString
    status: StatusCode

    @field_validator("path", mode="before")
    @classmethod
    def normalize_path(cls, path: object) -> object:
        return "/" if path == "" else path


class SendResponseNode(MessageNode):
    type: Literal["Send"] = "Send"
    message: Literal["Response"] = "Response"
    pattern: NonEmptyString
    status: StatusCode


def _node_discriminator(value: object) -> str | None:
    if isinstance(value, Mapping):
        node_type = value.get("type")
        message = value.get("message")
    else:
        node_type = getattr(value, "type", None)
        message = getattr(value, "message", None)
    if node_type in {"Parameter", "Behavior"}:
        return str(node_type)
    if node_type in {"Receive", "Send"} and message in {"Request", "Response"}:
        return f"{node_type}.{message}"
    return None


PMNode = Annotated[
    Annotated[ParameterNode, Tag("Parameter")]
    | Annotated[BehaviorNode, Tag("Behavior")]
    | Annotated[ReceiveRequestNode, Tag("Receive.Request")]
    | Annotated[SendRequestNode, Tag("Send.Request")]
    | Annotated[ReceiveResponseNode, Tag("Receive.Response")]
    | Annotated[SendResponseNode, Tag("Send.Response")],
    Discriminator(_node_discriminator),
]


class PMEdge(CanonicalModel):
    source: NodeID
    target: NodeID
    evidence: Annotated[tuple[EvidenceRef, ...], Field(min_length=1)]

    @field_validator("evidence")
    @classmethod
    def validate_evidence_order(
        cls, evidence: tuple[EvidenceRef, ...]
    ) -> tuple[EvidenceRef, ...]:
        if evidence != merge_evidence(evidence):
            raise ValueError("evidence must be merged and in canonical order")
        return evidence


class PMGraph(CanonicalModel):
    format: Literal["conftamer.pmgraph"]
    version: Literal[2]
    module_id: NonEmptyString
    sources: Annotated[tuple[SourceArtifact, ...], Field(min_length=1)]
    nodes: tuple[PMNode, ...]
    edges: tuple[PMEdge, ...]

    @model_validator(mode="after")
    def validate_document(self) -> "PMGraph":
        self._validate_sources()
        nodes_by_id = self._validate_nodes()
        self._validate_edges(nodes_by_id)
        self._validate_evidence_sources()
        return self

    def _validate_sources(self) -> None:
        source_ids = [source.id for source in self.sources]
        if len(set(source_ids)) != len(source_ids):
            raise ValueError("source IDs must be unique")
        if self.sources != tuple(
            sorted(self.sources, key=lambda item: (item.kind, item.id))
        ):
            raise ValueError("sources must be in canonical order")

    def _validate_nodes(self) -> dict[str, PMNode]:
        nodes_by_id = {node.id: node for node in self.nodes}
        if len(nodes_by_id) != len(self.nodes):
            raise ValueError("node IDs must be unique")
        if self.nodes != tuple(sorted(self.nodes, key=lambda item: item.id)):
            raise ValueError("nodes must be in canonical order")
        for node in self.nodes:
            if node.id != make_node_id(self.module_id, semantic_node_fields(node)):
                raise ValueError(f"node {node.id!r} does not match its semantic ID")
        return nodes_by_id

    def _validate_edges(self, nodes_by_id: Mapping[str, PMNodeBase]) -> None:
        endpoint_pairs = [(edge.source, edge.target) for edge in self.edges]
        if len(set(endpoint_pairs)) != len(endpoint_pairs):
            raise ValueError("edge endpoint pairs must be unique")
        if self.edges != tuple(
            sorted(self.edges, key=lambda item: (item.source, item.target))
        ):
            raise ValueError("edges must be in canonical order")
        for edge in self.edges:
            source = nodes_by_id.get(edge.source)
            target = nodes_by_id.get(edge.target)
            if source is None or target is None:
                raise ValueError("edge endpoints must reference existing nodes")
            if source.id == target.id:
                raise ValueError("self-edges are not allowed")
            if not isinstance(
                source, (ParameterNode, ReceiveRequestNode, ReceiveResponseNode)
            ):
                raise ValueError("edge source must be a Parameter or Receive node")
            if not isinstance(
                target, (BehaviorNode, SendRequestNode, SendResponseNode)
            ):
                raise ValueError("edge target must be a Send or Behavior node")

    def _validate_evidence_sources(self) -> None:
        source_ids = {source.id for source in self.sources}
        nodes_by_id = {node.id: node for node in self.nodes}
        for node in self.nodes:
            self._validate_node_evidence(node, source_ids)
        for edge in self.edges:
            self._validate_edge_evidence(edge, nodes_by_id, source_ids)

    @staticmethod
    def _validate_node_evidence(node: PMNodeBase, source_ids: set[str]) -> None:
        derivations = {reference.derivation for reference in node.evidence}
        PMGraph._reject_dangling_evidence(node.evidence, source_ids)
        if "context-order" in derivations:
            raise ValueError("context-order evidence is valid only on an edge")
        if "paramtrack-unique-method-path" in derivations:
            raise ValueError(
                "paramtrack-unique-method-path evidence is valid only on an edge"
            )
        if "route-inference" in derivations and not isinstance(
            node, (ReceiveRequestNode, SendResponseNode)
        ):
            raise ValueError(
                "route-inference evidence requires a Receive Request or Send Response node"
            )
        if "response-correlation" in derivations and not isinstance(
            node, (ReceiveResponseNode, SendResponseNode)
        ):
            raise ValueError("response-correlation evidence requires a Response node")
        inferred = derivations & {"route-inference", "response-correlation"}
        if inferred and "observed" not in derivations:
            raise ValueError("an inferred node must retain observed evidence")
        if isinstance(node, (ReceiveResponseNode, SendResponseNode)) and (
            "response-correlation" not in derivations
        ):
            raise ValueError("a Response node requires response-correlation evidence")

    @staticmethod
    def _validate_edge_evidence(
        edge: PMEdge,
        nodes_by_id: Mapping[str, PMNodeBase],
        source_ids: set[str],
    ) -> None:
        PMGraph._reject_dangling_evidence(edge.evidence, source_ids)
        source = nodes_by_id[edge.source]
        target = nodes_by_id[edge.target]
        for reference in edge.evidence:
            if reference.derivation in {"route-inference", "response-correlation"}:
                raise ValueError(
                    f"{reference.derivation} evidence is valid only on a node"
                )
            if reference.derivation == "context-order" and not (
                isinstance(source, (ReceiveRequestNode, ReceiveResponseNode))
                and isinstance(target, (SendRequestNode, SendResponseNode))
            ):
                raise ValueError(
                    "context-order evidence requires a Receive-to-Send edge"
                )
            if reference.derivation == "paramtrack-unique-method-path" and not (
                isinstance(source, ParameterNode)
                and isinstance(target, SendRequestNode)
            ):
                raise ValueError(
                    "paramtrack-unique-method-path evidence requires a "
                    "Parameter-to-Send Request edge"
                )

    @staticmethod
    def _reject_dangling_evidence(
        evidence: tuple[EvidenceRef, ...], source_ids: set[str]
    ) -> None:
        for reference in evidence:
            if reference.source_id not in source_ids:
                raise ValueError(
                    f"evidence source {reference.source_id!r} is not in sources"
                )


def make_node_id(module_id: str, fields: Mapping[str, object]) -> str:
    identity = {"module_id": module_id, **fields}
    encoded = json.dumps(
        identity,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"n:{hashlib.sha256(encoded).hexdigest()}"


def semantic_node_fields(node: PMNode) -> dict[str, object]:
    if isinstance(node, (ParameterNode, BehaviorNode)):
        return {"type": node.type, "name": node.name}
    fields: dict[str, object] = {
        "type": node.type,
        "message": node.message,
        "api_id": node.api_id,
        "method": node.method,
    }
    if isinstance(node, ReceiveRequestNode):
        fields["pattern"] = node.pattern
    elif isinstance(node, (SendRequestNode, ReceiveResponseNode)):
        fields.update(host=node.host, path=node.path)
    else:
        fields["pattern"] = node.pattern
    if isinstance(node, (ReceiveResponseNode, SendResponseNode)):
        fields["status"] = node.status
    return fields


def make_pmgraph(
    *,
    module_id: str,
    sources: Iterable[SourceArtifact],
    nodes: Iterable[PMNode],
    edges: Iterable[PMEdge],
) -> PMGraph:
    merged_sources = _merge_sources(sources)
    merged_nodes = _merge_nodes(nodes)
    merged_edges = _merge_edges(edges)
    return PMGraph(
        format="conftamer.pmgraph",
        version=2,
        module_id=module_id,
        sources=tuple(sorted(merged_sources, key=lambda item: (item.kind, item.id))),
        nodes=tuple(sorted(merged_nodes, key=lambda item: item.id)),
        edges=tuple(sorted(merged_edges, key=lambda item: (item.source, item.target))),
    )


def _merge_sources(sources: Iterable[SourceArtifact]) -> list[SourceArtifact]:
    by_id: dict[str, SourceArtifact] = {}
    for source in sources:
        existing = by_id.get(source.id)
        if existing is not None and existing != source:
            raise ValueError(f"conflicting source artifact {source.id!r}")
        by_id[source.id] = source
    return list(by_id.values())


def _merge_nodes(nodes: Iterable[PMNode]) -> list[PMNode]:
    by_id: dict[str, PMNode] = {}
    evidence_by_id: dict[str, list[EvidenceRef]] = {}
    for node in nodes:
        existing = by_id.get(node.id)
        if existing is not None and semantic_node_fields(
            existing
        ) != semantic_node_fields(node):
            raise ValueError(f"conflicting semantic node {node.id!r}")
        by_id.setdefault(node.id, node)
        evidence_by_id.setdefault(node.id, []).extend(node.evidence)
    return [
        type(node).model_validate(
            {**node.model_dump(), "evidence": merge_evidence(evidence_by_id[node_id])}
        )
        for node_id, node in by_id.items()
    ]


def _merge_edges(edges: Iterable[PMEdge]) -> list[PMEdge]:
    evidence_by_pair: dict[tuple[str, str], list[EvidenceRef]] = {}
    for edge in edges:
        evidence_by_pair.setdefault((edge.source, edge.target), []).extend(
            edge.evidence
        )
    return [
        PMEdge(
            source=source,
            target=target,
            evidence=merge_evidence(evidence),
        )
        for (source, target), evidence in evidence_by_pair.items()
    ]
