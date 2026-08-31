import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated, Literal, Never

import igraph as ig
import typer

from conftamer.analysis import (
    ctype_to_igraph,
    find_vertices,
    influence_subgraph,
    to_igraph,
    write_graphml,
)
from conftamer.appgraph import (
    AppGraph,
    load_appgraph,
    prune_unmatched,
    stitch_pmgraph_files,
    write_appgraph,
)
from conftamer.build import build_pmgraph
from conftamer.ctype_graph import CTypeGraph, load_ctype_graph
from conftamer.diagnostics import Diagnostic
from conftamer.pmgraph import PMGraph, load_pmgraph, write_pmgraph

app = typer.Typer()
GraphInput = PMGraph | AppGraph | CTypeGraph
Direction = Literal["ancestors", "descendants", "both"]


@app.command()
def build(
    module_id: Annotated[str, typer.Option("--module-id")],
    events: Annotated[Path, typer.Option("--events")],
    output: Annotated[Path, typer.Option("--output")],
    paramtrack_csv: Annotated[Path | None, typer.Option("--paramtrack-csv")] = None,
    unmarshaler: Annotated[Path | None, typer.Option("--unmarshaler")] = None,
    accessors: Annotated[Path | None, typer.Option("--accessors")] = None,
) -> None:
    enrichment = (paramtrack_csv, unmarshaler, accessors)
    supplied = tuple(value is not None for value in enrichment)
    if any(supplied) and not all(supplied):
        _exit_with_error(
            "--paramtrack-csv, --unmarshaler, and --accessors "
            "must all be provided together"
        )

    with _user_errors():
        result = build_pmgraph(
            module_id=module_id,
            events=events,
            paramtrack_csv=paramtrack_csv,
            unmarshaler=unmarshaler,
            accessors=accessors,
        )
        write_pmgraph(result.graph, output)
    _emit_diagnostics(result.diagnostics)
    _echo_summary("PMGraph", len(result.graph.nodes), len(result.graph.edges), output)


@app.command()
def stitch(
    inputs: Annotated[list[Path], typer.Argument()],
    output: Annotated[Path, typer.Option("--output")],
    drop_unmatched: Annotated[bool, typer.Option("--drop-unmatched")] = False,
) -> None:
    if len(inputs) < 2:
        _exit_with_error("stitching requires at least two PMGraphs")

    with _user_errors():
        result = stitch_pmgraph_files(inputs)
        graph = prune_unmatched(result.graph) if drop_unmatched else result.graph
        write_appgraph(graph, output)
    _emit_diagnostics(result.diagnostics)
    _echo_summary("AppGraph", len(graph.nodes), len(graph.edges), output)


@app.command()
def query(
    graph: Annotated[Path, typer.Argument()],
    query: Annotated[str, typer.Argument()],
    output: Annotated[Path, typer.Option("--output")],
    direction: Annotated[Direction, typer.Option("--direction")] = "both",
    all_matches: Annotated[bool, typer.Option("--all-matches")] = False,
) -> None:
    with _user_errors():
        projected = _project(_load_graph(graph))
        matches = find_vertices(projected, query)
        if not matches:
            _exit_with_error(f"no vertices match {query!r}")
        if len(matches) > 1 and not all_matches:
            _exit_with_error(
                f"{len(matches)} vertices match {query!r}; use --all-matches"
            )
        selected = influence_subgraph(projected, matches, direction=direction)
        write_graphml(selected, output)
    _echo_summary("GraphML", selected.vcount(), selected.ecount(), output)


@app.command("export")
def export_graph(
    graph: Annotated[Path, typer.Argument()],
    output: Annotated[Path, typer.Option("--output")],
) -> None:
    with _user_errors():
        projected = _project(_load_graph(graph))
        write_graphml(projected, output)
    _echo_summary("GraphML", projected.vcount(), projected.ecount(), output)


def _load_graph(path: Path) -> GraphInput:
    if path.suffix.lower() == ".graphml":
        raise ValueError("visualization GraphML input is not supported")

    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError("graph input must be a JSON object")

    discriminator = (document.get("format"), document.get("version"))
    if discriminator == ("conftamer.pmgraph", 2):
        return load_pmgraph(path)
    if discriminator == ("conftamer.appgraph", 1):
        return load_appgraph(path)
    if "format" in document or "version" in document:
        raise ValueError(f"unrecognized graph document discriminator {discriminator!r}")
    if path.suffix.lower() == ".text" and {
        "Edges",
        "Vertices",
        "List",
    }.issubset(document):
        return load_ctype_graph(path)
    raise ValueError("input is not canonical graph JSON or a verified CType transport")


def _project(document: GraphInput) -> ig.Graph:
    if isinstance(document, CTypeGraph):
        return ctype_to_igraph(document)
    return to_igraph(document)


def _emit_diagnostics(diagnostics: tuple[Diagnostic, ...]) -> None:
    for diagnostic in diagnostics:
        location = diagnostic.source or ""
        if diagnostic.line is not None:
            location = f"{location}:{diagnostic.line}"
        prefix = f"{location}: " if location else ""
        typer.echo(
            f"warning: {prefix}{diagnostic.code}: {diagnostic.message}",
            err=True,
        )


def _echo_summary(kind: str, nodes: int, edges: int, output: Path) -> None:
    node_label = "node" if nodes == 1 else "nodes"
    edge_label = "edge" if edges == 1 else "edges"
    typer.echo(
        f"Wrote {kind} with {nodes} {node_label} and {edges} {edge_label} to {output}"
    )


@contextmanager
def _user_errors() -> Iterator[None]:
    try:
        yield
    except (OSError, UnicodeError, ValueError) as error:
        _exit_with_error(str(error))


def _exit_with_error(message: str) -> Never:
    typer.echo(f"error: {message}", err=True)
    raise typer.Exit(code=1)
