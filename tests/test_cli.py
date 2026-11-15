import json
from pathlib import Path

import igraph
import pytest
from typer.testing import CliRunner

from conftamer.cli import app
from conftamer.io import load_appgraph_json
from conftamer.pmgraph.io import load_pmgraph_json

runner = CliRunner()
NORMALIZED_REQUEST = (
    '{"schema_version":1,"kind":"receive_request","pid":1,"context":{},'
    '"message":{"method":"GET","path":"/"}}'
)
QUERY_GRAPH = (
    '{"module_id":"m","nodes":{"c":{"kind":"parameter","key":"z"},'
    '"a":{"kind":"parameter","key":"x"},"b":{"kind":"parameter","key":"y"}},'
    '"edges":[["a","b"],["b","c"]]}'
)
APPGRAPH = (
    '{"nodes":{"frontend::cfg":{"kind":"parameter","key":"timeout"},'
    '"link0":{"kind":"linked_message","api_id":"api","method":"GET",'
    '"pattern":"/items/{id}","status_code":null,"sender_module":"frontend",'
    '"sender_node":"send","receiver_module":"backend","receiver_node":"recv"}},'
    '"edges":[["frontend::cfg","link0"]]}'
)
AMBIGUOUS_APPGRAPH = (
    '{"nodes":{"frontend::p1":{"kind":"parameter","key":"timeout"},'
    '"orders::p2":{"kind":"parameter","key":"timeout"}},"edges":[]}'
)
ROOT = Path(__file__).parents[1]
PMGRAPHS = sorted((ROOT / "examples/pmgraphs").glob("*.pmgraph.json"))
# One request that the client sends and the server receives: one link, and
# nothing left out.
CLIENT = (
    '{"module_id":"client","nodes":{"send":{"kind":"send_request","api_id":"api",'
    '"method":"GET","host":"server:80","path":"/items/1"}},"edges":[]}'
)
SERVER = (
    '{"module_id":"server","nodes":{"recv":{"kind":"receive_request",'
    '"api_id":"api","method":"GET","pattern":"/items/{id}"}},"edges":[]}'
)
# The one message in examples/pmgraphs that no other module receives.
ANALYTICS_DROPPED = {
    "module_id": "frontend",
    "node_id": "send-analytics",
    "reason": "unmatched",
    "message": {
        "kind": "send_request",
        "api_id": "analytics-api",
        "method": "POST",
        "host": "analytics:9000",
        "path": "/events",
        "pattern": None,
        "status_code": None,
    },
}


def _stitch(*arguments: object):
    return runner.invoke(app, ["stitch", *map(str, arguments)])


def _stitched(tmp_path: Path) -> Path:
    output = tmp_path / "app.json"
    result = _stitch(*PMGRAPHS, "--output", output)
    assert result.exit_code == 0, result.output
    return output


def _client_and_server(tmp_path: Path) -> list[Path]:
    paths = [tmp_path / "client.json", tmp_path / "server.json"]
    for path, text in zip(paths, (CLIENT, SERVER)):
        path.write_text(text, encoding="utf-8")
    return paths


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _names(directory: Path) -> list[str]:
    return sorted(path.name for path in directory.iterdir())


def test_build_capture(tmp_path, normalized_scrape_capture):
    output = tmp_path / "graph.json"
    result = runner.invoke(
        app,
        [
            "build",
            str(normalized_scrape_capture),
            "--module-id",
            "scraper",
            "--output",
            str(output),
        ],
    )
    assert result.exit_code == 0, result.output
    assert result.stdout == result.stderr == ""
    graph = load_pmgraph_json(output)
    assert graph.module_id == "scraper"
    assert len(graph.nodes) == 4 and graph.edges == {("n1", "n2")}


def test_build_rejects_raw_capture(tmp_path, raw_scrape_capture):
    output = tmp_path / "graph.json"
    result = runner.invoke(
        app,
        [
            "build",
            str(raw_scrape_capture),
            "--module-id",
            "scraper",
            "--output",
            str(output),
        ],
    )
    assert result.exit_code == 2 and result.stdout == ""
    assert f"{raw_scrape_capture}:1:" in result.stderr
    assert "Traceback" not in result.stderr
    assert not output.exists()


@pytest.mark.parametrize(
    "text, line, existing_output",
    [
        ("{", 1, False),
        (
            NORMALIZED_REQUEST
            + "\n \n"
            + NORMALIZED_REQUEST.replace('"schema_version":1', '"schema_version":2'),
            3,
            False,
        ),
        ("", None, True),
    ],
)
def test_build_reports_errors_without_overwriting(
    tmp_path, text, line, existing_output
):
    source, output = tmp_path / "events.jsonl", tmp_path / "graph.json"
    source.write_text(text, encoding="utf-8")
    if existing_output:
        output.write_bytes(b"keep")
    result = runner.invoke(
        app, ["build", str(source), "--module-id", "m", "--output", str(output)]
    )
    assert result.exit_code == 2
    assert result.stdout == ""
    assert f"Cannot build {source}:" in result.stderr
    if line is not None:
        assert f"{source}:{line}:" in result.stderr
    assert "Traceback" not in result.stderr
    if existing_output:
        assert output.read_bytes() == b"keep"
    else:
        assert not output.exists()


def test_stitch_example_pmgraphs(tmp_path):
    output = tmp_path / "app.json"

    result = _stitch(*PMGRAPHS, "--output", output)

    assert result.exit_code == 0, result.output
    assert result.stdout == result.stderr == ""
    assert _names(tmp_path) == ["app.dropped.json", "app.json"]
    graph = load_appgraph_json(output)
    assert sorted(graph.nodes) == [
        "frontend::param-checkout-timeout",
        "inventory::param-db-pool-size",
        "link0",
        "link1",
        "link2",
        "link3",
        "orders::param-max-retries",
    ]
    assert ("link0", "link1") in graph.edges
    assert _read_json(tmp_path / "app.dropped.json") == [ANALYTICS_DROPPED]


@pytest.mark.parametrize(
    "output_name, report_name",
    [("app", "app.dropped.json"), ("app.graph", "app.graph.dropped.json")],
)
def test_stitch_default_report_name(tmp_path, output_name, report_name):
    result = _stitch(*PMGRAPHS, "--output", tmp_path / output_name)

    assert result.exit_code == 0, result.output
    assert _names(tmp_path) == sorted([output_name, report_name])


def test_stitch_dropped_option_replaces_the_default_report(tmp_path):
    output, report = tmp_path / "app.json", tmp_path / "other.json"

    result = _stitch(*PMGRAPHS, "--output", output, "--dropped", report)

    assert result.exit_code == 0, result.output
    assert result.stdout == result.stderr == ""
    assert _names(tmp_path) == ["app.json", "other.json"]
    assert _read_json(report) == [ANALYTICS_DROPPED]


def test_stitch_writes_an_empty_report(tmp_path):
    inputs = _client_and_server(tmp_path)
    output = tmp_path / "app.json"

    result = _stitch(*inputs, "--output", output)

    assert result.exit_code == 0, result.output
    assert list(load_appgraph_json(output).nodes) == ["link0"]
    assert (tmp_path / "app.dropped.json").read_text(encoding="utf-8") == "[]\n"


def test_stitch_single_input(tmp_path):
    output = tmp_path / "app.json"

    result = _stitch(PMGRAPHS[0], "--output", output)

    assert result.exit_code == 0, result.output
    graph = load_appgraph_json(output)
    assert list(graph.nodes) == ["frontend::param-checkout-timeout"]
    assert graph.edges == set()
    assert [
        (entry["node_id"], entry["reason"])
        for entry in _read_json(tmp_path / "app.dropped.json")
    ] == [
        ("recv-checkout-201", "unmatched"),
        ("send-analytics", "unmatched"),
        ("send-checkout", "unmatched"),
    ]


def test_build_then_stitch_the_tracked_capture(tmp_path, normalized_scrape_capture):
    pmgraph, output = tmp_path / "scraper.pmgraph.json", tmp_path / "app.json"
    built = runner.invoke(
        app,
        [
            "build",
            str(normalized_scrape_capture),
            "--module-id",
            "scraper",
            "--output",
            str(pmgraph),
        ],
    )

    stitched = _stitch(pmgraph, "--output", output)
    exported = runner.invoke(
        app, ["export", str(output), "--output", str(tmp_path / "app.graphml")]
    )

    assert built.exit_code == stitched.exit_code == 0, stitched.output
    # One module, and messages in the same module are never linked.
    assert _read_json(output) == {"nodes": {}, "edges": []}
    report = _read_json(tmp_path / "app.dropped.json")
    assert [
        (entry["module_id"], entry["node_id"], entry["reason"]) for entry in report
    ] == [("scraper", node_id, "unmatched") for node_id in ("n0", "n1", "n2", "n3")]
    assert [entry["message"] for entry in report] == list(
        _read_json(pmgraph)["nodes"].values()
    )
    assert exported.exit_code == 0, exported.output


def test_stitch_prune_unconfigured(tmp_path):
    inputs = _client_and_server(tmp_path)
    output = tmp_path / "app.json"

    result = _stitch(*inputs, "--output", output, "--prune-unconfigured")

    assert result.exit_code == 0, result.output
    assert _read_json(output) == {"nodes": {}, "edges": []}
    assert [entry["reason"] for entry in _read_json(tmp_path / "app.dropped.json")] == [
        "unreachable",
        "unreachable",
    ]


@pytest.mark.parametrize(
    "problem",
    [
        "report-exists",
        "dropped-exists",
        "same-file",
        "report-dangling-symlink",
        "output-dangling-symlink",
    ],
)
def test_stitch_checks_both_paths_before_writing(tmp_path, monkeypatch, problem):
    def fail(*args, **kwargs):
        raise AssertionError("wrote the AppGraph before checking both paths")

    monkeypatch.setattr("conftamer.cli.write_graph_json", fail)
    output, report = tmp_path / "app.json", tmp_path / "app.dropped.json"
    options = []
    if problem == "report-exists":
        report.write_bytes(b"keep")
    elif problem == "dropped-exists":
        report = tmp_path / "other.json"
        report.write_bytes(b"keep")
        options = ["--dropped", report]
    elif problem == "same-file":
        (tmp_path / "sub").mkdir()
        options = ["--dropped", tmp_path / "sub" / ".." / "app.json"]
    elif problem == "report-dangling-symlink":
        report.symlink_to(tmp_path / "nowhere")
    else:
        output.symlink_to(tmp_path / "nowhere")
    before = sorted(tmp_path.iterdir())

    result = _stitch(*PMGRAPHS, "--output", output, *options)

    assert result.exit_code == 2 and result.stdout == ""
    assert "Cannot stitch:" in result.stderr
    assert "Traceback" not in result.stderr
    assert sorted(tmp_path.iterdir()) == before
    assert not output.exists()
    if problem == "same-file":
        assert "must be different files" in result.stderr
    elif problem.endswith("exists"):
        assert report.name in result.stderr
        assert report.read_bytes() == b"keep"


@pytest.mark.parametrize(
    "problem", ["missing-directory", "partial-report", "report-appeared"]
)
def test_stitch_removes_its_files_if_the_report_cannot_be_written(
    tmp_path, monkeypatch, problem
):
    output, report = tmp_path / "app.json", tmp_path / "app.dropped.json"
    options = []
    if problem == "missing-directory":
        options = ["--dropped", tmp_path / "missing-dir" / "dropped.json"]
    elif problem == "partial-report":

        def fail_midway(dropped, path):
            Path(path).write_bytes(b"[")
            raise OSError("disk full")

        monkeypatch.setattr("conftamer.cli.write_dropped_json", fail_midway)
    else:

        def lose_the_race(dropped, path):
            Path(path).write_bytes(b"theirs")
            raise FileExistsError(17, "File exists", str(path))

        monkeypatch.setattr("conftamer.cli.write_dropped_json", lose_the_race)

    result = _stitch(*PMGRAPHS, "--output", output, *options)

    assert result.exit_code == 2 and result.stdout == ""
    assert "Cannot stitch:" in result.stderr
    assert "Traceback" not in result.stderr
    if problem == "partial-report":
        assert "disk full" in result.stderr
    if problem == "report-appeared":
        # Another process created it after the check; it is not ours to remove.
        assert _names(tmp_path) == ["app.dropped.json"]
        assert report.read_bytes() == b"theirs"
    else:
        assert _names(tmp_path) == []


@pytest.mark.parametrize(
    "problem",
    [
        "duplicate",
        "appgraph",
        "report-as-input",
        "missing",
        "missing-output-directory",
        "output-is-a-directory",
        "exists",
    ],
)
def test_stitch_reports_errors_without_overwriting(tmp_path, problem):
    output = tmp_path / "out.json"
    inputs = [PMGRAPHS[0]]
    if problem == "duplicate":
        inputs.append(PMGRAPHS[0])
    elif problem == "appgraph":
        inputs.append(_stitched(tmp_path))
    elif problem == "report-as-input":
        inputs.append(_stitched(tmp_path).with_name("app.dropped.json"))
    elif problem == "missing":
        inputs.append(tmp_path / "absent.json")
    elif problem == "missing-output-directory":
        output = tmp_path / "absent" / "out.json"
    elif problem == "output-is-a-directory":
        output = tmp_path
    else:
        output.write_bytes(b"keep")
    before = sorted(tmp_path.iterdir())

    result = _stitch(*inputs, "--output", output)

    assert result.exit_code == 2 and result.stdout == ""
    assert "Cannot stitch:" in result.stderr
    assert "Traceback" not in result.stderr
    assert sorted(tmp_path.iterdir()) == before
    if problem in ("appgraph", "report-as-input"):
        assert str(inputs[-1]) in result.stderr
    if problem == "exists":
        assert output.read_bytes() == b"keep"


def test_stitch_requires_an_input(tmp_path):
    output = tmp_path / "out.json"

    result = _stitch("--output", output)

    assert result.exit_code == 2 and result.stdout == ""
    assert "Traceback" not in result.stderr
    assert _names(tmp_path) == []


def test_query_prints_the_subgraph_as_graph_json(tmp_path):
    source = tmp_path / "graph.json"
    source.write_text(QUERY_GRAPH, encoding="utf-8")

    result = runner.invoke(app, ["query", str(source), "--node", "b"])

    assert result.exit_code == 0 and result.stderr == ""
    payload = json.loads(result.stdout)
    assert payload == json.loads(QUERY_GRAPH)
    assert list(payload["nodes"]) == ["c", "a", "b"]


def test_query_paths_flag_adds_the_path_list(tmp_path):
    source = tmp_path / "graph.json"
    source.write_text(QUERY_GRAPH, encoding="utf-8")

    result = runner.invoke(app, ["query", str(source), "--node", "c", "--paths"])

    assert result.exit_code == 0 and result.stderr == ""
    assert json.loads(result.stdout) == {
        "subgraph": json.loads(QUERY_GRAPH),
        "paths": [[["a"], ["b"], ["c"]]],
    }


def test_query_default_does_not_enumerate_paths(tmp_path, monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("paths were enumerated")

    monkeypatch.setattr(igraph.Graph, "get_all_simple_paths", fail)
    source = tmp_path / "graph.json"
    source.write_text(QUERY_GRAPH, encoding="utf-8")

    default = runner.invoke(app, ["query", str(source), "--node", "b"])
    with_paths = runner.invoke(app, ["query", str(source), "--node", "b", "--paths"])

    assert default.exit_code == 0, default.output
    assert isinstance(with_paths.exception, AssertionError)


def test_query_appgraph_json(tmp_path):
    source = _stitched(tmp_path)

    result = runner.invoke(app, ["query", str(source), "--node", "link2", "--paths"])

    assert result.exit_code == 0 and result.stderr == ""
    payload = json.loads(result.stdout)
    assert [[node for (node,) in path] for path in payload["paths"]] == [
        ["frontend::param-checkout-timeout", "link0", "link2"],
        ["inventory::param-db-pool-size", "link3", "link2"],
        ["frontend::param-checkout-timeout", "link0", "link1", "link3", "link2"],
        ["orders::param-max-retries", "link1", "link3", "link2"],
    ]
    assert "module_id" not in payload["subgraph"]
    assert len(payload["subgraph"]["nodes"]) == 7


def test_query_by_key_matches_query_by_node(tmp_path):
    source = _stitched(tmp_path)
    key = ["--key", "inventory.max_retries"]

    by_key = runner.invoke(app, ["query", str(source), *key])
    by_key_and_module = runner.invoke(
        app, ["query", str(source), *key, "--module", "orders"]
    )
    by_node = runner.invoke(
        app, ["query", str(source), "--node", "orders::param-max-retries"]
    )

    assert by_key.exit_code == by_key_and_module.exit_code == by_node.exit_code == 0
    assert by_key.stdout == by_key_and_module.stdout == by_node.stdout


def test_query_by_key_on_a_pmgraph(tmp_path):
    source = tmp_path / "graph.json"
    source.write_text(QUERY_GRAPH, encoding="utf-8")

    result = runner.invoke(app, ["query", str(source), "--key", "y", "--module", "m"])

    assert result.exit_code == 0 and result.stderr == ""
    assert json.loads(result.stdout) == json.loads(QUERY_GRAPH)


@pytest.mark.parametrize(
    "options,message",
    [
        (["--key", "nope"], "no parameter has key 'nope'"),
        (
            ["--key", "timeout", "--module", "inventory"],
            "no parameter has key 'timeout' in module 'inventory'",
        ),
        (
            ["--key", "timeout"],
            "key 'timeout' matches 2 parameters: frontend::p1, orders::p2; "
            "narrow it with --module or use --node",
        ),
        ([], "give exactly one of --node and --key"),
        (["--node", "orders::p2", "--key", "timeout"], "give exactly one of"),
        (["--node", "orders::p2", "--module", "orders"], "--module only applies"),
    ],
)
def test_query_by_key_reports_errors(tmp_path, options, message):
    source = tmp_path / "app.json"
    source.write_text(AMBIGUOUS_APPGRAPH, encoding="utf-8")

    result = runner.invoke(app, ["query", str(source), *options])

    assert result.exit_code == 2 and result.stdout == ""
    assert f"Cannot query {source}: {message}" in result.stderr
    assert "Traceback" not in result.stderr


def test_query_by_key_narrowed_by_module(tmp_path):
    source = tmp_path / "app.json"
    source.write_text(AMBIGUOUS_APPGRAPH, encoding="utf-8")

    result = runner.invoke(
        app, ["query", str(source), "--key", "timeout", "--module", "orders"]
    )

    assert result.exit_code == 0
    assert list(json.loads(result.stdout)["nodes"]) == ["orders::p2"]


@pytest.mark.parametrize("text, node", [(QUERY_GRAPH, "b"), (APPGRAPH, "link0")])
def test_query_output_can_be_exported(tmp_path, text, node):
    source, sub, output = (tmp_path / n for n in ("g.json", "sub.json", "sub.graphml"))
    source.write_text(text, encoding="utf-8")

    queried = runner.invoke(app, ["query", str(source), "--node", node])
    sub.write_text(queried.stdout, encoding="utf-8")
    exported = runner.invoke(app, ["export", str(sub), "--output", str(output)])

    assert queried.exit_code == exported.exit_code == 0, exported.output
    assert node in igraph.Graph.Read_GraphML(str(output)).vs["name"]


@pytest.mark.parametrize("text,node", [("{", "x"), (QUERY_GRAPH, "missing")])
def test_query_reports_expected_errors(tmp_path, text, node):
    source = tmp_path / "graph.json"
    source.write_text(text, encoding="utf-8")

    result = runner.invoke(app, ["query", str(source), "--node", node])

    assert result.exit_code == 2 and result.stdout == ""
    assert f"Cannot query {source}:" in result.stderr
    assert "Traceback" not in result.stderr


def test_export_pmgraph_json(tmp_path):
    source, output = tmp_path / "graph.json", tmp_path / "graph.graphml"
    source.write_text(
        '{"module_id":"m","nodes":{"input":{"kind":"parameter","key":"x"},'
        '"output":{"kind":"parameter","key":"y"},'
        '"isolate":{"kind":"parameter","key":"z"}},'
        '"edges":[["input","output"]]}',
        encoding="utf-8",
    )

    result = runner.invoke(app, ["export", str(source), "--output", str(output)])

    assert result.exit_code == 0, result.output
    assert result.stdout == result.stderr == ""
    network = igraph.Graph.Read_GraphML(str(output))
    assert network.vs["name"] == ["input", "output", "isolate"]
    assert network.get_eid("input", "output") >= 0
    assert network.degree("isolate", mode="all") == 0


def test_export_appgraph_json(tmp_path):
    source, output = tmp_path / "app.json", tmp_path / "app.graphml"
    source.write_text(APPGRAPH, encoding="utf-8")

    result = runner.invoke(app, ["export", str(source), "--output", str(output)])

    assert result.exit_code == 0, result.output
    assert result.stdout == result.stderr == ""
    network = igraph.Graph.Read_GraphML(str(output))
    assert network.vs["name"] == ["frontend::cfg", "link0"]
    assert network.vs.find(name="link0")["receiver_module"] == "backend"
    assert network.get_eid("frontend::cfg", "link0") >= 0


def test_export_stitched_appgraph(tmp_path):
    source, output = _stitched(tmp_path), tmp_path / "app.graphml"

    result = runner.invoke(app, ["export", str(source), "--output", str(output)])

    assert result.exit_code == 0, result.output
    network = igraph.Graph.Read_GraphML(str(output))
    assert network.vcount() == 7
    assert network.get_eid("link0", "link1") >= 0


def test_export_and_query_reject_the_dropped_report(tmp_path):
    report = _stitched(tmp_path).with_name("app.dropped.json")
    output = tmp_path / "report.graphml"

    exported = runner.invoke(app, ["export", str(report), "--output", str(output)])
    queried = runner.invoke(app, ["query", str(report), "--node", "send-analytics"])

    # The report is a list of messages, not a graph file.
    assert exported.exit_code == queried.exit_code == 2
    assert exported.stdout == queried.stdout == ""
    assert f"Cannot export {report} to {output}:" in exported.stderr
    assert f"Cannot query {report}:" in queried.stderr
    assert "Traceback" not in exported.stderr + queried.stderr
    assert not output.exists()


@pytest.mark.parametrize(
    "text, existing_output",
    [
        ("{", False),
        ("[]", False),
        ("null", False),
        ('{"nodes":{}}', False),
        pytest.param("[" * 200000, False, id="nested-too-deeply"),
        ('{"module_id":"m","nodes":{},"edges":[]}', True),
    ],
)
def test_export_reports_errors_without_overwriting(tmp_path, text, existing_output):
    source, output = tmp_path / "graph.json", tmp_path / "graph.graphml"
    source.write_text(text, encoding="utf-8")
    if existing_output:
        output.write_bytes(b"keep")
    result = runner.invoke(app, ["export", str(source), "--output", str(output)])

    assert result.exit_code == 2 and result.stdout == ""
    assert f"Cannot export {source} to {output}:" in result.stderr
    assert "Traceback" not in result.stderr
    if existing_output:
        assert output.read_bytes() == b"keep"
    else:
        assert not output.exists()
