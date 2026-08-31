import csv
import hashlib
import io
from collections.abc import Iterable
from pathlib import Path

from conftamer.ctype_graph import CTypeGraph
from conftamer.diagnostics import (
    Diagnostic,
    EvidenceRef,
    SourceArtifact,
    sort_diagnostics,
)
from conftamer.paramtrack.models import (
    ParamMessageKey,
    ParamTrackRecord,
    ParamTrackResult,
)
from conftamer.pmgraph import ParameterNode, PMEdge, SendRequestNode, make_node_id

_HEADER = ["API", "Verb", "Resource", "CType", "Param key"]


def import_paramtrack(
    path: str | Path,
    *,
    module_id: str,
    send_requests: Iterable[SendRequestNode],
    unmarshaler: CTypeGraph,
    accessors: CTypeGraph,
) -> ParamTrackResult:
    source_path = Path(path)
    source_name = str(path)
    data = source_path.read_bytes()
    source = SourceArtifact(
        id=f"sha256:{hashlib.sha256(data).hexdigest()}",
        kind="paramtrack-csv",
    )
    records, diagnostics = _read_records(data, source_name)
    eligible = _eligible_records(
        records,
        source_name,
        unmarshaler,
        accessors,
        diagnostics,
    )
    nodes, edges = _join_records(
        eligible,
        module_id,
        source,
        source_name,
        send_requests,
        diagnostics,
    )
    return ParamTrackResult(
        source=source,
        records=tuple(records),
        nodes=tuple(sorted(nodes, key=lambda node: node.id)),
        edges=tuple(sorted(edges, key=lambda edge: (edge.source, edge.target))),
        diagnostics=sort_diagnostics(diagnostics),
    )


def _read_records(
    data: bytes, source_name: str
) -> tuple[list[ParamTrackRecord], list[Diagnostic]]:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError(
            f"ParamTrack CSV {source_name!r} is not valid UTF-8"
        ) from error

    reader = csv.reader(io.StringIO(text, newline=""), strict=True)
    try:
        header = next(reader)
    except StopIteration:
        header = []
    except csv.Error as error:
        raise ValueError(f"could not read ParamTrack CSV header: {error}") from error
    if header != _HEADER:
        raise ValueError(f"invalid ParamTrack CSV header: expected {_HEADER!r}")

    records = []
    diagnostics = []
    while True:
        input_line = reader.line_num + 1
        try:
            row = next(reader)
        except StopIteration:
            break
        except csv.Error as error:
            raise ValueError(f"could not read ParamTrack CSV: {error}") from error
        if len(row) < 4:
            diagnostics.append(
                _diagnostic(
                    source_name,
                    input_line,
                    "paramtrack.invalid_row",
                    "row has fewer than four identity cells",
                )
            )
            continue
        keys = []
        for column, key in enumerate(row[4:], start=5):
            if key:
                keys.append(key)
            else:
                diagnostics.append(
                    _diagnostic(
                        source_name,
                        input_line,
                        "paramtrack.empty_key",
                        f"parameter key column {column} is empty",
                    )
                )
        records.append(
            ParamTrackRecord(
                input_line=input_line,
                api=row[0],
                verb=row[1],
                resource=row[2],
                ctype=row[3],
                keys=tuple(sorted(set(keys))),
            )
        )
    return records, diagnostics


def _eligible_records(
    records: list[ParamTrackRecord],
    source_name: str,
    unmarshaler: CTypeGraph,
    accessors: CTypeGraph,
    diagnostics: list[Diagnostic],
) -> dict[ParamMessageKey, list[ParamTrackRecord]]:
    represented = unmarshaler.name_to_node.keys() | accessors.name_to_node.keys()
    eligible: dict[ParamMessageKey, list[ParamTrackRecord]] = {}
    for record in records:
        usable = True
        if not record.verb:
            diagnostics.append(
                _diagnostic(
                    source_name,
                    record.input_line,
                    "paramtrack.empty_verb",
                    "Verb is empty",
                )
            )
            usable = False
        if not record.ctype:
            diagnostics.append(
                _diagnostic(
                    source_name,
                    record.input_line,
                    "paramtrack.empty_ctype",
                    "CType is empty",
                )
            )
            usable = False
        elif record.ctype not in represented:
            diagnostics.append(
                _diagnostic(
                    source_name,
                    record.input_line,
                    "paramtrack.unknown_ctype",
                    f"CType {record.ctype!r} is not represented",
                )
            )
            usable = False
        if len(record.verb) >= 10 or len(record.resource) >= 10:
            diagnostics.append(
                _diagnostic(
                    source_name,
                    record.input_line,
                    "paramtrack.possibly_truncated_message",
                    "Verb or Resource may have been truncated by ParamTrack",
                )
            )
            usable = False
        if usable and record.keys:
            key = ParamMessageKey(record.verb.upper(), record.resource or "/")
            eligible.setdefault(key, []).append(record)
    return eligible


def _join_records(
    records_by_message: dict[ParamMessageKey, list[ParamTrackRecord]],
    module_id: str,
    source: SourceArtifact,
    source_name: str,
    send_requests: Iterable[SendRequestNode],
    diagnostics: list[Diagnostic],
) -> tuple[list[ParameterNode], list[PMEdge]]:
    sends_by_message: dict[ParamMessageKey, dict[str, SendRequestNode]] = {}
    for request in send_requests:
        key = ParamMessageKey(request.method, request.path)
        sends_by_message.setdefault(key, {})[request.id] = request

    node_lines: dict[str, set[int]] = {}
    edges = []
    for message_key, records in sorted(records_by_message.items()):
        candidates = tuple(sends_by_message.get(message_key, {}).values())
        if len(candidates) != 1:
            diagnostics.extend(
                _match_diagnostic(
                    source_name, message_key, record.input_line, len(candidates)
                )
                for record in records
            )
            continue
        request = candidates[0]
        lines_by_key: dict[str, set[int]] = {}
        for record in records:
            for key in record.keys:
                lines_by_key.setdefault(key, set()).add(record.input_line)
        for parameter_name, lines in sorted(lines_by_key.items()):
            node_lines.setdefault(parameter_name, set()).update(lines)
            node_id = make_node_id(
                module_id, {"type": "Parameter", "name": parameter_name}
            )
            evidence_records = tuple(f"line:{line}" for line in sorted(lines))
            edges.append(
                PMEdge(
                    source=node_id,
                    target=request.id,
                    evidence=(
                        EvidenceRef(
                            source_id=source.id,
                            records=evidence_records,
                            derivation="paramtrack-unique-method-path",
                        ),
                    ),
                )
            )
    nodes = [
        ParameterNode(
            id=make_node_id(module_id, {"type": "Parameter", "name": name}),
            evidence=(
                EvidenceRef(
                    source_id=source.id,
                    records=tuple(f"line:{line}" for line in sorted(lines)),
                    derivation="observed",
                ),
            ),
            name=name,
        )
        for name, lines in sorted(node_lines.items())
    ]
    return nodes, edges


def _match_diagnostic(
    source_name: str,
    key: ParamMessageKey,
    input_line: int,
    candidate_count: int,
) -> Diagnostic:
    code = (
        "paramtrack.no_send_candidate"
        if candidate_count == 0
        else "paramtrack.ambiguous_send_candidate"
    )
    return _diagnostic(
        source_name,
        input_line,
        code,
        f"{key.method} {key.path} has {candidate_count} semantic Send candidates",
    )


def _diagnostic(source: str, line: int, code: str, message: str) -> Diagnostic:
    return Diagnostic(source=source, line=line, code=code, message=message)
