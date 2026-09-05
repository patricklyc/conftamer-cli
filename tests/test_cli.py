import importlib
import json
import subprocess
import sys
import tomllib
from pathlib import Path

import igraph as ig
import pytest
from typer.testing import CliRunner

runner = CliRunner()
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def invoke(*arguments: str):
    app = importlib.import_module("conftamer.cli").app
    return runner.invoke(app, list(arguments))


def write_ctype(path: Path) -> Path:
    document = {
        "Edges": [
            {
                "Source": "/root.Type",
                "Target": "/child.Type",
                "Properties": {"Data": [["Field:child"]]},
            }
        ],
        "Vertices": [
            {
                "Names": ["/child.Type"],
                "Methods": [],
                "Tags": None,
            },
            {
                "Names": ["/root.Type", "/alias.Type"],
                "Methods": ["Method"],
                "Tags": {"json": 'json:"root"'},
            },
        ],
        "List": {
            "/alias.Type": "/root.Type",
            "/child.Type": "/child.Type",
            "/root.Type": "/root.Type",
        },
    }
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


@pytest.mark.parametrize("arguments", [("--help",), ("export", "--help")])
def test_help_exposes_only_export(arguments):
    result = invoke(*arguments)

    assert result.exit_code == 0, result.output
    if arguments == ("--help",):
        assert "export" in result.stdout
        for removed in ("build", "stitch", "query"):
            assert removed not in result.stdout


@pytest.mark.parametrize("removed", ["build", "stitch", "query"])
def test_removed_commands_are_absent(removed):
    result = invoke(removed, "--help")

    assert result.exit_code != 0
    assert "No such command" in result.output


def test_export_writes_readable_graphml_and_summary(tmp_path):
    input_path = write_ctype(tmp_path / "types.text")
    output = tmp_path / "types.graphml"

    result = invoke("export", str(input_path), "--output", str(output))

    assert result.exit_code == 0, result.output
    graph = ig.Graph.Read_GraphML(str(output))
    assert graph.is_directed()
    assert (graph.vcount(), graph.ecount()) == (2, 1)
    assert graph.vs.find(name="/root.Type")["aliases"] == "/alias.Type"
    assert graph.es[0]["ast_paths"] == "Field:child"
    assert result.stderr == ""
    assert result.stdout == f"Wrote GraphML with 2 vertices and 1 edge to {output}\n"


def test_summary_uses_singular_vertex_and_plural_edges(tmp_path):
    input_path = write_ctype(tmp_path / "types.text")
    document = json.loads(input_path.read_text(encoding="utf-8"))
    document["Edges"] = []
    document["Vertices"] = document["Vertices"][:1]
    document["List"] = {"/child.Type": "/child.Type"}
    input_path.write_text(json.dumps(document), encoding="utf-8")
    output = tmp_path / "types.graphml"

    result = invoke("export", str(input_path), "--output", str(output))

    assert result.exit_code == 0, result.output
    assert result.stdout == f"Wrote GraphML with 1 vertex and 0 edges to {output}\n"


@pytest.mark.parametrize(
    ("name", "content", "error"),
    [
        ("malformed.text", "{", "error:"),
        ("unrelated.text", "{}", "error:"),
        ("types.gv", "{}", "Graphviz CType input is not supported"),
        ("types.graphml", "{}", "GraphML CType input is not supported"),
    ],
)
def test_invalid_or_unsupported_input_creates_no_output(tmp_path, name, content, error):
    input_path = tmp_path / name
    input_path.write_text(content, encoding="utf-8")
    output = tmp_path / "output.graphml"

    result = invoke("export", str(input_path), "--output", str(output))

    assert result.exit_code != 0
    assert "error:" in result.stderr
    assert error in result.stderr
    assert len(result.stderr.splitlines()) == 1
    assert not output.exists()


def test_missing_input_creates_no_output(tmp_path):
    output = tmp_path / "output.graphml"

    result = invoke(
        "export",
        str(tmp_path / "missing.text"),
        "--output",
        str(output),
    )

    assert result.exit_code != 0
    assert "error:" in result.stderr
    assert not output.exists()


def test_installed_entry_point_targets_app():
    project = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text())

    assert project["project"]["scripts"]["conftamer"] == "conftamer.cli:app"


def test_cli_runs_as_a_packaging_entry_script():
    result = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "src/conftamer/cli.py"), "--help"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "export" in result.stdout
    for removed in ("build", "stitch", "query"):
        assert removed not in result.stdout
