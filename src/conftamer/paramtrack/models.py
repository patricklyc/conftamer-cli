from dataclasses import dataclass

from conftamer.diagnostics import Diagnostic, SourceArtifact
from conftamer.pmgraph import ParameterNode, PMEdge


@dataclass(frozen=True, order=True)
class ParamMessageKey:
    method: str
    path: str


@dataclass(frozen=True)
class ParamTrackRecord:
    input_line: int
    api: str
    verb: str
    resource: str
    ctype: str
    keys: tuple[str, ...]


@dataclass(frozen=True)
class ParamTrackReadResult:
    source: SourceArtifact
    records: tuple[ParamTrackRecord, ...]
    diagnostics: tuple[Diagnostic, ...]


@dataclass(frozen=True)
class ParamTrackResult:
    source: SourceArtifact
    records: tuple[ParamTrackRecord, ...]
    nodes: tuple[ParameterNode, ...]
    edges: tuple[PMEdge, ...]
    diagnostics: tuple[Diagnostic, ...]
