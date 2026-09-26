import json
from pathlib import Path

from conftamer.pmgraph.models import PMGraph


def load_pmgraph_json(path: str | Path) -> PMGraph:
    try:
        return PMGraph.model_validate_json(
            Path(path).read_text(encoding="utf-8"), strict=True, extra="forbid"
        )
    except ValueError as error:
        raise ValueError(f"{path}: {error}") from error


def write_pmgraph_json(graph: PMGraph, path: str | Path) -> None:
    payload = graph.model_dump(mode="json")
    payload["edges"] = [list(edge) for edge in sorted(graph.edges)]
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    with Path(path).open("x", encoding="utf-8", newline="\n") as output:
        output.write(text)
