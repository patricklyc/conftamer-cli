import copy
import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from conftamer.ctype_graph import CTypeEdge, CTypeGraph, CTypeNode, load_ctype_graph

EXAMPLES = Path(__file__).parents[2] / "examples" / "paramtrack" / "static"


def write_document(tmp_path: Path, document: object, name: str = "graph.text") -> Path:
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, separators=(",", ":")), encoding="utf-8")
    return path


def complete_document() -> dict[str, Any]:
    return {
        "Edges": [
            {
                "Source": "/root.Type",
                "Target": "/child.Type",
                "Properties": {
                    "Attributes": {"ignored": "first"},
                    "Weight": 99,
                    "Data": [
                        ["Field:z", "Tail"],
                        None,
                        [],
                        ["Field:a"],
                        ["Field:z", "Tail"],
                    ],
                    "Future": "ignored",
                },
                "UnknownEdge": True,
            },
            {
                "Source": "/child.Type",
                "Target": "/root.Type",
                "Properties": {"Attributes": {}, "Weight": 0, "Data": None},
            },
        ],
        "Vertices": [
            {
                "Names": [
                    "/root.Type",
                    "/alias.Z",
                    "/alias.A",
                    "/alias.Z",
                    "/root.Type",
                ],
                "Methods": ["method.Z", "method.A", "method.Z"],
                "Tags": {"z": "yaml:z", "a": "yaml:a"},
                "UnknownVertex": {"ignored": True},
            },
            {"Names": ["/child.Type"], "Methods": [], "Tags": None},
            {"Names": ["/isolated.Type"], "Methods": [], "Tags": {}},
        ],
        "List": {
            "/root.Type": "/root.Type",
            "/alias.Z": "/root.Type",
            "/alias.A": "/root.Type",
            "/child.Type": "/child.Type",
            "/isolated.Type": "/isolated.Type",
            "/extra.Resolved": "/root.Type",
            "/extra.Unresolved": "/outside.Type",
            "/extra.AliasTarget": "/alias.A",
        },
        "UnknownTopLevel": ["ignored"],
    }


def minimal_document() -> dict[str, Any]:
    return {
        "Edges": [],
        "Vertices": [
            {
                "Names": ["/canonical.Type", "/alias.Type"],
                "Methods": [],
                "Tags": None,
            }
        ],
        "List": {
            "/canonical.Type": "/canonical.Type",
            "/alias.Type": "/canonical.Type",
        },
    }


def test_loads_complete_one_line_document_and_normalizes_semantics(tmp_path):
    path = write_document(tmp_path, complete_document())
    assert b"\n" not in path.read_bytes()

    graph = load_ctype_graph(path)

    assert graph.model_dump(mode="json") == {
        "nodes": [
            {
                "id": "/child.Type",
                "names": ["/child.Type"],
                "methods": [],
                "tags": None,
            },
            {
                "id": "/isolated.Type",
                "names": ["/isolated.Type"],
                "methods": [],
                "tags": {},
            },
            {
                "id": "/root.Type",
                "names": ["/root.Type", "/alias.A", "/alias.Z"],
                "methods": ["method.A", "method.Z"],
                "tags": {"a": "yaml:a", "z": "yaml:z"},
            },
        ],
        "edges": [
            {
                "source": "/child.Type",
                "target": "/root.Type",
                "ast_paths": [],
            },
            {
                "source": "/root.Type",
                "target": "/child.Type",
                "ast_paths": [[], ["Field:a"], ["Field:z", "Tail"]],
            },
        ],
        "name_to_node": {
            "/alias.A": "/root.Type",
            "/alias.Z": "/root.Type",
            "/child.Type": "/child.Type",
            "/extra.Resolved": "/root.Type",
            "/isolated.Type": "/isolated.Type",
            "/root.Type": "/root.Type",
        },
    }


def test_unknown_and_generic_properties_do_not_change_normalized_graph(tmp_path):
    first = complete_document()
    second = copy.deepcopy(first)
    second["UnknownTopLevel"] = {"different": "value"}
    second["Vertices"][0]["UnknownVertex"] = "different"
    second["Edges"][0]["Properties"]["Attributes"] = {"different": "value"}
    second["Edges"][0]["Properties"]["Weight"] = -1

    assert load_ctype_graph(
        write_document(tmp_path / "one", first)
    ) == load_ctype_graph(write_document(tmp_path / "two", second))


def test_models_are_canonical_and_nested_mappings_are_immutable(tmp_path):
    graph = load_ctype_graph(write_document(tmp_path, complete_document()))
    root = next(node for node in graph.nodes if node.id == "/root.Type")

    with pytest.raises(TypeError):
        graph.name_to_node["/new.Type"] = "/root.Type"  # ty: ignore[invalid-assignment]
    assert root.tags is not None
    with pytest.raises(TypeError):
        root.tags["new"] = "tag"  # ty: ignore[invalid-assignment]
    with pytest.raises(ValidationError):
        CTypeNode(
            id="/root.Type",
            names=("/root.Type",),
            methods=(),
            tags=None,
            unknown=True,  # ty: ignore[unknown-argument]
        )
    with pytest.raises(ValidationError, match="methods must be in canonical order"):
        CTypeNode(
            id="/root.Type",
            names=("/root.Type",),
            methods=("z", "a"),
            tags=None,
        )
    with pytest.raises(ValidationError, match="AST paths must be in canonical order"):
        CTypeEdge(
            source="/root.Type",
            target="/child.Type",
            ast_paths=(("z",), ("a",)),
        )


def test_models_are_strict_frozen_and_reject_dangling_endpoints():
    tags = {"json": "name"}
    node = CTypeNode(id="/a", names=("/a",), methods=(), tags=tags)
    tags["json"] = "changed"

    assert node.tags == {"json": "name"}
    with pytest.raises(ValidationError, match="frozen"):
        node.id = "/changed"  # ty: ignore[invalid-assignment]
    with pytest.raises(ValidationError):
        CTypeNode(
            id=1,  # ty: ignore[invalid-argument-type]
            names=("/a",),
            methods=(),
            tags=None,
        )
    with pytest.raises(ValidationError, match="edge endpoints"):
        CTypeGraph(
            nodes=(node,),
            edges=(CTypeEdge(source="/a", target="/missing", ast_paths=()),),
            name_to_node={"/a": "/a"},
        )


def test_graph_model_rejects_noncanonical_collections():
    first = CTypeNode(id="/a", names=("/a",), methods=(), tags=None)
    second = CTypeNode(id="/b", names=("/b",), methods=(), tags=None)

    with pytest.raises(ValidationError, match="nodes must be in canonical order"):
        CTypeGraph(
            nodes=(second, first),
            edges=(),
            name_to_node={"/a": "/a", "/b": "/b"},
        )


@pytest.mark.parametrize(
    ("mapping", "message"),
    [
        ({"/canonical.Type": "/canonical.Type"}, "missing.*alias.Type"),
        (
            {
                "/canonical.Type": "/canonical.Type",
                "/alias.Type": "/outside.Type",
            },
            "mapping.*alias.Type",
        ),
    ],
)
def test_rejects_missing_or_conflicting_represented_name_mappings(
    tmp_path, mapping, message
):
    document = minimal_document()
    document["List"] = mapping

    with pytest.raises(ValueError, match=message):
        load_ctype_graph(write_document(tmp_path, document))


def test_rejects_alias_represented_by_multiple_vertices(tmp_path):
    document = minimal_document()
    document["Vertices"].append(
        {"Names": ["/other.Type", "/alias.Type"], "Methods": [], "Tags": None}
    )
    document["List"]["/other.Type"] = "/other.Type"

    with pytest.raises(ValueError, match="represented name.*alias.Type"):
        load_ctype_graph(write_document(tmp_path, document))


@pytest.mark.parametrize(
    ("vertices", "edges", "mapping", "message"),
    [
        (
            [
                {"Names": ["/same.Type"], "Methods": [], "Tags": None},
                {"Names": ["/same.Type"], "Methods": [], "Tags": None},
            ],
            [],
            {"/same.Type": "/same.Type"},
            "vertex IDs must be unique",
        ),
        (
            [{"Names": ["/source.Type"], "Methods": [], "Tags": None}],
            [
                {
                    "Source": "/source.Type",
                    "Target": "/missing.Type",
                    "Properties": {"Data": []},
                }
            ],
            {"/source.Type": "/source.Type"},
            "edge endpoints",
        ),
        (
            [
                {"Names": ["/source.Type"], "Methods": [], "Tags": None},
                {"Names": ["/target.Type"], "Methods": [], "Tags": None},
            ],
            [
                {
                    "Source": "/source.Type",
                    "Target": "/target.Type",
                    "Properties": {"Data": []},
                },
                {
                    "Source": "/source.Type",
                    "Target": "/target.Type",
                    "Properties": {"Data": [["other"]]},
                },
            ],
            {
                "/source.Type": "/source.Type",
                "/target.Type": "/target.Type",
            },
            "edge endpoint pairs must be unique",
        ),
    ],
)
def test_rejects_duplicate_vertices_missing_endpoints_and_duplicate_edges(
    tmp_path, vertices, edges, mapping, message
):
    document = {"Vertices": vertices, "Edges": edges, "List": mapping}

    with pytest.raises(ValueError, match=message):
        load_ctype_graph(write_document(tmp_path, document))


@pytest.mark.parametrize(
    "document",
    [
        {"Vertices": [], "Edges": []},
        {"Vertices": "wrong", "Edges": [], "List": {}},
        {
            "Vertices": [{"Names": [], "Methods": [], "Tags": None}],
            "Edges": [],
            "List": {},
        },
        {
            "Vertices": [{"Names": ["/type"], "Methods": [""], "Tags": None}],
            "Edges": [],
            "List": {"/type": "/type"},
        },
        {
            "Vertices": [{"Names": ["/type"], "Methods": [], "Tags": ["wrong"]}],
            "Edges": [],
            "List": {"/type": "/type"},
        },
        {
            "Vertices": [{"Names": ["/type"], "Methods": [], "Tags": None}],
            "Edges": [
                {
                    "Source": "/type",
                    "Target": "/type",
                    "Properties": {"Data": [1]},
                }
            ],
            "List": {"/type": "/type"},
        },
    ],
)
def test_rejects_invalid_raw_contracts(tmp_path, document):
    with pytest.raises(ValidationError):
        load_ctype_graph(write_document(tmp_path, document))


def test_rejects_graphviz_and_blocked_graphml_inputs(tmp_path):
    with pytest.raises(ValueError, match="Graphviz.*not supported"):
        load_ctype_graph(EXAMPLES / "unmarshaler_subgraph.gv")

    graphviz = tmp_path / "graph.data"
    graphviz.write_text("strict digraph { a -> b }", encoding="utf-8")
    with pytest.raises(ValueError, match="Graphviz.*not supported"):
        load_ctype_graph(graphviz)

    graphml = tmp_path / "graph.graphml"
    graphml.write_text("<graphml/>", encoding="utf-8")
    with pytest.raises(ValueError, match="GraphML.*not supported"):
        load_ctype_graph(graphml)


def test_real_ctype_graph_counts_and_aliases():
    unmarshaler = load_ctype_graph(EXAMPLES / "unmarshaler_subgraph.text")
    accessors = load_ctype_graph(EXAMPLES / "accessors.text")

    assert (
        len(unmarshaler.nodes),
        len(unmarshaler.edges),
        len(unmarshaler.name_to_node),
        sum(len(node.names) - 1 for node in unmarshaler.nodes),
    ) == (57, 90, 58, 1)
    assert (
        len(accessors.nodes),
        len(accessors.edges),
        len(accessors.name_to_node),
        sum(len(node.names) - 1 for node in accessors.nodes),
    ) == (582, 822, 595, 13)


def test_manager_ctypes_resolve_only_through_accessors():
    unmarshaler = load_ctype_graph(EXAMPLES / "unmarshaler_subgraph.text")
    accessors = load_ctype_graph(EXAMPLES / "accessors.text")
    manager_ctypes = {
        "/discovery.Manager",
        "/scrape.Manager",
        "/scrape.scrapeLoop",
        "/scrape.targetScraper",
    }

    assert manager_ctypes.isdisjoint(unmarshaler.name_to_node)
    assert manager_ctypes <= accessors.name_to_node.keys()
