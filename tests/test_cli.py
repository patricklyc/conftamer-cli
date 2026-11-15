import json
from pathlib import Path

import igraph
import pytest
from typer.testing import CliRunner

from conftamer.appgraph.stitch import stitch
from conftamer.cli import app
from conftamer.io import write_graph_json
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


def _stitched(tmp_path: Path) -> Path:
    # No stitch command yet: build the AppGraph file through the library.
    output = tmp_path / "app.json"
    write_graph_json(stitch(load_pmgraph_json(path) for path in PMGRAPHS), output)
    return output


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
