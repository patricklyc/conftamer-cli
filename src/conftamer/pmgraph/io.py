import json
from pathlib import Path

from conftamer.pmgraph.models import PMGraph


def load_pmgraph(path: str | Path) -> PMGraph:
    text = Path(path).read_text(encoding="utf-8")
    graph = PMGraph.model_validate_json(text)
    if json.loads(text) != graph.model_dump(mode="json"):
        raise ValueError("PMGraph document is not canonical")
    return graph


def write_pmgraph(graph: PMGraph, path: str | Path) -> None:
    text = graph.model_dump_json(indent=2, ensure_ascii=False) + "\n"
    Path(path).write_bytes(text.encode("utf-8"))
