import hashlib
import importlib
import json
import subprocess
import sys
import tomllib
from pathlib import Path

import igraph as ig
import pytest
from typer.testing import CliRunner

from conftamer.appgraph import load_appgraph, stitch_pmgraphs, write_appgraph
from conftamer.diagnostics import EvidenceRef, SourceArtifact
from conftamer.pmgraph import (
    PMEdge,
    ParameterNode,
    ReceiveRequestNode,
    SendRequestNode,
    load_pmgraph,
    make_node_id,
    make_pmgraph,
    write_pmgraph,
)

runner = CliRunner()
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def invoke(*arguments: str):
    app = importlib.import_module("conftamer.cli").app
    return runner.invoke(app, list(arguments))


def write_events(tmp_path: Path, *, malformed: bool = False) -> Path:
    event = {
        "kind": "Request sent",
        "pid": 10,
        "message": {
            "req.Method": "GET",
            "req.URL.Host": "backend:8080",
            "req.URL.Path": "/items/1",
        },
        "context": {"context_id": "id:1"},
        "api_id": "example.org/client",
    }
    lines = ["{bad json"] if malformed else []
    lines.append(json.dumps(event))
    path = tmp_path / "events.jsonl"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def source_for(module_id: str) -> SourceArtifact:
    digest = hashlib.sha256(module_id.encode()).hexdigest()
    return SourceArtifact(id=f"sha256:{digest}", kind="contexttrack-jsonl")


def evidence_for(module_id: str) -> tuple[EvidenceRef, ...]:
    return (
        EvidenceRef(
            source_id=source_for(module_id).id,
            records=("line:1",),
            derivation="observed",
        ),
    )


def send_request(module_id: str, path: str = "/items/1") -> SendRequestNode:
    fields = {
        "type": "Send",
        "message": "Request",
        "api_id": None,
        "method": "GET",
        "host": "backend:8080",
        "path": path,
    }
    return SendRequestNode(
        id=make_node_id(module_id, fields),
        evidence=evidence_for(module_id),
        api_id=None,
        method="GET",
        host="backend:8080",
        path=path,
    )


def receive_request(module_id: str) -> ReceiveRequestNode:
    fields = {
        "type": "Receive",
        "message": "Request",
        "api_id": None,
        "method": "GET",
        "pattern": "/items/{id}",
    }
    return ReceiveRequestNode(
        id=make_node_id(module_id, fields),
        evidence=evidence_for(module_id),
        api_id=None,
        method="GET",
        pattern="/items/{id}",
    )


def parameter(module_id: str) -> ParameterNode:
    fields = {"type": "Parameter", "name": "timeout"}
    return ParameterNode(
        id=make_node_id(module_id, fields),
        evidence=evidence_for(module_id),
        name="timeout",
    )


def write_stitch_inputs(
    tmp_path: Path, *, unmatched: bool = False
) -> tuple[Path, Path]:
    client = "example.org/client"
    server = "example.org/server"
    send = send_request(client)
    nodes = [send]
    if unmatched:
        nodes.append(send_request(client, "/unmatched"))
    client_graph = make_pmgraph(
        module_id=client,
        sources=(source_for(client),),
        nodes=nodes,
        edges=(),
    )
    server_graph = make_pmgraph(
        module_id=server,
        sources=(source_for(server),),
        nodes=(receive_request(server),),
        edges=(),
    )
    first = tmp_path / "client.pmgraph.json"
    second = tmp_path / "server.pmgraph.json"
    write_pmgraph(client_graph, first)
    write_pmgraph(server_graph, second)
    return first, second


def write_ctype(path: Path) -> Path:
    document = {
        "Edges": [
            {"Source": "/a", "Target": "/b", "Properties": {"Data": [[]]}},
            {"Source": "/b", "Target": "/c", "Properties": {"Data": [[]]}},
        ],
        "Vertices": [
            {"Names": [name], "Methods": [], "Tags": None}
            for name in ("/a", "/b", "/c")
        ],
        "List": {name: name for name in ("/a", "/b", "/c")},
    }
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def write_graph_inputs(tmp_path: Path) -> dict[str, tuple[Path, str, int]]:
    client = "example.org/client"
    server = "example.org/server"
    setting = parameter(client)
    send = send_request(client)
    client_graph = make_pmgraph(
        module_id=client,
        sources=(source_for(client),),
        nodes=(setting, send),
        edges=(
            PMEdge(
                source=setting.id,
                target=send.id,
                evidence=evidence_for(client),
            ),
        ),
    )
    server_graph = make_pmgraph(
        module_id=server,
        sources=(source_for(server),),
        nodes=(receive_request(server),),
        edges=(),
    )
    pmgraph_path = tmp_path / "client.pmgraph.json"
    appgraph_path = tmp_path / "application.appgraph.json"
    write_pmgraph(client_graph, pmgraph_path)
    write_appgraph(stitch_pmgraphs((client_graph, server_graph)).graph, appgraph_path)
    ctype_path = write_ctype(tmp_path / "types.text")
    return {
        "pmgraph": (pmgraph_path, "timeout", 2),
        "appgraph": (appgraph_path, "timeout", 2),
        "ctype": (ctype_path, "/b", 3),
    }


@pytest.mark.parametrize(
    "arguments",
    [
        ("--help",),
        ("build", "--help"),
        ("stitch", "--help"),
        ("query", "--help"),
        ("export", "--help"),
    ],
)
def test_replacement_help_exposes_graph_compiler_commands(arguments):
    result = invoke(*arguments)

    assert result.exit_code == 0, result.output
    if arguments == ("--help",):
        for command in ("build", "stitch", "query", "export"):
            assert command in result.stdout


@pytest.mark.parametrize(
    "command",
    ("contexttrack", "graph", "subgraph", "analyzer", "runner", "delve"),
)
def test_replacement_cli_has_no_legacy_or_producer_commands(command):
    result = invoke(command, "--help")

    assert result.exit_code != 0
    assert "No such command" in result.output


def test_installed_entry_point_targets_replacement_app():
    project = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text())

    assert project["project"]["scripts"]["conftamer"] == "conftamer.cli:app"


def test_replacement_cli_runs_as_a_packaging_entry_script():
    result = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "src/conftamer/cli.py"), "--help"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "build" in result.stdout


def test_build_writes_canonical_pmgraph_and_separates_diagnostics(tmp_path):
    events = write_events(tmp_path, malformed=True)
    output = tmp_path / "service.pmgraph.json"

    result = invoke(
        "build",
        "--module-id",
        "example.org/service",
        "--events",
        str(events),
        "--output",
        str(output),
    )

    assert result.exit_code == 0, result.output
    assert len(load_pmgraph(output).nodes) == 1
    assert "PMGraph" in result.stdout
    assert "1 node" in result.stdout
    assert str(output) in result.stdout
    assert "contexttrack.invalid_event" in result.stderr
    assert "contexttrack.invalid_event" not in result.stdout


@pytest.mark.parametrize(
    "options",
    [
        ("--paramtrack-csv", "parameters.csv"),
        ("--unmarshaler", "unmarshaler.text"),
        ("--accessors", "accessors.text"),
        (
            "--paramtrack-csv",
            "parameters.csv",
            "--unmarshaler",
            "unmarshaler.text",
        ),
        (
            "--paramtrack-csv",
            "parameters.csv",
            "--accessors",
            "accessors.text",
        ),
        (
            "--unmarshaler",
            "unmarshaler.text",
            "--accessors",
            "accessors.text",
        ),
    ],
)
def test_build_rejects_partial_enrichment_options(tmp_path, options):
    output = tmp_path / "service.pmgraph.json"
    result = invoke(
        "build",
        "--module-id",
        "example.org/service",
        "--events",
        str(write_events(tmp_path)),
        "--output",
        str(output),
        *options,
    )

    assert result.exit_code != 0
    assert "must all be provided together" in result.output
    assert not output.exists()


def test_build_forwards_complete_enrichment_options(tmp_path):
    events = write_events(tmp_path)
    parameters = tmp_path / "parameters.csv"
    parameters.write_text(
        "API,Verb,Resource,CType,Param key\nagent,GET,/items/1,/Type,timeout\n",
        encoding="utf-8",
    )
    unmarshaler = write_ctype(tmp_path / "unmarshaler.text")
    accessors = tmp_path / "accessors.text"
    accessors.write_text(
        json.dumps(
            {
                "Edges": [],
                "Vertices": [{"Names": ["/Type"], "Methods": [], "Tags": None}],
                "List": {"/Type": "/Type"},
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "enriched.pmgraph.json"

    result = invoke(
        "build",
        "--module-id",
        "example.org/service",
        "--events",
        str(events),
        "--paramtrack-csv",
        str(parameters),
        "--unmarshaler",
        str(unmarshaler),
        "--accessors",
        str(accessors),
        "--output",
        str(output),
    )

    assert result.exit_code == 0, result.output
    assert any(isinstance(node, ParameterNode) for node in load_pmgraph(output).nodes)
    assert "build.paramtrack_caller_association" in result.stderr


def test_stitch_requires_at_least_two_inputs(tmp_path):
    first, _ = write_stitch_inputs(tmp_path)
    output = tmp_path / "application.appgraph.json"

    result = invoke("stitch", str(first), "--output", str(output))

    assert result.exit_code != 0
    assert "at least two PMGraphs" in result.output
    assert not output.exists()


def test_stitch_is_input_order_independent_and_reports_diagnostics(tmp_path):
    first, second = write_stitch_inputs(tmp_path)
    forward = tmp_path / "forward.appgraph.json"
    reverse = tmp_path / "reverse.appgraph.json"

    first_result = invoke("stitch", str(first), str(second), "--output", str(forward))
    second_result = invoke("stitch", str(second), str(first), "--output", str(reverse))

    assert first_result.exit_code == second_result.exit_code == 0
    assert forward.read_bytes() == reverse.read_bytes()
    assert load_appgraph(forward) == load_appgraph(reverse)
    assert "AppGraph" in first_result.stdout
    assert "appgraph.heuristic_match" in first_result.stderr


def test_stitch_can_drop_unmatched_message_nodes(tmp_path):
    first, second = write_stitch_inputs(tmp_path, unmatched=True)
    output = tmp_path / "pruned.appgraph.json"

    result = invoke(
        "stitch",
        str(first),
        str(second),
        "--drop-unmatched",
        "--output",
        str(output),
    )

    assert result.exit_code == 0, result.output
    graph = load_appgraph(output)
    assert len(graph.nodes) == 1
    assert graph.nodes[0].match.status == "matched"


@pytest.mark.parametrize("kind", ("pmgraph", "appgraph", "ctype"))
def test_export_accepts_canonical_and_verified_ctype_inputs(tmp_path, kind):
    input_path, _, expected_nodes = write_graph_inputs(tmp_path)[kind]
    output = tmp_path / f"{kind}.graphml"

    result = invoke("export", str(input_path), "--output", str(output))

    assert result.exit_code == 0, result.output
    graph = ig.Graph.Read_GraphML(str(output))
    assert graph.vcount() == expected_nodes
    assert "GraphML" in result.stdout
    assert result.stderr == ""


@pytest.mark.parametrize("kind", ("pmgraph", "appgraph", "ctype"))
def test_query_accepts_canonical_and_verified_ctype_inputs(tmp_path, kind):
    input_path, search, expected_nodes = write_graph_inputs(tmp_path)[kind]
    output = tmp_path / f"{kind}-query.graphml"

    result = invoke("query", str(input_path), search, "--output", str(output))

    assert result.exit_code == 0, result.output
    graph = ig.Graph.Read_GraphML(str(output))
    assert graph.vcount() == expected_nodes
    assert "GraphML" in result.stdout


@pytest.mark.parametrize(
    ("direction", "expected_names"),
    [
        ("ancestors", {"/a", "/b"}),
        ("descendants", {"/b", "/c"}),
        ("both", {"/a", "/b", "/c"}),
    ],
)
def test_query_selects_requested_influence_direction(
    tmp_path, direction, expected_names
):
    input_path = write_ctype(tmp_path / "types.text")
    output = tmp_path / f"{direction}.graphml"

    result = invoke(
        "query",
        str(input_path),
        "/b",
        "--direction",
        direction,
        "--output",
        str(output),
    )

    assert result.exit_code == 0, result.output
    assert set(ig.Graph.Read_GraphML(str(output)).vs["name"]) == expected_names


def test_query_rejects_no_match_without_writing_output(tmp_path):
    input_path = write_ctype(tmp_path / "types.text")
    output = tmp_path / "missing.graphml"

    result = invoke("query", str(input_path), "missing", "--output", str(output))

    assert result.exit_code != 0
    assert "no vertices match" in result.output
    assert not output.exists()


def test_query_requires_all_matches_for_ambiguity(tmp_path):
    input_path = write_ctype(tmp_path / "types.text")
    rejected = tmp_path / "rejected.graphml"
    accepted = tmp_path / "accepted.graphml"

    ambiguous = invoke("query", str(input_path), "/", "--output", str(rejected))
    all_matches = invoke(
        "query",
        str(input_path),
        "/",
        "--all-matches",
        "--output",
        str(accepted),
    )

    assert ambiguous.exit_code != 0
    assert "3 vertices match" in ambiguous.output
    assert "--all-matches" in ambiguous.output
    assert not rejected.exists()
    assert all_matches.exit_code == 0, all_matches.output
    assert ig.Graph.Read_GraphML(str(accepted)).vcount() == 3


@pytest.mark.parametrize(
    "document",
    [
        {"format": "conftamer.pmgraph", "version": 1},
        {"format": "conftamer.pmgraph"},
        {"version": 2},
    ],
)
def test_export_rejects_unknown_or_incomplete_canonical_discriminators(
    tmp_path, document
):
    input_path = tmp_path / "unknown.json"
    input_path.write_text(json.dumps(document), encoding="utf-8")
    output = tmp_path / "unknown.graphml"

    result = invoke("export", str(input_path), "--output", str(output))

    assert result.exit_code != 0
    assert "unrecognized graph document discriminator" in result.output
    assert not output.exists()


def test_export_rejects_visualization_graphml_input(tmp_path):
    input_path = tmp_path / "visualization.graphml"
    ig.Graph(n=1).write_graphml(str(input_path))
    output = tmp_path / "reexport.graphml"

    result = invoke("export", str(input_path), "--output", str(output))

    assert result.exit_code != 0
    assert "GraphML input is not supported" in result.output
    assert not output.exists()
