import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

import conftamer.build as build_module
from conftamer.build import BuildResult, build_pmgraph
from conftamer.pmgraph import (
    ParameterNode,
    SendRequestNode,
    load_pmgraph,
    write_pmgraph,
)

MODULE = "example.org/service"
EXAMPLES = Path(__file__).resolve().parents[1] / "examples"
CONTEXTTRACK = EXAMPLES / "contexttrack/prometheus"
PARAMTRACK = EXAMPLES / "paramtrack"
UNMARSHALER = PARAMTRACK / "static/unmarshaler_subgraph.text"
ACCESSORS = PARAMTRACK / "static/accessors.text"


def write_events(
    tmp_path: Path,
    events: list[dict[str, object] | str],
    *,
    name: str = "events.jsonl",
) -> Path:
    path = tmp_path / name
    lines = [event if isinstance(event, str) else json.dumps(event) for event in events]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def write_csv(tmp_path: Path, body: str, *, name: str = "parameters.csv") -> Path:
    path = tmp_path / name
    path.write_text(
        "API,Verb,Resource,CType,Param key\n" + body,
        encoding="utf-8",
    )
    return path


def write_ctype(path: Path, *names: str) -> Path:
    document = {
        "Edges": [],
        "Vertices": [{"Names": [name], "Methods": [], "Tags": None} for name in names],
        "List": {name: name for name in names},
    }
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def request_sent(*, path: str = "/items") -> dict[str, object]:
    return {
        "kind": "Request sent",
        "pid": 10,
        "message": {
            "req.Method": "GET",
            "req.URL.Host": "backend:8080",
            "req.URL.Path": path,
        },
        "context": {"context_id": "id:1"},
        "api_id": "example.org/client",
    }


def test_message_only_build_uses_caller_module_and_contexttrack_source(tmp_path):
    events = write_events(tmp_path, [request_sent()])

    result = build_pmgraph(module_id=MODULE, events=events)

    assert isinstance(result, BuildResult)
    assert result.graph.module_id == MODULE
    assert result.graph.version == 2
    assert len(result.graph.nodes) == 1
    assert isinstance(result.graph.nodes[0], SendRequestNode)
    assert result.graph.sources[0].kind == "contexttrack-jsonl"
    assert result.graph.sources[0].id == (
        f"sha256:{hashlib.sha256(events.read_bytes()).hexdigest()}"
    )
    assert result.diagnostics == ()


@pytest.mark.parametrize(
    ("paramtrack_csv", "unmarshaler", "accessors"),
    [
        ("parameters.csv", None, None),
        (None, "unmarshaler.text", None),
        (None, None, "accessors.text"),
        ("parameters.csv", "unmarshaler.text", None),
        ("parameters.csv", None, "accessors.text"),
        (None, "unmarshaler.text", "accessors.text"),
    ],
)
def test_enrichment_options_are_all_or_none(
    tmp_path, paramtrack_csv, unmarshaler, accessors
):
    events = write_events(tmp_path, [request_sent()])

    with pytest.raises(ValueError, match="all be provided together"):
        build_pmgraph(
            module_id=MODULE,
            events=events,
            paramtrack_csv=paramtrack_csv,
            unmarshaler=unmarshaler,
            accessors=accessors,
        )


def test_enriched_build_merges_fragments_sources_evidence_and_diagnostics(tmp_path):
    events = write_events(tmp_path, [request_sent(), request_sent()])
    parameters = write_csv(tmp_path, "agent,get,/items,/Type,timeout\n")
    unmarshaler = write_ctype(tmp_path / "unmarshaler.text")
    accessors = write_ctype(tmp_path / "accessors.text", "/Type")

    result = build_pmgraph(
        module_id=MODULE,
        events=events,
        paramtrack_csv=parameters,
        unmarshaler=unmarshaler,
        accessors=accessors,
    )

    assert {(source.kind, source.id) for source in result.graph.sources} == {
        (
            "contexttrack-jsonl",
            f"sha256:{hashlib.sha256(events.read_bytes()).hexdigest()}",
        ),
        (
            "paramtrack-csv",
            f"sha256:{hashlib.sha256(parameters.read_bytes()).hexdigest()}",
        ),
        (
            "ctype-graph",
            f"sha256:{hashlib.sha256(unmarshaler.read_bytes()).hexdigest()}",
        ),
        (
            "ctype-graph",
            f"sha256:{hashlib.sha256(accessors.read_bytes()).hexdigest()}",
        ),
    }
    send = next(
        node for node in result.graph.nodes if isinstance(node, SendRequestNode)
    )
    parameter = next(
        node for node in result.graph.nodes if isinstance(node, ParameterNode)
    )
    assert send.evidence[0].records == ("line:1", "line:2")
    assert parameter.name == "timeout"
    assert parameter.evidence[0].records == ("line:2",)
    assert len(result.graph.edges) == 1
    edge = result.graph.edges[0]
    assert (edge.source, edge.target) == (parameter.id, send.id)
    assert edge.evidence[0].derivation == "paramtrack-unique-method-path"
    assert edge.evidence[0].records == ("line:2",)
    assert [(item.source, item.line, item.code) for item in result.diagnostics] == [
        (None, None, "build.paramtrack_caller_association")
    ]
    assert "aggregate" in result.diagnostics[0].message
    assert "caller" in result.diagnostics[0].message


def test_ctype_provenance_hashes_the_same_bytes_used_for_validation(
    tmp_path, monkeypatch
):
    events = write_events(tmp_path, [request_sent()])
    parameters = write_csv(tmp_path, "agent,GET,/items,/Type,timeout\n")
    unmarshaler = write_ctype(tmp_path / "unmarshaler.text")
    accessors = write_ctype(tmp_path / "accessors.text", "/Type")
    consumed_bytes = accessors.read_bytes()
    replacement_bytes = write_ctype(
        tmp_path / "replacement.text", "/Other"
    ).read_bytes()
    original_loader = build_module._load_ctype_graph_bytes

    def load_then_replace(path, data):
        graph = original_loader(path, data)
        if Path(path) == accessors:
            accessors.write_bytes(replacement_bytes)
        return graph

    monkeypatch.setattr(build_module, "_load_ctype_graph_bytes", load_then_replace)

    result = build_pmgraph(
        module_id=MODULE,
        events=events,
        paramtrack_csv=parameters,
        unmarshaler=unmarshaler,
        accessors=accessors,
    )

    ctype_source_ids = {
        source.id for source in result.graph.sources if source.kind == "ctype-graph"
    }
    assert any(isinstance(node, ParameterNode) for node in result.graph.nodes)
    assert f"sha256:{hashlib.sha256(consumed_bytes).hexdigest()}" in ctype_source_ids
    assert (
        f"sha256:{hashlib.sha256(replacement_bytes).hexdigest()}"
        not in ctype_source_ids
    )


def test_enriched_build_unions_and_globally_sorts_importer_diagnostics(tmp_path):
    events = write_events(
        tmp_path,
        ["{bad json", request_sent()],
        name="z-events.jsonl",
    )
    parameters = write_csv(
        tmp_path,
        "agent,GET,/items,/Type,timeout,\n",
        name="a-parameters.csv",
    )
    unmarshaler = write_ctype(tmp_path / "unmarshaler.text")
    accessors = write_ctype(tmp_path / "accessors.text", "/Type")

    result = build_pmgraph(
        module_id=MODULE,
        events=events,
        paramtrack_csv=parameters,
        unmarshaler=unmarshaler,
        accessors=accessors,
    )

    assert [(item.source, item.line, item.code) for item in result.diagnostics] == [
        (None, None, "build.paramtrack_caller_association"),
        (str(parameters), 2, "paramtrack.empty_key"),
        (str(events), 1, "contexttrack.invalid_event"),
    ]


def test_build_is_deterministic_when_parameter_semantics_are_shuffled(
    tmp_path, monkeypatch
):
    events = write_events(tmp_path, [request_sent()])
    parameters = write_csv(tmp_path, "agent,GET,/items,/Type,timeout,retries\n")
    unmarshaler = write_ctype(tmp_path / "unmarshaler.text")
    accessors = write_ctype(tmp_path / "accessors.text", "/Type")
    options = {
        "module_id": MODULE,
        "events": events,
        "paramtrack_csv": parameters,
        "unmarshaler": unmarshaler,
        "accessors": accessors,
    }
    expected = build_pmgraph(**options)
    original_import = build_module.import_paramtrack

    def import_shuffled(*args, **kwargs):
        result = original_import(*args, **kwargs)
        return replace(
            result,
            nodes=tuple(reversed(result.nodes)),
            edges=tuple(reversed(result.edges)),
        )

    monkeypatch.setattr(build_module, "import_paramtrack", import_shuffled)

    actual = build_pmgraph(**options)

    assert actual.graph.model_dump_json() == expected.graph.model_dump_json()
    assert actual.diagnostics == expected.diagnostics


def test_target_scraper_build_creates_108_edges_to_unique_root_send(tmp_path):
    result = build_pmgraph(
        module_id=MODULE,
        events=CONTEXTTRACK / "scrape-ok.jsonl",
        paramtrack_csv=PARAMTRACK / "runs/target-scraper-all/parameters.csv",
        unmarshaler=UNMARSHALER,
        accessors=ACCESSORS,
    )

    root_sends = [
        node
        for node in result.graph.nodes
        if isinstance(node, SendRequestNode)
        and (node.method, node.path) == ("GET", "/")
    ]
    parameter_ids = {
        node.id for node in result.graph.nodes if isinstance(node, ParameterNode)
    }
    parameter_edges = [
        edge for edge in result.graph.edges if edge.source in parameter_ids
    ]
    assert len(root_sends) == 1
    assert len(parameter_edges) == 108
    assert {edge.target for edge in parameter_edges} == {root_sends[0].id}
    assert len(result.graph.edges) == 109
    assert [item.code for item in result.diagnostics] == [
        "build.paramtrack_caller_association"
    ]

    output = tmp_path / "target.pmgraph.json"
    write_pmgraph(result.graph, output)
    assert load_pmgraph(output) == result.graph


def test_manager_build_deduplicates_226_edges_and_retains_all_source_lines(
    tmp_path,
):
    events = write_events(tmp_path, [request_sent(path="/metrics")])

    result = build_pmgraph(
        module_id=MODULE,
        events=events,
        paramtrack_csv=PARAMTRACK / "runs/manager-st-zero/parameters.csv",
        unmarshaler=UNMARSHALER,
        accessors=ACCESSORS,
    )

    parameter_ids = {
        node.id for node in result.graph.nodes if isinstance(node, ParameterNode)
    }
    parameter_edges = [
        edge for edge in result.graph.edges if edge.source in parameter_ids
    ]
    supporting_records = {
        record
        for edge in parameter_edges
        for reference in edge.evidence
        for record in reference.records
    }
    assert len(parameter_ids) == len(parameter_edges) == 226
    assert supporting_records == {"line:2", "line:3", "line:4", "line:5"}
    assert any(len(edge.evidence[0].records) > 1 for edge in parameter_edges)
    assert [item.code for item in result.diagnostics] == [
        "build.paramtrack_caller_association"
    ]


def test_manager_build_omits_parameters_for_47_ambiguous_sends():
    result = build_pmgraph(
        module_id=MODULE,
        events=CONTEXTTRACK / "all-tests.jsonl",
        paramtrack_csv=PARAMTRACK / "runs/manager-st-zero/parameters.csv",
        unmarshaler=UNMARSHALER,
        accessors=ACCESSORS,
    )

    candidates = [
        node
        for node in result.graph.nodes
        if isinstance(node, SendRequestNode)
        and (node.method, node.path) == ("GET", "/metrics")
    ]
    ambiguity = [
        item
        for item in result.diagnostics
        if item.code == "paramtrack.ambiguous_send_candidate"
    ]
    assert len(candidates) == 47
    assert not any(isinstance(node, ParameterNode) for node in result.graph.nodes)
    assert not any(
        reference.derivation == "paramtrack-unique-method-path"
        for edge in result.graph.edges
        for reference in edge.evidence
    )
    assert [item.line for item in ambiguity] == [2, 3, 4, 5]
    assert all("47 semantic Send candidates" in item.message for item in ambiguity)
