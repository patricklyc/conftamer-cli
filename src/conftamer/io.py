import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from conftamer.appgraph.models import AppGraph, DroppedMessage, Graph
from conftamer.igraph_ops import write_graphml
from conftamer.pmgraph.models import PMGraph

__all__ = [
    "graph_to_json",
    "load_appgraph_json",
    "load_graph_json",
    "load_pmgraph_json",
    "write_dropped_json",
    "write_graph_json",
    "write_graphml",
]


def _read(path: str | Path) -> str:
    try:
        return Path(path).read_text(encoding="utf-8")
    except UnicodeDecodeError as error:
        raise ValueError(f"{path}: {error}") from error


def _validate[M: BaseModel](model: type[M], text: str, path: str | Path) -> M:
    try:
        return model.model_validate_json(text, strict=True, extra="forbid")
    except ValueError as error:
        raise ValueError(f"{path}: {error}") from error


def load_pmgraph_json(path: str | Path) -> PMGraph:
    return _validate(PMGraph, _read(path), path)


def load_appgraph_json(path: str | Path) -> AppGraph:
    return _validate(AppGraph, _read(path), path)


def load_graph_json(path: str | Path) -> Graph:
    """Load a PMGraph or AppGraph, telling them apart by ``module_id``."""
    text = _read(path)
    try:
        is_pmgraph = "module_id" in json.loads(text)
    except (ValueError, TypeError, RecursionError) as error:
        raise ValueError(f"{path}: {error}") from error
    if is_pmgraph:
        return _validate(PMGraph, text, path)
    return _validate(AppGraph, text, path)


def graph_to_json(graph: Graph) -> dict[str, Any]:
    payload = graph.model_dump(mode="json")
    payload["edges"] = [list(edge) for edge in sorted(graph.edges)]
    return payload


def write_graph_json(graph: Graph, path: str | Path) -> None:
    text = json.dumps(graph_to_json(graph), ensure_ascii=False, indent=2) + "\n"
    with Path(path).open("x", encoding="utf-8", newline="\n") as output:
        output.write(text)


def write_dropped_json(dropped: Iterable[DroppedMessage], path: str | Path) -> None:
    """Write the messages stitching dropped as a JSON list, in the given order."""
    payload = [message.model_dump(mode="json") for message in dropped]
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    with Path(path).open("x", encoding="utf-8", newline="\n") as output:
        output.write(text)
