"""Serialize and parse PMGraph <-> GraphML.

GraphML represents every node with one flat attribute schema: the union of
all fields across ``Parameter`` and ``Message``. A given node only carries
the ``<data>`` elements for the fields that apply to it (unset fields are
simply absent, not written as empty). ``kind`` is always present and is
what a reader switches on to know which fields to expect.

Node IDs in the emitted GraphML are prefixed with the PMGraph's
``module_id`` (``"{module_id}::{node_id}"``), so IDs stay globally unique
once multiple per-module GraphML files are later combined into an
AppGraph. ``module_id`` is also recorded as a graph-level attribute so it
can be recovered on its own when reading a single file back.

This module is hand-written (stdlib ``xml.etree.ElementTree``) rather than
routed through a general graph library, so the on-disk schema is fully
explicit and there is no intermediate graph-object semantics to account
for when checking round-trip accuracy.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from conftamer.pmgraph.models import Message, Node, Parameter, PMGraph

GRAPHML_NS = "http://graphml.graphdrawing.org/xmlns"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
SCHEMA_LOCATION = (
    "http://graphml.graphdrawing.org/xmlns "
    "http://graphml.graphdrawing.org/xmlns/1.0/graphml.xsd"
)

NODE_ID_SEPARATOR = "::"

# (attribute name, GraphML attr.type), in declaration order.
# "kind" is common to every node; the rest are the union of Parameter's
# and Message's fields, each optional on any given node.
NODE_ATTRIBUTES: list[tuple[str, str]] = [
    ("kind", "string"),
    ("key", "string"),
    ("api_id", "string"),
    ("method", "string"),
    ("host", "string"),
    ("path", "string"),
    ("pattern", "string"),
    ("status_code", "int"),
]

GRAPH_ATTRIBUTES: list[tuple[str, str]] = [
    ("module_id", "string"),
]

# Message fields the pydantic model requires the caller to supply even
# though their value may be None (i.e. no default in the model). These
# must be backfilled with None on read if the corresponding <data>
# element was omitted from the file.
MESSAGE_REQUIRED_NULLABLE_FIELDS = ("api_id",)


def _prefixed_id(module_id: str, node_id: str) -> str:
    return f"{module_id}{NODE_ID_SEPARATOR}{node_id}"

#Used when converting from graphML back to PMGraph
def _strip_prefix(module_id: str, prefixed_id: str) -> str:
    prefix = f"{module_id}{NODE_ID_SEPARATOR}"
    if not prefixed_id.startswith(prefix):
        raise ValueError(
            f"Node id {prefixed_id!r} is not prefixed with module_id {module_id!r}"
        )
    return prefixed_id[len(prefix) :]


def _node_attributes(node: Node) -> dict[str, object]:
    """This node's fields as a flat dict, omitting any that are None."""
    if isinstance(node, Parameter):
        return {"kind": node.kind, "key": node.key}
    if isinstance(node, Message):
        attrs: dict[str, object] = {"kind": node.kind, "method": node.method}
        for field in ("api_id", "host", "path", "pattern", "status_code"):
            value = getattr(node, field)
            if value is not None: #Just Omit none values, can be changed if needed
                attrs[field] = value
        return attrs
    raise TypeError(f"Unknown PMGraph node type: {type(node)!r}")


def pmgraph_to_graphml_element(graph: PMGraph) -> ET.Element:
    """Build the ``ElementTree`` for ``graph``.

    Exposed separately from ``pmgraph_to_graphml`` so tests (and callers who
    want the tree rather than a serialized string) can inspect it directly.
    """
    ET.register_namespace("", GRAPHML_NS)

    root = ET.Element(
        f"{{{GRAPHML_NS}}}graphml",
        {f"{{{XSI_NS}}}schemaLocation": SCHEMA_LOCATION},
    )

    key_ids: dict[tuple[str, str], str] = {}

    def declare_key(name: str, attr_type: str, for_: str) -> None:
        key_ids[(for_, name)] = name
        ET.SubElement(
            root,
            f"{{{GRAPHML_NS}}}key",
            {"id": name, "for": for_, "attr.name": name, "attr.type": attr_type},
        )

    for name, attr_type in GRAPH_ATTRIBUTES:
        declare_key(name, attr_type, "graph")
    for name, attr_type in NODE_ATTRIBUTES:
        declare_key(name, attr_type, "node")

    graph_el = ET.SubElement(
        root,
        f"{{{GRAPHML_NS}}}graph",
        {"id": graph.module_id, "edgedefault": "directed"},
    )

    module_id_data = ET.SubElement(
        graph_el, f"{{{GRAPHML_NS}}}data", {"key": key_ids[("graph", "module_id")]}
    )
    module_id_data.text = graph.module_id

    for node_id in sorted(graph.nodes):
        node = graph.nodes[node_id]
        node_el = ET.SubElement(
            graph_el,
            f"{{{GRAPHML_NS}}}node",
            {"id": _prefixed_id(graph.module_id, node_id)},
        )
        for attr_name, value in _node_attributes(node).items():
            data_el = ET.SubElement(
                node_el, f"{{{GRAPHML_NS}}}data", {"key": key_ids[("node", attr_name)]}
            )
            data_el.text = str(value)

    for source, target in sorted(graph.edges):
        ET.SubElement(
            graph_el,
            f"{{{GRAPHML_NS}}}edge",
            {
                "source": _prefixed_id(graph.module_id, source),
                "target": _prefixed_id(graph.module_id, target),
            },
        )

    return root


def pmgraph_to_graphml(graph: PMGraph) -> str:
    """Serialize ``graph`` to a GraphML XML document, as a string."""
    root = pmgraph_to_graphml_element(graph)
    ET.indent(root, space="  ")
    body = ET.tostring(root, encoding="unicode")
    return '<?xml version="1.0" encoding="utf-8"?>\n' + body


def write_graphml(graph: PMGraph, path: str) -> None:
    """Serialize ``graph`` to GraphML and write it to ``path``."""
    root = pmgraph_to_graphml_element(graph)
    ET.indent(root, space="  ")
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)

#Usefull for testing
def graphml_to_pmgraph(xml_text: str) -> PMGraph:
    """Parse a GraphML document (as produced by this module) back into a PMGraph."""
    root = ET.fromstring(xml_text)
    ns = {"g": GRAPHML_NS}

    # Map key id -> attr.name, separately for "graph"-scoped and "node"-scoped keys.
    graph_key_names: dict[str, str] = {}
    node_key_names: dict[str, str] = {}
    key_types: dict[str, str] = {}
    for key_el in root.findall("g:key", ns):
        key_id = key_el.attrib["id"]
        name = key_el.attrib["attr.name"]
        key_types[key_id] = key_el.attrib.get("attr.type", "string")
        if key_el.attrib["for"] == "graph":
            graph_key_names[key_id] = name
        elif key_el.attrib["for"] == "node":
            node_key_names[key_id] = name

    graph_el = root.find("g:graph", ns)
    if graph_el is None:
        raise ValueError("GraphML document has no <graph> element")

    module_id: str | None = None
    for data_el in graph_el.findall("g:data", ns):
        name = graph_key_names.get(data_el.attrib["key"])
        if name == "module_id":
            module_id = data_el.text
    if module_id is None:
        raise ValueError("GraphML <graph> element is missing a module_id attribute")

    nodes: dict[str, Node] = {}
    for node_el in graph_el.findall("g:node", ns):
        node_id = _strip_prefix(module_id, node_el.attrib["id"])
        attrs: dict[str, object] = {}
        for data_el in node_el.findall("g:data", ns):
            name = node_key_names.get(data_el.attrib["key"])
            if name is None:
                continue
            value: object = data_el.text
            if key_types.get(data_el.attrib["key"]) == "int" and value is not None:
                value = int(value)  # type: ignore[arg-type]
            attrs[name] = value

        kind = attrs.get("kind")
        if kind == "parameter":
            nodes[node_id] = Parameter.model_validate(attrs)
        else:
            for field in MESSAGE_REQUIRED_NULLABLE_FIELDS:
                attrs.setdefault(field, None)
            nodes[node_id] = Message.model_validate(attrs)

    edges: set[tuple[str, str]] = set()
    for edge_el in graph_el.findall("g:edge", ns):
        source = _strip_prefix(module_id, edge_el.attrib["source"])
        target = _strip_prefix(module_id, edge_el.attrib["target"])
        edges.add((source, target))

    return PMGraph(module_id=module_id, nodes=nodes, edges=edges)