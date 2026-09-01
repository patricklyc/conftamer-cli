import hashlib
from pathlib import Path

import pytest

from conftamer.ctype_graph import CTypeGraph, CTypeNode, load_ctype_graph
from conftamer.diagnostics import EvidenceRef
from conftamer.paramtrack import import_paramtrack, read_paramtrack
from conftamer.pmgraph import SendRequestNode, make_node_id

MODULE = "example.org/service"
HEADER = "API,Verb,Resource,CType,Param key\n"
OBSERVED_SOURCE = f"sha256:{'1' * 64}"
EXAMPLES = Path(__file__).parents[2] / "examples" / "paramtrack"


def write_csv(tmp_path: Path, body: str | bytes, name: str = "parameters.csv") -> Path:
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    data = body if isinstance(body, bytes) else body.encode()
    path.write_bytes(data)
    return path


def ctype_graph(*names: str) -> CTypeGraph:
    ordered = tuple(sorted(names))
    return CTypeGraph(
        nodes=tuple(
            CTypeNode(id=name, names=(name,), methods=(), tags=None) for name in ordered
        ),
        edges=(),
        name_to_node={name: name for name in ordered},
    )


def send_request(
    method: str,
    path: str,
    *,
    host: str = "backend:8080",
    api_id: str | None = "contexttrack-api",
) -> SendRequestNode:
    fields = {
        "type": "Send",
        "message": "Request",
        "api_id": api_id,
        "method": method.upper(),
        "host": host,
        "path": path or "/",
    }
    return SendRequestNode(
        id=make_node_id(MODULE, fields),
        evidence=(
            EvidenceRef(
                source_id=OBSERVED_SOURCE,
                records=("line:1",),
                derivation="observed",
            ),
        ),
        api_id=api_id,
        method=method,
        host=host,
        path=path,
    )


def import_csv(
    path: Path,
    sends: tuple[SendRequestNode, ...] = (),
    *,
    unmarshaler: CTypeGraph | None = None,
    accessors: CTypeGraph | None = None,
):
    empty = ctype_graph()
    return import_paramtrack(
        path,
        module_id=MODULE,
        send_requests=sends,
        unmarshaler=unmarshaler or empty,
        accessors=accessors or empty,
    )


def node_by_name(result, name: str):
    return next(node for node in result.nodes if node.name == name)


def evidence_records(item, derivation: str) -> tuple[str, ...]:
    return next(
        reference.records
        for reference in item.evidence
        if reference.derivation == derivation
    )


@pytest.mark.parametrize(
    "contents",
    [
        "",
        "API,Verb,Resource,CType,Wrong\n",
        " API,Verb,Resource,CType,Param key\n",
        "API,Verb,Resource,CType,Param key,Extra\n",
    ],
)
def test_requires_the_exact_observed_header(tmp_path, contents):
    path = write_csv(tmp_path, contents)

    with pytest.raises(ValueError, match="header"):
        import_csv(path)


def test_rejects_unreadable_or_lexically_malformed_csv(tmp_path):
    unreadable = write_csv(tmp_path / "encoding", b"\xff")
    malformed = write_csv(
        tmp_path / "syntax",
        HEADER + 'api,GET,/,/Type,"unterminated\n',
    )

    with pytest.raises(ValueError, match="UTF-8"):
        import_csv(unreadable)
    with pytest.raises(ValueError, match="CSV"):
        import_csv(malformed)


def test_reads_paramtrack_without_enrichment_inputs(tmp_path):
    path = write_csv(
        tmp_path,
        HEADER
        + "api,,/ok,/Type,alpha,,alpha\n"
        + "api,GET,/123456789,,beta\n"
        + "too,short,for\n",
    )

    result = read_paramtrack(path)

    assert result.source.id == (
        f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"
    )
    assert [(record.input_line, record.keys) for record in result.records] == [
        (2, ("alpha",)),
        (3, ("beta",)),
    ]
    assert [(item.line, item.code) for item in result.diagnostics] == [
        (2, "paramtrack.empty_key"),
        (2, "paramtrack.empty_verb"),
        (3, "paramtrack.empty_ctype"),
        (3, "paramtrack.possibly_truncated_message"),
        (4, "paramtrack.invalid_row"),
    ]
    assert not any(
        item.code
        in {
            "paramtrack.unknown_ctype",
            "paramtrack.no_send_candidate",
            "paramtrack.ambiguous_send_candidate",
        }
        for item in result.diagnostics
    )


def test_parses_quoted_variable_width_rows_and_tracks_starting_physical_lines(
    tmp_path,
):
    path = write_csv(
        tmp_path,
        HEADER
        + '"Agent,\nName",get,,/Type,"alpha,\nbeta",alpha,alpha,\n'
        + "Agent,GET,/,/Type\n"
        + "too,short,for\n",
    )

    result = import_csv(
        path,
        (send_request("GET", "/"),),
        accessors=ctype_graph("/Type"),
    )

    assert result.source.id == f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"
    assert result.source.kind == "paramtrack-csv"
    assert [
        (record.input_line, record.api, record.keys) for record in result.records
    ] == [
        (2, "Agent,\nName", ("alpha", "alpha,\nbeta")),
        (5, "Agent", ()),
    ]
    assert {node.name for node in result.nodes} == {"alpha,\nbeta", "alpha"}
    assert all(
        evidence_records(node, "observed") == ("line:2",) for node in result.nodes
    )
    assert [(item.line, item.code) for item in result.diagnostics] == [
        (2, "paramtrack.empty_key"),
        (6, "paramtrack.invalid_row"),
    ]


def test_invalid_identities_truncation_and_exact_ctype_validation_are_local(
    tmp_path,
):
    path = write_csv(
        tmp_path,
        HEADER
        + ",GET,/ok,/Type,accepted\n"
        + "api,,/ok,/Type,empty-verb\n"
        + "api,GET,/ok,,empty-ctype\n"
        + "api,VERYLONGXX,/ok,/Type,long-verb\n"
        + "api,GET,/123456789,/Type,long-resource\n"
        + "api,GET,/ok,Type,missing-leading-slash\n",
    )

    result = import_csv(
        path,
        (send_request("GET", "/ok", api_id="not-the-paramtrack-api"),),
        accessors=ctype_graph("/Type"),
    )

    assert result.records[0].api == ""
    assert {node.name for node in result.nodes} == {"accepted"}
    assert [item.code for item in result.diagnostics] == [
        "paramtrack.empty_verb",
        "paramtrack.empty_ctype",
        "paramtrack.possibly_truncated_message",
        "paramtrack.possibly_truncated_message",
        "paramtrack.unknown_ctype",
    ]


def test_enrichment_preserves_unknown_ctype_with_other_local_row_issues(tmp_path):
    path = write_csv(
        tmp_path,
        HEADER
        + "api,,/ok,/Unknown,empty-verb\n"
        + "api,GET,/123456789,/Unknown,truncated\n"
        + "api,,/ok,,empty-both\n",
    )

    result = import_csv(path)

    assert [(item.line, item.code) for item in result.diagnostics] == [
        (2, "paramtrack.empty_verb"),
        (2, "paramtrack.unknown_ctype"),
        (3, "paramtrack.possibly_truncated_message"),
        (3, "paramtrack.unknown_ctype"),
        (4, "paramtrack.empty_ctype"),
        (4, "paramtrack.empty_verb"),
    ]


def test_unique_normalized_message_join_unions_ctypes_keys_and_line_evidence(
    tmp_path,
):
    path = write_csv(
        tmp_path,
        HEADER
        + "first-api,get,,/A,a,shared,shared\n"
        + "second-api,GET,,/B,b,shared\n"
        + "third-api,GET,,/A,shared\n",
    )

    candidate = send_request("GET", "/", api_id="unrelated-contexttrack-id")
    result = import_csv(
        path,
        (candidate,),
        unmarshaler=ctype_graph("/A"),
        accessors=ctype_graph("/B"),
    )

    assert result.diagnostics == ()
    assert {node.name for node in result.nodes} == {"a", "b", "shared"}
    shared = node_by_name(result, "shared")
    shared_edge = next(edge for edge in result.edges if edge.source == shared.id)
    assert evidence_records(shared, "observed") == (
        "line:2",
        "line:3",
        "line:4",
    )
    assert evidence_records(shared_edge, "paramtrack-unique-method-path") == (
        "line:2",
        "line:3",
        "line:4",
    )
    assert len(result.edges) == 3
    assert {edge.target for edge in result.edges} == {candidate.id}


def test_parameter_nodes_are_reused_across_distinct_unique_message_joins(tmp_path):
    path = write_csv(
        tmp_path,
        HEADER + "api,GET,/one,/Type,shared\n" + "api,POST,/two,/Type,shared\n",
    )
    sends = (
        send_request("GET", "/one"),
        send_request("POST", "/two"),
    )

    result = import_csv(path, sends, accessors=ctype_graph("/Type"))

    assert len(result.nodes) == 1
    assert len(result.edges) == 2
    assert evidence_records(result.nodes[0], "observed") == ("line:2", "line:3")


def test_zero_and_several_send_candidates_are_diagnosed_for_each_row(tmp_path):
    path = write_csv(
        tmp_path,
        HEADER
        + "api,GET,/missing,/Type,no-candidate-a\n"
        + "other-api,GET,/missing,/Type,no-candidate-b\n"
        + "api,POST,/same,/Type,ambiguous-a\n"
        + "different-api,POST,/same,/Type,ambiguous-b\n",
    )
    sends = (
        send_request("POST", "/same", host="one", api_id="one"),
        send_request("POST", "/same", host="two", api_id="two"),
    )

    result = import_csv(path, sends, accessors=ctype_graph("/Type"))

    assert result.nodes == ()
    assert result.edges == ()
    assert [(item.line, item.code) for item in result.diagnostics] == [
        (2, "paramtrack.no_send_candidate"),
        (3, "paramtrack.no_send_candidate"),
        (4, "paramtrack.ambiguous_send_candidate"),
        (5, "paramtrack.ambiguous_send_candidate"),
    ]
    assert all("0" in item.message for item in result.diagnostics[:2])
    assert all("2" in item.message for item in result.diagnostics[2:])


def test_reordering_rows_preserves_semantics_and_updates_provenance(tmp_path):
    first_path = write_csv(
        tmp_path / "first",
        HEADER + "api,GET,/,/Type,a\n" + "api,GET,/,/Type,b\n",
    )
    second_path = write_csv(
        tmp_path / "second",
        HEADER + "api,GET,/,/Type,b\n" + "api,GET,/,/Type,a\n",
    )
    sends = (send_request("GET", "/"),)
    ctypes = ctype_graph("/Type")

    first = import_csv(first_path, sends, accessors=ctypes)
    second = import_csv(second_path, sends, accessors=ctypes)

    assert {node.id for node in first.nodes} == {node.id for node in second.nodes}
    assert {(edge.source, edge.target) for edge in first.edges} == {
        (edge.source, edge.target) for edge in second.edges
    }
    assert first.source.id != second.source.id
    assert evidence_records(node_by_name(first, "a"), "observed") == ("line:2",)
    assert evidence_records(node_by_name(second, "a"), "observed") == ("line:3",)
    assert node_by_name(first, "a").evidence[0].source_id == first.source.id
    assert node_by_name(second, "a").evidence[0].source_id == second.source.id


def test_real_paramtrack_files_have_documented_key_counts_and_unions():
    unmarshaler = load_ctype_graph(EXAMPLES / "static/unmarshaler_subgraph.text")
    accessors = load_ctype_graph(EXAMPLES / "static/accessors.text")

    target = import_csv(
        EXAMPLES / "runs/target-scraper-all/parameters.csv",
        (send_request("GET", "/"),),
        unmarshaler=unmarshaler,
        accessors=accessors,
    )
    manager = import_csv(
        EXAMPLES / "runs/manager-st-zero/parameters.csv",
        (send_request("GET", "/metrics"),),
        unmarshaler=unmarshaler,
        accessors=accessors,
    )

    assert [len(record.keys) for record in target.records] == [108]
    assert len(target.nodes) == len(target.edges) == 108
    assert target.diagnostics == ()
    assert [len(record.keys) for record in manager.records] == [133, 120, 201, 108]
    assert len({key for record in manager.records for key in record.keys}) == 226
    assert len(manager.nodes) == len(manager.edges) == 226
    assert manager.diagnostics == ()
