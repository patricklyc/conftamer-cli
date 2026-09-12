# scratch.py — run once, then delete
from conftamer.pmgraph.pm_to_graphml import write_graphml
from conftamer.pmgraph.models import PMGraph, Parameter, Message

graph = PMGraph(
    module_id="frontend",
    nodes={
        "parameter-1": Parameter(key="timeout"),
        "message-1": Message(kind="send_request", api_id=None, method="POST", host="backend:8080", path="/jobs"),
    },
    edges={("parameter-1", "message-1")},
)
write_graphml(graph, "sample.graphml")