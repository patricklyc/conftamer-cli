from pathlib import Path

import igraph as ig
import pytest
from typer.testing import CliRunner

from conftamer.main import app

runner = CliRunner()


def write_csv(tmp_path: Path) -> Path:
    input_path = tmp_path / "edges.csv"
    input_path.write_text(
        "\n".join(
            [
                "Parameter,service,timeout,Send,service,inventory,GET /items,201",
                "Parameter,service,retries,Send,service,billing,POST /charge,503",
            ]
        )
        + "\n"
    )
    return input_path


def output_path(input_path: Path) -> Path:
    return Path(f"{input_path}.graphml")


def read_output(input_path: Path) -> ig.Graph:
    return ig.Graph.Read_GraphML(str(output_path(input_path)))


def test_subgraph_uses_a_unique_attribute_match_without_prompting(tmp_path):
    input_path = write_csv(tmp_path)

    result = runner.invoke(app, ["subgraph", str(input_path), "TIMEOUT"])

    assert result.exit_code == 0, result.output
    assert "Select a node" not in result.output
    assert output_path(input_path).is_file()
    assert set(read_output(input_path).vs["label"]) == {
        "service timeout",
        "service GET /items",
    }


def test_subgraph_interprets_an_integer_query_as_a_node_id(tmp_path):
    input_path = write_csv(tmp_path)

    result = runner.invoke(app, ["subgraph", str(input_path), " 2 "])

    assert result.exit_code == 0, result.output
    assert "Select a node" not in result.output
    assert set(read_output(input_path).vs["label"]) == {
        "service retries",
        "service POST /charge",
    }


def test_subgraph_displays_full_ambiguous_choices_and_uses_selection(tmp_path):
    input_path = write_csv(tmp_path)

    result = runner.invoke(
        app,
        ["subgraph", str(input_path), "service"],
        input="3\n",
    )

    assert result.exit_code == 0, result.output
    assert "Multiple nodes match 'service':" in result.output
    first_choice = result.output.split("1. node 0:", maxsplit=1)[1].split(
        "2. node 1:", maxsplit=1
    )[0]
    for attribute in (
        "label='service timeout'",
        "node_type='Parameter'",
        "param_name='timeout'",
    ):
        assert attribute in first_choice

    second_choice = result.output.split("2. node 1:", maxsplit=1)[1].split(
        "3. node 2:", maxsplit=1
    )[0]
    for attribute in (
        "api_id='inventory'",
        "label='service GET /items'",
        "node_type='Send'",
        "request_id='GET /items'",
        "response_code=201",
    ):
        assert attribute in second_choice
    assert "Select a node [1-4]" in result.output
    assert set(read_output(input_path).vs["label"]) == {
        "service retries",
        "service POST /charge",
    }


def test_subgraph_exits_without_output_when_no_node_matches(tmp_path):
    input_path = write_csv(tmp_path)

    result = runner.invoke(app, ["subgraph", str(input_path), "missing"])

    assert result.exit_code == 1
    assert "error: no nodes match 'missing'" in result.output
    assert not output_path(input_path).exists()


@pytest.mark.parametrize(
    ("query_arguments", "node_id"), [(["4"], 4), (["--", "-1"], -1)]
)
def test_subgraph_exits_without_output_for_out_of_range_node_id(
    tmp_path, query_arguments, node_id
):
    input_path = write_csv(tmp_path)

    result = runner.invoke(app, ["subgraph", str(input_path), *query_arguments])

    assert result.exit_code == 1
    assert (
        f"error: node id {node_id} is out of range for graph with 4 nodes"
        in result.output
    )
    assert not output_path(input_path).exists()


def test_subgraph_exits_without_output_for_blank_query(tmp_path):
    input_path = write_csv(tmp_path)

    result = runner.invoke(app, ["subgraph", str(input_path), "   "])

    assert result.exit_code == 1
    assert "error: search query must not be empty" in result.output
    assert not output_path(input_path).exists()


def test_subgraph_exits_without_output_when_ambiguous_selection_is_unavailable(
    tmp_path,
):
    input_path = write_csv(tmp_path)

    result = runner.invoke(app, ["subgraph", str(input_path), "service"], input="")

    assert result.exit_code == 1
    assert "error: a selection is required when multiple nodes match" in result.output
    assert not output_path(input_path).exists()


def test_subgraph_exits_without_output_for_out_of_range_selection(tmp_path):
    input_path = write_csv(tmp_path)

    result = runner.invoke(
        app,
        ["subgraph", str(input_path), "service"],
        input="5\n",
    )

    assert result.exit_code == 1
    assert "error: selection must be between 1 and 4" in result.output
    assert not output_path(input_path).exists()


def test_subgraph_help_accepts_query_instead_of_node_id():
    result = runner.invoke(app, ["subgraph", "--help"])

    assert result.exit_code == 0, result.output
    assert "{query}" in result.output
    assert "{node_id}" not in result.output
