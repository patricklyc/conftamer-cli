import csv

from conftamer.models import NodeType, ParameterNode, ReceiveNode, SendNode


def read_csv(file_path: str):
    nodes = []
    with open(file_path) as csvfile:
        reader = csv.reader(csvfile)
        for row in reader:
            match row:
                case [
                    "Parameter", module_id, name, 
                    "Send", _module_id, api_id, request_id, respond_code,
                ]:  # fmt: skip
                    nodes.append(
                        (
                            ParameterNode(
                                node_type=NodeType.PARAMETER,
                                module_id=module_id,
                                name=name,
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
                    nodes.append(
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
