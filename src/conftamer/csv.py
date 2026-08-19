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
                    "Send", _module_id, api_id, request_id, response_code,
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
                                response_code=response_code,
                            ),
                        )
                    )
                case [
                    "Receive", module_id, api_id, request_pattern, response_code,
                    "Send", _module_id, _api_id, request_id, _response_code,
                ]:  # fmt: skip
                    edges.append(
                        (
                            ReceiveNode(
                                node_type=NodeType.RECEIVE,
                                module_id=module_id,
                                api_id=api_id,
                                request_pattern=request_pattern,
                                response_code=response_code,
                            ),
                            SendNode(
                                node_type=NodeType.SEND,
                                module_id=_module_id,
                                api_id=_api_id,
                                request_id=request_id,
                                response_code=_response_code,
                            ),
                        )
                    )
                case _:
                    raise ValueError("parsing error")

    return edges
