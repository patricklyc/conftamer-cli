import json

import pytest

from conftamer.pmgraph.io import load_pmgraph_json, write_pmgraph_json
from conftamer.pmgraph.models import PMGraph


def test_json_round_trip_is_deterministic_utf8(tmp_path):
    source = tmp_path / "source.json"
    source.write_text(
        r"""{"module_id":"mödule","nodes":{
          "z":{"kind":"parameter","key":"\u00f6\u0000"},
          "a":{"kind":"send_request","api_id":null,"method":"gEt",
               "host":"Höst","path":""},
          "isolate":{"kind":"parameter","key":""}},
          "edges":[["z","a"],["a","z"],["z","a"]]}""",
        encoding="utf-8",
    )
    graph = load_pmgraph_json(str(source))
    first, second = tmp_path / "first.json", tmp_path / "second.json"
    write_pmgraph_json(graph, first)
    write_pmgraph_json(graph, str(second))
    raw = first.read_bytes()
    assert raw == second.read_bytes()
    assert load_pmgraph_json(first) == graph
    payload = json.loads(raw)
    assert list(payload["nodes"]) == ["z", "a", "isolate"]
    assert payload["nodes"]["z"]["key"] == "ö\0"
    message = payload["nodes"]["a"]
    assert message["api_id"] is message["pattern"] is message["status_code"] is None
    assert message["path"] == ""
    assert payload["edges"] == [["a", "z"], ["z", "a"]]
    assert raw.startswith('{\n  "module_id": "mödule",\n'.encode())
    assert raw.endswith(b"}\n") and b"\\u00f6" not in raw


@pytest.mark.parametrize(
    "data",
    [
        b"{",
        b"\xff",
        b'{"module_id":"m","nodes":{},"edges":[],"extra":true}',
        b'{"module_id":"m","nodes":{},"edges":[["absent","absent"]]}',
        b'{"module_id":"m","nodes":{"p":{"kind":"parameter","key":"",',
        b'"extra":true}},"edges":[]}',
        b'{"module_id":"m","nodes":{"r":{"kind":"send_response","api_id":null,',
        b'"method":"GET","path":"/","status_code":"200"}},"edges":[]}',
    ],
)
def test_load_rejects_invalid_input_with_path(tmp_path, data):
    path = tmp_path / "invalid.json"
    path.write_bytes(data)
    with pytest.raises(ValueError, match=rf"{path}: .+"):
        load_pmgraph_json(path)


def test_empty_graph_and_filesystem_errors(tmp_path):
    graph = PMGraph(module_id="m", nodes={}, edges=set())
    path = tmp_path / "graph.json"
    write_pmgraph_json(graph, path)
    assert load_pmgraph_json(path) == graph
    with pytest.raises(FileExistsError):
        write_pmgraph_json(graph, path)
    assert load_pmgraph_json(path) == graph
    missing = tmp_path / "absent" / "graph.json"
    with pytest.raises(FileNotFoundError):
        load_pmgraph_json(missing)
    with pytest.raises(FileNotFoundError):
        write_pmgraph_json(graph, missing)
    assert not missing.parent.exists()
