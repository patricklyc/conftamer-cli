from typing import Annotated, Literal, Self

from pydantic import BaseModel, Field, model_validator

from conftamer.pmgraph.models import Message, Parameter


class LinkedMessage(BaseModel):
    """One sent message joined to the received message it matched.

    There is one link per (send node, receive node) pair. The paper (§6.3,
    Figure 2) describes one AppGraph node per route and calling module, and an
    AppGraph no larger than its PMGraphs combined. Per-pair links keep which
    concrete request each link came from, at the cost of size: N senders of
    one route give N links, and an edge between two such messages becomes
    N x N edges. Reachability between parameters and other nodes is the same
    either way.
    """

    kind: Literal["linked_message"] = "linked_message"
    api_id: str
    method: str
    pattern: str
    status_code: int | None = None
    sender_module: str
    sender_node: str
    receiver_module: str
    receiver_node: str

    @model_validator(mode="after")
    def validate_linked_message(self) -> Self:
        if not self.api_id:
            raise ValueError("api_id must be nonempty")
        if not self.method:
            raise ValueError("method must be nonempty")
        if not self.pattern:
            raise ValueError("pattern must be nonempty")
        if not self.sender_module or not self.receiver_module:
            raise ValueError("sender_module and receiver_module must be nonempty")
        if not self.sender_node or not self.receiver_node:
            raise ValueError("sender_node and receiver_node must be nonempty")
        if self.sender_module == self.receiver_module:
            raise ValueError("sender_module and receiver_module must differ")
        return self


class DroppedMessage(BaseModel):
    """A PMGraph message that stitching left out of the AppGraph, and why.

    ``reason`` is ``"unmatched"`` when no message in another module matched it,
    or ``"unreachable"`` when it matched but no Parameter reaches any of the
    links it was merged into, so they were all pruned. ``"unreachable"`` only
    occurs when stitching with ``prune_unconfigured=True``. It is
    ``"unsupported_pattern"`` when the message's route pattern uses syntax the
    matcher cannot read, so it was never compared with anything.
    """

    module_id: str
    node_id: str
    reason: Literal["unmatched", "unreachable", "unsupported_pattern"]
    message: Message


AppGraphNode = Annotated[Parameter | LinkedMessage, Field(discriminator="kind")]


class AppGraph(BaseModel):
    nodes: dict[str, AppGraphNode]
    edges: set[tuple[str, str]]  # (source node ID, target node ID)

    @model_validator(mode="after")
    def validate_graph(self) -> Self:
        if "" in self.nodes:
            raise ValueError("node ID '' must be nonempty")
        for source, target in self.edges:
            if source not in self.nodes or target not in self.nodes:
                raise ValueError(f"edge {(source, target)!r} has a missing endpoint")
        return self
