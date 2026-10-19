import json
from pathlib import Path
from typing import Any

import igraph
from pydantic import BaseModel

from conftamer.appgraph.models import AppGraph
from conftamer.pmgraph.models import PMGraph
from conftamer.query import Graph, to_igraph


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
    except (ValueError, TypeError) as error:
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


def _check_graphml_identity(value: str) -> None:
    for character in value:
        code = ord(character)
        if character == "\r" or not (
            code in (9, 10)
            or 0x20 <= code <= 0xD7FF
            or 0xE000 <= code <= 0xFFFD
            or 0x10000 <= code <= 0x10FFFF
        ):
            raise ValueError(f"GraphML cannot preserve identity {value!r}")


def write_graphml(graph: Graph, path: str | Path) -> None:
    network = to_igraph(graph)
    nodes = [graph.nodes[name] for name in network.vs["name"]]
    network.vs["kind"] = [node.kind for node in nodes]
    network.vs["node_json"] = [
        node.model_dump_json(ensure_ascii=True) for node in nodes
    ]
    identities = list(graph.nodes)
    if isinstance(graph, PMGraph):
        network["module_id"] = graph.module_id
        identities.append(graph.module_id)
    for value in identities:
        _check_graphml_identity(value)
    with Path(path).open("xb") as output:
        try:
            network.write_graphml(output, prefixattr=True)
        except igraph.InternalError as error:
            raise OSError(f"cannot write GraphML {path}: {error}") from error
