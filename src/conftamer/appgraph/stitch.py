import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from conftamer.appgraph.matching import MatchPlan, NodeKey, plan_matches
from conftamer.appgraph.models import (
    AppEdge,
    AppGraph,
    AppNode,
    MatchInfo,
    QualifiedEdgeRef,
    QualifiedNodeRef,
    QualifiedPMNode,
    _make_app_node_id,
    _origin_key,
)
from conftamer.diagnostics import Diagnostic, SourceArtifact, sort_diagnostics
from conftamer.pmgraph import PMGraph, load_pmgraph


@dataclass(frozen=True)
class StitchResult:
    graph: AppGraph
    diagnostics: tuple[Diagnostic, ...]


def stitch_pmgraphs(graphs: Iterable[PMGraph]) -> StitchResult:
    documents = tuple(sorted(graphs, key=lambda item: item.module_id))
    if len(documents) < 2:
        raise ValueError("stitching requires at least two PMGraphs")
    module_ids = tuple(document.module_id for document in documents)
    if len(set(module_ids)) != len(module_ids):
        raise ValueError("PMGraph module IDs must be unique")

    qualified = {
        (document.module_id, node.id): QualifiedPMNode(
            module_id=document.module_id,
            node=node,
        )
        for document in documents
        for node in document.nodes
    }
    plans = plan_matches({key: member.node for key, member in qualified.items()})
    nodes = tuple(
        sorted(
            (_make_app_node(plan, qualified) for plan in plans),
            key=lambda item: item.id,
        )
    )
    graph = AppGraph(
        format="conftamer.appgraph",
        version=1,
        module_ids=module_ids,
        sources=_merge_sources(documents),
        nodes=nodes,
        edges=_remap_edges(documents, nodes),
    )
    diagnostics = [
        _diagnostic(
            "heuristic_match",
            "HTTP-label uniqueness does not prove network delivery: ",
            plan.members,
        )
        for plan in plans
        if plan.status == "matched"
    ]
    diagnostics.extend(_ambiguity_diagnostics(plans))
    return StitchResult(graph=graph, diagnostics=sort_diagnostics(diagnostics))


def _make_app_node(
    plan: MatchPlan,
    qualified: dict[NodeKey, QualifiedPMNode],
) -> AppNode:
    members = tuple(qualified[key] for key in plan.members)
    candidates = tuple(
        QualifiedNodeRef(module_id=module, node_id=node_id)
        for module, node_id in plan.candidates
    )
    return AppNode(
        id=_make_app_node_id(members),
        members=members,
        match=MatchInfo(
            status=plan.status,
            basis=plan.basis,
            candidates=candidates,
        ),
    )


def _remap_edges(
    documents: tuple[PMGraph, ...],
    nodes: tuple[AppNode, ...],
) -> tuple[AppEdge, ...]:
    containers = {
        (member.module_id, member.node.id): node.id
        for node in nodes
        for member in node.members
    }
    origins: dict[tuple[str, str], list[QualifiedEdgeRef]] = {}
    for document in documents:
        for edge in document.edges:
            endpoint = (
                containers[(document.module_id, edge.source)],
                containers[(document.module_id, edge.target)],
            )
            origins.setdefault(endpoint, []).append(
                QualifiedEdgeRef(
                    module_id=document.module_id,
                    source=edge.source,
                    target=edge.target,
                    evidence=edge.evidence,
                )
            )
    return tuple(
        AppEdge(
            source=source,
            target=target,
            origins=tuple(sorted(items, key=_origin_key)),
        )
        for (source, target), items in sorted(origins.items())
    )


def stitch_pmgraph_files(paths: Sequence[str | Path]) -> StitchResult:
    return stitch_pmgraphs(load_pmgraph(path) for path in paths)


def prune_unmatched(graph: AppGraph) -> AppGraph:
    kept_nodes = tuple(
        node
        for node in graph.nodes
        if len(node.members) > 1 or node.match.status == "not_applicable"
    )
    kept_ids = {node.id for node in kept_nodes}
    kept_edges = tuple(
        edge
        for edge in graph.edges
        if edge.source in kept_ids and edge.target in kept_ids
    )
    return AppGraph.model_validate(
        {
            **graph.model_dump(),
            "nodes": kept_nodes,
            "edges": kept_edges,
        }
    )


def load_appgraph(path: str | Path) -> AppGraph:
    text = Path(path).read_text(encoding="utf-8")
    graph = AppGraph.model_validate_json(text)
    if json.loads(text) != graph.model_dump(mode="json"):
        raise ValueError("AppGraph document is not canonical")
    return graph


def write_appgraph(graph: AppGraph, path: str | Path) -> None:
    text = graph.model_dump_json(indent=2, ensure_ascii=False) + "\n"
    Path(path).write_bytes(text.encode("utf-8"))


def _ambiguity_diagnostics(plans: tuple[MatchPlan, ...]) -> list[Diagnostic]:
    adjacency = {
        plan.members[0]: set(plan.candidates)
        for plan in plans
        if plan.status == "ambiguous"
    }
    diagnostics = []
    while adjacency:
        component = {next(iter(adjacency))}
        while additional := (
            set().union(*(adjacency.get(key, set()) for key in component)) - component
        ):
            component.update(additional)
        for key in component:
            adjacency.pop(key, None)
        diagnostics.append(
            _diagnostic(
                "ambiguous_match",
                "HTTP labels have multiple candidates: ",
                component,
            )
        )
    return diagnostics


def _diagnostic(code: str, message: str, keys: Iterable[NodeKey]) -> Diagnostic:
    members = ", ".join(f"{module}:{node}" for module, node in sorted(keys))
    return Diagnostic(
        source=None,
        line=None,
        code=f"appgraph.{code}",
        message=message + members,
    )


def _merge_sources(documents: tuple[PMGraph, ...]) -> tuple[SourceArtifact, ...]:
    by_id: dict[str, SourceArtifact] = {}
    for document in documents:
        for source in document.sources:
            existing = by_id.get(source.id)
            if existing is not None and existing != source:
                raise ValueError(f"conflicting source artifact {source.id!r}")
            by_id[source.id] = source
    return tuple(sorted(by_id.values(), key=lambda item: (item.kind, item.id)))
