import csv

from conftamer.models import (
    BaseNode,
    NodeType,
    ParameterNode,
    ReceiveNode,
    SendNode,
)


def read_csv(
    file_path: str,
) -> list[tuple[BaseNode, BaseNode]]:
    edges = []

    with open(file_path) as csvfile:
        reader = csv.reader(csvfile)
        for row in reader:
            match row:
                case [
                    "Parameter", module_id, param_name, 
                    "Send", _module_id, api_id, request_id, respond_code,
                ]:  # fmt: skip
                    edges.append(
                        (
                            ParameterNode(
                                node_type=NodeType.PARAMETER,
                                module_id=module_id,
                                param_name=param_name,
                            ),
                            SendNode(
                                node_type=NodeType.SEND,
                                module_id=_module_id,
                                api_id=api_id,
                                request_id=request_id,
                                respond_code=respond_code,
                            ),
                        )
                    )
                case [
                    "Receive", module_id, api_id, request_pattern, respond_code,
                    "Send", _module_id, _api_id, request_id, _respond_code,
                ]:  # fmt: skip
                    edges.append(
                        (
                            ReceiveNode(
                                node_type=NodeType.RECEIVE,
                                module_id=module_id,
                                api_id=api_id,
                                request_pattern=request_pattern,
                                respond_code=respond_code,
                            ),
                            SendNode(
                                node_type=NodeType.SEND,
                                module_id=_module_id,
                                api_id=_api_id,
                                request_id=request_id,
                                respond_code=_respond_code,
                            ),
                        )
                    )
                case _:
                    # TODO
                    raise Exception("parsing error")

    return edges


if __name__ == "__main__":
    nodes = read_csv("test_gen.csv")
    print(nodes)
    nodes = [(r[0].model_dump(), r[1].model_dump()) for r in nodes]
    import igraph as ig

    g = ig.Graph.TupleList(nodes, directed=True)
    print(g)
