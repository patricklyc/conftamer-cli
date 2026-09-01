import hashlib
from dataclasses import dataclass
from pathlib import Path

from conftamer.contexttrack import import_contexttrack
from conftamer.ctype_graph import CTypeGraph
from conftamer.ctype_graph.io import _load_ctype_graph_bytes
from conftamer.diagnostics import (
    Diagnostic,
    SourceArtifact,
    sort_diagnostics,
)
from conftamer.paramtrack import import_paramtrack
from conftamer.pmgraph import PMGraph, SendRequestNode, make_pmgraph


@dataclass(frozen=True)
class BuildResult:
    graph: PMGraph
    diagnostics: tuple[Diagnostic, ...]


def build_pmgraph(
    *,
    module_id: str,
    events: str | Path,
    paramtrack_csv: str | Path | None = None,
    unmarshaler: str | Path | None = None,
    accessors: str | Path | None = None,
) -> BuildResult:
    enrichment_options = (paramtrack_csv, unmarshaler, accessors)
    supplied = tuple(option is not None for option in enrichment_options)
    if any(supplied) and not all(supplied):
        raise ValueError(
            "paramtrack_csv, unmarshaler, and accessors must all be provided together"
        )

    messages = import_contexttrack(events, module_id=module_id)
    if not any(supplied):
        return BuildResult(graph=messages.graph, diagnostics=messages.diagnostics)

    assert paramtrack_csv is not None
    assert unmarshaler is not None
    assert accessors is not None
    unmarshaler_graph, unmarshaler_source = _load_ctype(unmarshaler)
    accessors_graph, accessors_source = _load_ctype(accessors)
    parameters = import_paramtrack(
        paramtrack_csv,
        module_id=module_id,
        send_requests=(
            node for node in messages.graph.nodes if isinstance(node, SendRequestNode)
        ),
        unmarshaler=unmarshaler_graph,
        accessors=accessors_graph,
    )
    graph = make_pmgraph(
        module_id=module_id,
        sources=(
            *messages.graph.sources,
            parameters.source,
            unmarshaler_source,
            accessors_source,
        ),
        nodes=(*messages.graph.nodes, *parameters.nodes),
        edges=(*messages.graph.edges, *parameters.edges),
    )
    diagnostic = Diagnostic(
        source=None,
        line=None,
        code="build.paramtrack_caller_association",
        message=(
            "ParamTrack enrichment is aggregate; supplying these inputs is the "
            "caller's assertion that they describe a compatible corpus"
        ),
    )
    return BuildResult(
        graph=graph,
        diagnostics=sort_diagnostics(
            (diagnostic, *messages.diagnostics, *parameters.diagnostics)
        ),
    )


def _load_ctype(path: str | Path) -> tuple[CTypeGraph, SourceArtifact]:
    data = Path(path).read_bytes()
    graph = _load_ctype_graph_bytes(path, data)
    source = SourceArtifact(
        id=f"sha256:{hashlib.sha256(data).hexdigest()}",
        kind="ctype-graph",
    )
    return graph, source
