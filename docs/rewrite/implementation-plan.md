# ConfTamer CType GraphML MVP implementation plan

> Execute the migration in order with test-driven development and verify each
> checkpoint before beginning the next.

**Goal:** reduce tool34 to one strict gopls CType `.text` validator and directed
visualization GraphML exporter, as specified by
[Architecture](architecture.md) and grounded in
[Input formats](input-formats.md).

The complete task-by-task procedure and acceptance criteria are in
[`docs/superpowers/plans/2026-09-03-ctype-graphml-mvp.md`](../superpowers/plans/2026-09-03-ctype-graphml-mvp.md).
That detailed plan is normative for execution.

## Ordered migration

1. Replace broad graph-compiler contracts with the CType export contract.
2. Add a readable and lossless CType-to-igraph/GraphML projection using TDD.
3. Replace the multi-workflow CLI with only
   `conftamer export INPUT.text --output OUTPUT.graphml`.
4. Make CType models self-contained and delete unrelated production/test
   systems without compatibility modules.
5. Move the two real CType artifacts to `examples/ctype/`, prune other examples,
   and rewrite user/API documentation around one-file export.
6. Align package metadata and release smoke tests, then run fresh full,
   real-data, line-count, scope, diff, and standalone-executable verification.

## Execution gates

- Preserve the verified `Edges`/`Vertices`/`List` producer contract and accept
  unknown raw fields without promoting them to semantics.
- Keep Unmarshaler and Accessors files independent; never merge two inputs.
- Reject DOT, GraphML/XML input, malformed JSON, and unrelated JSON.
- Preserve upstream IDs/names, aliases, methods, tags, grouped ordered AST
  paths, direction, exact producer edge cardinality, and isolated vertices.
- Every behavior change starts with a focused failing test.
- Every checked-in GraphML test re-reads with `ig.Graph.Read_GraphML()`.
- Production Python must remain at or below the **450-line** hard ceiling, with
  a target near 400.
- Do not add dependencies, raise Python 3.13, edit producers/sibling
  repositories, or retain removed command/domain compatibility surfaces.

## Final acceptance

Both real artifacts parse and export independently. Re-read GraphML has 57
vertices/90 edges for the Unmarshaler Subgraph and 582 vertices/822 edges for
Accessors, remains directed, and contains readable plus lossless string
attributes. Invalid input exits nonzero before output creation. The only
installed command is `export`, removed packages and claims are absent, full
quality checks pass, and the final production line count is recorded.
