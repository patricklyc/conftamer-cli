import runpy
from pathlib import Path

import pytest

WALKTHROUGH = Path(__file__).parent.parent / "examples" / "walkthrough.py"


def test_walkthrough_runs_and_matches_documented_output(
    capsys: pytest.CaptureFixture[str],
) -> None:
    runpy.run_path(str(WALKTHROUGH), run_name="__main__")
    output = capsys.readouterr().out

    # Spot-check the results examples/README.md documents.
    assert "frontend::send-checkout => orders::recv-checkout" in output
    stitched = output.split("== 2.")[1].split("== 3.")[0]
    nodes_and_edges, dropped = stitched.split("  dropped:\n")
    assert "send-analytics" not in nodes_and_edges
    assert dropped.split() == ["frontend::send-analytics", "unmatched"]
    assert (
        "inventory::param-db-pool-size -> link3 -> link2\n"
        "    frontend::param-checkout-timeout -> link0 -> link1 -> link3 -> link2\n"
        "    orders::param-max-retries -> link1 -> link3 -> link2\n"
    ) in output
    assert (
        "    orders::param-max-retries -> link1 -> link3 -> link2\n"
        in (output.split("== 4.")[1])
    )
