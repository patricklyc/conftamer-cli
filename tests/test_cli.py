import json
from pathlib import Path

import igraph
import pytest
from typer.testing import CliRunner

from conftamer.cli import app
from conftamer.io import load_appgraph_json, load_pmgraph_json

runner = CliRunner()
ROOT = Path(__file__).parents[1]
CAPTURE = ROOT / "examples/contexttrack/prometheus/scrape-ok.jsonl"
PMGRAPHS = sorted((ROOT / "examples/pmgraphs").glob("*.pmgraph.json"))
QUERY_GRAPH = (
    '{"module_id":"m","nodes":{"c":{"kind":"parameter","key":"z"},'
    '"a":{"kind":"parameter","key":"x"},"b":{"kind":"parameter","key":"y"}},'
    '"edges":[["a","b"],["b","c"]]}'
)


def _stitched(tmp_path: Path) -> Path:
    output = tmp_path / "app.json"
    result = runner.invoke(
        app, ["stitch", *map(str, PMGRAPHS), "--output", str(output)]
    )
    assert result.exit_code == 0, result.output
    return output


def test_build_capture(tmp_path):
    output = tmp_path / "graph.json"
    result = runner.invoke(
        app, ["build", str(CAPTURE), "--module-id", "scraper", "--output", str(output)]
    )
    assert result.exit_code == 0, result.output
    assert result.stdout == result.stderr == ""
    graph = load_pmgraph_json(output)
    assert graph.module_id == "scraper"
    assert len(graph.nodes) == 4 and graph.edges == {("n1", "n2")}


@pytest.mark.parametrize(
    "text, existing_output", [("{", False), ("null", False), ("", True)]
)
def test_build_reports_errors_without_overwriting(tmp_path, text, existing_output):
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
    assert "Traceback" not in result.stderr
    if existing_output:
        assert output.read_bytes() == b"keep"
    else:
        assert not output.exists()


def test_stitch_example_pmgraphs(tmp_path):
    output = _stitched(tmp_path)

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


@pytest.mark.parametrize("problem", ["duplicate", "appgraph", "missing", "exists"])
def test_stitch_reports_errors_without_overwriting(tmp_path, problem):
    output = tmp_path / "out.json"
    inputs = [str(PMGRAPHS[0])]
    if problem == "duplicate":
        inputs.append(str(PMGRAPHS[0]))
    elif problem == "appgraph":
        inputs.append(str(_stitched(tmp_path)))
    elif problem == "missing":
        inputs.append(str(tmp_path / "absent.json"))
    else:
        output.write_bytes(b"keep")

    result = runner.invoke(app, ["stitch", *inputs, "--output", str(output)])

    assert result.exit_code == 2 and result.stdout == ""
    assert "Cannot stitch:" in result.stderr
    assert "Traceback" not in result.stderr
    if problem == "exists":
        assert output.read_bytes() == b"keep"
    else:
        assert not output.exists()


def test_query_pmgraph_json(tmp_path):
    source = tmp_path / "graph.json"
    source.write_text(QUERY_GRAPH, encoding="utf-8")

    result = runner.invoke(app, ["query", str(source), "--node", "c"])

    assert result.exit_code == 0 and result.stderr == ""
    assert json.loads(result.stdout) == {
        "subgraph": json.loads(QUERY_GRAPH) | {"edges": [["a", "b"], ["b", "c"]]},
        "paths": [["a", "b", "c"]],
        "truncated": False,
    }


def test_query_appgraph_json_with_path_limit(tmp_path):
    source = _stitched(tmp_path)

    result = runner.invoke(
        app, ["query", str(source), "--node", "link2", "--path-limit", "2"]
    )

    assert result.exit_code == 0 and result.stderr == ""
    payload = json.loads(result.stdout)
    assert payload["paths"] == [
        ["frontend::param-checkout-timeout", "link0", "link2"],
        ["inventory::param-db-pool-size", "link3", "link2"],
    ]
    assert payload["truncated"] is True
    assert "module_id" not in payload["subgraph"]
    assert len(payload["subgraph"]["nodes"]) == 7


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
    assert network.vs["name"] == ["input", "isolate", "output"]
    assert network.get_eid("input", "output") >= 0
    assert network.degree("isolate", mode="all") == 0


def test_export_appgraph_json(tmp_path):
    source, output = _stitched(tmp_path), tmp_path / "app.graphml"

    result = runner.invoke(app, ["export", str(source), "--output", str(output)])

    assert result.exit_code == 0, result.output
    network = igraph.Graph.Read_GraphML(str(output))
    assert network.vcount() == 7
    assert network.get_eid("link0", "link1") >= 0


@pytest.mark.parametrize(
    "text, existing_output",
    [("{", False), ('{"module_id":"m","nodes":{},"edges":[]}', True)],
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
